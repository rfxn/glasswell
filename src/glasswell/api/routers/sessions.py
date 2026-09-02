"""Session administration: what is live, and how one is ended from outside.

Its own module rather than a route on `users.router`, which is owner-gated at construction:
`DELETE` must also admit a viewer acting on their own session, so the gate is per operation
here. The list is owner-only, and neither operation serves the client address a session was
created from — no ruling permits one in a body, so the row carries a derived class instead.
"""

from __future__ import annotations

import ipaddress
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from glasswell.api import accounts
from glasswell.api.deps import (
    CSRF_PARAMETER,
    Connection,
    Principal,
    SpineLimit,
    require_scope,
    rows,
)
from glasswell.api.errors import ProblemError, problem_responses
from glasswell.api.examples import request_example
from glasswell.api.pagination import DEFAULT_LIMIT
from glasswell.api.principal import MUTATION_POST_SCOPES, utc_now
from glasswell.api.responses import EnvelopeModel, enveloped, iso
from glasswell.lineage.audit import emit

router = APIRouter(tags=["sessions"])

EXAMPLE_SESSION_ID = "ses_01JBQ7M0Z8K2V4N6X8R0T2Y4W6"
SESSION_ID_NOTE = (
    " The example id is the contract fixture's. Session ids are minted at login and exist"
    " only on the deployment that issued them, so read one off `GET /v1/sessions`."
)

LAN = "lan"
REMOTE = "remote"
UNKNOWN = "unknown"

_COLUMNS = (
    "s.session_id, s.user_id, s.created_at, s.last_seen_at, s.idle_expires_at,"
    " s.absolute_expires_at, s.revoked_at, s.revoked_reason, s.created_ip,"
    " s.user_agent_family, u.username, u.role"
)
_FROM = " from lineage.sessions s join lineage.users u on u.user_id = s.user_id"

_LIST = f"""
select {_COLUMNS}
{_FROM}
 order by s.created_at desc, s.session_id desc
 limit %(limit)s
"""
_GET = f"select {_COLUMNS}{_FROM} where s.session_id = %(session_id)s"


class SessionRecordModel(BaseModel):
    session_id: str = Field(description="Stable id of the session row; safe to log.")
    user_id: str = Field(description="Account holding the session.")
    username: str = Field(description="Lowercased account name.")
    role: str = Field(description="owner or viewer.")
    state: str = Field(description="active, revoked or expired.")
    created_at: str = Field(description="When the session was created.")
    last_seen_at: str = Field(description="Last request this session authenticated.")
    expires_at: str = Field(description="When idleness ends this session.")
    absolute_expires_at: str = Field(description="Hard cap; never extended.")
    revoked_at: str | None = Field(description="When it was revoked, if it was.")
    revoked_reason: str | None = Field(description="Why it was revoked, if it was.")
    user_agent_family: str = Field(
        description="Coarse client label recorded at login; `unknown` where none was resolved."
    )
    address_class: str = Field(
        description=(
            "lan, remote or unknown, derived from the address the session was created from."
            " The address itself is not served by any operation."
        )
    )


def _address_class(created_ip: str | None) -> str:
    """A class, never the address. `unknown` is the honest majority: `resolve_client_ip`
    answers UNKNOWN whenever the request carried no edge marker."""
    if not created_ip or created_ip == accounts.UNKNOWN_IP:
        return UNKNOWN
    try:
        parsed = ipaddress.ip_address(created_ip)
    except ValueError:
        return UNKNOWN
    return LAN if parsed.is_private else REMOTE


def _state(row: dict[str, Any], *, now: datetime) -> str:
    if row["revoked_at"] is not None:
        return "revoked"
    if row["idle_expires_at"] <= now or row["absolute_expires_at"] <= now:
        return "expired"
    return "active"


def _serialize(row: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    return {
        "session_id": row["session_id"],
        "user_id": row["user_id"],
        "username": row["username"],
        "role": row["role"],
        "state": _state(row, now=now),
        "created_at": iso(row["created_at"]),
        "last_seen_at": iso(row["last_seen_at"]),
        "expires_at": iso(row["idle_expires_at"]),
        "absolute_expires_at": iso(row["absolute_expires_at"]),
        "revoked_at": iso(row["revoked_at"]),
        "revoked_reason": row["revoked_reason"],
        # Null on every row created before the column existed; nothing branches on it.
        "user_agent_family": row["user_agent_family"] or accounts.UNKNOWN_USER_AGENT,
        "address_class": _address_class(row["created_ip"]),
    }


def _existing(connection: Connection, session_id: str) -> dict[str, Any]:
    found = rows(connection, _GET, {"session_id": session_id})
    if not found:
        raise ProblemError("not_found", detail=f"no session {session_id}")
    return found[0]


@router.get(
    "/sessions",
    operation_id="list_sessions",
    summary="List sessions",
    description=(
        "Every session this deployment holds a row for, newest first, with the account it"
        " belongs to and where it stands against the idle and absolute windows. Neither the"
        " token nor its hash nor the client address appears here — the list answers *who is"
        " signed in*, not *what they hold* or *where they are*."
    ),
    response_model=EnvelopeModel[list[SessionRecordModel]],
    openapi_extra=request_example(query={"limit": 20}),
    responses=problem_responses("forbidden", "validation_failed", "service_degraded"),
    dependencies=[Depends(require_scope(*MUTATION_POST_SCOPES))],
)
def list_sessions(
    request: Request,
    connection: Connection,
    principal: Principal,
    limit: SpineLimit = DEFAULT_LIMIT,
) -> JSONResponse:
    now = utc_now()
    found = rows(connection, _LIST, {"limit": limit})
    return enveloped(request, [_serialize(row, now=now) for row in found])


@router.delete(
    "/sessions/{session_id}",
    operation_id="revoke_session",
    summary="Revoke a session",
    description=(
        "Ends a session server-side. The owner may revoke any session; anyone else may revoke"
        " the one they are calling with and nothing else. The holder's very next request is"
        " refused, because every request re-reads the row rather than trusting a cache."
        "\n\nRevoking an already-revoked session returns the same record and writes no second"
        " audit event, so a retry after a timeout is safe." + SESSION_ID_NOTE
    ),
    response_model=EnvelopeModel[SessionRecordModel],
    openapi_extra=request_example(path={"session_id": EXAMPLE_SESSION_ID}),
    responses=problem_responses("forbidden", "not_found", "service_degraded"),
)
def revoke_session(
    request: Request,
    connection: Connection,
    principal: Principal,
    session_id: Annotated[str, Path(description="Id of the session to revoke.")],
    csrf_token: CSRF_PARAMETER = None,
) -> JSONResponse:
    now = utc_now()
    by_owner = principal.scope in MUTATION_POST_SCOPES
    # Decided before any read: a caller who is not the owner learns nothing about whether the
    # id exists, so the route is not an existence oracle. An owner mismatches by construction
    # and is admitted on scope rather than on identity.
    if not by_owner and (not principal.session_id or session_id != principal.session_id):
        raise ProblemError(
            "forbidden", detail="a session is revoked by its holder or by the owner"
        )
    existing = _existing(connection, session_id)
    reason: accounts.RevokeReason = "admin" if by_owner else "logout"
    if accounts.revoke_session(connection, session_id, reason=reason, now=now) == 1:
        payload = (
            {"reason": reason, "user_id": existing["user_id"]} if by_owner else {"reason": reason}
        )
        emit(
            connection,
            "session.ended",
            subject_type="session",
            subject_id=session_id,
            payload=payload,
            actor=principal.id,
            occurred_at=now,
        )
    connection.commit()
    return enveloped(request, _serialize(_existing(connection, session_id), now=now))
