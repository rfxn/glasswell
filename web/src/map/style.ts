import type { LayerSpecification, SourceSpecification } from "maplibre-gl";

import { tileUrl } from "../api/client.ts";
import type { BasemapVariant } from "./basemap.ts";
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
import { rgba, variantStyle } from "./variant-style.ts";

export const WELLS_SOURCE = "nd_wells";
export const LATERALS_SOURCE = "nd_laterals";
export const SPACING_SOURCE = "nd_spacing_units";
export const TX_WELLS_SOURCE = "tx_wells";
export const TX_LATERALS_SOURCE = "tx_laterals";

/** The point layers the legend counts from. Both basins, because the legend counts what is drawn. */
export const WELL_POINT_LAYERS = ["wells", "tx-wells"] as const;

const INK = "#0B1014";
const SPACING_LABEL_SIZE = 10;

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
  for (const [parameter, fallback] of [
    ["wells", WELLS_SOURCE],
    ["laterals", LATERALS_SOURCE],
    ["spacing", SPACING_SOURCE],
    ["tx_wells", TX_WELLS_SOURCE],
    ["tx_laterals", TX_LATERALS_SOURCE],
  ] as const) {
    const name = publishedSource(parameter, fallback, search);
    specs[name] = {
      type: "vector",
      tiles: [absoluteTileUrl(tileUrl(name), origin)],
      minzoom: lowestDrawnZoom(name, search),
      maxzoom: 14,
      // API-10 is a string, so MapLibre cannot use it as a feature id without promoteId,
      // and without a feature id there is no feature-state and no selection without a
      // duplicate filter layer per source.
      promoteId: { [name]: "api10" },
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

function wellRadius(): Expr {
  return step(zoom, selectable(3, 0.9), [
    [6, selectable(4, 1.2)],
    [8, selectable(5, 1.9)],
    [10, selectable(6, 3)],
    [13, selectable(9, 5)],
    [15, selectable(11, 6.5)],
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

  const built: LayerSpecification[] = [
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
      metadata: STATUS_GATED,
      paint: {
        "line-color": selectable(SELECTION_COLOUR, statusColourExpression()),
        "line-width": lateralWidth(),
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
    // Texas, drawn from the same expressions as North Dakota. The status vocabulary is
    // per-source (cr_tx_status_vocab_1 there, cr_nd_status_vocab_1 here) but the canonical
    // classes are one list, so a reader compares like with like across the two basins.
    {
      id: "tx-laterals",
      type: "line",
      source: txLaterals,
      "source-layer": txLaterals,
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
    built.push({
      id: "spacing-units-label",
      type: "symbol",
      source: spacing,
      "source-layer": spacing,
      minzoom: 11,
      layout: {
        "text-field": ["coalesce", ["get", "label"], ""],
        "text-font": ["Noto Sans Regular"],
        // The base size; applyVariantStyling owns the per-variant bump, for this label and
        // the basemap's alike, so the two cannot compound into a size neither declares.
        "text-size": SPACING_LABEL_SIZE,
        "symbol-placement": "point",
      },
      paint: {
        "text-color": tokens.primary.colour,
        "text-halo-color": tokens.primary.halo,
        "text-halo-width": tokens.primary.haloWidth,
      },
    });
  }
  return built;
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
