import type { LayerSpecification, SourceSpecification } from "maplibre-gl";

import { tileUrl } from "../api/client.ts";
import type { BasemapVariant } from "./basemap.ts";
import { coalesce, featureState, get, inSet, interpolate, step, toNumber, when, zoom } from "./expr.ts";
import type { Expr } from "./expr.ts";
import {
  SELECTION_COLOUR,
  STATUS_CLASSES,
  STRUCK_STATUSES,
  UNMAPPED_STATUS,
  statusColourExpression,
  statusFillExpression,
  statusProperty,
} from "./status.ts";
import { labelSize, rgba, variantStyle } from "./variant-style.ts";

export const WELLS_SOURCE = "nd_wells";
export const LATERALS_SOURCE = "nd_laterals";
export const SPACING_SOURCE = "nd_spacing_units";

const INK = "#0B1014";
const SPACING_LABEL_SIZE = 10;

/** martin publishes one source id per table and the MVT layer inside carries that id. */
function published(parameter: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  return new URLSearchParams(window.location.search).get(parameter) ?? fallback;
}

/** Same-origin by default. Not `new URL()`: it percent-encodes MapLibre's {z}/{x}/{y}. */
export function absoluteTileUrl(template: string, origin?: string): string {
  if (/^https?:\/\//i.test(template)) return template;
  const base = origin ?? (typeof window === "undefined" ? "" : window.location.origin);
  return `${base}${template}`;
}

export function sourceSpecs(origin?: string): Record<string, SourceSpecification> {
  const specs: Record<string, SourceSpecification> = {};
  for (const [parameter, fallback] of [
    ["wells", WELLS_SOURCE],
    ["laterals", LATERALS_SOURCE],
    ["spacing", SPACING_SOURCE],
  ] as const) {
    const name = published(parameter, fallback);
    specs[name] = {
      type: "vector",
      tiles: [absoluteTileUrl(tileUrl(name), origin)],
      minzoom: 0,
      maxzoom: 14,
      // API-10 is a string, so MapLibre cannot use it as a feature id without promoteId,
      // and without a feature id there is no feature-state and no selection without a
      // duplicate filter layer per source.
      promoteId: { [name]: "api10" },
    };
  }
  return specs;
}

export function visibleStatusesAt(atZoom: number): string[] {
  return STATUS_CLASSES.filter((status) => atZoom >= status.minZoom).map((status) => status.id);
}

/**
 * The rendered set is the zoom gate intersected with the legend's own filter. An unmapped
 * status is always in it: a class the build cannot name is a defect, and a defect that
 * disappears at low zoom is worse than one that shows.
 */
export function statusFilter(atZoom: number, on: ReadonlySet<string>): Expr {
  const allowed = visibleStatusesAt(atZoom).filter((id) => on.has(id));
  return inSet(statusProperty(), [...allowed, UNMAPPED_STATUS.id]);
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
}

export function dataLayers(options: DataLayerOptions = {}): LayerSpecification[] {
  const hollow = options.hollowFill ?? INK;
  const variant = options.variant ?? "dark";
  const tokens = variantStyle(variant);
  const wells = published("wells", WELLS_SOURCE);
  const laterals = published("laterals", LATERALS_SOURCE);
  const spacing = published("spacing", SPACING_SOURCE);

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
        "text-size": labelSize(SPACING_LABEL_SIZE, variant),
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
