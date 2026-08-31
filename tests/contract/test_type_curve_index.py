"""`/v1/type-curves`: the control population, browsable by peer-ladder rung."""

from __future__ import annotations

import base64
import json

import psycopg
import pytest
from fastapi.testclient import TestClient

from glasswell.api.examples import EXAMPLE_API10
from tests.contract.conftest import (
    OTHER_API10S,
    as_principal,
    issue_key,
    spend_rate_window,
)

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


def test_the_second_page_is_served_and_mints_its_own_derivation(client: TestClient) -> None:
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


def _instances(body: dict) -> list[tuple[str, str]]:
    """A row is (subject, origin). A set of api10s hides a dropped duplicate-subject row."""
    series = body["data"]["series"]
    return list(zip(series["api10"], series["origin"], strict=True))


def test_the_population_holds_a_subject_at_two_origins(client: TestClient) -> None:
    """The precondition M-1 needs to be falsifiable: without it no boundary lands mid-subject."""
    instances = _instances(_page(client, limit=200))
    subjects = [api10 for api10, _ in instances]
    repeated = {api10 for api10 in subjects if subjects.count(api10) > 1}

    assert repeated, "no subject appears at two origins, so paging cannot be tested"
    assert len(instances) == len(set(instances))


def test_paging_walks_the_whole_population_without_repeating(client: TestClient) -> None:
    """Compared as (api10, origin) pairs in order, not as a set of api10s: a row lost at a
    page boundary inside a multi-origin subject is invisible to a set comparison."""
    whole = _instances(_page(client, limit=200))
    seen: list[tuple[str, str]] = []
    params: dict[str, object] = {"limit": 2}
    for _ in range(20):
        body = _page(client, **params)
        seen.extend(_instances(body))
        cursor = body["meta"]["next_cursor"]
        if not cursor:
            break
        params = {"limit": 2, "cursor": cursor}

    assert len(seen) == len(set(seen))
    assert seen == whole


def test_paging_at_every_limit_reaches_the_whole_population(client: TestClient) -> None:
    """A boundary that lands mid-subject only exists at some limits, so sweep them.

    On its own principal: the sweep costs `1 + sum(ceil(N/L))` requests against an endpoint
    capped at 30 a minute, which is 25 at today's N and would 429 at N+1. A test whose cost
    grows with the fixture and whose budget does not is a test that fails on the day someone
    adds a subject, for a reason that has nothing to do with what it asserts.
    """
    sweeper = as_principal(client, issue_key(client, label="qa-typecurve-sweep", scope="guest"))
    whole = _instances(_page(sweeper, limit=200))
    for limit in range(1, len(whole) + 1):
        seen: list[tuple[str, str]] = []
        params: dict[str, object] = {"limit": limit}
        for _ in range(len(whole) + 2):
            body = _page(sweeper, **params)
            seen.extend(_instances(body))
            cursor = body["meta"]["next_cursor"]
            if not cursor:
                break
            params = {"limit": limit, "cursor": cursor}
        assert seen == whole, f"rows lost or repeated at limit={limit}"


@pytest.mark.parametrize(
    ("tiebreak", "detail"),
    [("not-a-date", "is not an ISO-8601 date"), ("", "carries no origin")],
)
def test_a_forged_cursor_tiebreak_is_a_malformed_cursor_not_a_500(
    client: TestClient, tiebreak: str, detail: str
) -> None:
    """Cursors are unsigned base64 JSON and the fingerprint is an unkeyed sha256, so any caller
    can mint one. This is the only site in the codebase that parses a tiebreak, and a malformed
    input from a caller is never a 500."""
    first = _page(client, limit=2)
    forged = _reissue(first["meta"]["next_cursor"], tiebreak)

    response = client.get(INDEX, params={"limit": 2, "cursor": forged})

    assert response.status_code == 422
    assert response.json()["type"].endswith("/cursor_malformed")
    assert detail in response.json()["detail"]


def _reissue(cursor: str, tiebreak: str) -> str:
    """Re-mint a cursor with one field replaced, the way an attacker would."""
    padded = cursor + "=" * (-len(cursor) % 4)
    payload = json.loads(base64.urlsafe_b64decode(padded.encode()))
    payload["t"] = tiebreak
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")


@pytest.mark.parametrize("facet", ["fallback_level", "formation_group"])
def test_an_empty_facet_value_is_an_unset_filter_not_a_second_identity(
    client: TestClient, facet: str
) -> None:
    """The B-2 regression. `?fallback_level=` binds to "", which is falsy but not None. Guarded
    on truthiness in the partition and on `is not None` in the filter, it minted one derivation
    id for two different pages — and derivation rows are immutable, so the first collision
    poisoned the default page permanently with an unhandled DeterminismViolation."""
    plain = _page(client, stream="oil")
    empty = _page(client, stream="oil", **{facet: ""})
    replay = _page(client, stream="oil")

    assert empty["data"]["series"] == plain["data"]["series"]
    assert empty["data"]["_lineage"] == plain["data"]["_lineage"]
    assert replay["data"]["_lineage"] == plain["data"]["_lineage"]


def test_an_empty_facet_value_does_not_poison_a_later_page(client: TestClient) -> None:
    """The persistence half: the collision was recorded, so a replay had to 500 for ever."""
    first = _page(client, stream="oil", limit=2, fallback_level="")
    cursor = first["meta"]["next_cursor"]
    assert cursor
    assert _page(client, stream="oil", limit=2, cursor=cursor)["data"]["series"]["api10"]
    assert _page(client, stream="oil", limit=2)["data"]["series"] == first["data"]["series"]


def test_the_index_is_rate_limited(client: TestClient, seeded: psycopg.Connection) -> None:
    """The ceiling is the shipped constant: one under it serves, at it refuses.

    Both edges are asserted against `TYPE_CURVE_INDEX_REQUESTS_PER_MINUTE` rather than walked
    to, because the window is a truncated UTC minute -- a loop long enough to reach the limit
    is a loop long enough to cross a boundary, and past one the counter has reset and the
    refusal never comes. The opening request is what writes the row the two edges move.
    """
    from glasswell.api.routers.type_curves import TYPE_CURVE_INDEX_REQUESTS_PER_MINUTE

    assert client.get(INDEX, params={"limit": 1}).status_code == 200

    spend_rate_window(
        seeded, operation="list_type_curves", count=TYPE_CURVE_INDEX_REQUESTS_PER_MINUTE - 1
    )
    assert client.get(INDEX, params={"limit": 1}).status_code == 200, (
        "the index refused a request below its limit"
    )

    spend_rate_window(
        seeded, operation="list_type_curves", count=TYPE_CURVE_INDEX_REQUESTS_PER_MINUTE
    )
    exhausted = client.get(INDEX, params={"limit": 1})

    assert exhausted.status_code == 429
    assert exhausted.json()["type"].endswith("/rate_limited")


def test_the_detail_link_is_the_operation_that_carries_the_volumes(client: TestClient) -> None:
    document = client.get("/openapi.json").json()
    declaration = document["paths"][INDEX]["get"]["x-glasswell-dataset"]
    assert declaration["detail_operation"] == "get_well_type_curve"
    assert declaration["series_pointer"] == "/series"
    assert declaration["row_projection"]["axis"] == "/api10"
