"""N-2 as a class: every column martin can serve is audited, not every column we declared.

Migration 015 fixed one column. The defect it fixed is structural — `ST_AsMVT` has no
`numeric` encoding, so a numeric column arrives as a protobuf *string* and a MapLibre
expression then compares `'9000' > '22727'`.

The first version of this file parametrised over `TILE_LAYERS` and therefore audited the
declarations rather than the database. It missed `lateral_length_ft_exact`, a `numeric`
column of a relation martin auto-publishes, which rode the live wire as
`('string', '255.9982469701856955')` across 8,611 features (Gate-O MAJOR-1). Columns are
now enumerated from the catalog, and an unencodable one is only allowed to exist if the
`martin` role cannot read it — a privilege, not a declaration, is what keeps it off the wire.
"""

from __future__ import annotations

from pathlib import Path

import psycopg
import pytest
import yaml

from glasswell.marts import ND_LAYERS, TILE_LAYERS
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

# The role martin.service authenticates as. Everything outside `marts` is off-limits to it, and
# `staging` is the one blueprint §3.0.1 names.
MARTIN_ROLE = "martin"
OFF_LIMITS_RELATIONS = (
    "staging.nd_gis_wells",
    "staging.nd_gis_laterals",
    "staging.nd_gis_spacing_units",
    "canonical.well_spatial",
    "canonical.spacing_units",
    "lineage.derivations",
)


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


def martin_readable_columns(connection: psycopg.Connection, relation: str) -> set[str]:
    """Every column the tile server's own role may select — the grant, read back."""
    return {
        name
        for (name,) in rows(
            connection,
            "select a.attname"
            "  from pg_attribute a"
            " where a.attrelid = %s::regclass and a.attnum > 0 and not a.attisdropped"
            "   and has_column_privilege(%s, a.attrelid, a.attname, 'select')",
            (relation, MARTIN_ROLE),
        )
    }


def base_relation(connection: psycopg.Connection, view: str) -> str:
    """The relation a published view selects from, read from the catalogue rather than named.

    A view over a mart is the publication boundary only if the mart underneath it is unreadable,
    and which mart that is differs per layer.
    """
    schema, relation = view.split(".")
    rows_found = rows(
        connection,
        "select distinct d.refobjid::regclass::text"
        "  from pg_rewrite r"
        "  join pg_depend d on d.objid = r.oid and d.classid = 'pg_rewrite'::regclass"
        " where r.ev_class = %s::regclass and d.refobjid <> %s::regclass"
        "   and d.refclassid = 'pg_class'::regclass",
        (f"{schema}.{relation}", f"{schema}.{relation}"),
    )
    assert rows_found, f"{view} selects from nothing"
    return rows_found[0][0]


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
def test_every_column_of_a_served_relation_is_encodable_or_unreadable_by_martin(
    canonical_nd, refreshed, layer  # noqa: F811
):
    """The class, widened past the declarations.

    A relation martin can publish carries columns no declaration mentions, and auto-publish
    serves all of them. So the audit is over the catalog, and the escape hatch is a privilege:
    an unencodable column may exist only where the tile server cannot read it.
    """
    readable = martin_readable_columns(canonical_nd, layer.source)
    offenders = {
        column: type_name
        for column, type_name in column_types(canonical_nd, layer.source).items()
        if type_name in UNENCODABLE_TYPES and column in readable
    }
    assert not offenders, (
        f"{layer.source} lets the martin role read {sorted(offenders)} —"
        f" ST_AsMVT would put {sorted(offenders.values())} on the wire as a string"
    )


@pytest.mark.parametrize("layer", TILE_LAYERS, ids=lambda layer: layer.name)
def test_martin_reads_the_published_columns_and_no_others(
    canonical_nd, refreshed, layer  # noqa: F811
):
    """Auto-publish serves whatever the role can select, so the grant is the real allowlist."""
    expected = {*layer.columns, "geom"}
    assert martin_readable_columns(canonical_nd, layer.source) == expected
    assert set(column_types(canonical_nd, layer.source)) == expected, (
        "the published view carries a column nobody publishes"
    )


@pytest.mark.parametrize("layer", TILE_LAYERS, ids=lambda layer: layer.name)
def test_martin_holds_table_privilege_on_what_it_publishes(
    canonical_nd, refreshed, layer  # noqa: F811
):
    """PostGIS's `geometry_columns` filters on has_table_privilege, and martin discovers table
    sources through it. A column grant leaves the schema looking empty and the server exits —
    with Restart=on-failure, a crash loop (Gate-O B-3)."""
    assert scalar(
        canonical_nd, "select has_table_privilege(%s, %s, 'select')", (MARTIN_ROLE, layer.source)
    )
    # This layer's own base relation, not a hardcoded ND one: with the literal in place,
    # widening the grant to a TX mart table left the whole suite green, so the negative
    # assertion proved nothing about the layer it was parameterised over.
    assert not scalar(
        canonical_nd,
        "select has_table_privilege(%s, %s, 'select')",
        (MARTIN_ROLE, base_relation(canonical_nd, layer.source)),
    ), f"the tile server can read {layer.name}'s mart directly, so the view is not the boundary"


@pytest.mark.parametrize("layer", TILE_LAYERS, ids=lambda layer: layer.name)
def test_geometry_columns_resolves_for_the_role_martin_runs_as(
    canonical_nd, refreshed, layer  # noqa: F811
):
    """The catalogue martin actually reads, read as martin reads it."""
    schema, relation = layer.source.split(".")
    with canonical_nd.cursor() as cursor:
        cursor.execute("set local role martin")
        cursor.execute(
            "select count(*) from geometry_columns"
            " where f_table_schema = %s and f_table_name = %s",
            (schema, relation),
        )
        assert cursor.fetchone()[0] == 1, f"{layer.source} is invisible to the tile server"
    canonical_nd.rollback()


@pytest.mark.parametrize("relation", OFF_LIMITS_RELATIONS)
def test_the_martin_role_cannot_read_outside_marts(canonical_nd, refreshed, relation):  # noqa: F811
    """Blueprint §3.0.1 held by a privilege, so `auto_publish: true` could not undo it."""
    with canonical_nd.cursor() as cursor:
        cursor.execute("set local role martin")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cursor.execute(f"select 1 from {relation} limit 1")
    canonical_nd.rollback()


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


# ND_LAYERS: reading the protobuf needs features, and this fixture's features are ND's. The
# TX layers are read the same way, from TX data, in test_tx_marts.py.
@pytest.mark.parametrize("layer", ND_LAYERS, ids=lambda layer: layer.name)
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


def test_the_martin_config_can_publish_nothing_outside_marts():
    """DR-05's point: `auto_publish` off with explicit sources is what stops martin serving
    `staging.*`. Auto-published, it offers eleven sources, three of them staging relations,
    and the proxy allowlist is the only control holding blueprint §3.0.1."""
    config = yaml.safe_load(MARTIN_CONFIG.read_text())["postgres"]

    assert config["auto_publish"] is False, "auto_publish would discover staging and canonical"
    assert "tables" not in config, "two publication mechanisms, one set of ids, is a collision"
    for name, source in config["functions"].items():
        assert source["schema"] == "marts", f"{name} publishes out of {source['schema']}"
