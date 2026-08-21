"""The z<=7 overplot gate: the cell ladder, the rank, and which layers carry it."""

from __future__ import annotations

import pytest

from glasswell.marts.tiles import (
    THIN_MAX_ZOOM,
    THIN_PIXELS,
    TILE_CSS_PIXELS,
    TILE_LAYERS,
    WORLD_SPAN_3857,
    TileLayer,
    thin_cell,
    thin_key_sql,
    tile_function_sql,
)

LAYERS = {layer.name: layer for layer in TILE_LAYERS}


@pytest.mark.parametrize("zoom", [0, 4, 6, 7])
def test_the_cell_is_half_a_css_pixel_through_the_band_the_gate_approved(zoom):
    assert thin_cell(zoom) == WORLD_SPAN_3857 / 2**zoom / TILE_CSS_PIXELS * THIN_PIXELS


@pytest.mark.parametrize("zoom", [8, 11, 14])
def test_above_the_band_the_cell_is_finer_than_any_position_a_source_publishes(zoom):
    """A micrometre in 3857, against six decimal places of degree (~0.1 m) from the RRC and
    the DMR: no two distinct wells snap together above the band, so nothing is thinned."""
    assert thin_cell(zoom) == 0.000001
    assert thin_cell(zoom) < 0.1


def test_the_ladder_halves_with_the_zoom_the_way_the_tile_grid_does():
    assert thin_cell(6) == pytest.approx(thin_cell(7) * 2)
    assert thin_cell(7) == pytest.approx(611.4962, abs=1e-4)


@pytest.mark.parametrize("name", ["nd_wells", "nd_laterals", "tx_wells", "tx_laterals"])
def test_the_gate_and_the_rank_are_both_in_the_installed_sql(name):
    sql = tile_function_sql(LAYERS[name])

    assert "distinct on (" in sql
    assert f"case when z <= {THIN_MAX_ZOOM}" in sql
    assert "md5(t.api10)" in sql


@pytest.mark.parametrize("name", ["nd_wells", "nd_laterals", "tx_wells", "tx_laterals"])
def test_the_rank_is_the_one_the_gate_approved_and_carries_no_tilt(name):
    """C1: `spud_year desc` and `lateral_length_ft desc` visibly shift the status colour
    mix, which is a biased sample of something the reader reads as information."""
    sql = tile_function_sql(LAYERS[name])
    order = next(line for line in sql.splitlines() if line.strip().startswith("order by"))

    assert order.rstrip().endswith("md5(t.api10))")
    assert "spud_year" not in order
    assert "lateral_length_ft" not in order


def test_a_layer_outside_the_approval_carries_no_gate():
    """Spacing units are polygons with no api10, so they have neither a rank nor a case
    for one: a township outline is not overplot."""
    sql = tile_function_sql(LAYERS["nd_spacing_units"])

    assert "distinct on" not in sql
    assert "ST_SnapToGrid" not in sql
    assert "order by" not in sql


def test_a_thinned_layer_that_publishes_no_rank_is_refused_rather_than_installed():
    unrankable = TileLayer(
        name="nd_spacing_units",
        source="marts.tile_nd_spacing_units",
        geometry_type="MULTIPOLYGON",
        properties=(("spacing_unit_id", "text"),),
        thin=True,
    )

    with pytest.raises(ValueError, match="no api10"):
        tile_function_sql(unrankable)


def test_the_gate_reads_the_projected_geometry_rather_than_the_simplified_one():
    """The cell is a position, not a shape: ranking on a simplified centreline would make
    which feature survives depend on the zoom's simplify tolerance as well as its cell."""
    assert "ST_Simplify" not in thin_key_sql()
    assert "ST_Centroid(ST_Transform(t.geom, 3857))" in thin_key_sql()
