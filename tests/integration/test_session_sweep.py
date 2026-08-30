"""The two session-side tables are pruned, and a live session is never reachable by the sweep.

Both grow with traffic rather than with data. `login_attempts` is written by every failed
login, so on a public origin a table nobody prunes is how a login flood becomes a disk
incident. The sweep keys on `absolute_expires_at`, never on `revoked_at`: a live session has
a cap in the future, so it cannot be reached however the row was last touched.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from glasswell.api.accounts import (
    ABSOLUTE_WINDOW,
    create_session,
    create_user,
    find_user,
    record_attempt,
    resolve_session,
    revoke_session,
)
from glasswell.lineage.retention import (
    ATTEMPT_RETENTION,
    SESSION_GRACE,
    sweep_login_attempts,
    sweep_sessions,
)

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 30, 12, 0, 0, tzinfo=UTC)
PASSWORD = "a-sufficiently-long-password"


@pytest.fixture
def user(db: psycopg.Connection):
    create_user(
        db, username="sweeper", password=PASSWORD, role="viewer", created_by="t", now=NOW
    )
    return find_user(db, "sweeper")


def sessions_left(connection: psycopg.Connection) -> int:
    with connection.cursor() as cursor:
        cursor.execute("select count(*) from lineage.sessions")
        return cursor.fetchone()[0]


def test_sessions_past_the_absolute_cap_plus_the_grace_are_deleted(db, user) -> None:
    create_session(db, user=user, now=NOW)
    later = NOW + ABSOLUTE_WINDOW + SESSION_GRACE + timedelta(seconds=1)

    assert sweep_sessions(db, now=later) == 1
    assert sessions_left(db) == 0


def test_a_session_inside_the_grace_window_survives(db, user) -> None:
    create_session(db, user=user, now=NOW)
    just_expired = NOW + ABSOLUTE_WINDOW + timedelta(days=1)

    assert sweep_sessions(db, now=just_expired) == 0
    assert sessions_left(db) == 1


def test_a_live_session_is_never_swept(db, user) -> None:
    """Probed inside the 12 h idle window, so "still resolves" means live rather than merely
    "the row is still there"."""
    _, token = create_session(db, user=user, now=NOW)
    later = NOW + timedelta(hours=6)

    swept = sweep_sessions(db, now=later)

    assert swept == 0
    assert resolve_session(db, token, now=later) is not None


def test_an_idle_session_row_survives_the_sweep_until_its_cap_passes(db, user) -> None:
    """Idle is not the sweep's business: the row stays until the absolute cap plus the grace,
    so the reason a session stopped working is still explicable a week later."""
    create_session(db, user=user, now=NOW)

    assert sweep_sessions(db, now=NOW + timedelta(days=1)) == 0
    assert sessions_left(db) == 1


def test_a_revoked_but_recent_session_is_not_swept_early(db, user) -> None:
    """Keyed on the cap, not on revocation: a logout should not erase its own evidence."""
    session, _ = create_session(db, user=user, now=NOW)
    revoke_session(db, session.session_id, reason="logout", now=NOW)

    assert sweep_sessions(db, now=NOW + timedelta(days=1)) == 0
    assert sessions_left(db) == 1


def test_login_attempts_older_than_ninety_days_are_deleted(db) -> None:
    record_attempt(
        db,
        username="ancient",
        client_ip="203.0.113.9",
        outcome="bad_credential",
        session_id=None,
        now=NOW - ATTEMPT_RETENTION - timedelta(days=1),
    )
    record_attempt(
        db,
        username="recent",
        client_ip="203.0.113.9",
        outcome="bad_credential",
        session_id=None,
        now=NOW - timedelta(days=1),
    )

    assert sweep_login_attempts(db, now=NOW) == 1
    with db.cursor() as cursor:
        cursor.execute("select username_submitted from lineage.login_attempts")
        assert [row[0] for row in cursor.fetchall()] == ["recent"]


def test_the_api_role_may_run_both_sweeps(db) -> None:
    """The grants the sweep needs, exercised as the role that runs it."""
    with db.cursor() as cursor:
        cursor.execute("set local role glasswell_api")
        cursor.execute("delete from lineage.sessions where false")
        cursor.execute("delete from lineage.login_attempts where false")
    db.rollback()
