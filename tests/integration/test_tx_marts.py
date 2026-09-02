"""The TX tile marts, audited the way the ND ones are: over the data, not the declarations."""

from __future__ import annotations

from pathlib import Path

import pytest

from glasswell.lineage.capture import lineage_session
from glasswell.lineage.store import PostgresRecorder
from glasswell.marts import TX_LAYERS
from glasswell.marts.wells import refresh_for
from tests.integration.test_marts_nd import covering_tile, extent_of, rows, scalar
from tests.integration.test_tile_wire_types import (
    NUMERIC_WIRE_KINDS,
    feature_attributes,
    tile_of_layer,
)
from tests.integration.test_tx_gis_load import (  # noqa: F401
    COUNTY,
    client_for,
    identity,
    seeded,
)
from tests.integration.test_tx_gis_load import county as county_loaded  # noqa: F401
from tests.support.mvt import layers

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture
def refreshed(county_loaded, seeded, lineage_env):  # noqa: F811
    with lineage_session(recorder=PostgresRecorder(seeded), environment=lineage_env):
        report = refresh_for(seeded, "TX")
    seeded.commit()
    return report


def test_refresh_projects_canonical_into_both_tile_marts(refreshed, seeded, county_loaded):  # noqa: F811
    assert refreshed.row_counts["tx_wells_tile"] == county_loaded.geometries["surface"]
    assert refreshed.row_counts["tx_laterals_tile"] == county_loaded.geometries["lateral"]
    assert set(refreshed.layers) == {layer.name for layer in TX_LAYERS}


def test_the_wells_tile_mart_holds_surface_points_only(refreshed, seeded):  # noqa: F811
    kinds = {
        kind
        for (kind,) in rows(
            seeded,
            "select distinct ST_GeometryType(geom) from marts.tx_wells_tile",
        )
    }
    assert kinds == {"ST_Point"}
    assert scalar(seeded, "select count(*) from marts.tx_wells_tile") == scalar(
        seeded,
        "select count(distinct api10) from canonical.well_spatial where geom_type = 'surface'",
    )


def test_every_tile_row_carries_a_handle_that_resolves_to_a_derivation(refreshed, seeded):  # noqa: F811
    for table in ("tx_wells_tile", "tx_laterals_tile"):
        assert scalar(
            seeded,
            f"select count(*) from marts.{table} m"
            "  left join lineage.derivations d on d.derivation_id = m.derivation_id"
            " where d.derivation_id is null",
        ) == 0


def test_the_unrounded_length_is_stored_and_is_not_published(refreshed, seeded):  # noqa: F811
    exact, published = rows(
        seeded,
        "select lateral_length_ft_exact, lateral_length_ft from marts.tx_laterals_tile limit 1",
    )[0]
    assert float(exact) == pytest.approx(published, abs=0.01)
    columns = {
        name
        for (name,) in rows(
            seeded,
            "select column_name from information_schema.columns"
            " where table_schema = 'marts' and table_name = 'tile_tx_laterals'",
        )
    }
    assert "lateral_length_ft_exact" not in columns, (
        "numeric on the wire is a string; the publication boundary is the view (N-2)"
    )


@pytest.mark.parametrize("layer", TX_LAYERS, ids=lambda layer: layer.name)
def test_the_function_source_returns_a_tile_over_the_data(refreshed, seeded, layer):  # noqa: F811
    zoom, x, y = covering_tile(extent_of(seeded, layer.source))
    tile = scalar(seeded, f"select marts.{layer.name}(%s, %s, %s, null)", (zoom, x, y))
    assert tile, f"{layer.name} produced no MVT for {zoom}/{x}/{y}, which covers its own extent"
    assert layer.name.encode() in bytes(tile)


@pytest.mark.parametrize("layer", TX_LAYERS, ids=lambda layer: layer.name)
def test_the_function_source_returns_nothing_off_the_data(refreshed, seeded, layer):  # noqa: F811
    zoom, x, y = covering_tile(extent_of(seeded, layer.source))
    opposite = (x + 2**zoom // 2) % 2**zoom
    tile = scalar(seeded, f"select marts.{layer.name}(%s, %s, %s, null)", (zoom, opposite, y))
    assert not tile, "an empty tile must be empty so the proxy can answer 204, not 200"


@pytest.mark.parametrize("layer", TX_LAYERS, ids=lambda layer: layer.name)
def test_every_numeric_attribute_rides_the_wire_as_a_number(refreshed, seeded, layer):  # noqa: F811
    numeric_columns = {
        column for column, declared in layer.properties if declared not in ("text", "varchar")
    }
    if not numeric_columns:
        pytest.skip(f"{layer.name} publishes no numeric attribute")
    features = feature_attributes(layers(tile_of_layer(seeded, layer))[0])
    assert features
    for column in numeric_columns:
        kinds = {kind for kind, _ in (f[column] for f in features if column in f)}
        assert kinds, f"{layer.name}.{column} is on no feature in the tile"
        assert kinds <= NUMERIC_WIRE_KINDS


def test_a_tx_feature_carries_the_status_the_legend_paints_with(refreshed, seeded):  # noqa: F811
    painted = {
        status
        for (status,) in rows(
            seeded,
            "select distinct status_canonical from marts.tx_wells_tile"
            " where status_canonical is not null",
        )
    }
    known = {
        status
        for (status,) in rows(seeded, "select distinct status_canonical from lineage.tx_status_map")
    }
    assert painted
    assert painted <= known


def test_the_refresh_cites_the_tx_length_rule_and_the_datum_rule(refreshed, seeded):  # noqa: F811
    cited = {
        rule_id
        for (rule_id,) in rows(
            seeded,
            "select rule_id from lineage.derivation_rules where derivation_id = %s",
            (refreshed.derivation_id,),
        )
    }
    assert {"cr_tx_compute_crs_1", "cr_tx_nad27_1"} <= cited
