"""SB-04 §2.3 / M17: opaque cursors over a total order, and no offset anywhere."""

from __future__ import annotations

import base64
import json

import pytest
from fastapi.testclient import TestClient

from glasswell.api.errors import TYPE_BASE
from glasswell.api.pagination import DEFAULT_LIMIT, SPINE_LIMIT_CAP, WELLS_LIMIT_CAP

SPINE_COLLECTIONS = ("/v1/manifests", "/v1/quarantine", "/v1/conformance", "/v1/glossary")


def decode(cursor: str) -> dict:
    padded = cursor + "=" * (-len(cursor) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


def test_the_cursor_carries_the_four_declared_fields(client: TestClient) -> None:
    cursor = client.get("/v1/wells", params={"limit": 2}).json()["meta"]["next_cursor"]

    assert set(decode(cursor)) == {"k", "t", "v", "q"}


def test_paginating_twice_yields_the_same_order(client: TestClient) -> None:
    def traverse() -> list[str]:
        seen: list[str] = []
        cursor = None
        while True:
            params = {"limit": 2} | ({"cursor": cursor} if cursor else {})
            body = client.get("/v1/wells", params=params).json()
            seen.extend(item["api10"] for item in body["data"])
            cursor = body["meta"]["next_cursor"]
            if cursor is None:
                return seen

    first = traverse()

    assert first == traverse()
    assert len(first) == len(set(first))
    assert first == sorted(first)


def test_the_last_page_closes_the_traversal(client: TestClient) -> None:
    body = client.get("/v1/wells", params={"limit": 100}).json()

    assert body["meta"]["next_cursor"] is None


def test_a_cursor_presented_against_different_filters_is_refused(client: TestClient) -> None:
    cursor = client.get("/v1/wells", params={"limit": 2}).json()["meta"]["next_cursor"]

    response = client.get("/v1/wells", params={"limit": 2, "cursor": cursor, "status": "active"})

    assert response.status_code == 422
    assert response.json()["type"] == f"{TYPE_BASE}/cursor_query_mismatch"


def test_the_well_type_filter_cannot_rescope_a_page_mid_traversal(client: TestClient) -> None:
    """F-3, replayed for R-1: a filter that escapes the cursor fingerprint lets a client open
    a page under one population and continue it under another. Both directions must refuse,
    and the served next link must carry the filter it was minted under."""
    unfiltered = client.get("/v1/wells", params={"limit": 2}).json()
    filtered = client.get("/v1/wells", params={"limit": 2, "well_type": "OG"}).json()

    added = client.get(
        "/v1/wells",
        params={"limit": 2, "cursor": unfiltered["meta"]["next_cursor"], "well_type": "OG"},
    )
    dropped = client.get(
        "/v1/wells", params={"limit": 2, "cursor": filtered["meta"]["next_cursor"]}
    )

    assert added.status_code == 422
    assert added.json()["type"] == f"{TYPE_BASE}/cursor_query_mismatch"
    assert dropped.status_code == 422
    assert dropped.json()["type"] == f"{TYPE_BASE}/cursor_query_mismatch"
    assert "well_type=OG" in filtered["links"]["next"]


def test_the_provenance_filter_cannot_rescope_a_page_mid_traversal(client: TestClient) -> None:
    """F-3, replayed a third time for the m13 residual: both refusal directions, and the
    served next link carries the filter the cursor was minted under."""
    unfiltered = client.get("/v1/wells", params={"limit": 2}).json()
    filtered = client.get(
        "/v1/wells", params={"limit": 1, "geometry_provenance": "surface"}
    ).json()

    added = client.get(
        "/v1/wells",
        params={
            "limit": 2,
            "cursor": unfiltered["meta"]["next_cursor"],
            "geometry_provenance": "surface",
        },
    )
    dropped = client.get(
        "/v1/wells", params={"limit": 1, "cursor": filtered["meta"]["next_cursor"]}
    )

    assert added.status_code == 422
    assert added.json()["type"] == f"{TYPE_BASE}/cursor_query_mismatch"
    assert dropped.status_code == 422
    assert dropped.json()["type"] == f"{TYPE_BASE}/cursor_query_mismatch"
    assert "geometry_provenance=surface" in filtered["links"]["next"]


def test_a_corrupt_cursor_is_refused(client: TestClient) -> None:
    response = client.get("/v1/wells", params={"cursor": "not-a-cursor"})

    assert response.status_code == 422
    assert response.json()["type"] == f"{TYPE_BASE}/cursor_malformed"


def test_a_structurally_wrong_cursor_is_refused(client: TestClient) -> None:
    forged = base64.urlsafe_b64encode(json.dumps({"k": "x", "extra": 1}).encode()).decode()

    response = client.get("/v1/wells", params={"cursor": forged.rstrip("=")})

    assert response.status_code == 422
    assert response.json()["type"] == f"{TYPE_BASE}/cursor_malformed"


def test_no_offset_parameter_exists_anywhere(client: TestClient) -> None:
    document = client.get("/openapi.json").json()

    names = {
        parameter["name"]
        for item in document["paths"].values()
        for operation in item.values()
        if isinstance(operation, dict)
        for parameter in operation.get("parameters", ())
    }

    assert "offset" not in names
    assert "page" not in names


def test_the_default_limit_is_declared(client: TestClient) -> None:
    document = client.get("/openapi.json").json()
    limits = [
        parameter
        for item in document["paths"].values()
        for operation in item.values()
        if isinstance(operation, dict)
        for parameter in operation.get("parameters", ())
        if parameter["name"] == "limit"
    ]

    assert all(parameter["schema"].get("default") == DEFAULT_LIMIT for parameter in limits)


@pytest.mark.parametrize("path", SPINE_COLLECTIONS)
def test_spine_collections_cap_at_two_hundred(client: TestClient, path: str) -> None:
    """§10 E-16: the spine's own collections are cheaper to cap now than after the freeze."""
    assert client.get(path, params={"limit": SPINE_LIMIT_CAP}).status_code == 200

    response = client.get(path, params={"limit": SPINE_LIMIT_CAP + 1})

    assert response.status_code == 422
    assert response.json()["type"] == f"{TYPE_BASE}/validation_failed"


def test_the_wells_collection_caps_at_a_thousand(client: TestClient) -> None:
    assert client.get("/v1/wells", params={"limit": WELLS_LIMIT_CAP}).status_code == 200
    assert client.get("/v1/wells", params={"limit": WELLS_LIMIT_CAP + 1}).status_code == 422
