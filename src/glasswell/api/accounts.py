"""Owner-created accounts and their server-side sessions.

Fail-closed is the design, as it is for keys. An unknown token, a revoked session, an idle
session, one past its absolute cap and a session whose user was disabled all resolve to the
same `None`, because a caller who can tell them apart has an oracle.

Every comparison takes an injected `now` rather than reading the clock in SQL, so a test can
pin time and a sliding window cannot drift against the row it is measuring.
"""

from __future__ import annotations

import hmac
import secrets
from datetime import datetime, timedelta
from typing import Literal

import psycopg
from psycopg.rows import dict_row

from glasswell.api.password import verify_password
from glasswell.api.principal import fingerprint
from glasswell.lineage.ids import new_ulid
from glasswell.lineage.models import Frozen

SESSION_TOKEN_BYTES = 32
SESSION_TOKEN_PREFIX = "gws_"
USER_ID_PREFIX = "usr_"
SESSION_ID_PREFIX = "ses_"
ATTEMPT_ID_PREFIX = "att_"

IDLE_WINDOW = timedelta(hours=12)
ABSOLUTE_WINDOW = timedelta(days=7)
# Refresh at most once a minute: the write is off the hot path for the same reason SB-04 §3.2
# gives for api_keys.last_used_at.
LAST_SEEN_REFRESH = timedelta(seconds=60)

UNKNOWN_IP = "unknown"
USERNAME_MIN = 3
USERNAME_MAX = 64
PASSWORD_MIN = 12

Role = Literal["owner", "viewer"]
ROLES: tuple[Role, ...] = ("owner", "viewer")
RevokeReason = Literal["logout", "rotated", "password_changed", "admin", "swept"]


class User(Frozen):
    user_id: str
    username: str
    role: Role
    password_hash: str
    created_at: datetime
    created_by: str
    password_changed_at: datetime
    last_login_at: datetime | None = None
    disabled_at: datetime | None = None
    disabled_by: str | None = None

    @property
    def enabled(self) -> bool:
        return self.disabled_at is None


class Session(Frozen):
    session_id: str
    user_id: str
    created_at: datetime
    last_seen_at: datetime
    idle_expires_at: datetime
    absolute_expires_at: datetime
    revoked_at: datetime | None = None
    revoked_reason: str | None = None
    created_ip: str = UNKNOWN_IP
    user_agent_sha256: str | None = None


_USER_COLUMNS = (
    "user_id, username, role, password_hash, created_at, created_by, password_changed_at,"
    " last_login_at, disabled_at, disabled_by"
)
_SESSION_COLUMNS = (
    "session_id, user_id, created_at, last_seen_at, idle_expires_at, absolute_expires_at,"
    " revoked_at, revoked_reason, created_ip, user_agent_sha256"
)


def normalise_username(username: str) -> str:
    """Lowercased and trimmed before any lookup or counter, so case cannot split a bucket."""
    return username.strip().lower()


def mint_session_token() -> str:
    return SESSION_TOKEN_PREFIX + secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def session_fingerprint(token: str) -> str:
    return fingerprint(token)


def new_user_id(now: datetime) -> str:
    return USER_ID_PREFIX + new_ulid(now)


def new_session_id(now: datetime) -> str:
    return SESSION_ID_PREFIX + new_ulid(now)


def new_attempt_id(now: datetime) -> str:
    return ATTEMPT_ID_PREFIX + new_ulid(now)


def find_user(connection: psycopg.Connection, username: str) -> User | None:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            f"select {_USER_COLUMNS} from lineage.users where username = %(username)s",
            {"username": normalise_username(username)},
        )
        row = cursor.fetchone()
    return User(**dict(row)) if row else None


def find_user_by_id(connection: psycopg.Connection, user_id: str) -> User | None:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            f"select {_USER_COLUMNS} from lineage.users where user_id = %(user_id)s",
            {"user_id": user_id},
        )
        row = cursor.fetchone()
    return User(**dict(row)) if row else None


def create_session(
    connection: psycopg.Connection,
    *,
    user: User,
    now: datetime,
    client_ip: str = UNKNOWN_IP,
    user_agent: str | None = None,
) -> tuple[Session, str]:
    """Returns the row and the cleartext token. The token is never stored and never logged."""
    token = mint_session_token()
    session = Session(
        session_id=new_session_id(now),
        user_id=user.user_id,
        created_at=now,
        last_seen_at=now,
        idle_expires_at=now + IDLE_WINDOW,
        absolute_expires_at=now + ABSOLUTE_WINDOW,
        created_ip=client_ip or UNKNOWN_IP,
        user_agent_sha256=fingerprint(user_agent) if user_agent else None,
    )
    with connection.cursor() as cursor:
        cursor.execute(
            f"insert into lineage.sessions ({_SESSION_COLUMNS}, sha256)"
            " values (%(session_id)s, %(user_id)s, %(created_at)s, %(last_seen_at)s,"
            " %(idle_expires_at)s, %(absolute_expires_at)s, null, null, %(created_ip)s,"
            " %(user_agent_sha256)s, %(sha256)s)",
            {**session.model_dump(), "sha256": session_fingerprint(token)},
        )
        cursor.execute(
            "update lineage.users set last_login_at = %(now)s where user_id = %(user_id)s",
            {"now": now, "user_id": user.user_id},
        )
    return session, token


def resolve_session(
    connection: psycopg.Connection, token: str, *, now: datetime
) -> tuple[Session, User] | None:
    """One `None` for unknown, revoked, idle-expired, past the cap, or a disabled user."""
    if not token:
        return None
    presented = session_fingerprint(token)
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            f"select {_SESSION_COLUMNS}, sha256 from lineage.sessions where sha256 = %(sha256)s",
            {"sha256": presented},
        )
        row = cursor.fetchone()
    if row is None:
        return None
    stored = dict(row)
    # Belt and braces: the unique index already selected on the hash, but the fetched value is
    # compared in constant time so no code path ever compares a credential-derived value with ==.
    if not hmac.compare_digest(str(stored.pop("sha256")), presented):
        return None
    session = Session(**stored)
    if session.revoked_at is not None:
        return None
    if session.idle_expires_at <= now or session.absolute_expires_at <= now:
        return None
    user = find_user_by_id(connection, session.user_id)
    if user is None or not user.enabled:
        return None
    return session, user


def touch_session(connection: psycopg.Connection, session: Session, *, now: datetime) -> bool:
    """Slide the idle window. `absolute_expires_at` is never touched: the cap is a cap."""
    if now - session.last_seen_at < LAST_SEEN_REFRESH:
        return False
    with connection.cursor() as cursor:
        cursor.execute(
            "update lineage.sessions"
            "   set last_seen_at = %(now)s, idle_expires_at = %(idle)s"
            " where session_id = %(session_id)s and revoked_at is null",
            {"now": now, "idle": now + IDLE_WINDOW, "session_id": session.session_id},
        )
    return True


def revoke_session(
    connection: psycopg.Connection, session_id: str, *, reason: RevokeReason, now: datetime
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "update lineage.sessions set revoked_at = %(now)s, revoked_reason = %(reason)s"
            " where session_id = %(session_id)s and revoked_at is null",
            {"now": now, "reason": reason, "session_id": session_id},
        )


def revoke_user_sessions(
    connection: psycopg.Connection,
    user_id: str,
    *,
    reason: RevokeReason,
    now: datetime,
    keep: str | None = None,
) -> int:
    """Revoke every live session for a user, optionally sparing the one acting."""
    with connection.cursor() as cursor:
        cursor.execute(
            "update lineage.sessions set revoked_at = %(now)s, revoked_reason = %(reason)s"
            " where user_id = %(user_id)s and revoked_at is null"
            "   and (%(keep)s::text is null or session_id <> %(keep)s)",
            {"now": now, "reason": reason, "user_id": user_id, "keep": keep},
        )
        return cursor.rowcount


def verify_user_password(user: User, password: str) -> bool:
    return verify_password(user.password_hash, password)
