"""Session login: the interactive credential path, beside the machine one.

Every authentication failure answers the same `403 unauthenticated` with no `detail` and no
`errors` — unknown username, wrong password, disabled account, locked account, expired
session, revoked session and a malformed cookie alike. No new error code is added: a
`session_expired` code was considered and rejected, because it tells the holder of a stale
cookie that the cookie was once valid.
"""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from glasswell.api import accounts, csrf
from glasswell.api.client_ip import resolve_client_ip
from glasswell.api.csrf import CSRF_COOKIE, CSRF_HEADER
from glasswell.api.deps import (
    CSRF_PARAMETER,
    SESSION_COOKIE,
    Connection,
    Principal,
    csrf_binding,
    optional_principal,
    require_csrf,
    require_principal,
)
from glasswell.api.errors import ProblemError, problem_responses
from glasswell.api.examples import not_a_figure, request_example
from glasswell.api.principal import utc_now
from glasswell.api.responses import EnvelopeModel, enveloped, iso
from glasswell.lineage.audit import emit

router = APIRouter(tags=["session"])

# `Secure` is not negotiable and neither is the absence of `Domain`: the __Host- prefix
# forbids one, which is what stops a sibling host in this zone from setting a cookie this
# origin would accept. SameSite is Lax rather than Strict so following a link into the app
# does not silently log the reader out -- Lax still withholds the cookie on cross-site POST
# and cross-site fetch, which is the CSRF-relevant case.
COOKIE_KWARGS = {
    "httponly": True,
    "secure": True,
    "samesite": "lax",
    "path": "/",
}


class LoginRequest(BaseModel):
    model_config = {"extra": "forbid"}

    username: str = Field(
        min_length=accounts.USERNAME_MIN,
        max_length=accounts.USERNAME_MAX,
        description="Case-insensitive. Accounts are created by the owner; there is no signup.",
    )
    password: str = Field(
        min_length=1,
        max_length=1024,
        description="Never echoed, never logged, never accepted in a query string.",
    )


class PasswordChangeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=accounts.PASSWORD_MIN, max_length=1024)


class ChallengeModel(BaseModel):
    csrf_token: str = Field(description="Echo in X-Glasswell-CSRF on state-changing requests.")
    expires_in: int = Field(
        description="Seconds the token remains valid.",
        json_schema_extra=not_a_figure(
            "Lifetime in seconds of a CSRF token, a protocol parameter of the exchange."
        ),
    )


class SessionModel(BaseModel):
    username: str | None = Field(description="The account, when the caller holds a session.")
    role: str = Field(description="owner or viewer.")
    kind: str = Field(description="user, owner, service or anonymous.")
    expires_at: str | None = Field(description="When idleness ends this session.")
    absolute_expires_at: str | None = Field(description="Hard cap; never extended.")


def _refuse() -> ProblemError:
    """One refusal for every failure class. No detail, so nothing distinguishes them."""
    return ProblemError("unauthenticated")


@router.get(
    "/session/challenge",
    operation_id="get_session_challenge",
    summary="Mint a CSRF token",
    description=(
        "Open, because the login request itself needs a token and no session exists yet."
        " Without a session the token is bound to a short-lived pre-session cookie; with"
        " one it is bound to that session and is useless in any other."
    ),
    response_model=EnvelopeModel[ChallengeModel],
    openapi_extra=request_example(),
    responses=problem_responses("rate_limited", "service_degraded"),
)
def get_session_challenge(
    request: Request,
    caller: Annotated[object | None, Depends(optional_principal)] = None,
) -> JSONResponse:
    now = utc_now()
    nonce = request.cookies.get(CSRF_COOKIE)
    set_nonce = None

    # A live session binds to itself. A dead or absent one falls through to the pre-session
    # path without saying so -- telling the holder their cookie was once valid is an oracle.
    binding = csrf_binding(caller) if caller is not None else ""

    if not binding:
        if not nonce:
            nonce = csrf.mint_pre_session_nonce()
            set_nonce = nonce
        binding = csrf.pre_session_binding(nonce)

    response = enveloped(
        request,
        {
            "csrf_token": csrf.mint(binding, now=now),
            "expires_in": int(csrf.CSRF_WINDOW.total_seconds()),
        },
    )
    if set_nonce is not None:
        response.set_cookie(CSRF_COOKIE, set_nonce, max_age=3600, **COOKIE_KWARGS)
    return response


@router.post(
    "/session",
    operation_id="create_session",
    summary="Log in",
    description=(
        "Exchanges a username and password for a `__Host-` session cookie. Every failure —"
        " unknown account, wrong password, disabled account, throttled account — answers the"
        " same 403 with no detail, and takes the same time to do it."
    ),
    response_model=EnvelopeModel[SessionModel],
    status_code=201,
    openapi_extra=request_example(),
    responses=problem_responses("unauthenticated", "validation_failed", "service_degraded"),
)
def create_session(
    request: Request,
    connection: Connection,
    body: LoginRequest,
    caller: Annotated[object | None, Depends(optional_principal)] = None,
    presented: CSRF_PARAMETER = None,
) -> JSONResponse:
    started = time.monotonic()
    now = utc_now()
    client_ip = resolve_client_ip(request)

    # Login CSRF: without a bound token an attacker can silently log a victim into their own
    # account. Either binding is accepted, because both are reachable states -- a first login
    # holds only the pre-session nonce, and someone switching accounts already holds a
    # session, whose challenge binds to that session instead.
    nonce = request.cookies.get(CSRF_COOKIE)
    bindings = [csrf.pre_session_binding(nonce)] if nonce else []
    if caller is not None and csrf_binding(caller):
        bindings.append(csrf_binding(caller))
    if not presented or not any(csrf.check(presented, one, now=now) for one in bindings):
        accounts.enforce_login_floor(started)
        raise ProblemError("forbidden", detail=f"send a valid {CSRF_HEADER}")

    user = accounts.authenticate(
        connection,
        username=body.username,
        password=body.password,
        client_ip=client_ip,
        now=now,
    )
    if user is None:
        connection.commit()
        accounts.enforce_login_floor(started)
        raise _refuse()

    # Fixation: a new id every login, and whatever session the presented cookie named dies in
    # the same transaction.
    stale = request.cookies.get(SESSION_COOKIE)
    if stale:
        existing = accounts.resolve_session(connection, stale, now=now)
        if existing is not None:
            accounts.revoke_session(connection, existing[0].session_id, reason="rotated", now=now)

    session, token = accounts.create_session(
        connection,
        user=user,
        now=now,
        client_ip=client_ip,
        user_agent=request.headers.get("user-agent"),
    )
    emit(
        connection,
        "session.started",
        subject_type="session",
        subject_id=session.session_id,
        payload={"username": user.username, "role": user.role, "client_ip": client_ip},
        actor=f"user:{user.user_id}",
        occurred_at=now,
    )
    connection.commit()

    response = enveloped(
        request,
        _serialize_session(session, user),
        links={"self": "/v1/session"},
        status_code=201,
    )
    response.set_cookie(SESSION_COOKIE, token, **COOKIE_KWARGS)
    response.delete_cookie(CSRF_COOKIE, path="/")
    accounts.enforce_login_floor(started)
    return response


@router.get(
    "/session",
    operation_id="read_session",
    summary="Who am I",
    description=(
        "The calling principal, resolved. Returns the account and role for a session, and"
        " the kind alone for a key. Never returns a token, a hash or a password."
    ),
    response_model=EnvelopeModel[SessionModel],
    openapi_extra=request_example(),
    responses=problem_responses("key_required", "unauthenticated", "service_degraded"),
    dependencies=[Depends(require_principal)],
)
def read_session(request: Request, principal: Principal) -> JSONResponse:
    return enveloped(
        request,
        {
            "username": principal.label if principal.kind == "user" else None,
            "role": principal.role,
            "kind": principal.kind,
            "expires_at": None,
            "absolute_expires_at": None,
        },
    )


@router.delete(
    "/session",
    operation_id="end_session",
    summary="Log out",
    description=(
        "Revokes the session server-side and clears the cookie. A copy of the cookie taken"
        " before logout is dead afterwards, because every request re-reads the row."
    ),
    response_model=EnvelopeModel[SessionModel],
    openapi_extra=request_example(),
    responses=problem_responses("key_required", "unauthenticated", "forbidden"),
    dependencies=[Depends(require_principal), Depends(require_csrf)],
)
def end_session(
    request: Request,
    connection: Connection,
    principal: Principal,
    csrf_token: CSRF_PARAMETER = None,
) -> JSONResponse:
    now = utc_now()
    if principal.kind != "user" or not principal.session_id:
        raise _refuse()
    accounts.revoke_session(connection, principal.session_id, reason="logout", now=now)
    emit(
        connection,
        "session.ended",
        subject_type="session",
        subject_id=principal.session_id,
        payload={"reason": "logout"},
        actor=principal.id,
        occurred_at=now,
    )
    connection.commit()

    response = enveloped(
        request,
        {
            "username": None,
            "role": principal.role,
            "kind": "anonymous",
            "expires_at": None,
            "absolute_expires_at": None,
        },
    )
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.post(
    "/session/password",
    operation_id="change_own_password",
    summary="Change your own password",
    description=(
        "Requires the current password. Every other session this account holds is revoked;"
        " the one making the change survives, so a password change is not a self-logout."
    ),
    response_model=EnvelopeModel[SessionModel],
    openapi_extra=request_example(),
    responses=problem_responses(
        "key_required", "unauthenticated", "forbidden", "validation_failed"
    ),
    dependencies=[Depends(require_principal), Depends(require_csrf)],
)
def change_own_password(
    request: Request,
    connection: Connection,
    principal: Principal,
    body: PasswordChangeRequest,
    csrf_token: CSRF_PARAMETER = None,
) -> JSONResponse:
    now = utc_now()
    if principal.kind != "user" or not principal.user_id:
        raise _refuse()
    user = accounts.find_user_by_id(connection, principal.user_id)
    if user is None or not accounts.verify_user_password(user, body.current_password):
        raise _refuse()

    accounts.set_password(connection, user.user_id, password=body.new_password, now=now)
    revoked = accounts.revoke_user_sessions(
        connection,
        user.user_id,
        reason="password_changed",
        now=now,
        keep=principal.session_id,
    )
    emit(
        connection,
        "password.changed",
        subject_type="user",
        subject_id=user.user_id,
        payload={"sessions_revoked": revoked, "self_service": True},
        actor=principal.id,
        occurred_at=now,
    )
    connection.commit()
    return enveloped(
        request,
        {
            "username": user.username,
            "role": user.role,
            "kind": principal.kind,
            "expires_at": None,
            "absolute_expires_at": None,
        },
    )


def _serialize_session(session: accounts.Session, user: accounts.User) -> dict[str, object]:
    return {
        "username": user.username,
        "role": user.role,
        "kind": "user",
        "expires_at": iso(session.idle_expires_at),
        "absolute_expires_at": iso(session.absolute_expires_at),
    }
