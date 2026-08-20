"""Function tile sources: one `marts.<layer>(z, x, y, query)` per published layer.

martin publishes a function source under the function's own name, so these names are the
`/v1/tiles/{layer}/…` ids the API proxies and the `source-layer` MapLibre binds to.
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg

TILE_EXTENT = 4096
TILE_BUFFER = 64
WEB_MERCATOR = 3857
# The deepest zoom the map source publishes (web/src/map/map.ts). Below the resolution it
# implies, ST_AsMVTGeom returns NULL and the feature is on no tile at any zoom (A3-F5).
TILE_MAX_ZOOM = 14


@dataclass(frozen=True, slots=True)
class TileLayer:
    name: str
    source: str
    geometry_type: str
    properties: tuple[tuple[str, str], ...]

    @property
    def columns(self) -> tuple[str, ...]:
        return tuple(column for column, _ in self.properties)


TILE_LAYERS: tuple[TileLayer, ...] = (
    TileLayer(
        name="nd_laterals",
        source="marts.nd_laterals_tile",
        geometry_type="LINESTRING",
        properties=(
            ("api10", "text"),
            ("linekey", "text"),
            ("operator_name", "text"),
            ("status_canonical", "text"),
            ("spud_year", "int4"),
            ("lateral_length_ft", "float8"),
            ("derivation_id", "text"),
        ),
    ),
    TileLayer(
        name="nd_wells",
        source="marts.nd_wells_tile",
        geometry_type="POINT",
        properties=(
            ("api10", "text"),
            ("operator_name", "text"),
            ("status_canonical", "text"),
            ("spud_year", "int4"),
            ("derivation_id", "text"),
        ),
    ),
    TileLayer(
        name="nd_spacing_units",
        source="marts.nd_spacing_units_tile",
        geometry_type="MULTIPOLYGON",
        properties=(
            ("spacing_unit_id", "text"),
            ("label", "text"),
            ("formation_reported", "text"),
            ("ds_size_acres", "numeric"),
            ("derivation_id", "text"),
        ),
    ),
)

# `stable parallel safe` is what martin's function discovery expects, and the argument names
# are part of the contract: it looks for (z, x, y) plus an optional json `query`.
_TILE_FUNCTION = """
create or replace function marts.{name}(z integer, x integer, y integer, query json default null)
returns bytea
language sql
stable
parallel safe
as $tile$
    select ST_AsMVT(feature, '{name}', {extent}, 'geom')
      from (select ST_AsMVTGeom(ST_Transform(t.geom, {mercator}), ST_TileEnvelope(z, x, y),
                                {extent}, {buffer}, true) as geom,
                   {columns}
              from {source} t
             where t.geom && ST_Transform(ST_TileEnvelope(z, x, y), 4326)) feature
     where feature.geom is not null
$tile$
"""


def install_tile_functions(connection: psycopg.Connection) -> tuple[str, ...]:
    """Create or replace every layer's MVT function. Its relation must already exist."""
    with connection.cursor() as cursor:
        for layer in TILE_LAYERS:
            cursor.execute(
                _TILE_FUNCTION.format(
                    name=layer.name,
                    source=layer.source,
                    extent=TILE_EXTENT,
                    buffer=TILE_BUFFER,
                    mercator=WEB_MERCATOR,
                    columns=", ".join(f"t.{column}" for column in layer.columns),
                )
            )
    return tuple(layer.name for layer in TILE_LAYERS)
