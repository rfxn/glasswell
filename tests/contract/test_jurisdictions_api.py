"""`GET /v1/jurisdictions`: the registry as a served collection.

Four registrations, every figure with a handle that resolves, and two clocks the caller can
move independently. The counts are deliberately partial — North Dakota and Texas measured, New
Mexico and Montana registered and not — because "not measured yet" and "zero wells" are
different facts and only one of them is true here.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from glasswell.seed.jurisdictions import JURISDICTIONS, REGISTERED_ON
from tests.contract.conftest import JURISDICTION_MEASURED_ON, ND_MEASURED
from tests.support.jurisdictions import restate

pytestmark = pytest.mark.contract

PATH = "/v1/jurisdictions"


def body(client: TestClient, **params: Any) -> dict[str, Any]:
    response = client.get(PATH, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def refused(client: TestClient, **params: Any) -> dict[str, Any]:
    response = client.get(PATH, params=params)
    assert response.status_code >= 400, response.text
    return response.json()


@pytest.fixture(autouse=True)
def _uncached() -> None:
    from glasswell.lineage.jurisdictions import clear_jurisdiction_cache

    clear_jurisdiction_cache()


def test_it_serves_every_registration_as_a_bare_array_in_code_order(client: TestClient) -> None:
    envelope = body(client)
    data = envelope["data"]

    assert isinstance(data, list)
    assert [row["jurisdiction_code"] for row in data] == ["MT", "ND", "NM", "TX"]
    assert len(data) == len(JURISDICTIONS)
    assert envelope["links"]["self"] == PATH


def test_a_row_carries_the_regulator_the_identity_and_the_capabilities(
    client: TestClient,
) -> None:
    row = next(item for item in body(client)["data"] if item["jurisdiction_code"] == "ND")

    assert row["name"] == "North Dakota"
    assert row["level"] == "state"
    assert row["regulator"]["name"].startswith("ND Dept. of Mineral Resources")
    assert row["regulator"]["url"].startswith("https://")
    assert row["identity"] == {
        "scheme": "api10",
        "prefix": "33",
        "pattern": "^33[0-9]{8}$",
        "is_unique": True,
    }
    assert row["capabilities"] == {
        "neighbors": True,
        "land_grid_state": True,
        "land_grid_scope": True,
    }
    assert row["map"] == {"wells_tile_layer_id": "nd_wells", "colour": "#3FA55E"}
    assert row["liquids_basis"] == "oil+condensate"
    assert row["effective_from"] == REGISTERED_ON.isoformat()
    assert row["published_at"] == REGISTERED_ON.isoformat()


def test_montanas_two_inventory_rules_are_both_visible_and_one_serves(
    client: TestClient,
) -> None:
    """An array of decisions rather than a column per decision is what makes this expressible:
    a scalar `inventory_rule_id` would have had to pick one and say nothing about the other."""
    row = next(item for item in body(client)["data"] if item["jurisdiction_code"] == "MT")
    inventory = [
        rule for rule in row["rules"] if rule["decision"] == "inventory_jurisdiction"
    ]

    assert sorted(rule["rule_id"] for rule in inventory) == [
        "cr_mt_inventory_jurisdiction_1",
        "cr_mt_pru_inventory_jurisdiction_1",
    ]
    assert [rule["serving"] for rule in sorted(inventory, key=lambda r: r["rule_id"])] == [
        True,
        False,
    ]
    assert next(rule for rule in inventory if not rule["serving"])["note"] == "PRU lease grain"


def test_texas_registers_no_geometry_provenance_decision_and_says_so_by_omission(
    client: TestClient,
) -> None:
    row = next(item for item in body(client)["data"] if item["jurisdiction_code"] == "TX")

    assert all(rule["decision"] != "geometry_provenance" for rule in row["rules"])
    assert row["liquids_basis"] is None


def test_every_rule_it_names_resolves_at_the_conformance_route(client: TestClient) -> None:
    """A registry that cites a rule nobody can read is a citation to nothing."""
    named = {rule["rule_id"] for row in body(client)["data"] for rule in row["rules"]}

    assert named
    for rule_id in sorted(named):
        assert client.get(f"/v1/conformance/{rule_id}").status_code == 200, rule_id


def test_a_measured_count_is_a_figure_with_a_handle_and_a_date(client: TestClient) -> None:
    row = next(item for item in body(client)["data"] if item["jurisdiction_code"] == "ND")

    assert row["measured_on"] == JURISDICTION_MEASURED_ON.isoformat()
    assert row["well_count"]["value"] == str(ND_MEASURED[None])
    assert row["well_count"]["unit"] == "wells"
    assert row["well_count"]["d"].endswith("#jurisdiction=ND")
    by_status = {item["status_canonical"]: item for item in row["well_counts_by_status"]}
    assert set(by_status) == {"active", "plugged"}
    assert by_status["active"]["wells"]["value"] == str(ND_MEASURED["active"])
    assert by_status["active"]["wells"]["d"].endswith("#jurisdiction=ND&status=active")


def test_an_unmeasured_jurisdiction_serves_no_count_rather_than_a_zero(
    client: TestClient,
) -> None:
    """R-3. A zero here would say Montana holds no wells, which is a claim nothing measured."""
    row = next(item for item in body(client)["data"] if item["jurisdiction_code"] == "MT")

    assert row["well_count"] is None
    assert row["well_counts_by_status"] == []
    assert row["measured_on"] is None


def test_explain_resolves_a_count_to_the_manifest_the_file_arrived_in(
    client: TestClient,
) -> None:
    """No naked numbers, end to end: the count's handle walks to a government file."""
    envelope = body(client, explain="true", explain_depth=3)
    inlined = envelope["_explain"]

    row = next(item for item in envelope["data"] if item["jurisdiction_code"] == "ND")
    handle = row["well_count"]["d"]
    assert handle in inlined, envelope["meta"]["warnings"]
    chain = inlined[handle]
    assert chain["terminals"], chain
    assert all(terminal.startswith("man_") for terminal in chain["terminals"])
    assert chain["truncated"] is False
    assert not [
        item for item in envelope["meta"]["warnings"] if item["code"].startswith("explain_")
    ]


def test_the_level_filter_narrows_to_the_registrations_at_that_level(
    client: TestClient,
) -> None:
    assert len(body(client, level="state")["data"]) == len(JURISDICTIONS)
    assert body(client, level="province")["data"] == []


def test_the_page_is_a_page_and_its_cursor_walks_the_rest(client: TestClient) -> None:
    first = body(client, limit=2)

    assert [row["jurisdiction_code"] for row in first["data"]] == ["MT", "ND"]
    assert first["meta"]["next_cursor"]
    second = body(client, limit=2, cursor=first["meta"]["next_cursor"])
    assert [row["jurisdiction_code"] for row in second["data"]] == ["NM", "TX"]
    assert second["meta"]["next_cursor"] is None


def test_a_registration_published_after_the_cut_is_not_served_under_it(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """B-6 on the wire. `as_of` is the knowledge cut, which is exactly what a static
    current-state view could not have honoured."""
    corrected = "https://www.dmr.nd.gov/oilgas/"
    restate(seeded, "ND", regulator_url=corrected)
    later = REGISTERED_ON + timedelta(days=1)

    before = body(client, as_of=REGISTERED_ON.isoformat())
    after = body(client, as_of=later.isoformat())

    assert next(r for r in before["data"] if r["jurisdiction_code"] == "ND")["regulator"][
        "url"
    ].endswith("mprindex.asp")
    restated = next(r for r in after["data"] if r["jurisdiction_code"] == "ND")
    assert restated["regulator"]["url"] == corrected
    assert restated["published_at"] == later.isoformat()
    assert restated["effective_from"] == REGISTERED_ON.isoformat()


def test_a_cut_before_the_first_registration_is_out_of_range_not_an_empty_page(
    client: TestClient,
) -> None:
    """An empty array would read as "glasswell serves no jurisdictions", which is false."""
    problem = refused(client, as_of=(REGISTERED_ON - timedelta(days=1)).isoformat())

    assert problem["status"] == 422
    assert problem["type"].endswith("as_of_out_of_range")


def test_a_cursor_minted_against_another_cut_is_refused(client: TestClient) -> None:
    minted = body(client, limit=2)["meta"]["next_cursor"]

    problem = refused(client, limit=2, cursor=minted, as_of=REGISTERED_ON.isoformat())

    assert problem["type"].endswith("cursor_query_mismatch")


def test_a_malformed_cursor_is_refused(client: TestClient) -> None:
    problem = refused(client, cursor="not-a-cursor")

    assert problem["type"].endswith("cursor_malformed")
