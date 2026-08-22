"""M2-3: observed rollups on the land grid, membership by cr_land_agg_membership_1.

The geometry is arranged so the membership decision is what the assertions read: one
horizontal well whose surface hole and lateral midpoint sit in different sections, one
vertical whose surface hole is the answer, one well with nothing observed, one off-grid.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest

from glasswell.lineage.capture import lineage_session
from glasswell.lineage.store import PostgresRecorder
from glasswell.marts.land_metrics import refresh_land_metrics
from glasswell.marts.land_units import refresh_land_units
from glasswell.seed import seed_all
from tests.integration.test_blm_plss_load import load_all
from tests.integration.test_marts_nd import covering_tile, extent_of, rows, scalar
from tests.support.mvt import attribute_keys, attribute_values, feature_count, layer_name, layers
from tests.support.seed import (
    seed_derivation,
    seed_manifest,
    seed_production,
    seed_well,
    seed_well_spatial,
)

# Fixture grid geography (tests/fixtures/blm_plss): T152N R95W sections 36 and 13, and
# T153N R95W sections 36 and 13.
SECTION_A = "ND051520N0950W0SN360"  # holds the pad and the vertical
SECTION_B = "ND051520N0950W0SN130"  # holds the horizontal's lateral midpoint
SECTION_Z = "ND051530N0950W0SN360"  # holds a well with nothing observed
TOWNSHIP_152 = "ND051520N0950W0"
TOWNSHIP_153 = "ND051530N0950W0"

HORIZONTAL = "3305399001"
VERTICAL = "3305399002"
UNPRODUCED = "3305399003"
OFF_GRID = "3305399004"

# Surface in section A (y 47.940), toe two sections north: the arc-length midpoint lands at
# y 47.985, inside section B — the divergent case the membership rule exists for.
HORIZONTAL_SURFACE = "POINT(-102.7850 47.9400)"
HORIZONTAL_LATERAL = "LINESTRING(-102.7850 47.9400, -102.7850 48.0300)"
VERTICAL_SURFACE = "POINT(-102.7800 47.9420)"
UNPRODUCED_SURFACE = "POINT(-102.8390 48.0310)"
OFF_GRID_SURFACE = "POINT(-103.5000 47.5000)"

MONTH = date(2024, 1, 1)
VINTAGE = date(2024, 3, 14)

METRIC_KEYS = {
    "land_unit_id", "unit_type", "plssid", "label", "well_count", "prod_well_count",
    "liquid_cum_bbl", "gas_cum_mcf", "water_cum_bbl", "liquid_bin", "bin_edges",
    "bin_population", "derivation_id",
}


@pytest.fixture
def gridded(db, raw_root, lineage_env):
    seed_all(db)
    db.commit()
    load_all(db, raw_root, lineage_env)

    for api10, surface in (
        (HORIZONTAL, HORIZONTAL_SURFACE),
        (VERTICAL, VERTICAL_SURFACE),
        (UNPRODUCED, UNPRODUCED_SURFACE),
        (OFF_GRID, OFF_GRID_SURFACE),
    ):
        seed_well(db, api10=api10)
        seed_well_spatial(db, api10=api10, geom_type="surface", wkt=surface)
    seed_well_spatial(db, api10=HORIZONTAL, geom_type="lateral", wkt=HORIZONTAL_LATERAL)

    manifest_id = seed_manifest(db, sha256="f" * 64)
    derivation_id = seed_derivation(db)
    production = (
        (HORIZONTAL, "oil", MONTH, Decimal("1000")),
        (HORIZONTAL, "oil", date(2024, 2, 1), Decimal("500")),
        (HORIZONTAL, "gas", MONTH, Decimal("3000")),
        (VERTICAL, "oil", MONTH, Decimal("200")),
        (VERTICAL, "water", MONTH, Decimal("100")),
    )
    for api10, stream, month, volume in production:
        seed_production(
            db,
            api10=api10,
            production_month=month,
            report_vintage=VINTAGE,
            volume=volume,
            stream=stream,
            manifest_id=manifest_id,
            derivation_id=derivation_id,
        )
    db.commit()

    with lineage_session(recorder=PostgresRecorder(db), environment=lineage_env):
        refresh_land_units(db)
        refresh = refresh_land_metrics(db)
    db.commit()
    return db, refresh


def cell(db, land_unit_id):
    found = rows(
        db,
        "select unit_type, well_count, prod_well_count, liquid_cum_bbl, gas_cum_mcf,"
        " water_cum_bbl, liquid_bin, bin_edges, bin_population"
        " from marts.land_metrics_tile where land_unit_id = %s",
        (land_unit_id,),
    )
    assert found, f"no metrics cell for {land_unit_id}"
    return found[0]


def test_membership_is_the_lateral_midpoint_not_the_surface_hole(gridded):
    db, refresh = gridded
    # Five cells: three sections hold a well, both townships inherit through their sections.
    assert refresh.row_counts == {"land_metrics_tile": 5}
    # The off-grid well is a grid-state (ND) well, so it trips both exclusion counters.
    assert refresh.unassigned_wells == 1
    assert refresh.unassigned_grid_state_wells == 1

    unit_type, wells, producing, liquid, gas, water, _, _, _ = cell(db, SECTION_B)
    assert (unit_type, wells, producing) == ("section", 1, 1)
    assert (liquid, gas, water) == (1500.0, 3000.0, 0.0)

    unit_type, wells, producing, liquid, gas, water, _, _, _ = cell(db, SECTION_A)
    assert (unit_type, wells, producing) == ("section", 1, 1)
    assert (liquid, gas, water) == (200.0, 0.0, 100.0)


def test_a_cell_with_nothing_observed_is_present_and_unpainted(gridded):
    db, _ = gridded
    unit_type, wells, producing, liquid, _, _, bin_index, _, _ = cell(db, SECTION_Z)
    assert (unit_type, wells, producing) == ("section", 1, 0)
    assert liquid == 0.0
    assert bin_index == -1
    # A section nobody's anchor reached is absent — bare grid, not an interpolated zero.
    assert (
        scalar(
            db,
            "select count(*) from marts.land_metrics_tile where land_unit_id = %s",
            ("ND051530N0950W0SN130",),
        )
        == 0
    )


def test_townships_inherit_through_their_sections(gridded):
    db, _ = gridded
    unit_type, wells, producing, liquid, gas, water, _, _, _ = cell(db, TOWNSHIP_152)
    assert (unit_type, wells, producing) == ("township", 2, 2)
    assert (liquid, gas, water) == (1700.0, 3000.0, 100.0)
    unit_type, wells, producing, liquid, _, _, bin_index, _, _ = cell(db, TOWNSHIP_153)
    assert (unit_type, wells, producing) == ("township", 1, 0)
    assert bin_index == -1


def test_the_bin_frame_is_refresh_frozen_and_carried_on_every_cell(gridded):
    db, refresh = gridded
    frame = refresh.bin_frames["section"]
    assert frame["population"] == 2
    edges = frame["edges"]
    assert len(edges) == 8
    assert edges[0] == 200.0
    assert edges[-1] == 1500.0
    _, _, _, _, _, _, low_bin, low_edges, low_population = cell(db, SECTION_A)
    _, _, _, _, _, _, high_bin, high_edges, high_population = cell(db, SECTION_B)
    assert json.loads(low_edges) == edges
    assert low_edges == high_edges
    assert low_population == high_population == 2
    assert (low_bin, high_bin) == (0, 6)


def test_the_refresh_derivation_carries_the_rules_and_the_frame(gridded):
    db, refresh = gridded
    linked = {
        rule
        for (rule,) in rows(
            db,
            "select rule_id from lineage.derivation_rules where derivation_id = %s",
            (refresh.derivation_id,),
        )
    }
    assert {
        "cr_land_agg_membership_1", "cr_nd_liquids_policy_1", "cr_blm_plss_publisher_1"
    } <= linked
    params = scalar(
        db,
        "select params from lineage.derivations where derivation_id = %s",
        (refresh.derivation_id,),
    )
    assert params["liquids_basis"] == "oil+condensate"
    assert params["membership"] == "lateral_midpoint_else_surface"
    assert params["observed_only"] is True
    assert params["unassigned_wells"] == 1
    assert params["unassigned_grid_state_wells"] == 1
    assert params["bin_frames"]["section"]["population"] == 2
    assert (
        scalar(db, "select distinct derivation_id from marts.land_metrics_tile")
        == refresh.derivation_id
    )


def test_both_grains_serve_as_decodable_tiles_with_numeric_measures(gridded):
    db, refresh = gridded
    assert refresh.layers == ("land_township_metrics", "land_section_metrics")
    zoom, x, y = covering_tile(extent_of(db, "marts.land_metrics_tile"))
    for function, expected in (("land_township_metrics", 2), ("land_section_metrics", 3)):
        tile = scalar(db, f"select marts.{function}(%s, %s, %s)", (zoom, x, y))
        assert tile is not None, f"{function} returned no tile at z{zoom}"
        decoded = {layer_name(layer): layer for layer in layers(bytes(tile))}
        assert set(decoded) == {function}
        assert feature_count(decoded[function]) == expected
        assert set(attribute_keys(decoded[function])) == METRIC_KEYS
        # The N-2 wire hazard: a measure served as an MVT string interpolates as nothing.
        pool = attribute_values(decoded[function])
        kinds = {kind for kind, _ in pool}
        assert "double" in kinds
        assert ("string", "1500.0") not in pool
    section_tile = scalar(db, "select marts.land_section_metrics(%s, %s, %s)", (zoom, x, y))
    pool = attribute_values(bytes(layers(bytes(section_tile))[0]))
    assert ("double", 1500.0) in pool
