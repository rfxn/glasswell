"""CSRF as it is actually wired: which callers must carry a token, and which need not.

The token is required of cookie-authenticated callers only. CSRF is an ambient-authority
problem — a browser attaches the cookie to a cross-site request by itself — and
`X-Glasswell-Key` is never sent automatically. Requiring a token from a key-authenticated
caller would buy nothing and would break the deploy gate, which runs `verify.sh` and
`smoke.sh` with no browser and no cookie jar.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from glasswell.api.csrf import CSRF_HEADER, SAFE_METHODS
from tests.contract.conftest import (
    OWNER_PASSWORD,
    SESSION_BASE_URL,
    challenge,
    login,
    seed_user,
)

pytestmark = pytest.mark.contract

NON_SAFE = ("POST", "PUT", "PATCH", "DELETE")


@pytest.fixture
def actor(client: TestClient, seeded) -> TestClient:
    seed_user(seeded, username="csrf-owner", password=OWNER_PASSWORD, role="owner")
    return login(client, username="csrf-owner", password=OWNER_PASSWORD)


def test_a_state_changing_request_with_no_token_is_refused(actor) -> None:
    assert actor.delete("/v1/session").status_code == 403


def test_a_valid_token_is_accepted(actor) -> None:
    assert actor.delete(
        "/v1/session", headers={CSRF_HEADER: challenge(actor)}
    ).status_code == 200


def test_a_token_bound_to_another_session_is_refused(client, actor, seeded) -> None:
    seed_user(seeded, username="csrf-other", password=OWNER_PASSWORD, role="owner")
    other = login(client, username="csrf-other", password=OWNER_PASSWORD)

    stolen = challenge(other)

    assert actor.delete("/v1/session", headers={CSRF_HEADER: stolen}).status_code == 403


def test_a_tampered_token_is_refused(actor) -> None:
    token = challenge(actor)
    flipped = ("A" if token[0] != "A" else "B") + token[1:]

    assert actor.delete("/v1/session", headers={CSRF_HEADER: flipped}).status_code == 403


@pytest.mark.parametrize("token", ["", "not-a-token", "AAAA"])
def test_a_malformed_token_is_refused(actor, token: str) -> None:
    assert actor.delete("/v1/session", headers={CSRF_HEADER: token}).status_code == 403


def test_a_safe_method_never_requires_a_token(actor) -> None:
    for path in ("/v1/health", "/v1/session", "/v1/wells?limit=1"):
        assert actor.get(path).status_code == 200, path


def test_login_requires_a_pre_session_token(client) -> None:
    """Login CSRF: without this an attacker can silently log a victim into their account."""
    session = TestClient(client.app, base_url=SESSION_BASE_URL)

    response = session.post(
        "/v1/session", json={"username": "whoever", "password": "whatever-they-typed"}
    )

    assert response.status_code == 403
    assert response.json()["type"] == "/v1/errors/forbidden"


def test_a_key_authenticated_caller_needs_no_token(client) -> None:
    """The deploy gate's path. A key is not ambient authority, so there is nothing to forge."""
    issued = client.post("/v1/keys", json={"label": "csrf-machine-2026", "scope": "guest"})

    assert issued.status_code == 201, issued.text


def test_every_non_safe_operation_declares_the_header(client) -> None:
    """Structural: a new state-changing route that forgets to document the header fails here."""
    document = client.get("/openapi.json").json()

    missing = []
    for path, operations in document["paths"].items():
        for method, operation in operations.items():
            if method.upper() not in NON_SAFE:
                continue
            names = {
                parameter.get("name") for parameter in operation.get("parameters", []) or []
            }
            if CSRF_HEADER not in names:
                missing.append(f"{method.upper()} {path}")

    assert missing == [], f"non-safe operations that do not declare {CSRF_HEADER}: {missing}"


def test_a_get_never_declares_the_header_as_required(client) -> None:
    document = client.get("/openapi.json").json()

    for path, operations in document["paths"].items():
        for method, operation in operations.items():
            if method.upper() not in SAFE_METHODS:
                continue
            for parameter in operation.get("parameters", []) or []:
                if parameter.get("name") == CSRF_HEADER:
                    assert not parameter.get("required"), f"{method.upper()} {path}"
