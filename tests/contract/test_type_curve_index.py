"""`/v1/type-curves`: the control population, browsable by peer-ladder rung."""

from __future__ import annotations

import psycopg
from fastapi.testclient import TestClient

from glasswell.api.examples import EXAMPLE_API10
from tests.contract.conftest import OTHER_API10S

INDEX = "/v1/type-curves"
UNAVAILABLE_SUBJECT = OTHER_API10S[2]


def _page(client: TestClient, **params) -> dict:
    response = client.get(INDEX, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_the_index_rows_are_subject_instances_at_the_horizon(client: TestClient) -> None:
    body = _page(client)
    series = body["data"]["series"]
    assert body["data"]["horizon_months"] == 24
    assert EXAMPLE_API10 in series["api10"]
    assert len(series["api10"]) == len(series["fallback_level"]) == len(series["peer_count"])
    assert series["api10"] == sorted(series["api10"])
    assert body["data"]["relation"] == "control_type_curve_not_a_forecast"
    # Volumes live on the detail; the rollup states support and sends the reader there.
    assert "monthly_p50" not in series
    assert "cumulative_p50" not in series


def test_the_index_states_the_support_distribution_not_a_mean(client: TestClient) -> None:
    data = _page(client)["data"]
    assert data["_units"]["series.peer_count"] == "wells"
    assert data["_lineage"]["series.peer_count"]
    assert data["_lineage"]["series.cumulative_peer_count"]
    assert "mean" not in str(data)
    assert len(set(data["_lineage"].values())) == 2


def test_control_unavailable_subjects_appear_with_their_reasons(client: TestClient) -> None:
    series = _page(client)["data"]["series"]
    index = series["api10"].index(UNAVAILABLE_SUBJECT)
    assert series["fallback_level"][index] == "control_unavailable"
    assert series["control_unavailable_reasons"][index] == ["missing_lateral_length"]
    assert series["peer_count"][index] == 0


def test_the_fallback_level_facet_narrows_the_population(client: TestClient) -> None:
    narrowed = _page(client, fallback_level="control_unavailable")["data"]["series"]
    assert narrowed["api10"] == [UNAVAILABLE_SUBJECT]
    empty = _page(client, formation_group="spraberry")["data"]["series"]
    assert empty["api10"] == []


def test_the_cursor_pins_the_publication_and_the_facets(client: TestClient) -> None:
    first = _page(client, limit=2)
    cursor = first["meta"]["next_cursor"]
    assert cursor
    refused = client.get(INDEX, params={"limit": 2, "cursor": cursor, "stream": "gas"})
    assert refused.status_code == 422
    assert refused.json()["type"].endswith("/cursor_query_mismatch")


def test_the_second_page_is_served_and_mints_its_own_derivation(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """B-2's regression. Page two under one facet set must 200 and must not reuse page one's
    api.respond derivation: a shared id with disjoint selector evidence is a 500."""
    first = _page(client, limit=2)
    cursor = first["meta"]["next_cursor"]
    second = _page(client, limit=2, cursor=cursor)

    first_handles = set(first["data"]["_lineage"].values())
    second_handles = set(second["data"]["_lineage"].values())
    assert first["data"]["series"]["api10"] != second["data"]["series"]["api10"]
    assert first_handles.isdisjoint(second_handles)
    assert {handle.split("#")[0] for handle in first_handles} != {
        handle.split("#")[0] for handle in second_handles
    }


def test_paging_walks_the_whole_population_without_repeating(client: TestClient) -> None:
    seen: list[str] = []
    params: dict[str, object] = {"limit": 2}
    for _ in range(10):
        body = _page(client, **params)
        seen.extend(body["data"]["series"]["api10"])
        cursor = body["meta"]["next_cursor"]
        if not cursor:
            break
        params = {"limit": 2, "cursor": cursor}
    assert len(seen) == len(set(seen))
    assert set(seen) == set(_page(client, limit=200)["data"]["series"]["api10"])


def test_the_index_is_rate_limited(client: TestClient) -> None:
    from glasswell.api.routers.type_curves import TYPE_CURVE_INDEX_REQUESTS_PER_MINUTE

    for _ in range(TYPE_CURVE_INDEX_REQUESTS_PER_MINUTE):
        assert client.get(INDEX, params={"limit": 1}).status_code == 200
    exhausted = client.get(INDEX, params={"limit": 1})
    assert exhausted.status_code == 429
    assert exhausted.json()["type"].endswith("/rate_limited")


def test_the_detail_link_is_the_operation_that_carries_the_volumes(client: TestClient) -> None:
    document = client.get("/openapi.json").json()
    declaration = document["paths"][INDEX]["get"]["x-glasswell-dataset"]
    assert declaration["detail_operation"] == "get_well_type_curve"
    assert declaration["series_pointer"] == "/series"
    assert declaration["row_projection"]["axis"] == "/api10"
