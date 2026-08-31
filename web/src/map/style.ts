import type { LayerSpecification, SourceSpecification } from "maplibre-gl";

import { tileUrl } from "../api/client.ts";
import type { BasemapVariant } from "./basemap.ts";
import { DISPOSAL_COLOUR, disposalFilter } from "./disposal.ts";
import {
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
import type { VariantStyle } from "./variant-style.ts";

export const WELLS_SOURCE = "nd_wells";
export const LATERALS_SOURCE = "nd_laterals";
export const SPACING_SOURCE = "nd_spacing_units";
export const TX_WELLS_SOURCE = "tx_wells";
export const TX_LATERALS_SOURCE = "tx_laterals";
// A point source and no lateral sibling: no in-scope New Mexico source ships one, and
// cr_nm_wellhistory_geometry_scope_1 is the row that says so.
export const NM_WELLS_SOURCE = "nm_wells";
export const MT_WELLS_SOURCE = "mt_wells";
// Not `mt_laterals`: the source carries laterals, sidetracks and vertical wellbores alike, and
// cr_mt_paths_geometry_class_1 keeps the map-stick class off the lateral vocabulary.
export const MT_PATHS_SOURCE = "mt_paths";
export const TRACES_SOURCE = "nd_survey_traces";
export const TOWNSHIPS_SOURCE = "land_townships";
export const SECTIONS_SOURCE = "land_sections";

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

/** Published zoom thresholds: geometry at 8/10, labels at 9/12 — stated on the registry rows. */
export const TOWNSHIP_MIN_ZOOM = 8;
export const SECTION_MIN_ZOOM = 10;
const TOWNSHIP_LABEL_MIN_ZOOM = 9;
const SECTION_LABEL_MIN_ZOOM = 12;
const SPACING_UNIT_LABEL_MIN_ZOOM = 11;

/** One point layer per wells-family row; registry.test.ts holds the two in step as states land. */
export const WELL_POINT_LAYERS = ["wells", "tx-wells", "nm-wells", "mt-wells"] as const;

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
    ["wells", WELLS_SOURCE, "api10"],
    ["laterals", LATERALS_SOURCE, "api10"],
    ["spacing", SPACING_SOURCE, "api10"],
    ["tx_wells", TX_WELLS_SOURCE, "api10"],
    ["tx_laterals", TX_LATERALS_SOURCE, "api10"],
    ["nm_wells", NM_WELLS_SOURCE, "api10"],
    ["mt_wells", MT_WELLS_SOURCE, "api10"],
    ["mt_paths", MT_PATHS_SOURCE, "api10"],
    ["traces", TRACES_SOURCE, "api10"],
    // The land grid's identity is the publisher's unit id, not a well spine key.
    ["townships", TOWNSHIPS_SOURCE, "land_unit_id"],
    ["sections", SECTIONS_SOURCE, "land_unit_id"],
    ["township_metrics", METRICS_TOWNSHIPS_SOURCE, "land_unit_id"],
    ["section_metrics", METRICS_SECTIONS_SOURCE, "land_unit_id"],
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

export function dataLayers(options: DataLayerOptions = {}): LayerSpecification[] {
  const hollow = options.hollowFill ?? INK;
  const variant = options.variant ?? "dark";
  const tokens = variantStyle(variant);
  const wells = publishedSource("wells", WELLS_SOURCE, options.search);
  const laterals = publishedSource("laterals", LATERALS_SOURCE, options.search);
  const spacing = publishedSource("spacing", SPACING_SOURCE, options.search);
  const txWells = publishedSource("tx_wells", TX_WELLS_SOURCE, options.search);
  const txLaterals = publishedSource("tx_laterals", TX_LATERALS_SOURCE, options.search);
  const nmWells = publishedSource("nm_wells", NM_WELLS_SOURCE, options.search);
  const mtWells = publishedSource("mt_wells", MT_WELLS_SOURCE, options.search);
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

  const built: LayerSpecification[] = [
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
    {
      id: "wells",
      type: "circle",
      source: wells,
      "source-layer": wells,
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
    },
    {
      id: "wells-struck",
      type: "symbol",
      source: wells,
      "source-layer": wells,
      minzoom: 11,
      filter: inSet(statusProperty(), [...STRUCK_STATUSES]),
      layout: {
        "icon-image": "gw-strike",
        // A well symbol is a data mark, not a label: collision placement would drop marks
        // silently, which is the same defect class as an unlabelled status.
        "icon-allow-overlap": true,
        "icon-ignore-placement": true,
        "icon-size": interpolate(zoom, [
          [11, 0.55],
          [15, 1],
        ]) as unknown as number,
      },
    },
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
    {
      id: "tx-wells",
      type: "circle",
      source: txWells,
      "source-layer": txWells,
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
    },
    {
      // No struck sibling: the strike marks a status class, and every New Mexico
      // status_canonical is null under cr_nm_wellhistory_status_vocab_1 — the OCD publishes
      // no codebook — so the class can never be matched and the layer would be dead.
      id: "nm-wells",
      type: "circle",
      source: nmWells,
      "source-layer": nmWells,
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
    },
    {
      // Montana draws from the same expressions as the other two, and unlike New Mexico it has
      // a codebook to draw from: cr_mt_gis_status_vocab_1 maps thirteen of nineteen MBOGC
      // values and quarantines the other six rather than defaulting them to active.
      id: "mt-wells",
      type: "circle",
      source: mtWells,
      "source-layer": mtWells,
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
    },
    {
      // A struck sibling, where New Mexico has none: 63% of Montana's mapped wells are plugged,
      // so the class the strike marks is the largest one on this canvas.
      id: "mt-wells-struck",
      type: "symbol",
      source: mtWells,
      "source-layer": mtWells,
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
    },
    {
      id: "tx-wells-struck",
      type: "symbol",
      source: txWells,
      "source-layer": txWells,
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
    },
  ];

  if (options.labels) {
    built.push(
      unitLabelLayer("land-townships-label", townships, TOWNSHIP_LABEL_MIN_ZOOM, SPACING_LABEL_SIZE, tokens),
      unitLabelLayer("land-sections-label", sections, SECTION_LABEL_MIN_ZOOM, SPACING_LABEL_SIZE - 1, tokens),
      unitLabelLayer("spacing-units-label", spacing, SPACING_UNIT_LABEL_MIN_ZOOM, SPACING_LABEL_SIZE, tokens),
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
function unitLabelLayer(
  id: string,
  source: string,
  minzoom: number,
  size: number,
  tokens: VariantStyle,
): LayerSpecification {
  return {
    id,
    type: "symbol",
    source,
    "source-layer": `${source}_label`,
    minzoom,
    layout: {
      "text-field": ["coalesce", ["get", "label"], ""],
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
