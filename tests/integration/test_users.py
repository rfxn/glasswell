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


# --- the routes: re-enabling, and the refusals that keep it from being a second disable path ---
#
# `state` is `Literal["active"]` and nothing else. A PATCH that could disable would be a second
# lockout path with neither the owner floor nor the session revocation the DELETE carries, so
# the refusals below are the guard rail rather than a validation nicety.

CREATED = {"username": "patchable", "password": PASSWORD, "role": "viewer"}


def created_user(api_client) -> str:
    response = api_client.post("/v1/users", json=CREATED)
    assert response.status_code == 201, response.text
    return response.json()["data"]["user_id"]


def disabled_user(api_client) -> str:
    user_id = created_user(api_client)
    assert api_client.delete(f"/v1/users/{user_id}").status_code == 200
    return user_id


def test_a_patch_that_would_disable_is_refused_by_the_schema(api_client) -> None:
    """Before the handler, so no code path exists that could disable without the floor."""
    user_id = created_user(api_client)

    response = api_client.patch(f"/v1/users/{user_id}", json={"state": "disabled"})

    assert response.status_code == 422, response.text
    # FastAPI's own loc, not the handler's: a body refusal is pointed at from the body root.
    assert response.json()["errors"][0]["pointer"] == "/body/state"


def test_enabling_clears_both_the_time_and_the_actor(api_client, db: psycopg.Connection) -> None:
    """The 055 CHECK admits a null disabled_at beside a stale disabled_by, and the serializer
    would then answer `active` for an account still naming whoever disabled it."""
    user_id = disabled_user(api_client)

    response = api_client.patch(f"/v1/users/{user_id}", json={"state": "active"})

    assert response.status_code == 200, response.text
    assert response.json()["data"]["state"] == "active"
    assert response.json()["data"]["disabled_at"] is None
    assert response.json()["data"]["disabled_by"] is None
    with db.cursor() as cursor:
        cursor.execute(
            "select disabled_at, disabled_by from lineage.users where user_id = %s", (user_id,)
        )
        assert cursor.fetchone() == (None, None)


def test_enabling_an_active_account_is_refused_rather_than_answered_silently(api_client) -> None:
    """The list the caller acted on said the account was disabled; it is stale, and saying so
    is the difference between a stale screen and a screen that is quietly wrong."""
    user_id = created_user(api_client)

    response = api_client.patch(f"/v1/users/{user_id}", json={"state": "active"})

    assert response.status_code == 422, response.text
    assert response.json()["errors"][0]["code"] == "not_disabled"
    assert response.json()["errors"][0]["pointer"] == "/state"
    assert response.json()["detail"] == "that account is not disabled"


def test_an_unknown_id_is_a_not_found_before_any_state_is_inspected(api_client) -> None:
    response = api_client.patch("/v1/users/usr_not_here", json={"state": "active"})

    assert response.status_code == 404, response.text


def test_a_role_and_a_state_in_one_call_are_refused(api_client) -> None:
    """Two changes are two calls and two audit events, and no ordering question against the
    lock the floor takes."""
    user_id = disabled_user(api_client)

    response = api_client.patch(
        f"/v1/users/{user_id}", json={"role": "owner", "state": "active"}
    )

    assert response.status_code == 422, response.text
    assert response.json()["errors"][0]["pointer"] == "/state"
    assert response.json()["errors"][0]["code"] == "one_change_at_a_time"


def test_the_owner_floor_survives_an_enable(api_client, db: psycopg.Connection) -> None:
    """Re-enabling does not add an owner, so the sole enabled owner is still undemotable."""
    sole = create_user(
        db, username="sole-owner", password=PASSWORD, role="owner", created_by="t", now=NOW
    )
    other = disabled_user(api_client)
    db.commit()

    assert api_client.patch(f"/v1/users/{other}", json={"state": "active"}).status_code == 200
    refused = api_client.patch(f"/v1/users/{sole}", json={"role": "viewer"})

    assert refused.status_code == 422, refused.text
    assert refused.json()["errors"][0]["code"] == "last_owner"
    assert refused.json()["errors"][0]["pointer"] == "/role"


def test_the_disable_refusal_points_at_no_field_because_it_carries_no_body(
    api_client, db: psycopg.Connection
) -> None:
    """One helper, two callers: a DELETE has no body, so a `/role` pointer described a field
    the caller never sent."""
    sole = create_user(
        db, username="only-owner", password=PASSWORD, role="owner", created_by="t", now=NOW
    )
    db.commit()

    refused = api_client.delete(f"/v1/users/{sole}")

    assert refused.status_code == 422, refused.text
    assert refused.json()["errors"][0]["code"] == "last_owner"
    assert "pointer" not in refused.json()["errors"][0]


def test_a_created_account_carries_its_live_session_count(
    api_client, db: psycopg.Connection
) -> None:
    """Counted against the injected clock: a session past its idle window is not live, and a
    count read off SQL now() would drift against the row it is describing."""
    from glasswell.api.accounts import IDLE_WINDOW, create_session

    user_id = created_user(api_client)
    user = find_user(db, "patchable")
    assert user is not None
    create_session(db, user=user, now=datetime.now(UTC))
    create_session(db, user=user, now=datetime.now(UTC) - IDLE_WINDOW * 2)
    db.commit()

    listed = api_client.get("/v1/users").json()["data"]

    assert next(row["sessions_live"] for row in listed if row["user_id"] == user_id) == 1


def test_a_password_the_caller_supplied_is_never_echoed_back(api_client) -> None:
    created = api_client.post("/v1/users", json=CREATED)

    assert created.status_code == 201, created.text
    assert created.json()["data"]["password"] is None
    assert PASSWORD not in created.text
    assert created.json()["meta"]["warnings"] == []


def test_an_omitted_password_is_minted_and_shown_exactly_once(api_client) -> None:
    created = api_client.post("/v1/users", json={"username": "minted", "role": "viewer"})

    assert created.status_code == 201, created.text
    minted = created.json()["data"]["password"]
    assert minted is not None
    assert len(minted) >= 43
    assert [warning["code"] for warning in created.json()["meta"]["warnings"]] == [
        "password_shown_once"
    ]
    assert minted not in api_client.get("/v1/users").text


def test_a_reset_mints_when_no_password_is_supplied(api_client) -> None:
    user_id = created_user(api_client)

    reset = api_client.post(f"/v1/users/{user_id}/password", json={})
    supplied = api_client.post(
        f"/v1/users/{user_id}/password", json={"new_password": "another-long-password"}
    )

    assert reset.status_code == 200, reset.text
    assert reset.json()["data"]["password"]
    assert supplied.status_code == 200, supplied.text
    assert supplied.json()["data"]["password"] is None
    assert supplied.json()["meta"]["warnings"] == []
