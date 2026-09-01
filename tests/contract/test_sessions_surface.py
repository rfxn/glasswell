"""`/v1/sessions` over the wire: who reaches it, and what it never returns.

The list is owner-only. The revoke admits two callers and no more — the owner, on any session,
and a holder on the one they are calling with — and the rule that a viewer may revoke their own
is asserted here rather than in the auth matrix, whose table keys on the path and cannot say
"the caller's own row".
"""

from __future__ import annotations

import psycopg
import pytest
from fastapi.testclient import TestClient

from glasswell.api.csrf import CSRF_HEADER
from tests.contract.conftest import VIEWER_USERNAME, challenge, seed_session

pytestmark = pytest.mark.contract

FOREIGN_USERNAME = "foreign-holder"
REFUSED_TO_OTHERS = ("viewer_session", "guest_client", "agent_client")


@pytest.fixture
def foreign_session_id(client: TestClient, seeded: psycopg.Connection) -> str:
    """A live session belonging to nobody in this test, read back off the owner's own list."""
    seed_session(client, seeded, username=FOREIGN_USERNAME, role="viewer")
    listed = client.get("/v1/sessions").json()["data"]
    return next(row["session_id"] for row in listed if row["username"] == FOREIGN_USERNAME)


def test_the_owner_lists_every_session_newest_first(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    seed_session(client, seeded, username="listed-first", role="viewer")
    seed_session(client, seeded, username="listed-second", role="owner")

    response = client.get("/v1/sessions")

    assert response.status_code == 200, response.text
    rows = response.json()["data"]
    assert {row["username"] for row in rows} >= {"listed-first", "listed-second"}
    assert [row["created_at"] for row in rows] == sorted(
        (row["created_at"] for row in rows), reverse=True
    )


@pytest.mark.parametrize("caller", REFUSED_TO_OTHERS)
def test_no_other_principal_class_lists_sessions(request, caller: str) -> None:
    other: TestClient = request.getfixturevalue(caller)

    assert other.get("/v1/sessions").status_code == 403


@pytest.mark.parametrize("caller", REFUSED_TO_OTHERS)
def test_no_other_principal_class_revokes_a_foreign_session(
    request, caller: str, foreign_session_id: str
) -> None:
    """Refused before the lookup, so the route is not an existence oracle for a viewer."""
    other: TestClient = request.getfixturevalue(caller)
    headers = {CSRF_HEADER: challenge(other)} if caller == "viewer_session" else {}

    response = other.delete(f"/v1/sessions/{foreign_session_id}", headers=headers)

    assert response.status_code == 403, response.text


def test_an_unknown_session_id_is_refused_rather_than_answered_for_a_viewer(
    viewer_session: TestClient,
) -> None:
    """A viewer meets the same 403 for an id that does not exist as for one that does."""
    response = viewer_session.delete(
        "/v1/sessions/ses_does_not_exist", headers={CSRF_HEADER: challenge(viewer_session)}
    )

    assert response.status_code == 403


def test_an_unknown_session_id_is_a_not_found_for_the_owner(client: TestClient) -> None:
    """The owner may already enumerate the collection, so 404 tells them nothing 200 would not."""
    assert client.delete("/v1/sessions/ses_does_not_exist").status_code == 404


def test_a_viewer_may_revoke_their_own_session_and_is_signed_out_by_it(
    client: TestClient, viewer_session: TestClient
) -> None:
    listed = client.get("/v1/sessions").json()["data"]
    own = next(row["session_id"] for row in listed if row["username"] == VIEWER_USERNAME)

    revoked = viewer_session.delete(
        f"/v1/sessions/{own}", headers={CSRF_HEADER: challenge(viewer_session)}
    )

    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["data"]["state"] == "revoked"
    assert revoked.json()["data"]["revoked_reason"] == "logout"
    assert viewer_session.get("/v1/health").status_code == 403


def test_the_owner_revokes_somebody_elses_session_as_an_admin_action(
    client: TestClient, viewer_session: TestClient
) -> None:
    listed = client.get("/v1/sessions").json()["data"]
    victim = next(row["session_id"] for row in listed if row["username"] == VIEWER_USERNAME)

    revoked = client.delete(f"/v1/sessions/{victim}")

    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["data"]["revoked_reason"] == "admin"
    assert viewer_session.get("/v1/health").status_code == 403


def test_revoking_an_already_revoked_session_answers_the_same_record(
    client: TestClient, foreign_session_id: str
) -> None:
    first = client.delete(f"/v1/sessions/{foreign_session_id}")
    second = client.delete(f"/v1/sessions/{foreign_session_id}")

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["data"] == second.json()["data"]


def test_no_session_response_carries_a_credential_or_an_address(
    client: TestClient, foreign_session_id: str
) -> None:
    """The token hash and the client address are both in the row and in neither response."""
    listing = client.get("/v1/sessions")
    revoked = client.delete(f"/v1/sessions/{foreign_session_id}")

    assert listing.status_code == 200, listing.text
    for body in (listing.text, revoked.text):
        assert "sha256" not in body
        assert "created_ip" not in body
        assert "198.51.100.4" not in body
        assert "gws_" not in body


def test_a_listed_row_states_a_class_rather_than_an_address(
    client: TestClient, viewer_session: TestClient
) -> None:
    rows = client.get("/v1/sessions").json()["data"]

    assert rows
    assert {row["address_class"] for row in rows} <= {"lan", "remote", "unknown"}
    assert all(row["state"] in {"active", "revoked", "expired"} for row in rows)
    assert all(row["user_agent_family"] for row in rows)
