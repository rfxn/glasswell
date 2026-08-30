"""`/v1/users` over the wire: who reaches it, and what it never returns.

The last-owner guard is asserted here as well as in the integration tier, because the
integration test proves the lock and this one proves the *route* refuses — a guard that
exists only in a helper nobody calls is not a guard.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from glasswell.api.csrf import CSRF_HEADER
from tests.contract.conftest import OWNER_PASSWORD, challenge, seed_user

pytestmark = pytest.mark.contract

NEW_PASSWORD = "a-sufficiently-long-new-password"
OPERATIONS = (
    ("GET", "/v1/users", None),
    ("POST", "/v1/users", {"username": "intruder", "password": NEW_PASSWORD, "role": "viewer"}),
    ("PATCH", "/v1/users/usr_whatever", {"role": "owner"}),
    ("DELETE", "/v1/users/usr_whatever", None),
    ("POST", "/v1/users/usr_whatever/password", {"new_password": NEW_PASSWORD}),
)


def call(client: TestClient, method: str, path: str, body, csrf: str | None = None):
    headers = {CSRF_HEADER: csrf} if csrf else {}
    return client.request(method, path, json=body, headers=headers)


@pytest.mark.parametrize(("method", "path", "body"), OPERATIONS)
def test_a_viewer_session_is_refused_every_user_operation(
    viewer_session: TestClient, method: str, path: str, body
) -> None:
    response = call(viewer_session, method, path, body, csrf=challenge(viewer_session))

    assert response.status_code == 403, f"{method} {path} reached a viewer"


@pytest.mark.parametrize(("method", "path", "body"), OPERATIONS)
def test_an_issued_guest_key_is_refused_every_user_operation(
    guest_client: TestClient, method: str, path: str, body
) -> None:
    assert call(guest_client, method, path, body).status_code == 403


@pytest.mark.parametrize(("method", "path", "body"), OPERATIONS)
def test_an_agent_key_is_refused_every_user_operation(
    agent_client: TestClient, method: str, path: str, body
) -> None:
    assert call(agent_client, method, path, body).status_code == 403


def test_no_response_ever_carries_a_password_hash(client: TestClient, seeded) -> None:
    seed_user(seeded, username="listed", password=OWNER_PASSWORD, role="viewer")

    listing = client.get("/v1/users")
    created = client.post(
        "/v1/users",
        json={"username": "made-here", "password": NEW_PASSWORD, "role": "viewer"},
    )

    assert listing.status_code == 200, listing.text
    assert created.status_code == 201, created.text
    for body in (listing.text, created.text):
        assert "password_hash" not in body
        assert "$argon2id$" not in body
        assert NEW_PASSWORD not in body
        assert OWNER_PASSWORD not in body


def test_the_owner_can_create_update_disable_and_reset(client: TestClient, seeded) -> None:
    # A second owner row, so promoting the account under test does not make it the last one.
    # The acting principal here is the static owner *key*, which is not a lineage.users row
    # and therefore does not count toward the enabled-owner set the guard protects.
    seed_user(seeded, username="standby-owner", password=OWNER_PASSWORD, role="owner")
    created = client.post(
        "/v1/users",
        json={"username": "lifecycle", "password": NEW_PASSWORD, "role": "viewer"},
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["data"]["user_id"]

    promoted = client.patch(f"/v1/users/{user_id}", json={"role": "owner"})
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["data"]["role"] == "owner"

    reset = client.post(f"/v1/users/{user_id}/password", json={"new_password": OWNER_PASSWORD})
    assert reset.status_code == 200, reset.text

    disabled = client.delete(f"/v1/users/{user_id}")
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["data"]["state"] == "disabled"


def test_the_last_enabled_owner_cannot_be_disabled(client: TestClient, seeded) -> None:
    user_id = seed_user(seeded, username="sole-owner", password=OWNER_PASSWORD, role="owner")

    response = client.delete(f"/v1/users/{user_id}")

    assert response.status_code == 422, response.text
    assert response.json()["errors"][0]["code"] == "last_owner"


def test_the_last_enabled_owner_cannot_be_demoted(client: TestClient, seeded) -> None:
    user_id = seed_user(seeded, username="only-owner", password=OWNER_PASSWORD, role="owner")

    response = client.patch(f"/v1/users/{user_id}", json={"role": "viewer"})

    assert response.status_code == 422, response.text
    assert response.json()["errors"][0]["code"] == "last_owner"


def test_a_second_owner_makes_the_first_demotable(client: TestClient, seeded) -> None:
    """The floor under the two refusals above: they must be about the *last* owner, not
    about owners generally."""
    first = seed_user(seeded, username="owner-a", password=OWNER_PASSWORD, role="owner")
    seed_user(seeded, username="owner-b", password=OWNER_PASSWORD, role="owner")

    response = client.patch(f"/v1/users/{first}", json={"role": "viewer"})

    assert response.status_code == 200, response.text
    assert response.json()["data"]["role"] == "viewer"


def test_a_duplicate_username_is_refused(client: TestClient, seeded) -> None:
    seed_user(seeded, username="taken", password=OWNER_PASSWORD, role="viewer")

    response = client.post(
        "/v1/users", json={"username": "TAKEN", "password": NEW_PASSWORD, "role": "viewer"}
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "duplicate"


def test_a_short_password_is_refused(client: TestClient) -> None:
    response = client.post(
        "/v1/users", json={"username": "weakling", "password": "short", "role": "viewer"}
    )

    assert response.status_code == 422


def test_disabling_a_user_revokes_their_session(client: TestClient, seeded) -> None:
    from tests.contract.conftest import seed_session

    victim = seed_session(client, seeded, username="to-disable", role="viewer")
    assert victim.get("/v1/health").status_code == 200
    user_id = client.get("/v1/users").json()["data"]
    target = next(row["user_id"] for row in user_id if row["username"] == "to-disable")

    client.delete(f"/v1/users/{target}")

    assert victim.get("/v1/health").status_code == 403


def test_an_owner_reset_revokes_the_targets_sessions(client: TestClient, seeded) -> None:
    from tests.contract.conftest import seed_session

    victim = seed_session(client, seeded, username="to-reset", role="viewer")
    listed = client.get("/v1/users").json()["data"]
    target = next(row["user_id"] for row in listed if row["username"] == "to-reset")

    client.post(f"/v1/users/{target}/password", json={"new_password": NEW_PASSWORD})

    assert victim.get("/v1/health").status_code == 403


def test_an_unknown_user_id_is_a_not_found(client: TestClient) -> None:
    assert client.get("/v1/users").status_code == 200
    assert client.delete("/v1/users/usr_does_not_exist").status_code == 404
