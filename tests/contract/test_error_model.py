"""RFC 9457 problem+json, the enumerated registry, and the auditor's never-a-bare-404."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from glasswell.api.errors import ERROR_REGISTRY, TYPE_BASE
from glasswell.api.examples import EXAMPLE_API10, KEY_HEADER
from glasswell.lineage.errors import UNRESOLVED_REASONS

PROBLEM_MEDIA_TYPE = "application/problem+json"
REQUIRED_FIELDS = ("type", "title", "status", "instance", "request_id")


def test_an_unknown_well_is_a_problem_document(client: TestClient) -> None:
    response = client.get("/v1/wells/3300000000")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    body = response.json()
    assert all(field in body for field in REQUIRED_FIELDS)
    assert body["type"] == f"{TYPE_BASE}/not_found"
    assert body["instance"] == "/v1/wells/3300000000"
    assert body["detail"]


def test_validation_failures_carry_pointers(client: TestClient) -> None:
    response = client.get("/v1/wells", params={"limit": 5000})

    assert response.status_code == 422
    body = response.json()
    assert body["type"] == f"{TYPE_BASE}/validation_failed"
    assert body["errors"]
    assert body["errors"][0]["pointer"].startswith("/query/")


def test_an_unresolvable_handle_is_never_a_bare_404(client: TestClient) -> None:
    response = client.get("/v1/explain", params={"h": "drv_doesnotexist", "depth": "full"})

    assert response.status_code == 404
    body = response.json()
    assert body["type"] == f"{TYPE_BASE}/lineage_unresolved"
    assert body["handle"] == "drv_doesnotexist"
    assert body["stop_reason"] in UNRESOLVED_REASONS
    assert "last_resolved" in body


def test_unknown_id_is_a_stop_reason_and_not_an_error_code() -> None:
    """m5: the registry is frozen; `unknown_id` lives inside `lineage_unresolved`."""
    assert "unknown_id" not in ERROR_REGISTRY
    assert "unknown_id" in UNRESOLVED_REASONS


def test_a_malformed_handle_is_a_validation_failure(client: TestClient) -> None:
    response = client.get("/v1/explain", params={"h": "not-a-handle"})

    assert response.status_code == 422
    assert response.json()["type"] == f"{TYPE_BASE}/validation_failed"


def test_an_ambiguous_selector_is_named_as_such(client: TestClient) -> None:
    response = client.get("/v1/explain", params={"h": "drv_abc#not+a+selector"})

    assert response.status_code == 422
    assert response.json()["type"] == f"{TYPE_BASE}/selector_ambiguous"


@pytest.mark.parametrize("code", sorted(ERROR_REGISTRY))
def test_every_type_uri_resolves(client: TestClient, code: str) -> None:
    response = client.get(f"/v1/errors/{code}")

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["code"] == code
    assert body["type"] == f"{TYPE_BASE}/{code}"
    assert body["title"]
    assert body["description"]


def test_an_unknown_error_code_is_not_found(client: TestClient) -> None:
    response = client.get("/v1/errors/no_such_code")

    assert response.status_code == 404
    assert response.json()["type"] == f"{TYPE_BASE}/not_found"


def test_type_uris_are_absolute(client: TestClient) -> None:
    """m5: a relative type URI resolves against the request URL and drifts per client."""
    assert TYPE_BASE.startswith("https://")

    body = client.get("/v1/wells/3300000000").json()

    assert body["type"].startswith("https://")


def test_a_request_with_no_key_is_refused(client: TestClient) -> None:
    anonymous = TestClient(client.app)

    response = anonymous.get("/v1/wells")

    assert response.status_code == 403
    assert response.json()["type"] == f"{TYPE_BASE}/key_required"


def test_a_wrong_key_is_refused_without_saying_why(client: TestClient) -> None:
    wrong = TestClient(client.app, headers={KEY_HEADER: "not-the-owner-key"})

    response = wrong.get("/v1/wells")

    assert response.status_code == 403
    body = response.json()
    assert body["type"] == f"{TYPE_BASE}/unauthenticated"
    assert "detail" not in body
    assert "errors" not in body


def test_healthz_stays_open(client: TestClient) -> None:
    anonymous = TestClient(client.app)

    assert anonymous.get("/healthz").status_code == 200


def test_the_registry_is_the_documented_set(client: TestClient) -> None:
    served = {entry["code"] for entry in client.get("/v1").json()["data"]["error_codes"]}

    assert served == set(ERROR_REGISTRY)


def test_an_as_of_before_the_first_vintage_is_refused(client: TestClient) -> None:
    response = client.get(
        f"/v1/wells/{EXAMPLE_API10}/production", params={"as_of": "2020-01-01"}
    )

    assert response.status_code == 422
    assert response.json()["type"] == f"{TYPE_BASE}/as_of_out_of_range"
