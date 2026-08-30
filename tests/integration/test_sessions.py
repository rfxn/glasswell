"""The session store: what is written, what is refused, and what a cap means.

Every assertion pins `now` explicitly. A sliding window measured against wall-clock time in
SQL would pass here and drift in production, which is the failure this file exists to catch.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from glasswell.api.accounts import (
    ABSOLUTE_WINDOW,
    IDLE_WINDOW,
    LAST_SEEN_REFRESH,
    SESSION_TOKEN_BYTES,
    SESSION_TOKEN_PREFIX,
    User,
    create_session,
    find_user,
    mint_session_token,
    new_user_id,
    resolve_session,
    revoke_session,
    revoke_user_sessions,
    session_fingerprint,
    touch_session,
)
from glasswell.api.password import hash_password

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)


def make_user(
    connection: psycopg.Connection,
    *,
    username: str = "owner",
    role: str = "owner",
    password: str = "a-sufficiently-long-password",
    now: datetime = NOW,
) -> User:
    user_id = new_user_id(now)
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into lineage.users (user_id, username, password_hash, role, created_at,"
            " created_by, password_changed_at) values (%s, %s, %s, %s, %s, %s, %s)",
            (user_id, username, hash_password(password), role, now, "test", now),
        )
    found = find_user(connection, username)
    assert found is not None
    return found


def test_the_three_tables_exist_with_their_grants(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute(
            "select table_name, privilege_type from information_schema.table_privileges"
            " where grantee = 'glasswell_api' and table_schema = 'lineage'"
            "   and table_name in ('users', 'sessions', 'login_attempts')"
            " order by table_name, privilege_type"
        )
        granted = {(name, privilege) for name, privilege in cursor.fetchall()}

    assert ("users", "SELECT") in granted
    assert ("users", "INSERT") in granted
    assert ("users", "UPDATE") in granted
    # Users are soft-disabled, never deleted: a session FK still points at a disabled row.
    assert ("users", "DELETE") not in granted
    assert ("sessions", "DELETE") in granted, "the retention sweep needs it"
    assert ("login_attempts", "DELETE") in granted
    for table in ("users", "sessions", "login_attempts"):
        assert (table, "TRUNCATE") not in granted


def test_a_minted_token_carries_256_bits() -> None:
    token = mint_session_token()

    assert token.startswith(SESSION_TOKEN_PREFIX)
    body = token[len(SESSION_TOKEN_PREFIX) :]
    # base64url of 32 bytes, unpadded.
    assert len(body) >= (SESSION_TOKEN_BYTES * 8 + 5) // 6
    assert mint_session_token() != mint_session_token()


def test_only_the_sha256_is_stored(db: psycopg.Connection) -> None:
    user = make_user(db)

    session, token = create_session(db, user=user, now=NOW)

    with db.cursor() as cursor:
        cursor.execute(
            "select sha256 from lineage.sessions where session_id = %s", (session.session_id,)
        )
        stored = cursor.fetchone()[0]
    assert stored == session_fingerprint(token)
    assert token not in stored
    with db.cursor() as cursor:
        cursor.execute("select sessions::text from lineage.sessions")
        assert token not in str(cursor.fetchall()), "the cleartext token reached a column"


def test_a_live_session_resolves_to_its_user(db: psycopg.Connection) -> None:
    user = make_user(db)
    _, token = create_session(db, user=user, now=NOW)

    resolved = resolve_session(db, token, now=NOW + timedelta(minutes=1))

    assert resolved is not None
    assert resolved[1].user_id == user.user_id


def test_an_unknown_token_resolves_to_none(db: psycopg.Connection) -> None:
    make_user(db)

    assert resolve_session(db, mint_session_token(), now=NOW) is None
    assert resolve_session(db, "", now=NOW) is None


def test_a_token_after_logout_is_refused(db: psycopg.Connection) -> None:
    user = make_user(db)
    session, token = create_session(db, user=user, now=NOW)

    revoke_session(db, session.session_id, reason="logout", now=NOW)

    assert resolve_session(db, token, now=NOW + timedelta(minutes=1)) is None


def test_a_session_past_idle_expiry_is_refused(db: psycopg.Connection) -> None:
    user = make_user(db)
    _, token = create_session(db, user=user, now=NOW)

    assert resolve_session(db, token, now=NOW + IDLE_WINDOW - timedelta(minutes=1)) is not None
    assert resolve_session(db, token, now=NOW + IDLE_WINDOW) is None


def test_the_absolute_cap_is_never_extended(db: psycopg.Connection) -> None:
    """Idle refresh moves the idle window only. A session active every hour still dies at 7 d."""
    user = make_user(db)
    session, token = create_session(db, user=user, now=NOW)

    moment = NOW
    for _ in range(24):
        moment += timedelta(hours=8)
        resolved = resolve_session(db, token, now=moment)
        if resolved is None:
            break
        touch_session(db, resolved[0], now=moment)

    with db.cursor() as cursor:
        cursor.execute(
            "select absolute_expires_at from lineage.sessions where session_id = %s",
            (session.session_id,),
        )
        assert cursor.fetchone()[0] == NOW + ABSOLUTE_WINDOW
    assert resolve_session(db, token, now=NOW + ABSOLUTE_WINDOW) is None


def test_an_active_session_past_the_cap_is_refused_even_when_never_idle(
    db: psycopg.Connection,
) -> None:
    user = make_user(db)
    _, token = create_session(db, user=user, now=NOW)
    resolved = resolve_session(db, token, now=NOW + timedelta(hours=1))
    assert resolved is not None
    touch_session(db, resolved[0], now=NOW + ABSOLUTE_WINDOW - timedelta(minutes=1))

    assert resolve_session(db, token, now=NOW + ABSOLUTE_WINDOW + timedelta(seconds=1)) is None


def test_idle_refresh_writes_at_most_once_per_minute(db: psycopg.Connection) -> None:
    user = make_user(db)
    session, _ = create_session(db, user=user, now=NOW)

    assert touch_session(db, session, now=NOW + LAST_SEEN_REFRESH - timedelta(seconds=1)) is False
    assert touch_session(db, session, now=NOW + LAST_SEEN_REFRESH) is True


def test_a_session_for_a_disabled_user_is_refused(db: psycopg.Connection) -> None:
    user = make_user(db)
    _, token = create_session(db, user=user, now=NOW)

    with db.cursor() as cursor:
        cursor.execute(
            "update lineage.users set disabled_at = %s, disabled_by = %s where user_id = %s",
            (NOW, "test", user.user_id),
        )

    assert resolve_session(db, token, now=NOW + timedelta(minutes=1)) is None


def test_revoking_a_users_sessions_can_spare_the_acting_one(db: psycopg.Connection) -> None:
    user = make_user(db)
    acting, acting_token = create_session(db, user=user, now=NOW)
    _, sibling_token = create_session(db, user=user, now=NOW)

    revoked = revoke_user_sessions(
        db, user.user_id, reason="password_changed", now=NOW, keep=acting.session_id
    )

    assert revoked == 1
    assert resolve_session(db, acting_token, now=NOW + timedelta(minutes=1)) is not None
    assert resolve_session(db, sibling_token, now=NOW + timedelta(minutes=1)) is None


def test_a_username_is_unique_and_case_folded(db: psycopg.Connection) -> None:
    make_user(db, username="ryan")

    assert find_user(db, "RYAN") is not None
    assert find_user(db, "  Ryan  ") is not None
    with pytest.raises(psycopg.errors.UniqueViolation):
        make_user(db, username="ryan")


def test_the_schema_refuses_a_non_argon2_hash(db: psycopg.Connection) -> None:
    """The CHECK is the floor under the application: a plaintext password cannot be stored."""
    with pytest.raises(psycopg.errors.CheckViolation), db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.users (user_id, username, password_hash, role, created_at,"
            " created_by, password_changed_at) values (%s, %s, %s, %s, %s, %s, %s)",
            (new_user_id(NOW), "plain", "hunter2", "owner", NOW, "test", NOW),
        )
