"""Every served Montana figure carries the rule that shaped it.

Stage 5. Montana reached canonical in v0.69 and reached nothing a reader could see; this file
is about what has to be true at the instant it does. The state has a status codebook, unlike
New Mexico, so its wells are classed and the vocabulary handle must be Montana's own. Its
geometry is a cartographic centreline, so the provenance handle must be the row that says so
rather than North Dakota's survey-derived default — which is what the fallback would have
served, dormant while nothing Montana was drawn and wrong the moment it is.

The North Dakota, Texas and New Mexico equivalents are asserted here too: a lookup that gained
a fourth key is exactly where a regression hides.
"""

from __future__ import annotations

from datetime import date

import psycopg
import pytest
from fastapi.testclient import TestClient

from glasswell.api.examples import EXAMPLE_API10
from tests.contract.conftest import TX_API10
from tests.support.jurisdictions import declared_rule, declared_rule_ids, registration
from tests.support.seed import seed_well, seed_well_spatial

MT_API10 = "2508321001"
MT_SURFACE = "POINT(-104.6000 47.8000)"
MT_PATH = "LINESTRING(-104.6000 47.8000, -104.5800 47.8100)"
MT_BBOX = "-105.0,47.5,-104.0,48.2"


@pytest.fixture
def with_montana(seeded: psycopg.Connection, client: TestClient) -> TestClient:
    """One Montana well beside the fixture's other states, shaped like the real load: a mapped
    status, no basin, no spud date, and a path keyed on its WellSub."""
    seed_well(
        seeded,
        api10=MT_API10,
        state_code="25",
        status_canonical="plugged",
        status_reported="P&A - Approved",
        well_type_reported="Dry Hole",
        operator_name_reported="CONTINENTAL RESOURCES INC",
        completion_date=date(2011, 7, 14),
        spud_date=None,
        basin=None,
    )
    seed_well_spatial(
        seeded,
        api10=MT_API10,
        geom_type="surface",
        wkt=MT_SURFACE,
        transform_rule_id="cr_mt_gis_datum_1",
    )
    seed_well_spatial(
        seeded,
        api10=MT_API10,
        geom_type="lateral",
        geom_key="LT01",
        wkt=MT_PATH,
        transform_rule_id="cr_mt_paths_datum_1",
    )
    seeded.commit()
    return client


def body(client: TestClient, path: str, **parameters: str) -> dict:
    response = client.get(path, params=parameters)
    assert response.status_code == 200, response.text
    return response.json()


def test_the_status_summary_cites_montanas_vocabulary_rule(with_montana: TestClient) -> None:
    envelope = body(with_montana, "/v1/wells/status-summary", bbox=MT_BBOX)

    assert envelope["data"]["wells"]
    assert (
        envelope["links"]["cr_mt_gis_status_vocab_1"]
        == "/v1/conformance/cr_mt_gis_status_vocab_1"
    )
    assert "cr_nd_status_vocab_1" not in envelope["links"]


def test_the_geometry_provenance_rule_is_montanas_and_not_north_dakotas(
    with_montana: TestClient,
) -> None:
    """A Montana path is a map stick. Serving it under cr_nd_geometry_provenance_1 would attach
    a survey-derived classing rule to geometry cr_mt_paths_geometry_class_1 says is not one."""
    envelope = body(with_montana, "/v1/wells/status-summary", bbox=MT_BBOX)

    assert envelope["data"]["geometry_provenance"]
    assert (
        envelope["links"]["cr_mt_paths_geometry_class_1"]
        == "/v1/conformance/cr_mt_paths_geometry_class_1"
    )
    assert "cr_nd_geometry_provenance_1" not in envelope["links"]


def test_every_registered_provenance_rule_resolves(client: TestClient) -> None:
    for rule_id in sorted(declared_rule_ids("geometry_provenance")):
        assert client.get(f"/v1/conformance/{rule_id}").status_code == 200, rule_id


def test_every_registered_status_vocabulary_rule_resolves(client: TestClient) -> None:
    for rule_id in sorted(declared_rule_ids("status_vocabulary")):
        assert client.get(f"/v1/conformance/{rule_id}").status_code == 200, rule_id


def test_the_well_card_serves_montana_without_a_basin(with_montana: TestClient) -> None:
    """cr_mt_basin_scope_1 all the way to the wire: a `williston` here is what would draw a
    Madison well into the type-curve peer ladder."""
    data = body(with_montana, f"/v1/wells/{MT_API10}")["data"]

    assert data["state_code"] == "25"
    assert data["basin"] is None
    assert data["status_canonical"] == "plugged"
    assert data["status_reported"] == "P&A - Approved"


def test_the_well_card_serves_no_spud_date_for_montana(with_montana: TestClient) -> None:
    """MBOGC files a completion date and no spud; the card may not invent one."""
    data = body(with_montana, f"/v1/wells/{MT_API10}")["data"]

    assert data["spud_date"] is None
    assert data["completion_date"] == "2011-07-14"


def test_the_montana_length_is_withheld_and_the_rule_is_served_in_its_place(
    with_montana: TestClient,
) -> None:
    """Without this the card served 6,120.87 ft under nd_gis_horizontals_line's rule: a Montana
    figure whose handle resolves to a rule about North Dakota geometry, summed across paths
    cr_mt_paths_subkey_1 measured as multiple per well."""
    envelope = body(with_montana, f"/v1/wells/{MT_API10}")
    data = envelope["data"]

    assert data["lateral_count"] == 1
    assert data["lateral_length_ft"] is None
    assert data["length_method"] == "not_served"
    assert data["compute_crs"] is None
    assert envelope["links"]["length_rule"] == "/v1/conformance/cr_mt_paths_length_scope_2"
    withheld = [
        warning
        for warning in envelope["meta"]["warnings"]
        if warning["code"] == "length_not_served"
    ]
    assert withheld == [
        {
            "code": "length_not_served",
            "detail": (
                "1 geometries are held for this well and no length is served for them;"
                " cr_mt_paths_length_scope_2 is the rule that withholds it"
            ),
            "pointer": "/lateral_length_ft",
            "rule_id": "cr_mt_paths_length_scope_2",
        }
    ]


def test_the_withholding_rule_is_registered_and_resolves(client: TestClient) -> None:
    response = client.get("/v1/conformance/cr_mt_paths_length_scope_2")

    assert response.status_code == 200
    rule = response.json()["data"]
    assert rule["spec"]["length_method"] == "not_served"
    assert rule["spec"]["basin_assigned"] is None
    assert rule["rationale"]


def test_the_north_dakota_length_is_still_served_under_its_own_rule(client: TestClient) -> None:
    """The regression half of the withholding: a per-state table is where a global one hides."""
    data = body(client, f"/v1/wells/{EXAMPLE_API10}")["data"]

    assert data["length_method"] == "geodesic"
    assert data["compute_crs"] == "EPSG:4326"
    assert declared_rule("33", "length_scope") is None


def test_a_montana_well_offers_the_neighbour_link_the_repaired_mart_supports(
    with_montana: TestClient,
) -> None:
    """The v0.69 border repair made Montana a neighbour-mart state; the link is how a reader
    reaches it."""
    envelope = body(with_montana, f"/v1/wells/{MT_API10}")

    assert registration("25")["neighbors_available"] is True
    assert envelope["links"]["neighbors"] == f"/v1/wells/{MT_API10}/neighbors"


def test_the_other_states_lookups_are_unchanged(client: TestClient) -> None:
    """The regression half. A fourth key in a lookup is where the first three get lost."""
    assert body(client, f"/v1/wells/{EXAMPLE_API10}")["data"]["state_code"] == "33"
    assert body(client, f"/v1/wells/{TX_API10}")["data"]["state_code"] == "42"
    assert declared_rule("33", "status_vocabulary") == "cr_nd_status_vocab_1"
    assert declared_rule("42", "status_vocabulary") == "cr_tx_status_vocab_1"
    assert declared_rule("30", "status_vocabulary") == "cr_nm_wellhistory_status_vocab_2"
    assert declared_rule("33", "geometry_provenance") == "cr_nd_geometry_provenance_1"
    # No longer North Dakota's, and no longer absent either: R-4 asked Texas for its own and
    # the v0.80 supersession registers it. The property this line holds is the one it always
    # held -- a rule Texas cites is a rule about Texas (gate-tx H-4).
    assert declared_rule("42", "geometry_provenance") == "cr_tx_geometry_provenance_1"
    assert declared_rule("42", "geometry_provenance") != declared_rule(
        "33", "geometry_provenance"
    )
    assert (
        declared_rule("30", "geometry_provenance")
        == "cr_nm_wellhistory_geometry_provenance_1"
    )


def test_montana_is_registered_in_both_lookups_rather_than_falling_back(
    client: TestClient,
) -> None:
    """The failure this file exists to close, stated as a property of the registrations."""
    assert declared_rule("25", "status_vocabulary") == "cr_mt_gis_status_vocab_1"
    assert declared_rule("25", "geometry_provenance") == "cr_mt_paths_geometry_class_1"
    assert declared_rule("25", "geometry_provenance") != declared_rule(
        "33", "geometry_provenance"
    )
    assert declared_rule("25", "length_scope") == "cr_mt_paths_length_scope_2"


def test_the_withholding_rule_is_true_on_completions_as_well_as_on_the_well_card(
    with_montana: TestClient, seeded: psycopg.Connection
) -> None:
    """cr_mt_paths_length_scope_2 asserts lateral_length_ft is null for every Montana well.
    That was true on /v1/wells and false on /completions, which called the length resolver
    unconditionally: `_LATERALS` matches on geom_type = 'lateral' and the Montana mart stores
    its paths as laterals, so any Montana well with a FracFocus disclosure was served a length
    computed under cr_nd_compute_crs and an intensity divided by it."""
    with seeded.cursor() as cursor:
        cursor.execute(
            "insert into canonical.well_completion_design (disclosure_id, api10,"
            " base_water_volume, base_water_unit, base_water_null_semantics, source_id,"
            " report_vintage, source_manifest_id, derivation_id)"
            " select 'ff-montana-0001', %s, 9000000, 'gal', 'reported', 'fracfocus_csv',"
            "        report_vintage, source_manifest_id, derivation_id"
            "   from canonical.well_completion_design limit 1",
            (MT_API10,),
        )
    seeded.commit()

    envelope = with_montana.get(f"/v1/wells/{MT_API10}/completions").json()
    design = envelope["data"]["design"]

    assert design["lateral_length_ft"] is None
    assert design["fluid_intensity"] is None
    assert design["intensity_null_semantics"] == "lateral_length_unavailable"
    withheld = [
        warning
        for warning in envelope["meta"]["warnings"]
        if warning["code"] == "length_not_served"
    ]
    assert [warning["rule_id"] for warning in withheld] == ["cr_mt_paths_length_scope_2"]
    assert withheld[0]["pointer"] == "/design/lateral_length_ft"


def test_an_unregistered_basin_is_a_registry_gap_on_completions_and_not_a_withheld_figure(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """The other half of M-3: two ways for a length to be absent, told apart on the wire."""
    api10 = "3001577003"
    seed_well(seeded, api10=api10, state_code="30", basin=None, spud_date=None)
    seed_well_spatial(seeded, api10=api10, geom_type="lateral")
    with seeded.cursor() as cursor:
        cursor.execute(
            "insert into canonical.well_completion_design (disclosure_id, api10,"
            " base_water_volume, base_water_unit, base_water_null_semantics, source_id,"
            " report_vintage, source_manifest_id, derivation_id)"
            " select 'ff-newmexico-0001', %s, 9000000, 'gal', 'reported', 'fracfocus_csv',"
            "        report_vintage, source_manifest_id, derivation_id"
            "   from canonical.well_completion_design limit 1",
            (api10,),
        )
    seeded.commit()

    envelope = client.get(f"/v1/wells/{api10}/completions").json()
    design = envelope["data"]["design"]

    assert design["lateral_length_ft"] is None
    assert design["intensity_null_semantics"] == "lateral_length_unavailable"
    gaps = [
        warning
        for warning in envelope["meta"]["warnings"]
        if warning["code"] == "length_scope_unregistered"
    ]
    assert len(gaps) == 1
    assert "rule_id" not in gaps[0]
