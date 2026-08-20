"""Key management (DR-67, SB-06 §8.3). Owner scope, shown once, sha256 at rest, audited.

This is the app-level half of the sharing design: Cloudflare Access says *who reached the
origin*, and a row here says *what that principal may do*. Issuance and revocation are
audit events because a credential that appears or disappears with no record is the one
change to a system nobody can reconstruct afterwards.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, Depends, Path, Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from glasswell.api.deps import (
    Connection,
    PostEffect,
    Principal,
    SpineLimit,
    require_scope,
    rows,
)
from glasswell.api.errors import ProblemError, problem_responses
from glasswell.api.examples import request_example
from glasswell.api.pagination import DEFAULT_LIMIT
from glasswell.api.principal import (
    MUTATION_POST_SCOPES,
    Scope,
    fingerprint,
    mint_secret,
    utc_now,
)
from glasswell.api.responses import EnvelopeModel, enveloped, iso
from glasswell.lineage.audit import emit
from glasswell.lineage.ids import new_ulid

router = APIRouter(tags=["keys"], dependencies=[Depends(require_scope(*MUTATION_POST_SCOPES))])

EXAMPLE_KEY_ID = "key_01JBQ7M0Z8K2V4N6X8R0T2Y4W6"
KEY_ID_NOTE = (
    " The example id is the contract fixture's. Key ids are minted by `POST /v1/keys` and"
    " exist only on the deployment that issued them, so read one off `GET /v1/keys` rather"
    " than replaying this one."
)
SHOWN_ONCE_NOTE = (
    " The cleartext key is returned by this call and by nothing else, ever: only its sha256"
    " is stored. A key that has been lost is rotated, not recovered."
)

_COLUMNS = (
    "key_id, label, scope, created_at, created_by, expires_at, revoked_at, revoked_by,"
    " last_used_at"
)

_INSERT = f"""
insert into lineage.api_keys
       (key_id, sha256, label, scope, created_at, created_by, expires_at)
values (%(key_id)s, %(sha256)s, %(label)s, %(scope)s, %(created_at)s, %(created_by)s,
        %(expires_at)s)
returning {_COLUMNS}
"""

_LIST = f"""
select {_COLUMNS}
  from lineage.api_keys
 order by created_at desc, key_id desc
 limit %(limit)s
"""

_GET = f"select {_COLUMNS} from lineage.api_keys where key_id = %(key_id)s"

_REVOKE = f"""
update lineage.api_keys
   set revoked_at = %(revoked_at)s, revoked_by = %(revoked_by)s
 where key_id = %(key_id)s and revoked_at is null
returning {_COLUMNS}
"""


class IssueRequest(BaseModel):
    model_config = {"extra": "forbid"}

    label: str = Field(
        min_length=3,
        max_length=64,
        pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$",
        description="`<consumer>-<purpose>-<year>`, lowercase and hyphenated (SB-06 §8.3).",
    )
    scope: Scope = Field(description="owner, agent or guest. The key carries it, not the class.")
    expires_at: datetime | None = Field(
        default=None, description="When the key stops working. A guest key should carry one."
    )


class KeyRecordModel(BaseModel):
    key_id: str = Field(description="Stable id of the key row; safe to log and to reference.")
    label: str = Field(description="Human label the key was issued under.")
    scope: str = Field(description="Effective scope of the principal presenting this key.")
    state: str = Field(description="active, expired or revoked.")
    created_at: str = Field(description="When the key was issued.")
    created_by: str = Field(description="Principal that issued it.")
    expires_at: str | None = Field(description="Expiry, where one was set.")
    revoked_at: str | None = Field(description="When it was revoked, if it was.")
    revoked_by: str | None = Field(description="Principal that revoked it.")
    last_used_at: str | None = Field(description="Last time this key authenticated a request.")


class IssuedKey(KeyRecordModel):
    key_id: str | None = Field(description="Id of the new key; null when `dry_run` is set.")
    created_at: str | None = Field(description="Issue time; null when `dry_run` is set.")
    secret: str | None = Field(
        description="The cleartext key. Returned once at issuance; null on a dry run."
    )


def _serialize(row: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    revoked_at = row["revoked_at"]
    expires_at = row["expires_at"]
    if revoked_at is not None:
        state = "revoked"
    elif expires_at is not None and expires_at <= now:
        state = "expired"
    else:
        state = "active"
    return {
        "key_id": row["key_id"],
        "label": row["label"],
        "scope": row["scope"],
        "state": state,
        "created_at": iso(row["created_at"]),
        "created_by": row["created_by"],
        "expires_at": iso(expires_at),
        "revoked_at": iso(revoked_at),
        "revoked_by": row["revoked_by"],
        "last_used_at": iso(row["last_used_at"]),
    }


def _issue(
    connection: Connection,
    *,
    label: str,
    scope: Scope,
    expires_at: datetime | None,
    actor: str,
    now: datetime,
) -> tuple[dict[str, Any], str]:
    secret = mint_secret()
    parameters = {
        "key_id": f"key_{new_ulid(now)}",
        "sha256": fingerprint(secret),
        "label": label,
        "scope": scope,
        "created_at": now,
        "created_by": actor,
        "expires_at": expires_at,
    }
    try:
        issued = rows(connection, _INSERT, parameters)[0]
    except psycopg.errors.UniqueViolation:
        connection.rollback()
        raise ProblemError(
            "validation_failed",
            detail=f"a live key is already labelled {label!r}; revoke or rotate it first",
            errors=[{"pointer": "/body/label", "code": "label_in_use", "detail": label}],
        ) from None
    emit(
        connection,
        "key.issued",
        subject_type="key",
        subject_id=issued["key_id"],
        payload={"label": label, "scope": scope, "expires_at": iso(expires_at)},
        actor=actor,
        occurred_at=now,
    )
    connection.commit()
    return issued, secret


def _revoke(
    connection: Connection, *, key_id: str, actor: str, now: datetime
) -> dict[str, Any] | None:
    revoked = rows(connection, _REVOKE, {"key_id": key_id, "revoked_at": now, "revoked_by": actor})
    if not revoked:
        return None
    emit(
        connection,
        "key.revoked",
        subject_type="key",
        subject_id=key_id,
        payload={"label": revoked[0]["label"], "scope": revoked[0]["scope"]},
        actor=actor,
        occurred_at=now,
    )
    connection.commit()
    return revoked[0]


def _existing(connection: Connection, key_id: str) -> dict[str, Any]:
    found = rows(connection, _GET, {"key_id": key_id})
    if not found:
        raise ProblemError("not_found", detail=f"no key {key_id}")
    return found[0]


@router.post(
    "/keys",
    operation_id="issue_key",
    summary="Issue an API key",
    description=(
        "Creates a key at one of three scopes and returns it. Labels are unique across live"
        " keys, so a rotation can reuse the label the consumer already knows."
        + SHOWN_ONCE_NOTE
    ),
    response_model=EnvelopeModel[IssuedKey],
    status_code=201,
    openapi_extra=request_example(),
    responses=problem_responses(
        "forbidden", "validation_failed", "explain_on_dry_run", "service_degraded"
    ),
)
def issue_key(
    request: Request,
    connection: Connection,
    principal: Principal,
    body: IssueRequest,
    flags: PostEffect,
) -> JSONResponse:
    now = utc_now()
    if flags.dry_run:
        preview = {
            "key_id": None,
            "label": body.label,
            "scope": body.scope,
            "state": "not_issued",
            "created_at": None,
            "created_by": principal.id,
            "expires_at": iso(body.expires_at),
            "revoked_at": None,
            "revoked_by": None,
            "last_used_at": None,
            "secret": None,
        }
        return enveloped(request, preview, warnings=[_dry_run_warning()])
    issued, secret = _issue(
        connection,
        label=body.label,
        scope=body.scope,
        expires_at=body.expires_at,
        actor=principal.id,
        now=now,
    )
    return enveloped(
        request,
        _serialize(issued, now=now) | {"secret": secret},
        warnings=[_explain_warning()] if flags.explain else (),
        links={"self": "/v1/keys"},
        status_code=201,
    )


def _dry_run_warning() -> dict[str, str]:
    return {
        "code": "dry_run",
        "detail": "no key was created and no audit event was written",
    }


def _explain_warning() -> dict[str, str]:
    return {
        "code": "explain_not_applicable",
        "detail": "issuing a key records an audit event, not a derivation, so there is no chain",
    }


@router.get(
    "/keys",
    operation_id="list_keys",
    summary="List API keys",
    description=(
        "Every key this deployment has issued, newest first, with its scope, lifecycle"
        " timestamps and last use. Neither the cleartext nor its hash appears here — the"
        " list answers *which credentials exist*, not *what they are*."
    ),
    response_model=EnvelopeModel[list[KeyRecordModel]],
    openapi_extra=request_example(query={"limit": 20}),
    responses=problem_responses("forbidden", "validation_failed", "service_degraded"),
)
def list_keys(
    request: Request,
    connection: Connection,
    principal: Principal,
    limit: SpineLimit = DEFAULT_LIMIT,
) -> JSONResponse:
    now = utc_now()
    found = rows(connection, _LIST, {"limit": limit})
    return enveloped(request, [_serialize(row, now=now) for row in found])


@router.delete(
    "/keys/{key_id}",
    operation_id="revoke_key",
    summary="Revoke an API key",
    description=(
        "Takes the key out of service immediately and records `key.revoked`. Revoking an"
        " already-revoked key returns the same record and writes no second event, so a"
        " retry after a timeout is safe."
        + KEY_ID_NOTE
    ),
    response_model=EnvelopeModel[KeyRecordModel],
    openapi_extra=request_example(path={"key_id": EXAMPLE_KEY_ID}),
    responses=problem_responses("forbidden", "not_found", "service_degraded"),
)
def revoke_key(
    request: Request,
    connection: Connection,
    principal: Principal,
    key_id: Annotated[str, Path(description="Id of the key to revoke.")],
) -> JSONResponse:
    now = utc_now()
    existing = _existing(connection, key_id)
    revoked = _revoke(connection, key_id=key_id, actor=principal.id, now=now) or existing
    return enveloped(request, _serialize(revoked, now=now))


@router.post(
    "/keys/{key_id}/rotate",
    operation_id="rotate_key",
    summary="Rotate an API key",
    description=(
        "Issues a replacement under the same label and scope and revokes the old key in the"
        " same call, which is what makes rotation a single step a consumer cannot half-do."
        + SHOWN_ONCE_NOTE
        + KEY_ID_NOTE
    ),
    response_model=EnvelopeModel[IssuedKey],
    status_code=201,
    openapi_extra=request_example(path={"key_id": EXAMPLE_KEY_ID}),
    responses=problem_responses(
        "forbidden", "not_found", "explain_on_dry_run", "service_degraded"
    ),
)
def rotate_key(
    request: Request,
    connection: Connection,
    principal: Principal,
    key_id: Annotated[str, Path(description="Id of the key being replaced.")],
    flags: PostEffect,
) -> JSONResponse:
    now = utc_now()
    existing = _existing(connection, key_id)
    if flags.dry_run:
        preview = _serialize(existing, now=now) | {"secret": None, "state": "not_issued"}
        return enveloped(request, preview, warnings=[_dry_run_warning()])
    _revoke(connection, key_id=key_id, actor=principal.id, now=now)
    issued, secret = _issue(
        connection,
        label=existing["label"],
        scope=existing["scope"],
        expires_at=existing["expires_at"],
        actor=principal.id,
        now=now,
    )
    return enveloped(
        request,
        _serialize(issued, now=now) | {"secret": secret},
        warnings=[_explain_warning()] if flags.explain else (),
        links={"replaces": f"/v1/keys/{key_id}"},
        status_code=201,
    )
