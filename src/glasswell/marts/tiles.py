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
    # Emits a second `{name}_label` MVT layer holding one interior anchor point per feature,
    # in the one tile whose envelope holds the point. MapLibre places a symbol per tile
    # fragment of a polygon, so binding text to the polygon layer duplicates every label
    # that crosses a tile seam (visual-m14 F1); a point owned by exactly one tile cannot.
    label_points: bool = False

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
        label_points=True,
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
        label_points=True,
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
        label_points=True,
    ),
)

# M2-3: observed well and production rollups on the land grid, one layer per grain so the
# township surface hands off to the section surface at the zoom where sections are readable.
# Numeric columns are int4/float8 on the wire deliberately: a Postgres numeric serves as an
# MVT string and every style interpolation over it silently falls back (the N-2 hazard the
# land layers avoided by being all-text). bin_edges is a JSON array serialized once per
# refresh; MVT interns repeated property values, so it costs one entry per tile, not one
# per feature.
METRIC_LAYERS: tuple[TileLayer, ...] = (
    TileLayer(
        name="land_township_metrics",
        source="marts.tile_land_township_metrics",
        geometry_type="MULTIPOLYGON",
        properties=(
            ("land_unit_id", "text"),
            ("unit_type", "text"),
            ("plssid", "text"),
            ("label", "text"),
            ("well_count", "int4"),
            ("prod_well_count", "int4"),
            ("liquid_cum_bbl", "float8"),
            ("gas_cum_mcf", "float8"),
            ("water_cum_bbl", "float8"),
            ("liquid_bin", "int4"),
            ("bin_edges", "text"),
            ("bin_population", "int4"),
            ("derivation_id", "text"),
        ),
    ),
    TileLayer(
        name="land_section_metrics",
        source="marts.tile_land_section_metrics",
        geometry_type="MULTIPOLYGON",
        properties=(
            ("land_unit_id", "text"),
            ("unit_type", "text"),
            ("plssid", "text"),
            ("label", "text"),
            ("well_count", "int4"),
            ("prod_well_count", "int4"),
            ("liquid_cum_bbl", "float8"),
            ("gas_cum_mcf", "float8"),
            ("water_cum_bbl", "float8"),
            ("liquid_bin", "int4"),
            ("bin_edges", "text"),
            ("bin_population", "int4"),
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

# A point layer and nothing else: no in-scope New Mexico source ships a lateral, and
# cr_nm_wellhistory_geometry_scope_1 is the row that says so.
NM_LAYERS: tuple[TileLayer, ...] = (
    TileLayer(
        name="nm_wells",
        source="marts.tile_nm_wells",
        geometry_type="POINT",
        properties=(
            ("api10", "text"),
            ("operator_name", "text"),
            ("status_canonical", "text"),
            ("status_reported", "text"),
            ("well_type_reported", "text"),
            ("county_code", "text"),
            ("spud_year", "int4"),
            ("derivation_id", "text"),
        ),
        thin=True,
    ),
)

TILE_LAYERS: tuple[TileLayer, ...] = (
    *ND_LAYERS, *LAND_LAYERS, *METRIC_LAYERS, *TX_LAYERS, *NM_LAYERS
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

# One anchor per feature, in the one tile whose envelope holds it: the bounds test is
# half-open ([min, max) on both axes) so a point landing exactly on a shared tile edge —
# ST_TileEnvelope computes both neighbours' shared bound from the same expression, so the
# floats are identical — belongs to exactly one of them. An anchor inside its polygon always
# has its polygon on the same tile, so the label sublayer never outlives the geometry one.
_LABELLED_TILE_FUNCTION = """
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
         where t.geom && ST_Transform(ST_TileEnvelope(z, x, y), 4326)),
    anchor as materialized (
        select ST_Transform(ST_PointOnSurface(t.geom), {mercator}) as pt,
               {columns}
          from {source} t
         where t.geom && ST_Transform(ST_TileEnvelope(z, x, y), 4326)),
    owned as materialized (
        select ST_AsMVTGeom(anchor.pt, ST_TileEnvelope(z, x, y), {extent}, {buffer}, true)
                   as geom,
               {bare_columns}
          from anchor
         where ST_X(anchor.pt) >= ST_XMin(ST_TileEnvelope(z, x, y))
           and ST_X(anchor.pt) <  ST_XMax(ST_TileEnvelope(z, x, y))
           and ST_Y(anchor.pt) >= ST_YMin(ST_TileEnvelope(z, x, y))
           and ST_Y(anchor.pt) <  ST_YMax(ST_TileEnvelope(z, x, y)))
    select (select ST_AsMVT(feature, '{name}', {extent}, 'geom')
              from feature where feature.geom is not null)
           || coalesce((select ST_AsMVT(owned, '{name}_label', {extent}, 'geom')
                          from owned where owned.geom is not null), ''::bytea)
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
    template = _LABELLED_TILE_FUNCTION if layer.label_points else _TILE_FUNCTION
    return template.format(
        name=layer.name,
        source=tile_source_sql(layer),
        geom=tile_geometry_sql(layer),
        mercator=WEB_MERCATOR,
        extent=TILE_EXTENT,
        buffer=TILE_BUFFER,
        columns=", ".join(f"t.{column}" for column in layer.columns),
        bare_columns=", ".join(layer.columns),
    )


def install_tile_functions(connection: psycopg.Connection) -> tuple[str, ...]:
    """Create or replace every layer's MVT function. Its relation must already exist."""
    with connection.cursor() as cursor:
        for layer in TILE_LAYERS:
            cursor.execute(tile_function_sql(layer))
    return tuple(layer.name for layer in TILE_LAYERS)
