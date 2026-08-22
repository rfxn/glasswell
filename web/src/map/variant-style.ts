import type { LayerSpecification } from "maplibre-gl";

import type { BasemapVariant } from "./basemap.ts";

/**
 * VF-5, as a class. Every text-bearing layer and every context line is coloured from the
 * table below, keyed to the basemap under it, and the pass runs over the whole layer list on
 * every style swap — so a label added later is styled by construction rather than by memory.
 * The numbers are held to the WCAG floors by variant-style.test.ts, not by inspection.
 */

export type LabelRole = "primary" | "context";

export interface LabelTokens {
  colour: string;
  halo: string;
  haloWidth: number;
  /** Imagery costs a pixel of type; a flat substrate does not. */
  sizeDelta: number;
}

export interface VariantStyle {
  /** The substrate a label lands on, as one colour. Satellite's is a mid-tone stand-in. */
  substrate: string;
  /** glasswell's own labels: spacing units today, well and lateral names when the tile carries them. */
  primary: LabelTokens;
  /** The basemap's labels — places, roads, water. Context, so quieter, but still measured. */
  context: LabelTokens;
  /** The spacing-unit outline, which carries the contrast. */
  spacing: string;
  /**
   * Spacing units stack about forty deep on the same acreage at basin scale, so a per-feature
   * alpha saturates: the shipped fill measured 93% opaque over the dark earth, which is what
   * turned every substrate into the same slate. The fill is a hint; the outline is the unit.
   * Carried in the colour rather than in `fill-opacity`, which the layer panel's slider owns.
   */
  spacingFill: string;
  spacingFillAlpha: number;
  boundary: string;
  /** PLSS reference linework: the paper the data sits on, quieter than a boundary. */
  grid: string;
  graticule: string;
}

const INK = "#0B1014";
const PAPER = "#E6EDF3";
const SLATE = "#9FB0BC";

export const VARIANT_STYLES: Readonly<Record<BasemapVariant, VariantStyle>> = {
  dark: {
    substrate: "#0E151B",
    primary: { colour: PAPER, halo: INK, haloWidth: 1.4, sizeDelta: 0 },
    context: { colour: SLATE, halo: INK, haloWidth: 1.2, sizeDelta: 0 },
    spacing: "#6E8B9B",
    spacingFill: "#4B6472",
    spacingFillAlpha: 0.015,
    boundary: "#7C93A1",
    grid: "#7C8B96",
    graticule: "#55707D",
  },
  light: {
    substrate: "#F2F5F8",
    primary: { colour: INK, halo: "#FFFFFF", haloWidth: 1.6, sizeDelta: 0 },
    context: { colour: "#2B3A45", halo: "#FFFFFF", haloWidth: 1.4, sizeDelta: 0 },
    spacing: "#33505F",
    spacingFill: "#557085",
    spacingFillAlpha: 0.015,
    boundary: "#557085",
    grid: "#7C8B96",
    graticule: "#557085",
  },
  satellite: {
    substrate: "#8A8A70",
    primary: { colour: "#FFFFFF", halo: "#000000", haloWidth: 2.4, sizeDelta: 1 },
    context: { colour: "#FFFFFF", halo: "#000000", haloWidth: 2.2, sizeDelta: 1 },
    spacing: "#FFFFFF",
    // A white veil over imagery erases it; a dark one keeps the detail and lifts white type.
    spacingFill: "#0B1014",
    spacingFillAlpha: 0.015,
    boundary: "#FFFFFF",
    grid: "#FFFFFF",
    graticule: "#FFFFFF",
  },
  none: {
    substrate: INK,
    primary: { colour: PAPER, halo: INK, haloWidth: 1.4, sizeDelta: 0 },
    context: { colour: SLATE, halo: INK, haloWidth: 1.2, sizeDelta: 0 },
    spacing: "#6E8B9B",
    spacingFill: "#4B6472",
    spacingFillAlpha: 0.015,
    boundary: "#7C93A1",
    grid: "#7C8B96",
    graticule: "#55707D",
  },
};

/**
 * A context line names its own role where it is defined, and the pass styles whatever is
 * marked — VF-5's class failure was a hand-kept id list going stale as layers were added.
 */
export type LineRole = "boundary" | "grid" | "graticule";
export const LINE_ROLE = "gw:line-role";

export function lineRole(layer: LayerSpecification): LineRole | undefined {
  const metadata = layer.metadata as Record<string, unknown> | undefined;
  const role = metadata?.[LINE_ROLE];
  return role === "boundary" || role === "grid" || role === "graticule" ? role : undefined;
}

export function rgba(colour: string, alpha: number): string {
  const digits = colour.replace("#", "");
  const [red, green, blue] = [0, 2, 4].map((at) => parseInt(digits.slice(at, at + 2), 16));
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
}

export function variantStyle(variant: BasemapVariant): VariantStyle {
  return VARIANT_STYLES[variant];
}

export function textLayers(layers: readonly LayerSpecification[]): LayerSpecification[] {
  return layers.filter(
    (layer) =>
      layer.type === "symbol" &&
      "layout" in layer &&
      (layer.layout as Record<string, unknown> | undefined)?.["text-field"] !== undefined,
  );
}

export function labelRole(
  layer: LayerSpecification,
  dataSources: ReadonlySet<string>,
): LabelRole {
  const source = "source" in layer ? layer.source : undefined;
  return typeof source === "string" && dataSources.has(source) ? "primary" : "context";
}

/** Where the base size is memoised, so a second pass bumps the base and not the bumped size. */
const BASE_TEXT_SIZE = "gw:base-text-size";

/**
 * A zoom expression is legal only at the top of a property, so `["+", <interpolate>, 1]` is a
 * style MapLibre rejects whole. Only a plain numeric size can be bumped; an undeclared one is
 * left to the spec default rather than pinned to it here.
 */
function sizedFor(layer: LayerSpecification, label: LabelTokens): Partial<LayerSpecification> {
  const layout = (("layout" in layer ? layer.layout : undefined) ?? {}) as Record<string, unknown>;
  const metadata = ((layer.metadata as Record<string, unknown> | undefined) ?? {}) as Record<
    string,
    unknown
  >;
  const base = metadata[BASE_TEXT_SIZE] ?? layout["text-size"];
  if (typeof base !== "number") return {};
  return {
    metadata: { ...metadata, [BASE_TEXT_SIZE]: base },
    layout: { ...layout, "text-size": base + label.sizeDelta },
  } as Partial<LayerSpecification>;
}

/**
 * Text colour is set even where the basemap flavour supplied an expression — Protomaps tints
 * POI labels by kind, and several of those tints measure under 3:1 on the ink. A legible
 * label the reader can find beats a hue they cannot name.
 */
export function applyVariantStyling(
  layers: readonly LayerSpecification[],
  variant: BasemapVariant,
  dataSources: ReadonlySet<string>,
): LayerSpecification[] {
  const tokens = variantStyle(variant);
  const text = new Set(textLayers(layers).map((layer) => layer.id));
  return layers.map((layer) => {
    if (text.has(layer.id)) {
      const label = tokens[labelRole(layer, dataSources)];
      return {
        ...layer,
        ...sizedFor(layer, label),
        paint: {
          ...("paint" in layer ? layer.paint : {}),
          "text-color": label.colour,
          "text-halo-color": label.halo,
          "text-halo-width": label.haloWidth,
        },
      } as LayerSpecification;
    }
    const line = lineRole(layer);
    if (!line) return layer;
    if (line === "grid") {
      // Colour only: the township/section weights and opacities are the layer's own register
      // — the grid sits under the data — and the pass must not flatten that hierarchy.
      return {
        ...layer,
        paint: { ...("paint" in layer ? layer.paint : {}), "line-color": tokens.grid },
      } as LayerSpecification;
    }
    return {
      ...layer,
      paint: {
        ...("paint" in layer ? layer.paint : {}),
        "line-color": line === "graticule" ? tokens.graticule : tokens.boundary,
        // Opaque, so the colour that renders is the colour that was measured; the county and
        // state lines are told apart by weight, which is what a fainter one was doing badly.
        "line-opacity": 1,
      },
    } as LayerSpecification;
  });
}
