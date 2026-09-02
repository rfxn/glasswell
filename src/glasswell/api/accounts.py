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
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from time import sleep
from typing import Literal, Protocol

import psycopg
from psycopg.rows import dict_row

from glasswell.api.password import DUMMY_HASH, hash_password, needs_rehash, verify_password
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
UNKNOWN_USER_AGENT = "unknown"

# Browser x OS, matched in this order because an Edge string also says Chrome and Safari, and a
# Chrome string also says Safari. Anything unrecognised is `unknown`; nothing authorises on it.
_BROWSERS: tuple[tuple[str, str], ...] = (
    ("edg/", "Edge"),
    ("opr/", "Opera"),
    ("firefox/", "Firefox"),
    ("chrome/", "Chrome"),
    ("safari/", "Safari"),
)
_SYSTEMS: tuple[tuple[str, str], ...] = (
    ("android", "Android"),
    ("iphone", "iOS"),
    ("ipad", "iOS"),
    ("mac os x", "macOS"),
    ("windows", "Windows"),
    ("cros", "ChromeOS"),
    ("linux", "Linux"),
)

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
    user_agent_family: str | None = None


_USER_COLUMNS = (
    "user_id, username, role, password_hash, created_at, created_by, password_changed_at,"
    " last_login_at, disabled_at, disabled_by"
)
_SESSION_COLUMNS = (
    "session_id, user_id, created_at, last_seen_at, idle_expires_at, absolute_expires_at,"
    " revoked_at, revoked_reason, created_ip, user_agent_sha256, user_agent_family"
)


def normalise_username(username: str) -> str:
    """Lowercased and trimmed before any lookup or counter, so case cannot split a bucket."""
    return username.strip().lower()


def user_agent_family(user_agent: str | None) -> str:
    """`<browser> on <system>` for the session list, or `unknown`.

    The stored fingerprint is one-way and dictionary-recoverable outside the database, so the
    label has to be derived here, at write time, rather than in SQL over the hash.
    """
    if not user_agent:
        return UNKNOWN_USER_AGENT
    lowered = user_agent.lower()
    browser = next((name for token, name in _BROWSERS if token in lowered), None)
    system = next((name for token, name in _SYSTEMS if token in lowered), None)
    if browser is None or system is None:
        return UNKNOWN_USER_AGENT
    return f"{browser} on {system}"


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
        user_agent_family=user_agent_family(user_agent),
    )
    with connection.cursor() as cursor:
        cursor.execute(
            f"insert into lineage.sessions ({_SESSION_COLUMNS}, sha256)"
            " values (%(session_id)s, %(user_id)s, %(created_at)s, %(last_seen_at)s,"
            " %(idle_expires_at)s, %(absolute_expires_at)s, null, null, %(created_ip)s,"
            " %(user_agent_sha256)s, %(user_agent_family)s, %(sha256)s)",
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
) -> int:
    """Rows revoked: 0 when the session was already revoked, which is what makes a re-revoke
    idempotent rather than a second audit event."""
    with connection.cursor() as cursor:
        cursor.execute(
            "update lineage.sessions set revoked_at = %(now)s, revoked_reason = %(reason)s"
            " where session_id = %(session_id)s and revoked_at is null",
            {"now": now, "reason": reason, "session_id": session_id},
        )
        return cursor.rowcount


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


def create_user(
    connection: psycopg.Connection,
    *,
    username: str,
    password: str,
    role: Role,
    created_by: str,
    now: datetime,
) -> str:
    user_id = new_user_id(now)
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into lineage.users (user_id, username, password_hash, role, created_at,"
            " created_by, password_changed_at) values (%s, %s, %s, %s, %s, %s, %s)",
            (
                user_id,
                normalise_username(username),
                hash_password(password),
                role,
                now,
                created_by,
                now,
            ),
        )
    return user_id


def set_password(
    connection: psycopg.Connection, user_id: str, *, password: str, now: datetime
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "update lineage.users"
            "   set password_hash = %(hash)s, password_changed_at = %(now)s"
            " where user_id = %(user_id)s",
            {"hash": hash_password(password), "now": now, "user_id": user_id},
        )


def rehash_if_weak(
    connection: psycopg.Connection, user: User, password: str, *, now: datetime
) -> bool:
    """Upgrade a stored hash whose parameters are below the current floor, after a good verify."""
    if not needs_rehash(user.password_hash):
        return False
    set_password(connection, user.user_id, password=password, now=now)
    return True


class SessionStore(Protocol):
    """Mirrors `KeyStore`: authentication runs on routes that never touch the request pool."""

    def authenticate(self, token: str, *, now: datetime) -> tuple[Session, User] | None: ...


class PostgresSessionStore:
    """Owns the connection it opens, so a route with no database dependency still works."""

    def __init__(self, connect: Callable[[], psycopg.Connection]) -> None:
        self._connect = connect

    def authenticate(self, token: str, *, now: datetime) -> tuple[Session, User] | None:
        connection = self._connect()
        try:
            resolved = resolve_session(connection, token, now=now)
            if resolved is not None:
                touch_session(connection, resolved[0], now=now)
            connection.commit()
            return resolved
        finally:
            connection.close()


class ConnectionSessionStore:
    """Bound to one live connection — the shape a request handler and a test share."""

    def __init__(self, connection: psycopg.Connection) -> None:
        self._connection = connection

    def authenticate(self, token: str, *, now: datetime) -> tuple[Session, User] | None:
        resolved = resolve_session(self._connection, token, now=now)
        if resolved is not None:
            touch_session(self._connection, resolved[0], now=now)
        return resolved


class DeniedSessionStore:
    """No store configured. Denying is the answer; defaulting open is the failure mode."""

    def authenticate(self, token: str, *, now: datetime) -> tuple[Session, User] | None:
        return None


ACCOUNT_BACKOFF_AFTER = 5
ACCOUNT_LOCK_AFTER = 20
ACCOUNT_LOCK_WINDOW = timedelta(hours=1)
IP_BACKOFF_AFTER = 15
IP_LOCK_AFTER = 30
IP_LOCK_WINDOW = timedelta(minutes=15)
LOCK_DURATION = timedelta(minutes=15)
MAX_BACKOFF = timedelta(seconds=900)
KNOWN_GOOD_WINDOW = timedelta(days=30)
# Padding every login to this floor keeps a database lookup's cost from separating the
# failure classes that §7.7 requires be indistinguishable.
LOGIN_FLOOR_SECONDS = 0.250
# What a limiter-refused attempt costs instead of an Argon2id verify. Enough to sit under the
# login floor so the response time is unchanged, and not memory-hard, so a flood cannot buy
# 64 MiB of work per request.
LOCKED_PAD_SECONDS = 0.005

def enforce_login_floor(
    started: float,
    *,
    floor: float = LOGIN_FLOOR_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> float:
    """Pad a login handler to a fixed floor. Returns the padding actually applied.

    The route is a sync `def`, so starlette runs it in the threadpool and this blocks one
    worker thread rather than the event loop.
    """
    remaining = floor - (time.monotonic() - started)
    if remaining > 0:
        sleep(remaining)
        return remaining
    return 0.0


Outcome = Literal["success", "bad_credential", "locked", "rate_limited", "disabled"]
LimiterState = Literal["open", "backoff", "locked"]

# Only these two are credential failures. An attempt refused by the limiter records `locked`
# or `rate_limited`, which do not arm anything -- otherwise a lock feeds itself and never
# expires, and the time-boxed guarantee in the DoS control would be false.
_CREDENTIAL_FAILURES = ("bad_credential", "disabled")


def backoff_for(consecutive_failures: int, *, after: int = ACCOUNT_BACKOFF_AFTER) -> timedelta:
    """min(2^(n-after), MAX_BACKOFF) seconds before the next attempt is *accepted*."""
    if consecutive_failures < after:
        return timedelta(0)
    seconds = min(float(2 ** (consecutive_failures - after)), MAX_BACKOFF.total_seconds())
    return timedelta(seconds=seconds)


def _failure_profile(
    connection: psycopg.Connection, column: str, value: str, *, window: timedelta, now: datetime
) -> tuple[int, int, datetime | None]:
    """(consecutive failures since the last success, failures inside the window, last failure)."""
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            with last_success as (
                select coalesce(max(attempted_at), '-infinity'::timestamptz) as at
                  from lineage.login_attempts
                 where {column} = %(value)s and outcome = 'success'
            )
            select
                count(*) filter (
                    where attempted_at > (select at from last_success)
                ) as consecutive,
                count(*) filter (where attempted_at > %(since)s) as in_window,
                max(attempted_at) as last_failure
              from lineage.login_attempts
             where {column} = %(value)s
               and outcome = any(%(failures)s)
               and attempted_at <= %(now)s
            """,
            {
                "value": value,
                "since": now - window,
                "now": now,
                "failures": list(_CREDENTIAL_FAILURES),
            },
        )
        consecutive, in_window, last_failure = cursor.fetchone()
    return int(consecutive), int(in_window), last_failure


def _state_from(
    consecutive: int,
    in_window: int,
    last_failure: datetime | None,
    *,
    lock_after: int,
    backoff_after: int,
    now: datetime,
) -> LimiterState:
    if last_failure is None:
        return "open"
    if in_window >= lock_after and now < last_failure + LOCK_DURATION:
        return "locked"
    if now < last_failure + backoff_for(consecutive, after=backoff_after):
        return "backoff"
    return "open"


def is_known_good_ip(
    connection: psycopg.Connection, username: str, client_ip: str, *, now: datetime
) -> bool:
    """Has this address ever completed a login for this account recently?

    This is the single control that turns per-account lockout from a denial of service into a
    nuisance: a flood from an unfamiliar address cannot lock the owner out of their own
    network. An unresolvable address is never known-good, or the bypass would be the hole.
    """
    if not client_ip or client_ip == UNKNOWN_IP:
        return False
    with connection.cursor() as cursor:
        cursor.execute(
            "select exists (select 1 from lineage.login_attempts"
            " where username_submitted = %(username)s and client_ip = %(client_ip)s"
            "   and outcome = 'success' and attempted_at > %(since)s)",
            {
                "username": normalise_username(username),
                "client_ip": client_ip,
                "since": now - KNOWN_GOOD_WINDOW,
            },
        )
        return bool(cursor.fetchone()[0])


def account_state(
    connection: psycopg.Connection, username: str, client_ip: str, *, now: datetime
) -> LimiterState:
    name = normalise_username(username)
    consecutive, in_window, last_failure = _failure_profile(
        connection, "username_submitted", name, window=ACCOUNT_LOCK_WINDOW, now=now
    )
    state = _state_from(
        consecutive,
        in_window,
        last_failure,
        lock_after=ACCOUNT_LOCK_AFTER,
        backoff_after=ACCOUNT_BACKOFF_AFTER,
        now=now,
    )
    if state == "locked" and is_known_good_ip(connection, name, client_ip, now=now):
        return "open"
    return state


def ip_state(connection: psycopg.Connection, client_ip: str, *, now: datetime) -> LimiterState:
    consecutive, in_window, last_failure = _failure_profile(
        connection, "client_ip", client_ip or UNKNOWN_IP, window=IP_LOCK_WINDOW, now=now
    )
    return _state_from(
        consecutive,
        in_window,
        last_failure,
        lock_after=IP_LOCK_AFTER,
        backoff_after=IP_BACKOFF_AFTER,
        now=now,
    )


def record_attempt(
    connection: psycopg.Connection,
    *,
    username: str,
    client_ip: str,
    outcome: Outcome,
    session_id: str | None,
    now: datetime,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into lineage.login_attempts (attempt_id, attempted_at, username_submitted,"
            " client_ip, outcome, session_id) values (%s, %s, %s, %s, %s, %s)",
            (
                new_attempt_id(now),
                now,
                normalise_username(username),
                client_ip or UNKNOWN_IP,
                outcome,
                session_id,
            ),
        )


def authenticate(
    connection: psycopg.Connection,
    *,
    username: str,
    password: str,
    client_ip: str,
    now: datetime,
) -> User | None:
    """One `None` for every failure class, and a dummy verify wherever no real hash exists.

    A locked account presented with the correct password still answers `None`; otherwise the
    lock is an oracle for a correct credential.
    """
    name = normalise_username(username)
    address = client_ip or UNKNOWN_IP

    if ip_state(connection, address, now=now) != "open":
        # No Argon2 verify here. Timing uniformity only has to hold between failure classes a
        # caller can reach *with* a credential attempt; a refused-by-limiter request already
        # tells the caller it was refused by the limiter. Running a 64 MiB verify would let an
        # unauthenticated flood buy ~60 ms of memory-hard work per request after being locked.
        sleep(LOCKED_PAD_SECONDS)
        record_attempt(
            connection,
            username=name,
            client_ip=address,
            outcome="rate_limited",
            session_id=None,
            now=now,
        )
        return None

    if account_state(connection, name, address, now=now) != "open":
        # Padded, not verified, for the same reason -- and the pad keeps a locked account
        # indistinguishable from a wrong password, which is the property that matters.
        sleep(LOCKED_PAD_SECONDS)
        record_attempt(
            connection,
            username=name,
            client_ip=address,
            outcome="locked",
            session_id=None,
            now=now,
        )
        return None

    user = find_user(connection, name)
    if user is None:
        verify_password(DUMMY_HASH, password)
        record_attempt(
            connection,
            username=name,
            client_ip=address,
            outcome="bad_credential",
            session_id=None,
            now=now,
        )
        return None

    if not user.enabled:
        verify_password(DUMMY_HASH, password)
        record_attempt(
            connection,
            username=name,
            client_ip=address,
            outcome="disabled",
            session_id=None,
            now=now,
        )
        return None

    if not verify_user_password(user, password):
        record_attempt(
            connection,
            username=name,
            client_ip=address,
            outcome="bad_credential",
            session_id=None,
            now=now,
        )
        return None

    record_attempt(
        connection,
        username=name,
        client_ip=address,
        outcome="success",
        session_id=None,
        now=now,
    )
    return user
