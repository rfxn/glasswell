"""The Montana layer declarations: what they publish, and what their flags are chosen from.

Every flag on a `TileLayer` is a claim about the data behind it, so each is asserted against the
measured reason rather than against itself. The path layer's `geometry_class` and `vertex_count`
are the load-bearing ones: cr_mt_paths_geometry_class_1 requires the map-stick distinction
wherever the geometry is served, and a tile client reads properties, not documentation.
"""

from __future__ import annotations

import pytest

from glasswell.marts.mt_wells import MAP_STICK
from glasswell.marts.tiles import MT_LAYERS, TILE_LAYERS, tile_function_sql

LAYERS = {layer.name: layer for layer in TILE_LAYERS}


def test_montana_publishes_a_point_layer_and_a_path_layer_and_no_third():
    assert tuple(layer.name for layer in MT_LAYERS) == ("mt_wells", "mt_paths")
    assert {name for name in LAYERS if name.startswith("mt_")} == {"mt_wells", "mt_paths"}


def test_the_path_layer_is_not_called_a_lateral_layer():
    """186 of the 4,173 paths are WL01 vertical wellbores and 192 are ST01 sidetracks
    (cr_mt_paths_subkey_1), so `mt_laterals` would misname the majority case for 378 of them."""
    assert "mt_laterals" not in LAYERS
    assert LAYERS["mt_paths"].source == "marts.tile_mt_paths"


def test_every_path_feature_carries_its_class_and_its_vertex_count():
    published = dict(LAYERS["mt_paths"].properties)

    assert published["geometry_class"] == "text"
    assert published["vertex_count"] == "int4"


def test_the_class_the_mart_writes_is_the_one_the_layer_publishes():
    """One vocabulary, spelled once: a mart writing `map_stick` under a layer publishing
    something else would leave the distinction unreadable on the wire."""
    assert MAP_STICK == "map_stick"


def test_neither_montana_layer_publishes_a_length():
    """cr_mt_paths_length_scope_2: Montana carries no basin, so no length method is registered
    for it, and a served length would be a figure with no rule to cite."""
    for layer in MT_LAYERS:
        assert not any("length" in column for column in layer.columns), layer.name


def test_the_point_layer_carries_a_completion_year_and_never_a_spud_one():
    published = dict(LAYERS["mt_wells"].properties)

    assert published["completion_year"] == "int4"
    assert "spud_year" not in published


def test_both_layers_carry_the_derivation_that_built_them():
    for layer in MT_LAYERS:
        assert "derivation_id" in layer.columns, layer.name


def test_the_point_layer_is_thinned_like_every_dense_point_layer():
    """42,026 points against North Dakota's 43,817, which the gate approved a rank for."""
    sql = tile_function_sql(LAYERS["mt_wells"])

    assert LAYERS["mt_wells"].thin is True
    assert "gw_overplot_rank" in sql


def test_the_path_layer_is_neither_thinned_nor_simplified():
    """Both are decisions, not omissions. Douglas-Peucker has nothing to take from a mean of
    2.82 vertices, and 4,173 lines over a state is the nd_survey_traces case rather than the
    overplot the thinning gate approved a rank for."""
    sql = tile_function_sql(LAYERS["mt_paths"])

    assert LAYERS["mt_paths"].thin is False
    assert LAYERS["mt_paths"].simplify is False
    assert "gw_overplot_rank" not in sql
    assert "ST_Simplify" not in sql


@pytest.mark.parametrize("name", ["mt_wells", "mt_paths"])
def test_each_layer_reads_the_publication_view_and_not_the_mart_beneath_it(name):
    """Migration 026's boundary: the view's column list is what the tile server is granted."""
    assert LAYERS[name].source.startswith("marts.tile_")
