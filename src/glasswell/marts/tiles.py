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

# At and below z7 the map draws more features than it has pixels for, and the surplus reads as
# alpha overplot rather than as information: half the features carry 15% of the ink at z7 and
# 0.5% of it at z4 (gate-inc3-visual.md §2). One feature per half CSS pixel, ranked by
# md5(api10) because it is deterministic across refreshes and carries no tilt — ranking by
# spud year or lateral length visibly shifts the status colour mix, which is a biased sample of
# something the reader is reading as information. The constants and the rank are the approval:
# changing either re-opens the gate.
THIN_MAX_ZOOM = 7
THIN_PIXELS = 0.5
TILE_CSS_PIXELS = 256


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
    # Per layer, because the rank is md5(api10) and a layer without that column has no rank —
    # and because the gate approved the rule for the well and lateral layers, not for anything
    # that later joins the roster.
    thin: bool = False

    @property
    def columns(self) -> tuple[str, ...]:
        return tuple(column for column, _ in self.properties)


ND_LAYERS: tuple[TileLayer, ...] = (
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
            ("geometry_provenance", "text"),
            ("derivation_id", "text"),
        ),
        simplify=True,
        thin=True,
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
            ("well_type_reported", "text"),
            ("geometry_provenance", "text"),
            ("derivation_id", "text"),
        ),
        thin=True,
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
    # Simplified for the reason the laterals are — Douglas-Peucker pays on lines, and these
    # are the highest-vertex lines the map has: 52,579 stations over 586 traces, a median of
    # 89 vertices where a lateral centreline carries a handful.
    #
    # Not thinned, and that is a decision rather than an omission. The gate approved a rank
    # inside a half-pixel cell for the well and lateral layers because they draw more features
    # than the zoom has pixels for; 586 traces over the whole of North Dakota is not overplot
    # at any zoom, and applying an approved remedy to a layer outside its approval would put a
    # sampling rule on data that has no case for one.
    TileLayer(
        name="nd_survey_traces",
        source="marts.tile_nd_survey_traces",
        geometry_type="LINESTRING",
        properties=(
            ("api10", "text"),
            ("trace_key", "text"),
            ("operator_name", "text"),
            ("status_canonical", "text"),
            ("spud_year", "int4"),
            ("wellbore_segment", "text"),
            ("segment_kind", "text"),
            ("station_count", "int4"),
            ("deepest_station_md_ft", "float8"),
            ("deepest_station_tvd_ft", "float8"),
            ("geometry_provenance", "text"),
            ("derivation_id", "text"),
        ),
        simplify=True,
    ),
)

# The land grid publishes as two layers over one mart: a z8 tile over the basin holds
# hundreds of townships but thousands of sections, and a split publication lets the section
# source start deeper so its tiles are never fetched where nothing draws them. Not simplified:
# a PLSS polygon is a handful of vertices. Not thinned: the gate's rank is md5(api10) and a
# land unit has none — and reference linework has no overplot case.
LAND_LAYERS: tuple[TileLayer, ...] = (
    TileLayer(
        name="land_townships",
        source="marts.tile_land_townships",
        geometry_type="MULTIPOLYGON",
        properties=(
            ("land_unit_id", "text"),
            ("unit_type", "text"),
            ("plssid", "text"),
            ("label", "text"),
            ("derivation_id", "text"),
        ),
    ),
    TileLayer(
        name="land_sections",
        source="marts.tile_land_sections",
        geometry_type="MULTIPOLYGON",
        properties=(
            ("land_unit_id", "text"),
            ("unit_type", "text"),
            ("plssid", "text"),
            ("label", "text"),
            ("derivation_id", "text"),
        ),
    ),
)

# TX carries no spud date — the RRC's free identity export publishes a completion date and not
# a spud — so the point layer styles on status and says what the wellbore is for instead.
TX_LAYERS: tuple[TileLayer, ...] = (
    TileLayer(
        name="tx_laterals",
        source="marts.tile_tx_laterals",
        geometry_type="GEOMETRY",
        properties=(
            ("api10", "text"),
            ("geom_key", "text"),
            ("operator_name", "text"),
            ("status_canonical", "text"),
            ("county_code", "text"),
            ("lateral_length_ft", "float8"),
            ("derivation_id", "text"),
        ),
        simplify=True,
        thin=True,
    ),
    TileLayer(
        name="tx_wells",
        source="marts.tile_tx_wells",
        geometry_type="POINT",
        properties=(
            ("api10", "text"),
            ("operator_name", "text"),
            ("status_canonical", "text"),
            ("well_type_reported", "text"),
            ("county_code", "text"),
            ("derivation_id", "text"),
        ),
        thin=True,
    ),
)

TILE_LAYERS: tuple[TileLayer, ...] = (*ND_LAYERS, *LAND_LAYERS, *TX_LAYERS)

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

# The gate is a rank inside the cell, not a `distinct on` over it: two wells at one coordinate
# — 547 of the 355,463 in Texas, 144 of North Dakota's 43,817 — are one cell at any cell size,
# so a set-collapse would have dropped them at every zoom rather than only inside the band.
_THIN_SOURCE = """(
              select ranked.*
                from (select src.*,
                             row_number() over (partition by {key} order by md5(src.api10))
                                 as gw_overplot_rank
                        from {source} src
                       where src.geom && ST_Transform(ST_TileEnvelope(z, x, y), 4326)) ranked
               where z > {max_zoom} or ranked.gw_overplot_rank = 1)"""
_THIN_CELL = "{span} / power(2, z) / {css} * {pixels}"
_THIN_KEY = "ST_SnapToGrid(ST_Centroid(ST_Transform(src.geom, {mercator})), {cell}, {cell})"

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


def thin_cell(zoom: int) -> float:
    """The 3857-unit grid cell one surviving feature is kept per, inside the gated band."""
    return WORLD_SPAN_3857 / 2**zoom / TILE_CSS_PIXELS * THIN_PIXELS


def thin_key_sql() -> str:
    """The grid cell a thinned layer's features are ranked within."""
    cell = _THIN_CELL.format(span=WORLD_SPAN_3857, css=TILE_CSS_PIXELS, pixels=THIN_PIXELS)
    return _THIN_KEY.format(mercator=WEB_MERCATOR, cell=f"({cell})")


def tile_source_sql(layer: TileLayer) -> str:
    """What the tile function reads: the relation, or the relation with the gate over it."""
    if not layer.thin:
        return layer.source
    return _THIN_SOURCE.format(
        source=layer.source, key=thin_key_sql(), max_zoom=THIN_MAX_ZOOM
    )


def tile_function_sql(layer: TileLayer) -> str:
    """The `create or replace function` statement one layer installs."""
    if layer.thin and "api10" not in layer.columns:
        raise ValueError(f"{layer.name} is thinned but publishes no api10 to rank by")
    return _TILE_FUNCTION.format(
        name=layer.name,
        source=tile_source_sql(layer),
        geom=tile_geometry_sql(layer),
        extent=TILE_EXTENT,
        buffer=TILE_BUFFER,
        columns=", ".join(f"t.{column}" for column in layer.columns),
    )


def install_tile_functions(connection: psycopg.Connection) -> tuple[str, ...]:
    """Create or replace every layer's MVT function. Its relation must already exist."""
    with connection.cursor() as cursor:
        for layer in TILE_LAYERS:
            cursor.execute(tile_function_sql(layer))
    return tuple(layer.name for layer in TILE_LAYERS)
