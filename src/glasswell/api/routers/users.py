"""Owner-only account administration. Modelled on `routers/keys.py`, the house pattern.

There is no self-registration and no password reset by email. Accounts exist because the
owner made them, which is the property the SB-06 §5 amendment promised to keep when the
"never grows a user table" wording was replaced.
"""

from __future__ import annotations

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

router = APIRouter(tags=["users"], dependencies=[Depends(require_scope(*MUTATION_POST_SCOPES))])

EXAMPLE_USER_ID = "usr_01JBQ7M0Z8K2V4N6X8R0T2Y4W6"
USER_ID_NOTE = (
    " The example id is the contract fixture's. User ids are minted by `POST /v1/users` and"
    " exist only on the deployment that created them, so read one off `GET /v1/users`."
)

# password_hash is never in this list. It is not served by any operation, at any scope.
_COLUMNS = (
    "user_id, username, role, created_at, created_by, password_changed_at, last_login_at,"
    " disabled_at, disabled_by"
)

_LIST = f"""
select {_COLUMNS}
  from lineage.users
 order by created_at desc, user_id desc
 limit %(limit)s
"""
_GET = f"select {_COLUMNS} from lineage.users where user_id = %(user_id)s"

# Taken inside the transaction. A handler-only count races: two concurrent demotions would
# each read "two owners exist" and both commit, leaving none.
_LOCK_ENABLED_OWNERS = (
    "select user_id from lineage.users"
    " where role = 'owner' and disabled_at is null"
    " for update"
)


class CreateUserRequest(BaseModel):
    model_config = {"extra": "forbid"}

    username: str = Field(
        min_length=accounts.USERNAME_MIN,
        max_length=accounts.USERNAME_MAX,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
        description="Stored lowercased and unique case-insensitively.",
    )
    password: str = Field(
        min_length=accounts.PASSWORD_MIN,
        max_length=1024,
        description="Argon2id-hashed on arrival. Never stored, echoed or logged in clear.",
    )
    role: accounts.Role = Field(description="owner or viewer.")


class UpdateUserRequest(BaseModel):
    model_config = {"extra": "forbid"}

    role: accounts.Role | None = Field(default=None, description="New role, when changing one.")


class SetPasswordRequest(BaseModel):
    model_config = {"extra": "forbid"}

    new_password: str = Field(min_length=accounts.PASSWORD_MIN, max_length=1024)


class UserModel(BaseModel):
    user_id: str = Field(description="Stable id; safe to log and to reference.")
    username: str = Field(description="Lowercased account name.")
    role: str = Field(description="owner or viewer.")
    state: str = Field(description="active or disabled.")
    created_at: str = Field(description="When the account was created.")
    created_by: str = Field(description="Principal that created it.")
    password_changed_at: str = Field(description="Last password change.")
    last_login_at: str | None = Field(description="Last successful login.")
    disabled_at: str | None = Field(description="When it was disabled, if it was.")
    disabled_by: str | None = Field(description="Principal that disabled it.")


def _serialize(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": row["user_id"],
        "username": row["username"],
        "role": row["role"],
        "state": "disabled" if row["disabled_at"] is not None else "active",
        "created_at": iso(row["created_at"]),
        "created_by": row["created_by"],
        "password_changed_at": iso(row["password_changed_at"]),
        "last_login_at": iso(row["last_login_at"]),
        "disabled_at": iso(row["disabled_at"]),
        "disabled_by": row["disabled_by"],
    }


def _existing(connection: Connection, user_id: str) -> dict[str, Any]:
    found = rows(connection, _GET, {"user_id": user_id})
    if not found:
        raise ProblemError("not_found", detail=f"no user {user_id}")
    return found[0]


def _enabled_owner_ids(connection: Connection) -> set[str]:
    return {row["user_id"] for row in rows(connection, _LOCK_ENABLED_OWNERS)}


def _refuse_emptying_the_owners(connection: Connection, user_id: str) -> None:
    """The last enabled owner cannot be disabled or demoted: that locks everyone out."""
    owners = _enabled_owner_ids(connection)
    if owners == {user_id}:
        raise ProblemError(
            "validation_failed",
            detail="this is the last enabled owner; promote another account first",
            errors=[
                {
                    "pointer": "/role",
                    "code": "last_owner",
                    "detail": "a deployment with no enabled owner cannot be administered",
                }
            ],
        )


@router.get(
    "/users",
    operation_id="list_users",
    summary="List accounts",
    description=(
        "Every account on this deployment, newest first. No password material appears here"
        " or anywhere else in the API — the list answers *who exists*, not *what they know*."
    ),
    response_model=EnvelopeModel[list[UserModel]],
    openapi_extra=request_example(query={"limit": 20}),
    responses=problem_responses("forbidden", "service_degraded"),
)
def list_users(
    request: Request,
    connection: Connection,
    principal: Principal,
    limit: SpineLimit = DEFAULT_LIMIT,
) -> JSONResponse:
    found = rows(connection, _LIST, {"limit": limit})
    return enveloped(request, [_serialize(row) for row in found])


@router.post(
    "/users",
    operation_id="create_user",
    summary="Create an account",
    description=(
        "Owner-only. There is no self-registration path and no password reset by email,"
        " so this is the only way an account comes into existence after the first one."
    ),
    response_model=EnvelopeModel[UserModel],
    status_code=201,
    openapi_extra=request_example(),
    responses=problem_responses("forbidden", "validation_failed", "service_degraded"),
)
def create_user(
    request: Request,
    connection: Connection,
    principal: Principal,
    body: CreateUserRequest,
    csrf_token: CSRF_PARAMETER = None,
) -> JSONResponse:
    now = utc_now()
    username = accounts.normalise_username(body.username)
    if accounts.find_user(connection, username) is not None:
        raise ProblemError(
            "validation_failed",
            detail="that username already exists",
            errors=[{"pointer": "/username", "code": "duplicate", "detail": "already taken"}],
        )
    user_id = accounts.create_user(
        connection,
        username=username,
        password=body.password,
        role=body.role,
        created_by=principal.id,
        now=now,
    )
    emit(
        connection,
        "user.created",
        subject_type="user",
        subject_id=user_id,
        payload={"username": username, "role": body.role},
        actor=principal.id,
        occurred_at=now,
    )
    connection.commit()
    return enveloped(
        request, _serialize(_existing(connection, user_id)), links={"self": "/v1/users"},
        status_code=201,
    )


@router.patch(
    "/users/{user_id}",
    operation_id="update_user",
    summary="Change an account's role",
    description=(
        "Owner-only. The last enabled owner cannot be demoted; the check takes a row lock"
        " on the enabled-owner set, because a handler-only count races under concurrency."
        + USER_ID_NOTE
    ),
    response_model=EnvelopeModel[UserModel],
    openapi_extra=request_example(path={"user_id": EXAMPLE_USER_ID}),
    responses=problem_responses(
        "forbidden", "not_found", "validation_failed", "service_degraded"
    ),
)
def update_user(
    request: Request,
    connection: Connection,
    principal: Principal,
    user_id: Annotated[str, Path(description="Id of the account to change.")],
    body: UpdateUserRequest,
    csrf_token: CSRF_PARAMETER = None,
) -> JSONResponse:
    now = utc_now()
    existing = _existing(connection, user_id)
    if body.role is not None and body.role != existing["role"] and existing["role"] == "owner":
        _refuse_emptying_the_owners(connection, user_id)
    if body.role is not None:
        with connection.cursor() as cursor:
            cursor.execute(
                "update lineage.users set role = %(role)s where user_id = %(user_id)s",
                {"role": body.role, "user_id": user_id},
            )
        emit(
            connection,
            "user.updated",
            subject_type="user",
            subject_id=user_id,
            payload={"role": body.role, "was": existing["role"]},
            actor=principal.id,
            occurred_at=now,
        )
    connection.commit()
    return enveloped(request, _serialize(_existing(connection, user_id)))


@router.delete(
    "/users/{user_id}",
    operation_id="disable_user",
    summary="Disable an account",
    description=(
        "Soft: the row is kept and marked disabled, and every session that account holds is"
        " revoked in the same transaction. Rows are never deleted, because a session and an"
        " audit event still point at them." + USER_ID_NOTE
    ),
    response_model=EnvelopeModel[UserModel],
    openapi_extra=request_example(path={"user_id": EXAMPLE_USER_ID}),
    responses=problem_responses(
        "forbidden", "not_found", "validation_failed", "service_degraded"
    ),
)
def disable_user(
    request: Request,
    connection: Connection,
    principal: Principal,
    user_id: Annotated[str, Path(description="Id of the account to disable.")],
    csrf_token: CSRF_PARAMETER = None,
) -> JSONResponse:
    now = utc_now()
    existing = _existing(connection, user_id)
    if existing["disabled_at"] is None:
        if existing["role"] == "owner":
            _refuse_emptying_the_owners(connection, user_id)
        with connection.cursor() as cursor:
            cursor.execute(
                "update lineage.users set disabled_at = %(now)s, disabled_by = %(actor)s"
                " where user_id = %(user_id)s and disabled_at is null",
                {"now": now, "actor": principal.id, "user_id": user_id},
            )
        revoked = accounts.revoke_user_sessions(
            connection, user_id, reason="admin", now=now, keep=None
        )
        emit(
            connection,
            "user.disabled",
            subject_type="user",
            subject_id=user_id,
            payload={"sessions_revoked": revoked},
            actor=principal.id,
            occurred_at=now,
        )
    connection.commit()
    return enveloped(request, _serialize(_existing(connection, user_id)))


@router.post(
    "/users/{user_id}/password",
    operation_id="set_user_password",
    summary="Set an account's password",
    description=(
        "Owner-only reset. Every session that account holds is revoked, because a password"
        " reset whose old sessions survive has not taken effect." + USER_ID_NOTE
    ),
    response_model=EnvelopeModel[UserModel],
    openapi_extra=request_example(path={"user_id": EXAMPLE_USER_ID}),
    responses=problem_responses(
        "forbidden", "not_found", "validation_failed", "service_degraded"
    ),
)
def set_user_password(
    request: Request,
    connection: Connection,
    principal: Principal,
    user_id: Annotated[str, Path(description="Id of the account to reset.")],
    body: SetPasswordRequest,
    csrf_token: CSRF_PARAMETER = None,
) -> JSONResponse:
    now = utc_now()
    _existing(connection, user_id)
    accounts.set_password(connection, user_id, password=body.new_password, now=now)
    revoked = accounts.revoke_user_sessions(
        connection, user_id, reason="password_changed", now=now, keep=None
    )
    emit(
        connection,
        "password.changed",
        subject_type="user",
        subject_id=user_id,
        payload={"sessions_revoked": revoked, "self_service": False},
        actor=principal.id,
        occurred_at=now,
    )
    connection.commit()
    return enveloped(request, _serialize(_existing(connection, user_id)))
