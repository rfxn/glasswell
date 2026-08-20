"""N-2 as a class: every tile declaration is audited against the relation it reads.

Migration 015 fixed one column. The defect it fixed is structural — `ST_AsMVT` has no
`numeric` encoding, so a numeric column arrives as a protobuf *string* and a MapLibre
expression then compares `'9000' > '22727'` — and the same declaration set carries a
geometry type, a srid and a column list that can drift from the database the same way.
This file audits all of it, for every layer, so the next drift fails here first.
"""

from __future__ import annotations

from pathlib import Path

import psycopg
import pytest
import yaml

from glasswell.marts import TILE_LAYERS
from tests.integration.test_marts_nd import (  # noqa: F401
    canonical_nd,
    covering_tile,
    extent_of,
    refreshed,
    rows,
    scalar,
)
from tests.support.mvt import VALUE_TYPES, attribute_keys, attribute_values, fields, layers

MARTIN_CONFIG = Path(__file__).resolve().parents[2] / "infra" / "martin" / "config.yaml"

# ST_AsMVT encodes a value as one of protobuf's seven scalars. `numeric` is in none of them:
# PostGIS falls back to the text representation, which is the whole A3-F4 defect.
UNENCODABLE_TYPES = frozenset({"numeric", "money", "interval", "uuid"})
NUMERIC_WIRE_KINDS = frozenset({"float", "double", "int", "uint", "sint"})

LAYER_PROPERTIES = [
    (layer, column, declared)
    for layer in TILE_LAYERS
    for column, declared in layer.properties
]


def _packed_varints(data: bytes) -> list[int]:
    values: list[int] = []
    value = shift = 0
    for byte in data:
        value |= (byte & 0x7F) << shift
        if byte & 0x80:
            shift += 7
            continue
        values.append(value)
        value = shift = 0
    return values


def feature_attributes(layer: bytes) -> list[dict[str, tuple[str, object]]]:
    """Every feature's tag pairs resolved through the layer's key and value pools."""
    keys = attribute_keys(layer)
    values = attribute_values(layer)
    decoded: list[dict[str, tuple[str, object]]] = []
    for field in fields(layer):
        if field.number != 2 or field.wire_type != 2:
            continue
        for tags in fields(bytes(field.payload)):
            if tags.number != 2 or tags.wire_type != 2:
                continue
            pairs = _packed_varints(bytes(tags.payload))
            decoded.append(
                {keys[k]: values[v] for k, v in zip(pairs[::2], pairs[1::2], strict=True)}
            )
    return decoded


def column_types(connection: psycopg.Connection, relation: str) -> dict[str, str]:
    """`typname` rather than `format_type`, so the answer is the token the config writes."""
    return {
        name: type_name
        for name, type_name in rows(
            connection,
            "select a.attname, t.typname"
            "  from pg_attribute a"
            "  join pg_type t on t.oid = a.atttypid"
            " where a.attrelid = %s::regclass and a.attnum > 0 and not a.attisdropped",
            (relation,),
        )
    }


def tile_of_layer(connection: psycopg.Connection, layer) -> bytes:
    zoom, x, y = covering_tile(extent_of(connection, layer.source))
    tile = scalar(connection, f"select marts.{layer.name}(%s, %s, %s, null)", (zoom, x, y))
    assert tile, f"{layer.name} produced no tile over its own extent"
    return bytes(tile)


@pytest.mark.parametrize(
    ("layer", "column", "declared"),
    LAYER_PROPERTIES,
    ids=[f"{layer.name}.{column}" for layer, column, _ in LAYER_PROPERTIES],
)
def test_every_declared_property_is_the_type_the_relation_holds(
    canonical_nd, refreshed, layer, column, declared  # noqa: F811
):
    actual = column_types(canonical_nd, layer.source)
    assert column in actual, f"{layer.source} has no column {column}"
    assert actual[column] == declared, (
        f"{layer.name}.{column} is declared {declared} and the relation holds"
        f" {actual[column]} — martin would publish the declaration"
    )


@pytest.mark.parametrize(
    ("layer", "column", "declared"),
    LAYER_PROPERTIES,
    ids=[f"{layer.name}.{column}" for layer, column, _ in LAYER_PROPERTIES],
)
def test_no_published_property_is_a_type_the_wire_cannot_encode(
    canonical_nd, refreshed, layer, column, declared  # noqa: F811
):
    """The class statement. A5/A3-F4 was one instance of it; this is the rule."""
    assert declared not in UNENCODABLE_TYPES
    assert column_types(canonical_nd, layer.source)[column] not in UNENCODABLE_TYPES


@pytest.mark.parametrize("layer", TILE_LAYERS, ids=lambda layer: layer.name)
def test_the_declared_geometry_matches_what_postgis_reports(
    canonical_nd, refreshed, layer  # noqa: F811
):
    """`geometry_columns` is the catalogue martin discovers a table source through."""
    schema, relation = layer.source.split(".")
    reported = rows(
        canonical_nd,
        "select type, srid, f_geometry_column from geometry_columns"
        " where f_table_schema = %s and f_table_name = %s",
        (schema, relation),
    )
    assert reported, f"{layer.source} is not in geometry_columns — martin cannot discover it"
    geometry_type, srid, geometry_column = reported[0]
    assert geometry_type == layer.geometry_type
    assert srid == 4326
    assert geometry_column == "geom"


@pytest.mark.parametrize("layer", TILE_LAYERS, ids=lambda layer: layer.name)
def test_every_numeric_attribute_rides_the_wire_as_a_number(
    canonical_nd, refreshed, layer  # noqa: F811
):
    """Read the protobuf, not the writer: a string here is the A3-F4 defect, one layer over."""
    numeric_columns = {
        column for column, declared in layer.properties if declared not in ("text", "varchar")
    }
    if not numeric_columns:
        pytest.skip(f"{layer.name} publishes no numeric attribute")

    features = feature_attributes(layers(tile_of_layer(canonical_nd, layer))[0])
    assert features, f"{layer.name} tiled no feature to read attributes from"

    seen = {
        column: {kind for kind, _ in (feature[column] for feature in features if column in feature)}
        for column in numeric_columns
    }
    for column, kinds in seen.items():
        assert kinds, f"{layer.name}.{column} is on no feature in the tile"
        assert kinds <= NUMERIC_WIRE_KINDS, (
            f"{layer.name}.{column} rode the wire as {sorted(kinds)};"
            f" MapLibre compares a string lexicographically"
        )
        assert kinds <= set(VALUE_TYPES.values())


def test_the_martin_config_and_the_allowlist_declare_the_same_property_types():
    """The config is what martin publishes; TILE_LAYERS is what the proxy admits (DR-05)."""
    config = yaml.safe_load(MARTIN_CONFIG.read_text())["postgres"]
    assert config["auto_publish"] is False
    assert set(config["tables"]) == {layer.name for layer in TILE_LAYERS}
    for layer in TILE_LAYERS:
        declared = config["tables"][layer.name]
        assert declared["properties"] == dict(layer.properties)
        assert declared["geometry_type"] == layer.geometry_type
        assert f"{declared['schema']}.{declared['table']}" == layer.source
