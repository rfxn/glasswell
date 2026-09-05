"""B-1: the owner key must never reach a place that persists it — query string or journal.

The refusals are here, against the served routes. The redaction filter itself is a pure
function over a log line, asserted in tests/unit/test_access_log_redaction.py.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from glasswell.api.errors import TYPE_BASE

OWNER_KEY = "f" * 64


def test_a_key_in_the_query_string_is_refused(client: TestClient) -> None:
    response = client.get("/v1/health", params={"key": OWNER_KEY})

    assert response.status_code == 422
    assert response.json()["type"] == f"{TYPE_BASE}/validation_failed"
    assert response.json()["errors"][0]["pointer"] == "/query/key"


def test_the_refusal_never_echoes_the_key_back(client: TestClient) -> None:
    response = client.get("/v1/health", params={"key": OWNER_KEY})

    assert OWNER_KEY not in response.text


def test_the_refusal_is_a_full_problem_document(client: TestClient) -> None:
    """The guard runs inside the request-id middleware, so the refusal joins the audit trail."""
    body = client.get("/v1/health", params={"key": OWNER_KEY}).json()

    assert body["request_id"]
    assert body["instance"] == "/v1/health"


def test_the_refusal_precedes_authentication(client: TestClient) -> None:
    """A wrong key in the query string is still a query-string key, not a 403 oracle."""
    anonymous = TestClient(client.app)

    assert anonymous.get("/v1/health", params={"key": "wrong"}).status_code == 422


def test_a_keyless_request_is_untouched(client: TestClient) -> None:
    assert client.get("/v1/health").status_code == 200


@pytest.mark.parametrize("parameter", ["key", "password", "token"])
def test_a_credential_in_the_query_string_is_refused(client, parameter: str) -> None:
    """A query string reaches the access log verbatim and the Referer of every outbound link."""
    response = client.get(f"/v1/health?{parameter}=whatever-they-typed")

    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "credential_in_query"
