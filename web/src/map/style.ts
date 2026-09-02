import type { LayerSpecification, SourceSpecification } from "maplibre-gl";

import { tileUrl } from "../api/client.ts";
import type { BasemapVariant } from "./basemap.ts";
import { DISPOSAL_COLOUR, disposalFilter } from "./disposal.ts";
import {
  all,
  any,
  coalesce,
  featureState,
  get,
  inSet,
  interpolate,
  not,
  step,
  toNumber,
  when,
  zoom,
} from "./expr.ts";
import type { Expr } from "./expr.ts";
import {
  SELECTION_COLOUR,
  STATUS_CLASSES,
  STRUCK_STATUSES,
  UNMAPPED_STATUS,
  statusColourExpression,
  statusFillExpression,
  statusIds,
  statusProperty,
} from "./status.ts";
import {
  METRICS_HANDOFF_ZOOM,
  METRICS_SECTIONS_SOURCE,
  METRICS_TOWNSHIPS_SOURCE,
  TOWNSHIP_METRICS_MIN_ZOOM,
  liquidFillColour,
  observedFilter,
} from "./thematics.ts";
import { LINE_ROLE, VARIANT_STYLES, rgba, variantStyle } from "./variant-style.ts";
import WELLS_ROSTER_JSON from "./wells-roster.json";
import type { VariantStyle } from "./variant-style.ts";

export interface WellsRosterRow {
  /** The registry's own code, e.g. ND. */
  readonly code: string;
  /** The style layer id of the point layer, and the stem of its struck sibling. */
  readonly id: string;
  readonly styleLayers: readonly string[];
  /** The published tile function this row draws from. */
  readonly tileLayerId: string;
  readonly drawOrder: number;
  readonly defaultOn: boolean;
}

/**
 * The wells rows as the registry publishes them: layer id, style layers, tile source, draw
 * order and first-paint default, one entry per registration. Four parallel constants and four
 * copies of one layer definition stood here, and none of them was a shape any gate could read
 * — a fifth jurisdiction was a hand edit in each.
 */
export const WELLS_ROSTER: readonly WellsRosterRow[] = WELLS_ROSTER_JSON;

/** The tile source each wells row draws from, keyed by its style layer id. */
export const WELLS_SOURCE_BY_LAYER: Readonly<Record<string, string>> = Object.fromEntries(
  WELLS_ROSTER.map((row) => [row.id, row.tileLayerId]),
);

/** The query parameter that overrides a wells source. `nd-wells` never existed: the founding
 *  row's layer id is the bare `wells`, and the parameter follows the layer rather than the
 *  source so a saved permalink keeps working. */
const sourceParameter = (row: WellsRosterRow): string => row.id.split("-").join("_");

/** The disposal ring is a North Dakota well-type fact and reads the row that carries it:
 *  the lowest draw order, which is the founding registration by construction. */
const DEFAULT_WELLS_SOURCE = WELLS_ROSTER[0]!.tileLayerId;

export const LATERALS_SOURCE = "nd_laterals";
export const SPACING_SOURCE = "nd_spacing_units";
export const TX_LATERALS_SOURCE = "tx_laterals";
// Not `mt_laterals`: the source carries laterals, sidetracks and vertical wellbores alike, and
// cr_mt_paths_geometry_class_1 keeps the map-stick class off the lateral vocabulary.
export const MT_PATHS_SOURCE = "mt_paths";
export const TRACES_SOURCE = "nd_survey_traces";
export const TOWNSHIPS_SOURCE = "land_townships";
export const SECTIONS_SOURCE = "land_sections";
// Two sources over one mart, because `marts.tile_basins` and `marts.tile_plays` are two
// published functions: a play surface is never handed to a style that reads a basin
// (cr_eia_boundary_taxonomy_1).
export const BASINS_SOURCE = "basins";
export const PLAYS_SOURCE = "plays";

/**
 * Provenance-keyed, not status-keyed: what this layer distinguishes is the filed survey path
 * from the GIS centreline, and painting it from the status vocabulary would erase exactly
 * that distinction wherever a trace overlies its own lateral. Orchid is in neither the
 * status palette nor the selection cyan; 6.2:1 on the dark substrate.
 */
export const TRACE_COLOUR = "#C878D2";

/**
 * Reference linework, so a neutral that cannot read as a data claim: BRAND.md's Muted, an
 * achromatic grey (1.13:1 against oil green and gas red, 1.03:1 against water blue — too
 * close to any stream colour to be mistaken for one, and in neither the status palette nor
 * the selection cyan). Clears the 3:1 non-text minimum on the dark and light substrates
 * (5.25:1 and 3.20:1); the per-variant `grid` token in variant-style.ts carries the
 * variants this one colour could not (satellite), and this export is the swatch's colour.
 */
export const LAND_GRID_COLOUR = VARIANT_STYLES.dark.grid;

/**
 * State-scale polygons, so the frame draws from the lowest zoom the map allows: a basin
 * outline is most useful where the reader cannot yet see a well. The names come off above
 * the band where the polygon is wider than the viewport and the label would sit off-screen.
 */
export const BOUNDARY_MIN_ZOOM = 3;
const BASIN_LABEL_MAX_ZOOM = 9;

/**
 * The geological frame's swatch colour, which is the dark substrate's token: a swatch is one
 * mark and the canvas has four substrates, so the panel shows the one the app opens on. The
 * variant pass owns what actually renders (variant-style.ts).
 */
export const GEOLOGY_FRAME_COLOUR = VARIANT_STYLES.dark.geology;

/** Published zoom thresholds: geometry at 8/10, labels at 9/12 — stated on the registry rows. */
export const TOWNSHIP_MIN_ZOOM = 8;
export const SECTION_MIN_ZOOM = 10;
const TOWNSHIP_LABEL_MIN_ZOOM = 9;
const SECTION_LABEL_MIN_ZOOM = 12;
const SPACING_UNIT_LABEL_MIN_ZOOM = 11;

/** One point layer per wells-family row, in registered draw order. */
export const WELL_POINT_LAYERS: readonly string[] = WELLS_ROSTER.map((row) => row.id);

const INK = "#0B1014";
const SPACING_LABEL_SIZE = 10;

/**
 * Both basins' laterals, gated together because one row toggles them. Declared here as well as
 * on the registry row — style.test.ts holds the two equal — because this is the copy the source
 * floor is derived from, and it is what keeps a 2 MB z7 tile off the wire below the gate.
 */
const LATERAL_MIN_ZOOM = 8;

/**
 * The shape martin publishes a source id in — a Postgres table name, which is what the
 * override is choosing between. Anchored with no `m` flag, so a trailing newline is refused.
 */
export const SOURCE_ID = /^[a-z][a-z0-9_]{0,63}$/;

/**
 * N-5. The id is interpolated into the tile path, the MVT `source-layer` and the `promoteId`
 * key, so an unvalidated one leaves the `/v1/tiles/` namespace entirely: Track O reproduced
 * `?wells=..%2F..%2Fetc%2Fpasswd` fetching `/etc/passwd/{z}/{x}/{y}.pbf`. Anything that is
 * not a published id falls back rather than failing, so a bad link still renders the map.
 */
export function publishedSource(parameter: string, fallback: string, search?: string): string {
  const query = search ?? (typeof window === "undefined" ? "" : window.location.search);
  const requested = new URLSearchParams(query).get(parameter);
  return requested !== null && SOURCE_ID.test(requested) ? requested : fallback;
}

/** Same-origin by default. Not `new URL()`: it percent-encodes MapLibre's {z}/{x}/{y}. */
export function absoluteTileUrl(template: string, origin?: string): string {
  if (/^https?:\/\//i.test(template)) return template;
  const base = origin ?? (typeof window === "undefined" ? "" : window.location.origin);
  return `${base}${template}`;
}

/**
 * The lowest zoom any layer draws this source at. A source that fetches below it pays for
 * tiles nothing can render: the spacing units start at z8, and their z7 tile is 568 KB
 * (work-output/tileperf-client-handoff.md item 1). Derived rather than tabulated, so a layer
 * added at a lower zoom pulls its source down with it instead of rendering nothing.
 */
function lowestDrawnZoom(source: string, search?: string): number {
  const drawn = dataLayers({ labels: true, ...(search === undefined ? {} : { search }) })
    .filter((layer) => "source" in layer && layer.source === source)
    .map((layer) => layer.minzoom ?? 0);
  return drawn.length > 0 ? Math.min(...drawn) : 0;
}

export function sourceSpecs(origin?: string, search?: string): Record<string, SourceSpecification> {
  const specs: Record<string, SourceSpecification> = {};
  for (const [parameter, fallback, featureId] of [
    ...WELLS_ROSTER.map(
      (row) => [sourceParameter(row), row.tileLayerId, "api10"] as [string, string, string],
    ),
    ["laterals", LATERALS_SOURCE, "api10"],
    ["spacing", SPACING_SOURCE, "api10"],
    ["tx_laterals", TX_LATERALS_SOURCE, "api10"],
    ["mt_paths", MT_PATHS_SOURCE, "api10"],
    ["traces", TRACES_SOURCE, "api10"],
    // The land grid's identity is the publisher's unit id, not a well spine key.
    ["townships", TOWNSHIPS_SOURCE, "land_unit_id"],
    ["sections", SECTIONS_SOURCE, "land_unit_id"],
    ["township_metrics", METRICS_TOWNSHIPS_SOURCE, "land_unit_id"],
    ["section_metrics", METRICS_SECTIONS_SOURCE, "land_unit_id"],
    // A boundary's identity is EIA's own feature id, which is what the mart keys on.
    ["basins", BASINS_SOURCE, "boundary_id"],
    ["plays", PLAYS_SOURCE, "boundary_id"],
  ] as const) {
    const name = publishedSource(parameter, fallback, search);
    specs[name] = {
      type: "vector",
      tiles: [absoluteTileUrl(tileUrl(name), origin)],
      minzoom: lowestDrawnZoom(name, search),
      maxzoom: 14,
      // The feature id is a string, so MapLibre cannot use it without promoteId, and
      // without a feature id there is no feature-state and no selection without a
      // duplicate filter layer per source.
      promoteId: { [name]: featureId },
    };
  }
  return specs;
}

/**
 * Marks the layers whose filter slot belongs to the status gate. Read off the built layers
 * rather than kept as a list of ids beside them: a hand list is what left a second basin's
 * layers ungated at style-build time until the reader happened to zoom (gate-inc3 4.1).
 */
const STATUS_GATE = "gw:status-gate";
const STATUS_GATED = { [STATUS_GATE]: true } as const;

/**
 * Names the paint property a row's opacity slider drives where the type's default is wrong:
 * the disposal ring's `circle-opacity` paints a fill that is transparent by design, so a
 * slider writing it would move nothing the reader can see.
 */
export const OPACITY_OVERRIDE = "gw:opacity-property";

export function statusStyledLayerIds(
  layers: readonly LayerSpecification[] = dataLayers({ labels: true }),
): string[] {
  return layers
    .filter((layer) => (layer.metadata as Record<string, unknown> | undefined)?.[STATUS_GATE])
    .map((layer) => layer.id);
}

export function visibleStatusesAt(atZoom: number): string[] {
  return STATUS_CLASSES.filter((status) => atZoom >= status.minZoom).map((status) => status.id);
}

/**
 * The rendered set is the zoom gate intersected with the legend's own filter. The unmapped
 * class is never withdrawn by the *zoom* — a defect that disappears at low zoom is worse than
 * one that shows — but the reader can switch it off, because on some slices it is the largest
 * class on the canvas and unfilterable ink is ink nobody can account for.
 */
export function statusFilter(atZoom: number, on: ReadonlySet<string>): Expr {
  const named = inSet(statusProperty(), visibleStatusesAt(atZoom).filter((id) => on.has(id)));
  if (!on.has(UNMAPPED_STATUS.id)) return named;
  // The absence class is anything the vocabulary cannot name — the rule `statusClass()` applies
  // when counting. Matching the literal id instead let a well with an unknown *present* status
  // fall out of the map, the count and the legend at once, with nothing saying so.
  return any(named, not(inSet(statusProperty(), statusIds())));
}

/** One bucket of the Wells-By panel, applied to the canvas. One value: `wb.pick` is one press. */
export interface FacetSelection {
  dimension: string;
  value: string;
}

/**
 * The tile property each Wells-By dimension filters the canvas by. A dimension absent from this
 * table cannot filter at all: `completion_year` rides one tile layer of thirteen and
 * `geometry_provenance` three, so a press on either would narrow one state and leave the rest
 * whole — which reads as "Texas has no wells of this year" rather than as a partial filter.
 */
export const FACET_TILE_PROPERTY: Readonly<Record<string, string>> = {
  operator: "operator_name",
  status: "status_canonical",
  well_type: "well_type_reported",
  county: "county_code",
};

export interface FacetLayer {
  id: string;
  /** The published tile layer it reads, which is what decides the columns it can filter on. */
  source: string;
  /** Whether the status gate owns this layer's filter slot, or the layer's own predicate does. */
  gated: boolean;
}

/**
 * Every style layer that draws a well or its bore, in draw order. Seven belong to the status
 * gate; the other five carry a predicate of their own — the strike's status set, the disposal
 * ring's type set, the trace layer's nothing — and a press that only rewrote the gate would
 * leave struck plugs, disposal rings and survey traces painted for the operator just filtered
 * away. facet-filter.test.ts holds this list against `dataLayers()` in both directions.
 */
export const FACET_FILTERED_LAYERS: readonly FacetLayer[] = [
  { id: "laterals", source: LATERALS_SOURCE, gated: true },
  { id: "survey-traces", source: TRACES_SOURCE, gated: false },
  { id: "mt-paths", source: MT_PATHS_SOURCE, gated: true },
  { id: "tx-laterals", source: TX_LATERALS_SOURCE, gated: true },
  // The point layer is gated by the status filter and its struck sibling is not: the strike
  // marks a class the filter may have just removed, and repainting it would contradict the
  // press. Two rows per registration, and the disposal ring reads the founding row's source.
  ...WELLS_ROSTER.flatMap((row) => [
    { id: row.id, source: row.tileLayerId, gated: true },
    { id: `${row.id}-struck`, source: row.tileLayerId, gated: false },
  ]),
  { id: "disposal-wells", source: DEFAULT_WELLS_SOURCE, gated: false },
];

/**
 * The facet-bearing columns each tile layer publishes. `marts/tiles.py` is the source of truth
 * — its `TileLayer.properties` tuple is the publication boundary — and this is the browser's
 * copy of it, held equal by facet-filter.test.ts, which parses the Python rather than restating
 * it. Operator and status are on all twelve; well type is on the four point layers only; county
 * is Texas and New Mexico.
 */
export const TILE_FACET_PROPERTIES: Readonly<Record<string, readonly string[]>> = {
  [WELLS_SOURCE_BY_LAYER["wells"]!]: ["operator_name", "status_canonical", "well_type_reported"],
  [LATERALS_SOURCE]: ["operator_name", "status_canonical"],
  [TRACES_SOURCE]: ["operator_name", "status_canonical"],
  [WELLS_SOURCE_BY_LAYER["tx-wells"]!]: ["operator_name", "status_canonical", "well_type_reported", "county_code"],
  [TX_LATERALS_SOURCE]: ["operator_name", "status_canonical", "county_code"],
  [WELLS_SOURCE_BY_LAYER["nm-wells"]!]: ["operator_name", "status_canonical", "well_type_reported", "county_code"],
  [WELLS_SOURCE_BY_LAYER["mt-wells"]!]: ["operator_name", "status_canonical", "well_type_reported"],
  [WELLS_SOURCE_BY_LAYER["co-wells"]!]: [
    "operator_name",
    "status_canonical",
    "well_type_reported",
    "county_code",
  ],
  [MT_PATHS_SOURCE]: ["operator_name", "status_canonical"],
};

/**
 * The tile pyramid keeps one feature per half CSS pixel at and below this zoom, ranked by
 * md5(api10) — `marts/tiles.py` THIN_MAX_ZOOM and THIN_PIXELS, held equal to the Python by
 * facet-pill.test.ts. The canvas is a sample down there, which nothing in this app has ever
 * said on screen, and a filtered canvas is a sample of a sample.
 */
export const TILE_THIN_MAX_ZOOM = 7;
export const TILE_THIN_PIXELS = 0.5;

/** The property this layer can filter `dimension` by, or null where its tile publishes none. */
export function facetTileProperty(layerId: string, dimension: string): string | null {
  const property = FACET_TILE_PROPERTY[dimension];
  const layer = FACET_FILTERED_LAYERS.find((entry) => entry.id === layerId);
  if (!property || !layer) return null;
  return TILE_FACET_PROPERTIES[layer.source]?.includes(property) ? property : null;
}

/** Whether any layer on the canvas can narrow by this dimension; a press on one that cannot is
 *  a control that would look clickable and narrow nothing. */
export function facetFilterable(dimension: string): boolean {
  return FACET_FILTERED_LAYERS.some((layer) => facetTileProperty(layer.id, dimension) !== null);
}

/** The layers a press on this dimension leaves drawing unfiltered, in draw order, so the pill
 *  can name them rather than leave the reader to notice the difference. */
export function facetUnfilteredLayers(dimension: string): string[] {
  return FACET_FILTERED_LAYERS.filter(
    (layer) => facetTileProperty(layer.id, dimension) === null,
  ).map((layer) => layer.id);
}

/** The press as a predicate over one layer, or null where the layer cannot carry it. */
export function facetPredicate(layerId: string, facet: FacetSelection | null): Expr | null {
  if (!facet) return null;
  const property = facetTileProperty(layerId, facet.dimension);
  return property === null ? null : inSet(get(property), [facet.value]);
}

let ownFilters: Map<string, Expr | undefined> | null = null;

/**
 * What an ungated well layer's filter slot already holds. Read off `dataLayers()` rather than
 * restated, so a press conjoins onto the live predicate and cannot drift from it; memoised
 * because these predicates are constants and this is called on every frame of a pinch.
 */
function declaredFilter(layerId: string): Expr | undefined {
  if (!ownFilters) {
    ownFilters = new Map(
      dataLayers().map((layer) => [
        layer.id,
        ("filter" in layer ? layer.filter : undefined) as Expr | undefined,
      ]),
    );
  }
  return ownFilters.get(layerId);
}

/**
 * The whole filter slot for one well layer: its own gate conjoined with the facet press.
 *
 * One expression rather than two writes, because `map.setFilter` replaces a layer's filter
 * whole and the map rewrites the status gate on every `zoom` event — a press written into the
 * slot separately is clobbered on the next frame of a pinch, which is the defect this signature
 * exists to make unrepresentable. `undefined` means the slot should hold no filter at all.
 */
export function wellFilter(
  atZoom: number,
  on: ReadonlySet<string>,
  facet: FacetSelection | null,
  layerId: string,
): Expr | undefined {
  const gated = FACET_FILTERED_LAYERS.find((layer) => layer.id === layerId)?.gated === true;
  const gate = gated ? statusFilter(atZoom, on) : declaredFilter(layerId);
  const press = facetPredicate(layerId, facet);
  if (!press) return gate;
  return gate ? all(gate, press) : press;
}

function selectable<T>(selected: T, base: T | Expr): Expr {
  return when([[featureState("selected"), selected]], base as T);
}

// martin serves a Postgres `numeric` as an MVT string, so the raw property is not a number
// and every interpolation over it silently falls back to its base value.
const LATERAL_LENGTH = toNumber(coalesce(get("lateral_length_ft"), 0));

/**
 * Zoom stays at the top of every size ramp: the style spec allows exactly one zoom-driven
 * `step`/`interpolate` per expression and it may not sit inside a `case`, so the selection
 * branch is folded into each stop rather than wrapped around the ramp.
 */
function lateralWidth(): Expr {
  const byLength = (thin: number, thick: number, selected: number): Expr =>
    selectable(
      selected,
      interpolate(LATERAL_LENGTH, [
        [0, thin],
        [12_000, thick],
      ]),
    );
  return interpolate(zoom, [
    [5, byLength(0.25, 0.5, 2)],
    [9, byLength(0.6, 1.4, 3.5)],
    [12, byLength(1.2, 2.8, 5)],
    [15, byLength(2.4, 5.5, 7)],
  ]);
}

/**
 * Zoom-only, because the Montana paths mart publishes no length: cr_mt_basin_scope_1 leaves the
 * state untagged and `lengths` is keyed by basin, so there is no registered method to measure
 * one with. A ramp reading `lateral_length_ft` here would coalesce every path to zero and draw
 * the whole state at the thin end while looking like it varied. Mid-ramp against a lateral, and
 * the same selected weights, so the two line layers stay comparable.
 */
function pathWidth(): Expr {
  return interpolate(zoom, [
    [8, selectable(3.5, 1)],
    [12, selectable(5, 2)],
    [15, selectable(7, 4)],
  ]);
}

/** Finer than a lateral at every stop: the trace is the precise path, not the emphasis. */
function traceWidth(): Expr {
  return interpolate(zoom, [
    [8, selectable(2.5, 1)],
    [12, selectable(4, 1.8)],
    [15, selectable(6, 3)],
  ]);
}

function wellRadius(): Expr {
  return step(zoom, selectable(3, 0.9), [
    [6, selectable(4, 1.2)],
    [8, selectable(5, 1.9)],
    [10, selectable(6, 3)],
    [13, selectable(9, 5)],
    [15, selectable(11, 6.5)],
  ]);
}

/**
 * Outside the wellhead at every stop, selected or not: the ring marks the same feature the
 * dot draws, so the selection radius must never swallow it.
 */
function disposalRingRadius(): Expr {
  return step(zoom, selectable(6.5, 3.5), [
    [10, selectable(7.5, 4.5)],
    [13, selectable(10.5, 6.5)],
    [15, selectable(12.5, 8.5)],
  ]);
}

export interface DataLayerOptions {
  /** Text layers need a `glyphs` url; without the font assets they are omitted, not broken. */
  labels?: boolean;
  /** Hollow glyphs are a ring over the substrate, so the fill follows the basemap. */
  hollowFill?: string;
  /** The basemap under the data, which is what its labels and outlines are coloured against. */
  variant?: BasemapVariant;
  /** Query string the source overrides are read from; the window's own when absent. */
  search?: string;
}

/** A registration's point layer. Every jurisdiction draws from the same status expressions:
 *  the vocabulary is canonical and the rule each class cites is the registry's. */
function wellPointLayer(
  row: WellsRosterRow, source: string, hollow: string,
): LayerSpecification {
  return {
    id: row.id,
    type: "circle",
    source,
    "source-layer": source,
    minzoom: 4,
    metadata: STATUS_GATED,
    paint: {
      "circle-color": selectable(SELECTION_COLOUR, statusFillExpression(hollow)),
      "circle-stroke-color": selectable(SELECTION_COLOUR, statusColourExpression()),
      "circle-stroke-width": interpolate(zoom, [
        [4, 0.4],
        [9, 0.7],
        [12, 1.2],
      ]),
      "circle-radius": wellRadius(),
    },
  };
}

/** The strike over a plugged wellbore. A well symbol is a data mark, not a label: collision
 *  placement would drop marks silently, which is the same defect class as an unlabelled
 *  status. */
function wellStruckLayer(row: WellsRosterRow, source: string): LayerSpecification {
  return {
    id: `${row.id}-struck`,
    type: "symbol",
    source,
    "source-layer": source,
    minzoom: 11,
    filter: inSet(statusProperty(), [...STRUCK_STATUSES]),
    layout: {
      "icon-image": "gw-strike",
      "icon-allow-overlap": true,
      "icon-ignore-placement": true,
      "icon-size": interpolate(zoom, [
        [11, 0.55],
        [15, 1],
      ]) as unknown as number,
    },
  };
}

export function dataLayers(options: DataLayerOptions = {}): LayerSpecification[] {
  const hollow = options.hollowFill ?? INK;
  const variant = options.variant ?? "dark";
  const tokens = variantStyle(variant);
  // One resolved source per registration, keyed by layer id: a fifth row needs no line here.
  const wellsSources: Record<string, string> = Object.fromEntries(
    WELLS_ROSTER.map((row) => [
      row.id,
      publishedSource(sourceParameter(row), row.tileLayerId, options.search),
    ]),
  );
  const wells = wellsSources["wells"]!;
  const laterals = publishedSource("laterals", LATERALS_SOURCE, options.search);
  const spacing = publishedSource("spacing", SPACING_SOURCE, options.search);
  const txLaterals = publishedSource("tx_laterals", TX_LATERALS_SOURCE, options.search);
  const mtPaths = publishedSource("mt_paths", MT_PATHS_SOURCE, options.search);
  const traces = publishedSource("traces", TRACES_SOURCE, options.search);
  const townships = publishedSource("townships", TOWNSHIPS_SOURCE, options.search);
  const sections = publishedSource("sections", SECTIONS_SOURCE, options.search);
  const townshipMetrics = publishedSource(
    "township_metrics", METRICS_TOWNSHIPS_SOURCE, options.search,
  );
  const sectionMetrics = publishedSource(
    "section_metrics", METRICS_SECTIONS_SOURCE, options.search,
  );
  const basins = publishedSource("basins", BASINS_SOURCE, options.search);
  const plays = publishedSource("plays", PLAYS_SOURCE, options.search);

  const built: LayerSpecification[] = [
    {
      // The frame under the framework: a basin is the largest thing on the canvas and the
      // wash is what says where its edge is at a zoom where the outline is off-screen. The
      // alpha rides the colour rather than `fill-opacity`, which the row's slider owns.
      id: "basins-fill",
      type: "fill",
      source: basins,
      "source-layer": basins,
      minzoom: BOUNDARY_MIN_ZOOM,
      paint: { "fill-color": rgba(GEOLOGY_FRAME_COLOUR, 0.05) },
    },
    {
      id: "basins-line",
      type: "line",
      source: basins,
      "source-layer": basins,
      minzoom: BOUNDARY_MIN_ZOOM,
      metadata: { [LINE_ROLE]: "geology" },
      paint: {
        "line-color": GEOLOGY_FRAME_COLOUR,
        "line-width": interpolate(zoom, [
          [BOUNDARY_MIN_ZOOM, 0.8],
          [8, 1.4],
          [12, 2],
        ]),
        "line-opacity": 0.75,
      },
    },
    {
      // Dashed and finer than the basin it sits inside: two objects, one frame colour, told
      // apart by register the way a nested boundary always is. A second hue would claim a
      // difference in kind that cr_eia_boundary_taxonomy_1 does not make.
      id: "plays-line",
      type: "line",
      source: plays,
      "source-layer": plays,
      minzoom: BOUNDARY_MIN_ZOOM,
      metadata: { [LINE_ROLE]: "geology" },
      paint: {
        "line-color": GEOLOGY_FRAME_COLOUR,
        "line-width": interpolate(zoom, [
          [BOUNDARY_MIN_ZOOM, 0.5],
          [8, 0.9],
          [12, 1.3],
        ]),
        "line-dasharray": [3, 2],
        "line-opacity": 0.7,
      },
    },
    {
      // The thematic wash under every mark and line: an aggregate is context, never cover.
      // Support rides in the colour's own alpha (thematics.ts), so the row's opacity slider
      // keeps the fill-opacity slot and dims the whole surface without erasing the support
      // signal. Township grain to the handoff zoom, then sections; filters keep unobserved
      // cells unpainted rather than bottom-binned.
      id: "land-township-metrics-fill",
      type: "fill",
      source: townshipMetrics,
      "source-layer": townshipMetrics,
      minzoom: TOWNSHIP_METRICS_MIN_ZOOM,
      maxzoom: METRICS_HANDOFF_ZOOM,
      filter: observedFilter(),
      paint: { "fill-color": liquidFillColour() },
    },
    {
      id: "land-section-metrics-fill",
      type: "fill",
      source: sectionMetrics,
      "source-layer": sectionMetrics,
      minzoom: METRICS_HANDOFF_ZOOM,
      filter: observedFilter(),
      paint: { "fill-color": liquidFillColour() },
    },
    {
      // Reference linework under everything: the grid is what the data sits on, never over.
      id: "land-townships-line",
      type: "line",
      source: townships,
      "source-layer": townships,
      minzoom: TOWNSHIP_MIN_ZOOM,
      metadata: { [LINE_ROLE]: "grid" },
      paint: {
        "line-color": tokens.grid,
        "line-width": interpolate(zoom, [
          [TOWNSHIP_MIN_ZOOM, 0.5],
          [12, 1],
          [15, 1.6],
        ]),
        "line-opacity": 0.9,
      },
    },
    {
      // Finer than the township it subdivides, and gated two zooms deeper: a z8 tile over
      // the basin holds thousands of sections and nothing at that scale can read them.
      id: "land-sections-line",
      type: "line",
      source: sections,
      "source-layer": sections,
      minzoom: SECTION_MIN_ZOOM,
      metadata: { [LINE_ROLE]: "grid" },
      paint: {
        "line-color": tokens.grid,
        "line-width": interpolate(zoom, [
          [SECTION_MIN_ZOOM, 0.3],
          [13, 0.8],
          [15, 1.2],
        ]),
        "line-opacity": 0.7,
      },
    },
    {
      id: "spacing-units-fill",
      type: "fill",
      source: spacing,
      "source-layer": spacing,
      minzoom: 8,
      // No `fill-opacity`: the layer panel's slider writes that one, and would replace it.
      paint: { "fill-color": rgba(tokens.spacingFill, tokens.spacingFillAlpha) },
    },
    {
      id: "spacing-units-line",
      type: "line",
      source: spacing,
      "source-layer": spacing,
      minzoom: 8,
      paint: {
        "line-color": selectable(SELECTION_COLOUR, tokens.spacing),
        "line-width": interpolate(zoom, [
          [8, 0.4],
          [13, 1.2],
        ]),
      },
    },
    {
      id: "laterals",
      type: "line",
      source: laterals,
      "source-layer": laterals,
      minzoom: LATERAL_MIN_ZOOM,
      metadata: STATUS_GATED,
      paint: {
        "line-color": selectable(SELECTION_COLOUR, statusColourExpression()),
        "line-width": lateralWidth(),
        "line-opacity": selectable(1, 0.85),
      },
    },
    {
      // Over the lateral it refines, under the wellhead that identifies it. Not status-gated:
      // it paints provenance, so the legend's status filter has no claim on its filter slot.
      id: "survey-traces",
      type: "line",
      source: traces,
      "source-layer": traces,
      minzoom: 8,
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": selectable(SELECTION_COLOUR, TRACE_COLOUR),
        "line-width": traceWidth(),
        "line-opacity": selectable(1, 0.9),
      },
    },
    {
      // Status-keyed like the other filed bore lines, because Montana has a status codebook
      // and a reader compares like with like. What this layer is *of* — a centreline that may
      // be a lateral, a sidetrack or a vertical wellbore — rides on the feature's own
      // geometry_class and vertex_count, so no colour has to carry it.
      id: "mt-paths",
      type: "line",
      source: mtPaths,
      "source-layer": mtPaths,
      minzoom: LATERAL_MIN_ZOOM,
      metadata: STATUS_GATED,
      paint: {
        "line-color": selectable(SELECTION_COLOUR, statusColourExpression()),
        "line-width": pathWidth(),
        "line-opacity": selectable(1, 0.85),
      },
    },
    // One point layer per registration, in registered draw order. The four were byte-identical
    // but for their id and their source, and every one of the differences that mattered --
    // which status expressions, which radius, which gate -- was the same in all four.
    ...WELLS_ROSTER.map((row) => wellPointLayer(row, wellsSources[row.id]!, hollow)),
    {
      // A ring over the wellhead, not a second dot: the status colour stays visible inside
      // it, because a disposal well still has a status. Type-keyed, so the legend's status
      // filter has no claim on its filter slot — the slot carries the class instead. z8 for
      // the thinning reason the laterals state: below it the wells tile keeps one feature
      // per half CSS pixel with no regard for type, and a ring layer down there would be a
      // random sample of the class presented as its geography.
      id: "disposal-wells",
      type: "circle",
      source: wells,
      "source-layer": wells,
      minzoom: 8,
      filter: disposalFilter(),
      metadata: { [OPACITY_OVERRIDE]: "circle-stroke-opacity" },
      paint: {
        "circle-color": "rgba(0, 0, 0, 0)",
        "circle-stroke-color": selectable(SELECTION_COLOUR, DISPOSAL_COLOUR),
        // Selection adds weight, not just the cyan: the hue pair is close at small radii
        // (visual-m17 judgment 3), and width is the register hue does not carry.
        "circle-stroke-width": interpolate(zoom, [
          [8, selectable(2.4, 1.2)],
          [12, selectable(3, 1.6)],
          [15, selectable(3.8, 2.2)],
        ]),
        "circle-radius": disposalRingRadius(),
      },
    },
    // Texas, drawn from the same expressions as North Dakota. The status vocabulary is
    // per-source (cr_tx_status_vocab_1 there, cr_nd_status_vocab_1 here) but the canonical
    // classes are one list, so a reader compares like with like across the two basins.
    {
      id: "tx-laterals",
      type: "line",
      source: txLaterals,
      "source-layer": txLaterals,
      minzoom: LATERAL_MIN_ZOOM,
      metadata: STATUS_GATED,
      paint: {
        "line-color": selectable(SELECTION_COLOUR, statusColourExpression()),
        "line-width": lateralWidth(),
        "line-opacity": selectable(1, 0.85),
      },
    },
    // The struck siblings, in the same order. A strike is a symbol over a class the status
    // filter may have just removed, so it is ungated where the point layer is gated.
    ...WELLS_ROSTER.map((row) => wellStruckLayer(row, wellsSources[row.id]!)),
  ];

  if (options.labels) {
    built.push(
      unitLabelLayer("land-townships-label", townships, TOWNSHIP_LABEL_MIN_ZOOM, SPACING_LABEL_SIZE, tokens),
      unitLabelLayer("land-sections-label", sections, SECTION_LABEL_MIN_ZOOM, SPACING_LABEL_SIZE - 1, tokens),
      unitLabelLayer("spacing-units-label", spacing, SPACING_UNIT_LABEL_MIN_ZOOM, SPACING_LABEL_SIZE, tokens),
      // EIA names the feature `name`, not `label`: the tile publishes the publisher's column
      // rather than a renamed copy, so the layer reads what the mart actually carries.
      unitLabelLayer("basins-label", basins, BOUNDARY_MIN_ZOOM, SPACING_LABEL_SIZE + 1, tokens, {
        property: "name",
        maxzoom: BASIN_LABEL_MAX_ZOOM,
      }),
    );
  }
  return built;
}

/**
 * Every unit label is this one layer shape — VF-5 is a class, so a labelled layer added
 * later inherits the treatment instead of forking it. Binds to the tile's `_label`
 * sublayer: one anchor point per unit, emitted by the tile function in the one tile that
 * owns it; bound to the polygons instead, MapLibre placed a symbol per tile fragment and
 * every unit crossing a seam wore its name twice (visual-m14 F1). `text-size` is the base;
 * applyVariantStyling owns the per-variant bump, for these labels and the basemap's alike,
 * so the two cannot compound into a size neither declares.
 */
interface UnitLabelOptions {
  /** The tile column the text comes from, where the publisher does not call it `label`. */
  property?: string;
  /** A ceiling, for a unit wider than the viewport above it: the anchor is then off-screen. */
  maxzoom?: number;
}

function unitLabelLayer(
  id: string,
  source: string,
  minzoom: number,
  size: number,
  tokens: VariantStyle,
  options: UnitLabelOptions = {},
): LayerSpecification {
  return {
    id,
    type: "symbol",
    source,
    "source-layer": `${source}_label`,
    minzoom,
    ...(options.maxzoom === undefined ? {} : { maxzoom: options.maxzoom }),
    layout: {
      "text-field": ["coalesce", ["get", options.property ?? "label"], ""],
      "text-font": ["Noto Sans Regular"],
      "text-size": size,
      "symbol-placement": "point",
    },
    paint: {
      "text-color": tokens.primary.colour,
      "text-halo-color": tokens.primary.halo,
      "text-halo-width": tokens.primary.haloWidth,
    },
  } as LayerSpecification;
}

/** The struck-through modifier, drawn once into a canvas rather than shipped as a sprite. */
export function strikeGlyph(size = 24): ImageData | null {
  if (typeof document === "undefined") return null;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const context = canvas.getContext("2d");
  if (!context) return null;
  context.strokeStyle = "#C4D0D8";
  context.lineWidth = Math.max(1.5, size / 12);
  context.lineCap = "round";
  const inset = size * 0.22;
  context.beginPath();
  context.moveTo(inset, size - inset);
  context.lineTo(size - inset, inset);
  context.stroke();
  return context.getImageData(0, 0, size, size);
}
