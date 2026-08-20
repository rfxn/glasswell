"""Function tile sources: one `marts.<layer>(z, x, y, query)` per published layer.

Each reads a `marts.tile_*` view rather than the mart it projects: that view's column list is
the publication boundary migration 026 grants the tile server, so both publication paths see
exactly the same columns.

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

# 3857 units spanned by the whole world, so one tile at zoom z spans this over 2^z and one
# MVT unit of that tile spans it over TILE_EXTENT again. Expressing the simplify tolerance
# in MVT units rather than metres keeps the discarded detail a constant fraction of a
# rendered pixel at every zoom: SIMPLIFY_MVT_UNITS of 4096 across 256 CSS pixels is a
# quarter-pixel ceiling on the deviation. SB-05 §2.4.1 pins a fixed metre ladder instead
# (40 m at z<=8 … 0 at z>=13) and marks it "[A - tune against measured tile bytes at P2]";
# measurement is in work-output/track-t-status.md and this is the tuned form.
WORLD_SPAN_3857 = 40075016.685578488
SIMPLIFY_MVT_UNITS = 4


@dataclass(frozen=True, slots=True)
class TileLayer:
    name: str
    source: str
    geometry_type: str
    properties: tuple[tuple[str, str], ...]
    # Douglas-Peucker pays on lines and loses on the other two: at z7 it cut the laterals
    # tile 12.7% and ran 30% faster, while on the spacing-unit polygons the topology-safe
    # variant cost 171% more time for 3% fewer bytes, and points have nothing to thin.
    simplify: bool = False

    @property
    def columns(self) -> tuple[str, ...]:
        return tuple(column for column, _ in self.properties)


TILE_LAYERS: tuple[TileLayer, ...] = (
    TileLayer(
        name="nd_laterals",
        source="marts.tile_nd_laterals",
        # Migration 017 widened the column to hold a multi-part centreline, so this is what
        # `geometry_columns` reports and therefore what martin discovers. MVT encodes a
        # multi-part line as LINESTRING either way.
        geometry_type="GEOMETRY",
        properties=(
            ("api10", "text"),
            ("linekey", "text"),
            ("operator_name", "text"),
            ("status_canonical", "text"),
            ("spud_year", "int4"),
            ("lateral_length_ft", "float8"),
            ("derivation_id", "text"),
        ),
        simplify=True,
    ),
    TileLayer(
        name="nd_wells",
        source="marts.tile_nd_wells",
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
        source="marts.tile_nd_spacing_units",
        geometry_type="MULTIPOLYGON",
        properties=(
            ("spacing_unit_id", "text"),
            ("label", "text"),
            ("formation_reported", "text"),
            ("ds_size_acres", "float8"),
            ("derivation_id", "text"),
        ),
    ),
)

# `stable parallel safe` is what martin's function discovery expects, and the argument names
# are part of the contract: it looks for (z, x, y) plus an optional json `query`.
#
# `as materialized` is load-bearing, not style. Inlined, the planner flattens the subquery
# and evaluates ST_AsMVTGeom twice per row — once for the null test and again for the
# aggregate — which cost 5% to 40% of every layer at every zoom on the live ND slice.
_TILE_FUNCTION = """
create or replace function marts.{name}(z integer, x integer, y integer, query json default null)
returns bytea
language sql
stable
parallel safe
as $tile$
    with feature as materialized (
        select ST_AsMVTGeom({geom}, ST_TileEnvelope(z, x, y), {extent}, {buffer}, true) as geom,
               {columns}
          from {source} t
         where t.geom && ST_Transform(ST_TileEnvelope(z, x, y), 4326))
    select ST_AsMVT(feature, '{name}', {extent}, 'geom')
      from feature
     where feature.geom is not null
$tile$
"""

_PROJECTED = "ST_Transform(t.geom, {mercator})"
# preserveCollapsed is true so a lateral shorter than the tolerance thins to its endpoints
# rather than vanishing: the feature count a tile carries must not depend on its zoom.
_SIMPLIFIED = (
    "ST_Simplify(ST_Transform(t.geom, {mercator}),"
    " {span} / power(2, z) / {extent} * {units}, true)"
)


def tile_geometry_sql(layer: TileLayer) -> str:
    """The geometry expression ST_AsMVTGeom is handed for one layer."""
    template = _SIMPLIFIED if layer.simplify else _PROJECTED
    return template.format(
        mercator=WEB_MERCATOR,
        span=WORLD_SPAN_3857,
        extent=TILE_EXTENT,
        units=SIMPLIFY_MVT_UNITS,
    )


def simplify_tolerance(zoom: int) -> float:
    """The 3857-unit tolerance the function applies at `zoom`, for tests and reporting."""
    return WORLD_SPAN_3857 / 2**zoom / TILE_EXTENT * SIMPLIFY_MVT_UNITS


def install_tile_functions(connection: psycopg.Connection) -> tuple[str, ...]:
    """Create or replace every layer's MVT function. Its relation must already exist."""
    with connection.cursor() as cursor:
        for layer in TILE_LAYERS:
            cursor.execute(
                _TILE_FUNCTION.format(
                    name=layer.name,
                    source=layer.source,
                    geom=tile_geometry_sql(layer),
                    extent=TILE_EXTENT,
                    buffer=TILE_BUFFER,
                    columns=", ".join(f"t.{column}" for column in layer.columns),
                )
            )
    return tuple(layer.name for layer in TILE_LAYERS)
