"""The boundary spine's pure-function surface: member selection, field mapping, declarations.

The promotion itself is SQL and is read at the integration tier; what is checkable here is what
the loader is willing to read, what it refuses, and what the tile layers declare.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from glasswell.ingest.eia_boundaries import (
    LAYERS,
    SchemaDrift,
    _staging_row,
    boundary_members,
)
from glasswell.ingest.shapefile import ShapefileRecord
from glasswell.marts import BASIN_LAYERS, TILE_LAYERS
from glasswell.marts.tiles import tile_function_sql
from glasswell.seed.conformance_basins import BASIN_RULES, BASIN_SOURCES

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "eia_boundaries"
BASINS = FIXTURES / "SedimentaryBasins_US_EIA_cut.zip"
PLAYS = FIXTURES / "TightOil_ShaleGas_IndividualPlays_Lower48_EIA_cut.zip"

# ST_AsMVT has no numeric encoding, so a numeric column rides the wire as a string and every
# MapLibre interpolation over it silently falls back (the N-2 class).
UNENCODABLE = frozenset({"numeric", "money", "interval", "uuid"})


def _record(attributes: dict[str, object]) -> ShapefileRecord:
    from shapely.geometry import Polygon

    return ShapefileRecord(
        ordinal=0,
        attributes=attributes,
        geometry=Polygon([(0, 0), (1, 0), (1, 1), (0, 0)]),
    )


def test_the_marker_selects_boundary_members_and_leaves_the_contours_alone():
    """The play archive ships elevation and isopach contours next to the boundaries."""
    members = boundary_members(PLAYS, LAYERS["plays"].member_marker)

    assert len(members) == 5
    assert all("_Boundary" in member for member in members)
    # The publisher's own double underscore, carried rather than normalised.
    assert "ShalePlay_ThreeForks_Boundary__EIA_Aug2015_v2" in members


def test_a_single_shapefile_archive_needs_no_marker():
    assert boundary_members(BASINS, None) == ("SedimentaryBasins_US_May2011_v2",)


def test_an_archive_whose_members_no_longer_match_the_marker_is_drift_not_an_empty_load(
    tmp_path,
):
    """Silently reading nothing is how a republished archive empties a served layer."""
    archive = tmp_path / "renamed.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("ShalePlay_Bakken_Outline_EIA_2030.shp", b"")

    with pytest.raises(SchemaDrift, match="_boundary"):
        boundary_members(archive, LAYERS["plays"].member_marker)


def test_the_one_field_only_wolfcamp_publishes_is_optional_and_lands_null():
    spec = LAYERS["plays"]
    attributes = {
        "Shale_play": "Bakken", "Basin": "Williston", "Lithology": "Mixed",
        "Age_shale": "Devonian", "Source": "EIA", "Area_sq_mi": 25929.0, "Area_sq_km": 67156.0,
    }

    row, note = _staging_row(spec, "member", _record(attributes), "man_1", 0)

    assert note is None
    assert row["sub_basin"] is None
    assert row["shale_play"] == "Bakken"
    assert row["source_layer"] == "member"


def test_a_required_field_that_stops_being_published_is_drift():
    spec = LAYERS["plays"]
    attributes = {
        "Shale_play": "Bakken", "Lithology": "Mixed", "Age_shale": "Devonian",
        "Source": "EIA", "Area_sq_mi": 25929.0, "Area_sq_km": 67156.0,
    }

    with pytest.raises(SchemaDrift, match="basin"):
        _staging_row(spec, "member", _record(attributes), "man_1", 0)


def test_a_record_with_no_polygon_is_noted_rather_than_staged_as_geometry():
    from shapely.geometry import LineString

    spec = LAYERS["basins"]
    record = ShapefileRecord(
        ordinal=0,
        attributes={"NAME": "WILLISTON", "Area_sq_mi": 1.0, "Area_sq_km": 1.0},
        geometry=LineString([(0, 0), (1, 1)]),
    )

    row, note = _staging_row(spec, "member", record, "man_1", 0)

    assert row["geom_wkt"] is None
    assert note is not None
    assert "MultiPolygon" in note


def test_both_boundary_layers_are_published_and_carry_a_derivation_handle():
    names = {layer.name for layer in BASIN_LAYERS}

    assert names == {"basins", "plays"}
    assert names <= {layer.name for layer in TILE_LAYERS}
    for layer in BASIN_LAYERS:
        assert "derivation_id" in layer.columns, "a served figure with no handle is a naked one"
        assert "boundary_kind" in layer.columns, "the taxonomy rides every feature"
        assert layer.label_points, "a polygon label bound to the polygon duplicates per tile"
        assert not layer.thin, "48 features over the lower 48 is not overplot at any zoom"
        assert not layer.simplify


def test_the_published_area_rides_the_wire_as_a_number_and_names_its_basis():
    for layer in BASIN_LAYERS:
        declared = dict(layer.properties)
        assert declared["area_sq_mi"] == "float8"
        assert declared["area_sq_mi"] not in UNENCODABLE
        assert "area_basis" in declared, "an area whose provenance is unstated is EIA's or ours"


def test_the_boundary_tile_functions_keep_the_materialised_cte():
    """Inlined, the planner evaluates ST_AsMVTGeom twice per row — 5% to 40% per layer."""
    for layer in BASIN_LAYERS:
        sql = tile_function_sql(layer)
        assert sql.count("as materialized") >= 1
        assert f"marts.{layer.name}(z integer, x integer, y integer" in sql
        assert layer.source in sql


def test_every_boundary_decision_is_a_row_with_a_rationale_and_evidence():
    for rule in BASIN_RULES:
        assert rule["rationale"], f"{rule['rule_id']} states no reason it exists"
        assert rule["evidence_url"], f"{rule['rule_id']} cites nothing"
        assert rule["stage"] in ("parse", "validate", "conform", "join")


def test_every_policy_declaration_names_the_module_that_executes_it():
    for rule in BASIN_RULES:
        if rule["rule_kind"] != "code_ref":
            continue
        spec = rule["spec"]
        assert str(spec["module_function"]).startswith("glasswell.")
        assert spec["contract_note"]


def test_the_overlap_rule_refuses_a_precedence_rather_than_omitting_one():
    """Overlap is the decision; a rule that merely failed to mention it would read the same."""
    overlap = next(r for r in BASIN_RULES if r["rule_id"] == "cr_eia_boundary_overlap_1")

    assert "never dissolved" in overlap["spec"]["policy"]
    assert "never assigned a precedence order" in overlap["spec"]["policy"]
    assert overlap["spec"]["membership_is_a_set"]
    assert "unassigned" in overlap["spec"]["outside_everything"]


def test_the_membership_rule_separates_the_geometric_claim_from_the_declared_column():
    membership = next(r for r in BASIN_RULES if r["rule_id"] == "cr_eia_well_membership_1")

    assert "canonical.wells.basin" in membership["spec"]["not_the_wells_basin_column"]
    assert membership["spec"]["no_stored_membership_yet"]


def test_the_sources_record_their_terms_and_are_not_marked_redistributable():
    assert {source["source_id"] for source in BASIN_SOURCES} == {
        "eia_sedimentary_basins", "eia_shale_plays"
    }
    for source in BASIN_SOURCES:
        assert "17 U.S.C" in str(source["license_note"])
        assert source["redistributable"] is False


def test_neither_archive_is_an_arcgis_host_needing_an_allowlist_amendment():
    """Blueprint v0.6 §4E.7: a host enters ALLOWED_HOSTS by amendment, not by a code change.
    A plain zip does not go through arcgis.py, so this track needs no amendment — and this is
    the assertion that turns red if a future revision routes a boundary fetch through it."""
    from glasswell.ingest.arcgis import ALLOWED_HOSTS

    for spec in LAYERS.values():
        assert spec.url.startswith("https://www.eia.gov/")
        assert "www.eia.gov" not in ALLOWED_HOSTS


def test_the_fixture_zip_round_trips_the_publisher_s_invalid_rings():
    """The repair case is only real while the fixture still carries the defect it repairs."""
    from glasswell.ingest.shapefile import ZippedShapefile

    invalid = []
    for member in boundary_members(PLAYS, LAYERS["plays"].member_marker):
        with ZippedShapefile(PLAYS, layer_suffix=member) as layer:
            invalid += [
                record.attributes["Shale_play"]
                for record in layer
                if not record.geometry.is_valid
            ]

    assert sorted(invalid) == ["Bakken", "Three Forks"]


def test_the_fixture_prj_still_resolves_to_the_datum_the_registry_declares():
    from glasswell.ingest.shapefile import ZippedShapefile

    for archive, marker in ((BASINS, None), (PLAYS, LAYERS["plays"].member_marker)):
        for member in boundary_members(archive, marker):
            with ZippedShapefile(archive, layer_suffix=member) as layer:
                assert layer.source_epsg == 4326

