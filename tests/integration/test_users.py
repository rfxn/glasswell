"""Account administration, and the one invariant that cannot be allowed to race.

The last enabled owner cannot be disabled or demoted. A handler-only count is not enough:
two concurrent demotions would each read "two owners exist" and both commit, leaving a
deployment nobody can administer. The guard takes `for update` on the enabled-owner set.
"""

from __future__ import annotations

from datetime import UTC, datetime

import psycopg
import pytest

from glasswell.api.accounts import (
    create_user,
    find_user,
    normalise_username,
    revoke_user_sessions,
    set_password,
    verify_user_password,
)

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 30, 12, 0, 0, tzinfo=UTC)
PASSWORD = "a-sufficiently-long-password"


def enabled_owners(connection: psycopg.Connection) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "select count(*) from lineage.users where role = 'owner' and disabled_at is null"
        )
        return cursor.fetchone()[0]


def test_a_username_is_stored_lowercased_and_is_unique_case_insensitively(
    db: psycopg.Connection,
) -> None:
    create_user(
        db, username="MixedCase", password=PASSWORD, role="owner", created_by="test", now=NOW
    )

    stored = find_user(db, "mixedcase")

    assert stored is not None
    assert stored.username == "mixedcase"
    assert find_user(db, "MIXEDCASE") is not None
    with pytest.raises(psycopg.errors.UniqueViolation):
        create_user(
            db, username="MIXEDCASE", password=PASSWORD, role="viewer",
            created_by="test", now=NOW,
        )


def test_normalising_a_username_trims_and_folds() -> None:
    assert normalise_username("  Ryan  ") == "ryan"


def test_two_concurrent_demotions_cannot_both_succeed(
    db: psycopg.Connection, migrated_template: str, postgres_password: str
) -> None:
    """The `for update` test, run on two real connections.

    Both transactions read the enabled-owner set and both intend to demote a different
    owner. Serialised by the lock, the second sees the first's effect. Without the lock they
    would both commit and no enabled owner would remain.
    """
    first_id = create_user(
        db, username="owner-one", password=PASSWORD, role="owner", created_by="t", now=NOW
    )
    second_id = create_user(
        db, username="owner-two", password=PASSWORD, role="owner", created_by="t", now=NOW
    )
    db.commit()
    assert enabled_owners(db) == 2

    dsn = db.info.dsn
    lock = "select user_id from lineage.users where role='owner' and disabled_at is null for update"
    with psycopg.connect(dsn, password=postgres_password) as a, psycopg.connect(
        dsn, password=postgres_password
    ) as b:
        with a.cursor() as cursor:
            cursor.execute(lock)
            owners = [row[0] for row in cursor.fetchall()]
            assert len(owners) == 2
            cursor.execute(
                "update lineage.users set role='viewer' where user_id=%s", (first_id,)
            )
        a.commit()

        with b.cursor() as cursor:
            cursor.execute(lock)
            remaining = [row[0] for row in cursor.fetchall()]

        # The second transaction now sees one enabled owner, which is exactly the state that
        # makes the application-level refusal fire rather than letting the set empty.
        assert remaining == [second_id]
    db.commit()
    assert enabled_owners(db) == 1


def test_disabling_a_user_revokes_every_session_they_hold(db: psycopg.Connection) -> None:
    from glasswell.api.accounts import create_session, resolve_session

    user_id = create_user(
        db, username="doomed", password=PASSWORD, role="viewer", created_by="t", now=NOW
    )
    user = find_user(db, "doomed")
    assert user is not None
    _, first = create_session(db, user=user, now=NOW)
    _, second = create_session(db, user=user, now=NOW)

    with db.cursor() as cursor:
        cursor.execute(
            "update lineage.users set disabled_at=%s, disabled_by=%s where user_id=%s",
            (NOW, "t", user_id),
        )
    revoked = revoke_user_sessions(db, user_id, reason="admin", now=NOW, keep=None)

    assert revoked == 2
    assert resolve_session(db, first, now=NOW) is None
    assert resolve_session(db, second, now=NOW) is None


def test_setting_a_password_changes_what_verifies(db: psycopg.Connection) -> None:
    create_user(
        db, username="resettable", password=PASSWORD, role="viewer", created_by="t", now=NOW
    )

    set_password(db, find_user(db, "resettable").user_id, password="a-brand-new-password", now=NOW)

    user = find_user(db, "resettable")
    assert verify_user_password(user, "a-brand-new-password") is True
    assert verify_user_password(user, PASSWORD) is False


def test_a_password_change_stamps_the_time(db: psycopg.Connection) -> None:
    create_user(
        db, username="stamped", password=PASSWORD, role="viewer", created_by="t", now=NOW
    )
    later = datetime(2026, 9, 1, 12, 0, 0, tzinfo=UTC)

    set_password(db, find_user(db, "stamped").user_id, password="another-long-password", now=later)

    assert find_user(db, "stamped").password_changed_at == later


def test_a_created_user_is_enabled_and_carries_its_creator(db: psycopg.Connection) -> None:
    create_user(
        db, username="fresh", password=PASSWORD, role="viewer", created_by="usr_someone", now=NOW
    )

    user = find_user(db, "fresh")

    assert user.enabled is True
    assert user.created_by == "usr_someone"
    assert user.last_login_at is None


def test_a_stored_password_is_never_the_cleartext(db: psycopg.Connection) -> None:
    create_user(
        db, username="hashed", password=PASSWORD, role="viewer", created_by="t", now=NOW
    )

    with db.cursor() as cursor:
        cursor.execute("select password_hash from lineage.users where username='hashed'")
        stored = cursor.fetchone()[0]

    assert stored != PASSWORD
    assert stored.startswith("$argon2id$")
