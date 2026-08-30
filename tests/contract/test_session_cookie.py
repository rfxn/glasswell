"""The cookie's attributes are the boundary, so each one is asserted by name.

`__Host-` is the load-bearing choice: the prefix forces `Secure` and `Path=/` and *forbids*
`Domain`, which is what stops a sibling host in this zone from setting a cookie this origin
would accept. The zone carries other lab services, so that is a real adjacency, not a
theoretical one.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from glasswell.api.csrf import CSRF_COOKIE, CSRF_HEADER
from glasswell.api.deps import SESSION_COOKIE
from tests.contract.conftest import (
    OWNER_PASSWORD,
    SESSION_BASE_URL,
    VIEWER_PASSWORD,
    challenge,
    login,
    seed_user,
)

pytestmark = pytest.mark.contract


def set_cookie_header(response) -> str:
    headers = response.headers.get_list("set-cookie")
    session = [value for value in headers if value.startswith(SESSION_COOKIE)]
    assert session, f"no {SESSION_COOKIE} in {headers}"
    return session[0]


@pytest.fixture
def owner_account(seeded) -> None:
    seed_user(seeded, username="cookie-owner", password=OWNER_PASSWORD, role="owner")


def fresh_login(client: TestClient) -> tuple[TestClient, object]:
    session = TestClient(client.app, base_url=SESSION_BASE_URL)
    token = challenge(session)
    response = session.post(
        "/v1/session",
        json={"username": "cookie-owner", "password": OWNER_PASSWORD},
        headers={CSRF_HEADER: token},
    )
    assert response.status_code == 201, response.text
    return session, response


def test_the_cookie_carries_the_host_prefix_and_no_domain(client, owner_account) -> None:
    _, response = fresh_login(client)

    header = set_cookie_header(response)

    assert header.startswith("__Host-")
    assert "domain=" not in header.lower(), "a Domain attribute voids the __Host- prefix"


def test_the_cookie_is_httponly_secure_samesite_lax_path_root(client, owner_account) -> None:
    _, response = fresh_login(client)

    header = set_cookie_header(response).lower()

    assert "httponly" in header
    assert "secure" in header
    assert "samesite=lax" in header
    assert "path=/" in header


def test_the_cookie_value_is_not_the_stored_representation(
    client, owner_account, seeded
) -> None:
    session, _ = fresh_login(client)
    token = session.cookies.get(SESSION_COOKIE)

    with seeded.cursor() as cursor:
        cursor.execute("select sha256 from lineage.sessions")
        stored = [row[0] for row in cursor.fetchall()]

    assert token not in stored
    assert all(len(value) == 64 for value in stored)


def test_logout_clears_the_cookie_with_the_same_attributes(client, owner_account) -> None:
    session, _ = fresh_login(client)

    response = session.delete("/v1/session", headers={CSRF_HEADER: challenge(session)})

    assert response.status_code == 200, response.text
    header = set_cookie_header(response).lower()
    assert 'max-age=0' in header or 'expires=' in header
    assert "path=/" in header


def test_a_cookie_replayed_after_logout_is_refused(client, owner_account) -> None:
    """The property a stateless token cannot have: the row is gone, so the copy is dead."""
    session, _ = fresh_login(client)
    token = session.cookies.get(SESSION_COOKIE)
    session.delete("/v1/session", headers={CSRF_HEADER: challenge(session)})

    replay = TestClient(client.app, base_url=SESSION_BASE_URL)
    replay.cookies.set(SESSION_COOKIE, token)

    assert replay.get("/v1/health").status_code == 403


def test_login_rotates_the_session_and_revokes_the_one_presented(
    client, owner_account, seeded
) -> None:
    """Fixation: an attacker who plants a known cookie must not still hold it after login."""
    session, _ = fresh_login(client)
    planted = session.cookies.get(SESSION_COOKIE)

    second = TestClient(client.app, base_url=SESSION_BASE_URL)
    second.cookies.set(SESSION_COOKIE, planted)
    token = challenge(second)
    response = second.post(
        "/v1/session",
        json={"username": "cookie-owner", "password": OWNER_PASSWORD},
        headers={CSRF_HEADER: token},
    )

    assert response.status_code == 201, response.text
    # Read from Set-Cookie, not the jar: the jar now holds both the hand-planted copy and the
    # freshly minted one, and asking it by name is ambiguous.
    minted = set_cookie_header(response).split(";")[0].split("=", 1)[1]
    assert minted != planted

    replay = TestClient(client.app, base_url=SESSION_BASE_URL)
    replay.cookies.set(SESSION_COOKIE, planted)
    assert replay.get("/v1/health").status_code == 403


def test_no_other_route_ever_sets_a_session_cookie(client, owner_session) -> None:
    """A Set-Cookie from a data route would be a credential appearing where none was minted."""
    probes = (
        "/v1/health",
        "/v1/wells?limit=1",
        "/v1/glossary",
        "/v1/session",
        "/v1/session/challenge",
        "/healthz",
    )

    for path in probes:
        response = owner_session.get(path)
        emitted = [
            value
            for value in response.headers.get_list("set-cookie")
            if value.startswith(SESSION_COOKIE)
        ]
        assert emitted == [], f"{path} set a session cookie"


def test_the_pre_session_csrf_cookie_carries_the_same_attributes(client) -> None:
    session = TestClient(client.app, base_url=SESSION_BASE_URL)

    response = session.get("/v1/session/challenge")

    header = next(
        value for value in response.headers.get_list("set-cookie")
        if value.startswith(CSRF_COOKIE)
    ).lower()
    assert header.startswith("__host-")
    assert "httponly" in header
    assert "secure" in header
    assert "samesite=lax" in header
    assert "domain=" not in header


def test_a_password_change_revokes_siblings_and_keeps_the_actor(client, seeded) -> None:
    seed_user(seeded, username="rotator", password=OWNER_PASSWORD, role="owner")
    acting = login(client, username="rotator", password=OWNER_PASSWORD)
    sibling = login(client, username="rotator", password=OWNER_PASSWORD)

    response = acting.post(
        "/v1/session/password",
        json={"current_password": OWNER_PASSWORD, "new_password": VIEWER_PASSWORD},
        headers={CSRF_HEADER: challenge(acting)},
    )

    assert response.status_code == 200, response.text
    assert acting.get("/v1/health").status_code == 200, "the acting session was logged out"
    assert sibling.get("/v1/health").status_code == 403, "a sibling session survived"


def test_changing_your_own_password_requires_the_current_one(client, seeded) -> None:
    seed_user(seeded, username="careful", password=OWNER_PASSWORD, role="owner")
    session = login(client, username="careful", password=OWNER_PASSWORD)

    response = session.post(
        "/v1/session/password",
        json={"current_password": "not-the-current-password", "new_password": VIEWER_PASSWORD},
        headers={CSRF_HEADER: challenge(session)},
    )

    assert response.status_code == 403
    assert session.get("/v1/health").status_code == 200
