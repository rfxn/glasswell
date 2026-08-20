"""A3-F4/F5: what the tile actually puts on the wire, read back out of the protobuf."""

from __future__ import annotations

from decimal import Decimal

import psycopg
import pytest

from tests.integration.test_lateral_length_truth import laterals_loaded  # noqa: F401
from tests.integration.test_marts_nd import covering_tile, extent_of, rows, scalar
from tests.support.mvt import attribute_keys, attribute_values, layers
from tests.support.seed import seed_well, seed_well_spatial

LAYER = "nd_laterals"


def laterals_tile(connection: psycopg.Connection) -> bytes:
    zoom, x, y = covering_tile(extent_of(connection, "marts.nd_laterals_tile"))
    tile = scalar(connection, f"select marts.{LAYER}(%s, %s, %s, null)", (zoom, x, y))
    assert tile, "the fixture extent produced no tile to read"
    return bytes(tile)


def test_the_length_rides_the_wire_as_a_number_not_as_a_string(laterals_loaded):  # noqa: F811
    """MapLibre compares a string attribute lexicographically: '9000' > '22727'."""
    layer = layers(laterals_tile(laterals_loaded))[0]
    values = attribute_values(layer)

    assert "lateral_length_ft" in attribute_keys(layer)
    lengths = [value for kind, value in values if kind == "double"]
    assert lengths, f"no double rode the tile; value types were {sorted({k for k, _ in values})}"
    stored = {
        row[0]
        for row in rows(laterals_loaded, "select lateral_length_ft from marts.nd_laterals_tile")
    }
    assert set(lengths) <= stored
    # api10 and linekey are identifiers and stay strings; a decimal one would be a length.
    decimal_strings = [
        value
        for kind, value in values
        if kind == "string" and value.replace(".", "", 1).isdigit() and "." in value
    ]
    assert decimal_strings == []


def test_the_tile_length_carries_a_sane_precision(laterals_loaded):  # noqa: F811
    """Twenty significant digits is a claim the geometry cannot support; a cent is enough."""
    layer = layers(laterals_tile(laterals_loaded))[0]

    for kind, value in attribute_values(layer):
        if kind == "double":
            assert Decimal(str(value)) == Decimal(str(value)).quantize(Decimal("0.01"))


def test_the_wire_value_is_the_rounding_of_the_exact_column(laterals_loaded):  # noqa: F811
    mismatched = rows(
        laterals_loaded,
        "select linekey from marts.nd_laterals_tile"
        " where lateral_length_ft <> round(lateral_length_ft_exact, 2)::float8",
    )

    assert mismatched == []


def test_a_lateral_that_cannot_reach_a_tile_is_disclosed_on_the_card(
    laterals_loaded,  # noqa: F811
    api_client,
):
    """A3-F5: eight production laterals are served by the API and absent from every zoom."""
    # 33053031750000_LAT1 really is 0.24 ft long; canonical is append-only, so it is seeded
    # rather than shrunk in place.
    api10 = "3305303175"
    seed_well(laterals_loaded, api10=api10)
    seed_well_spatial(
        laterals_loaded,
        api10=api10,
        geom_key=f"{api10}0000_LAT1",
        wkt="LINESTRING(-103.5803 47.9075, -103.580299 47.9075)",
    )

    body = api_client.get(f"/v1/wells/{api10}").json()
    codes = {warning["code"] for warning in body["meta"]["warnings"]}

    assert "below_tile_resolution" in codes
    assert body["data"]["lateral_length_ft"] is not None


def test_a_renderable_lateral_raises_no_such_warning(laterals_loaded, api_client):  # noqa: F811
    api10 = scalar(
        laterals_loaded,
        "select api10 from canonical.well_spatial where geom_type = 'lateral'"
        " order by ST_Length(geom::geography) desc limit 1",
    )

    body = api_client.get(f"/v1/wells/{api10}").json()

    assert "below_tile_resolution" not in {w["code"] for w in body["meta"]["warnings"]}


@pytest.mark.parametrize("column", ["lateral_length_ft", "lateral_length_ft_exact"])
def test_both_length_columns_are_typed_as_declared(laterals_loaded, column):  # noqa: F811
    declared = scalar(
        laterals_loaded,
        "select data_type from information_schema.columns"
        " where table_schema = 'marts' and table_name = 'nd_laterals_tile'"
        "   and column_name = %s",
        (column,),
    )

    assert declared == ("double precision" if column == "lateral_length_ft" else "numeric")
