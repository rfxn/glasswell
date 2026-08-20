"""SB-07 §10 check 1 and SB-04 §7.1: the document is the contract, so it must be complete."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from glasswell.api.examples import REQUEST_EXAMPLE_KEY

MINIMUM_PATHS = 17


def operations(document: dict) -> list[tuple[str, str, dict]]:
    return [
        (path, method, operation)
        for path, item in document["paths"].items()
        for method, operation in item.items()
        if method in {"get", "post", "put", "patch", "delete"}
    ]


@pytest.fixture
def document(client: TestClient) -> dict:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    return response.json()


def test_the_document_is_openapi_31(document: dict) -> None:
    assert document["openapi"].startswith("3.1")


def test_every_shipped_path_is_served(document: dict) -> None:
    assert len(document["paths"]) >= MINIMUM_PATHS


def test_every_operation_supplies_a_request_example(document: dict) -> None:
    """No example is a build failure — that is how a new endpoint is forced into scope."""
    missing = [
        f"{method.upper()} {path}"
        for path, method, operation in operations(document)
        if REQUEST_EXAMPLE_KEY not in operation
    ]

    assert missing == []


def test_every_operation_is_documented_for_a_stranger(document: dict) -> None:
    incomplete = [
        f"{method.upper()} {path}"
        for path, method, operation in operations(document)
        if not operation.get("operationId")
        or not operation.get("summary")
        or not operation.get("description")
        or not operation.get("tags")
    ]

    assert incomplete == []


def test_operation_ids_are_unique_and_snake_case(document: dict) -> None:
    identifiers = [operation["operationId"] for _, _, operation in operations(document)]

    assert len(identifiers) == len(set(identifiers))
    assert all(identifier.islower() and " " not in identifier for identifier in identifiers)


def test_every_parameter_carries_a_description(document: dict) -> None:
    undescribed = [
        f"{method.upper()} {path} {parameter['name']}"
        for path, method, operation in operations(document)
        for parameter in operation.get("parameters", ())
        if not parameter.get("description")
    ]

    assert undescribed == []


def test_every_capped_parameter_declares_its_cap(document: dict) -> None:
    """SB-04 §2.3: over the cap is 422, never a silent clamp — the cap is discoverable."""
    limits = [
        parameter
        for _, _, operation in operations(document)
        for parameter in operation.get("parameters", ())
        if parameter["name"] == "limit"
    ]

    assert limits
    assert all("maximum" in parameter["schema"] for parameter in limits)


def test_every_operation_declares_its_problem_responses(document: dict) -> None:
    undeclared = [
        f"{method.upper()} {path}"
        for path, method, operation in operations(document)
        if not any(code.startswith(("4", "5")) for code in operation["responses"])
    ]

    assert undeclared == []
