"""Backoff, lockout, and the two controls that keep a lockout from becoming the attack.

The counter keys on the *submitted* string rather than a resolved user id. If only real
accounts locked, the lock would answer "this name exists" — so an unknown name has to lock
too, which is what `test_an_unknown_username_also_locks` holds.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from glasswell.api.accounts import (
    ACCOUNT_BACKOFF_AFTER,
    ACCOUNT_LOCK_AFTER,
    IP_LOCK_AFTER,
    LOCK_DURATION,
    MAX_BACKOFF,
    account_state,
    authenticate,
    backoff_for,
    ip_state,
    is_known_good_ip,
    record_attempt,
)
from tests.integration.test_sessions import make_user

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
PASSWORD = "a-sufficiently-long-password"
ATTACKER = "203.0.113.9"
HOME = "198.51.100.4"


def fail_times(
    connection: psycopg.Connection,
    count: int,
    *,
    username: str = "owner",
    client_ip: str = ATTACKER,
    start: datetime = NOW,
    step: timedelta = timedelta(seconds=1),
) -> datetime:
    """Returns the moment of the *last* attempt, so a probe can sit just after it."""
    moment = start
    last = start
    for _ in range(count):
        record_attempt(
            connection,
            username=username,
            client_ip=client_ip,
            outcome="bad_credential",
            session_id=None,
            now=moment,
        )
        last = moment
        moment += step
    return last


TICK = timedelta(milliseconds=100)


def test_backoff_arms_after_five_failures(db: psycopg.Connection) -> None:
    make_user(db)
    last = fail_times(db, ACCOUNT_BACKOFF_AFTER - 1)
    assert account_state(db, "owner", ATTACKER, now=last + TICK) == "open"

    last = fail_times(db, 1, start=last + timedelta(seconds=1))

    assert account_state(db, "owner", ATTACKER, now=last + TICK) == "backoff"


def test_the_backoff_curve_doubles_and_is_capped(db: psycopg.Connection) -> None:
    assert backoff_for(ACCOUNT_BACKOFF_AFTER - 1) == timedelta(0)
    assert backoff_for(ACCOUNT_BACKOFF_AFTER) == timedelta(seconds=1)
    assert backoff_for(ACCOUNT_BACKOFF_AFTER + 1) == timedelta(seconds=2)
    assert backoff_for(ACCOUNT_BACKOFF_AFTER + 3) == timedelta(seconds=8)
    assert backoff_for(ACCOUNT_BACKOFF_AFTER + 40) == MAX_BACKOFF


def test_backoff_clears_once_the_wait_has_elapsed(db: psycopg.Connection) -> None:
    make_user(db)
    last = fail_times(db, ACCOUNT_BACKOFF_AFTER)

    assert account_state(db, "owner", ATTACKER, now=last + TICK) == "backoff"
    later = last + backoff_for(ACCOUNT_BACKOFF_AFTER) + TICK
    assert account_state(db, "owner", ATTACKER, now=later) == "open"


def test_twenty_failures_in_an_hour_lock_for_fifteen_minutes(db: psycopg.Connection) -> None:
    make_user(db)
    last = fail_times(db, ACCOUNT_LOCK_AFTER, step=timedelta(seconds=30))

    assert account_state(db, "owner", ATTACKER, now=last + TICK) == "locked"
    assert account_state(db, "owner", ATTACKER, now=last + LOCK_DURATION) != "locked"


def test_a_lock_expires_without_administrative_action(db: psycopg.Connection) -> None:
    """An attempt made while locked records `locked`, not a credential failure, so the lock
    cannot feed itself and no admin unlock is ever required."""
    make_user(db)
    last = fail_times(db, ACCOUNT_LOCK_AFTER, step=timedelta(seconds=30))

    for offset in range(5):
        during = last + timedelta(seconds=60 + offset)
        assert authenticate(
            db, username="owner", password=PASSWORD, client_ip=ATTACKER, now=during
        ) is None

    after = last + LOCK_DURATION + timedelta(seconds=1)
    assert authenticate(
        db, username="owner", password=PASSWORD, client_ip=ATTACKER, now=after
    ) is not None


def test_an_unknown_username_also_locks(db: psycopg.Connection) -> None:
    """The enumeration control: if only real accounts locked, the lock is an existence oracle."""
    last = fail_times(db, ACCOUNT_LOCK_AFTER, username="nobody", step=timedelta(seconds=30))

    assert account_state(db, "nobody", ATTACKER, now=last + TICK) == "locked"


def test_a_known_good_ip_bypasses_the_account_lock(db: psycopg.Connection) -> None:
    """The DoS control. A flood from an unfamiliar address must not lock the owner out of
    their own network, or the lockout becomes the attack."""
    make_user(db)
    record_attempt(
        db,
        username="owner",
        client_ip=HOME,
        outcome="success",
        session_id=None,
        now=NOW - timedelta(days=1),
    )
    last = fail_times(db, ACCOUNT_LOCK_AFTER, step=timedelta(seconds=30))
    probe = last + TICK

    assert is_known_good_ip(db, "owner", HOME, now=probe) is True
    assert is_known_good_ip(db, "owner", ATTACKER, now=probe) is False
    assert account_state(db, "owner", ATTACKER, now=probe) == "locked"
    assert account_state(db, "owner", HOME, now=probe) != "locked"
    assert authenticate(
        db, username="owner", password=PASSWORD, client_ip=HOME, now=probe
    ) is not None


def test_a_stale_success_no_longer_makes_an_ip_known_good(db: psycopg.Connection) -> None:
    make_user(db)
    record_attempt(
        db,
        username="owner",
        client_ip=HOME,
        outcome="success",
        session_id=None,
        now=NOW - timedelta(days=400),
    )

    assert is_known_good_ip(db, "owner", HOME, now=NOW) is False


def test_the_per_ip_bucket_locks_independently(db: psycopg.Connection) -> None:
    """Spreading across usernames does not evade the address bucket."""
    moment = NOW
    last = NOW
    for index in range(IP_LOCK_AFTER):
        last = fail_times(db, 1, username=f"name{index}", start=moment)
        moment = last + timedelta(seconds=5)

    assert ip_state(db, ATTACKER, now=last + TICK) == "locked"
    assert ip_state(db, HOME, now=last + TICK) == "open"


def test_an_unresolvable_ip_shares_one_bucket_and_never_bypasses(db: psycopg.Connection) -> None:
    make_user(db)
    record_attempt(
        db, username="owner", client_ip="unknown", outcome="success", session_id=None, now=NOW
    )

    assert is_known_good_ip(db, "owner", "unknown", now=NOW + timedelta(hours=1)) is False


def test_a_locked_account_with_the_right_password_still_gets_the_uniform_failure(
    db: psycopg.Connection,
) -> None:
    """Otherwise the lock is an oracle for a correct credential."""
    make_user(db)
    last = fail_times(db, ACCOUNT_LOCK_AFTER, step=timedelta(seconds=30))

    assert authenticate(
        db, username="owner", password=PASSWORD, client_ip=ATTACKER, now=last + TICK
    ) is None


def test_a_failed_login_writes_no_session_row(db: psycopg.Connection) -> None:
    make_user(db)

    authenticate(db, username="owner", password="wrong", client_ip=ATTACKER, now=NOW)
    authenticate(db, username="nobody", password="wrong", client_ip=ATTACKER, now=NOW)

    with db.cursor() as cursor:
        cursor.execute("select count(*) from lineage.sessions")
        assert cursor.fetchone()[0] == 0


def test_a_username_differing_by_case_or_space_hits_one_counter(db: psycopg.Connection) -> None:
    make_user(db)
    for name in ("owner", "OWNER", "  Owner  ", "OwNeR", "owner "):
        authenticate(db, username=name, password="wrong", client_ip=ATTACKER, now=NOW)

    assert account_state(db, "owner", ATTACKER, now=NOW) == "backoff"


def test_a_disabled_account_answers_none_and_records_its_own_outcome(
    db: psycopg.Connection,
) -> None:
    user = make_user(db)
    with db.cursor() as cursor:
        cursor.execute(
            "update lineage.users set disabled_at = %s, disabled_by = %s where user_id = %s",
            (NOW, "test", user.user_id),
        )

    assert authenticate(
        db, username="owner", password=PASSWORD, client_ip=HOME, now=NOW
    ) is None
    with db.cursor() as cursor:
        cursor.execute("select outcome from lineage.login_attempts")
        assert cursor.fetchone()[0] == "disabled"


def test_a_success_records_the_attempt_and_clears_the_consecutive_count(
    db: psycopg.Connection,
) -> None:
    make_user(db)
    last = fail_times(db, ACCOUNT_BACKOFF_AFTER)
    moment = last + backoff_for(ACCOUNT_BACKOFF_AFTER) + TICK

    assert authenticate(
        db, username="owner", password=PASSWORD, client_ip=HOME, now=moment
    ) is not None
    assert account_state(db, "owner", HOME, now=moment + TICK) == "open"
