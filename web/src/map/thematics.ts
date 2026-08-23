/**
 * M2-3: the land-grid thematic surface — ramp, fill expression and the key.
 *
 * The bins arrive on the wire: every cell carries its `liquid_bin` (cut at refresh over the
 * grain's whole population), the frame it was cut on (`bin_edges`, `bin_population`) and the
 * refresh's derivation handle. Nothing here recomputes an edge, so the same colour cannot
 * mean different things at different moments, and the key restates only what the tile says.
 */
import { get, step, toNumber } from "./expr.ts";
import type { Expr } from "./expr.ts";

export const METRICS_TOWNSHIPS_SOURCE = "land_township_metrics";
export const METRICS_SECTIONS_SOURCE = "land_section_metrics";

/** Townships carry the overview and hand off to sections where sections are readable. */
export const TOWNSHIP_METRICS_MIN_ZOOM = 5;
export const METRICS_HANDOFF_ZOOM = 10;

export const METRIC_FILL_LAYERS = [
  "land-township-metrics-fill",
  "land-section-metrics-fill",
] as const;

/**
 * Sequential single-hue amber, dark→light with the value, seven steps for the seven bins
 * between min/P2/P20/P40/P60/P80/P98/max. Amber because every other hue family on this map
 * is spoken for as a data claim: oil green, gas red, water blue are the stream colours,
 * cyan is selection, orchid is the survey trace, and the greys are reference linework.
 * OKLCH hue 75° throughout; lightness runs 0.42 → 0.925 strictly monotone with adjacent
 * step separation ΔE 8.0–9.6 (OKLab×100); the top step is 13.6:1 against the dark
 * substrate #0E151B and no step is within 3:1 of a stream colour's role because fills and
 * dots are different marks. Never spectral (BRAND.md).
 */
export const LIQUID_RAMP = [
  "#654617",
  "#845C1A",
  "#A5721B",
  "#C58A26",
  "#E3A340",
  "#FCBE62",
  "#FFDFA7",
] as const;

/**
 * Support modulates ink, so a 2-well cell cannot look like a 200-well cell. The classes
 * match the support_distribution the refresh records — what is served and what is rendered
 * are the same cut.
 */
export const SUPPORT_ALPHA = [
  [1, 0.38],
  [3, 0.58],
  [8, 0.78],
] as const;

/** The copy every liquid figure carries; cr_nd_liquids_policy_1 is the row behind it. */
export const LIQUIDS_BASIS_COPY = "oil + condensate as ND files it";
export const MEMBERSHIP_RULE = "cr_land_agg_membership_1";
export const MEMBERSHIP_COPY = "wells assigned by lateral midpoint, else surface hole";

function rgba(hex: string, alpha: number): string {
  const value = Number.parseInt(hex.slice(1), 16);
  return `rgba(${(value >> 16) & 255}, ${(value >> 8) & 255}, ${value & 255}, ${alpha})`;
}

function rampAt(alpha: number): Expr {
  return step(
    toNumber(get("liquid_bin")),
    rgba(LIQUID_RAMP[0], alpha),
    LIQUID_RAMP.slice(1).map((colour, index) => [index + 1, rgba(colour, alpha)]),
  );
}

/** Bin picks the hue step, support picks how much of it reaches the canvas. */
export function liquidFillColour(): Expr {
  const [low, mid, high] = SUPPORT_ALPHA;
  return step(toNumber(get("prod_well_count")), rampAt(low[1]), [
    [mid[0], rampAt(mid[1])],
    [high[0], rampAt(high[1])],
  ]);
}

/**
 * Cells with nothing observed are on the tile (their counts hover) but take no paint: an
 * unpainted cell is bare grid, never a bottom bin — the "visibly empty" the roadmap asks.
 */
export function observedFilter(): Expr {
  return [">=", toNumber(get("liquid_bin")), 0] as Expr;
}

const COMPACT = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumSignificantDigits: 3,
});

export function compactVolume(value: number): string {
  return COMPACT.format(value);
}

interface Frame {
  grain: string;
  edges: number[];
  population: number;
  handle: string | null;
}

/** The frame the canvas is painted from, read off a rendered cell — never recomputed. */
export function frameOf(cells: readonly Record<string, unknown>[]): Frame | null {
  for (const cell of cells) {
    const raw = cell["bin_edges"];
    if (typeof raw !== "string" || raw === "") continue;
    let edges: unknown;
    try {
      edges = JSON.parse(raw);
    } catch {
      continue; // A malformed frame on one feature must not take the key down.
    }
    if (!Array.isArray(edges) || edges.length !== 8) continue;
    if (!edges.every((edge) => typeof edge === "number" && Number.isFinite(edge))) continue;
    const population = Number(cell["bin_population"]);
    const handle = cell["derivation_id"];
    return {
      grain: cell["unit_type"] === "township" ? "township" : "section",
      edges: edges as number[],
      population: Number.isFinite(population) ? population : 0,
      handle: typeof handle === "string" && handle !== "" ? handle : null,
    };
  }
  return null;
}
