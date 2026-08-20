// @vitest-environment happy-dom
import { describe, expect, it } from "vitest";
import type { LayerSpecification } from "maplibre-gl";

import { BASEMAP_VARIANTS, basemapDef, graticuleStyle, rasterStyle, vectorStyle } from "./basemap.ts";
import type { BasemapVariant } from "./basemap.ts";
import { CONTRAST_FLOOR, NON_TEXT_FLOOR, contrastRatio } from "./contrast.ts";
import { dataLayers, sourceSpecs } from "./style.ts";
import {
  CONTEXT_LINES,
  VARIANT_STYLES,
  applyVariantStyling,
  labelRole,
  rgba,
  textLayers,
  variantStyle,
} from "./variant-style.ts";

const DATA_SOURCES = new Set(Object.keys(sourceSpecs()));

/** What map.ts assembles: the basemap's own layers with the data layers folded in. */
function styleFor(variant: BasemapVariant): LayerSpecification[] {
  const base =
    variant === "satellite"
      ? rasterStyle(basemapDef("satellite")!)
      : variant === "none"
        ? graticuleStyle()
        : vectorStyle(basemapDef(variant)!, { labels: true });
  return [...base.layers, ...dataLayers({ labels: true, variant })];
}

const paintOf = (layer: LayerSpecification): Record<string, unknown> =>
  ("paint" in layer && layer.paint ? layer.paint : {}) as Record<string, unknown>;

describe("the variant token table", () => {
  it("names one token set per basemap variant, and no orphan", () => {
    expect(Object.keys(VARIANT_STYLES).sort()).toEqual([...BASEMAP_VARIANTS].sort());
  });

  it("keeps every data label above the text floor against its own halo", () => {
    for (const variant of BASEMAP_VARIANTS) {
      const tokens = variantStyle(variant).primary;
      const ratio = contrastRatio(tokens.colour, tokens.halo);
      expect(ratio, `${variant}: data label vs halo is ${ratio.toFixed(2)}:1`).toBeGreaterThanOrEqual(
        CONTRAST_FLOOR,
      );
    }
  });

  it("keeps every context label above the text floor against its own halo", () => {
    for (const variant of BASEMAP_VARIANTS) {
      const tokens = variantStyle(variant).context;
      const ratio = contrastRatio(tokens.colour, tokens.halo);
      expect(ratio, `${variant}: context label vs halo is ${ratio.toFixed(2)}:1`).toBeGreaterThanOrEqual(
        CONTRAST_FLOOR,
      );
    }
  });

  it("clears the text floor against the substrate wherever the substrate is one colour", () => {
    // Imagery has no single value, so satellite is measured on its halo instead — below.
    for (const variant of ["dark", "light", "none"] as const) {
      const { primary, context, substrate } = variantStyle(variant);
      expect(contrastRatio(primary.colour, substrate)).toBeGreaterThanOrEqual(CONTRAST_FLOOR);
      expect(contrastRatio(context.colour, substrate)).toBeGreaterThanOrEqual(CONTRAST_FLOOR);
    }
  });

  it("makes the satellite halo do the work the substrate cannot", () => {
    const satellite = variantStyle("satellite");
    // White text over mid-tone imagery is 3.53:1 on its own; the halo is what is read.
    expect(contrastRatio(satellite.primary.colour, satellite.substrate)).toBeLessThan(CONTRAST_FLOOR);
    expect(contrastRatio(satellite.primary.halo, satellite.substrate)).toBeGreaterThanOrEqual(
      NON_TEXT_FLOOR,
    );
    for (const variant of BASEMAP_VARIANTS) {
      const heavier = satellite.primary.haloWidth >= variantStyle(variant).primary.haloWidth;
      expect(heavier, `satellite halo is not the heaviest (${variant})`).toBe(true);
    }
    expect(satellite.primary.haloWidth).toBeGreaterThanOrEqual(2);
    expect(satellite.primary.sizeDelta).toBe(1);
  });

  it("keeps the spacing-unit fill a wash, because the units stack on the same acreage", () => {
    // Measured from the rendered canvas: the shipped fill composited to 93% opaque over the
    // dark earth, so the substrate every label was read against was the fill, not the basemap.
    for (const variant of BASEMAP_VARIANTS) {
      const stacked = 1 - (1 - variantStyle(variant).spacingFillAlpha) ** 40;
      expect(stacked, `${variant}: a 40-deep stack composites to ${(stacked * 100).toFixed(0)}%`)
        .toBeLessThan(0.6);
    }
  });

  it("carries the fill alpha in the colour, where the opacity slider cannot overwrite it", () => {
    // registry.ts gives the spacing row opacity 0.75 and map.ts writes it to `fill-opacity`
    // for every style layer the row drives, so a fill-opacity token never reached the canvas.
    const fill = dataLayers({ variant: "satellite" }).find((l) => l.id === "spacing-units-fill");
    expect(paintOf(fill!)["fill-color"]).toBe(rgba("#0B1014", 0.015));
    expect(paintOf(fill!)["fill-opacity"]).toBeUndefined();
  });

  it("keeps every context line above the non-text floor on its own substrate", () => {
    for (const variant of BASEMAP_VARIANTS) {
      const tokens = variantStyle(variant);
      for (const line of [tokens.boundary, tokens.spacing, tokens.graticule]) {
        const ratio = contrastRatio(line, tokens.substrate);
        expect(ratio, `${variant}: ${line} on ${tokens.substrate} is ${ratio.toFixed(2)}:1`)
          .toBeGreaterThanOrEqual(NON_TEXT_FLOOR);
      }
    }
  });
});

describe("the variant styling pass", () => {
  it("classifies a label by the source it is drawn from, not by a hand-kept id list", () => {
    const label = dataLayers({ labels: true, variant: "dark" }).find((l) => l.type === "symbol" && "paint" in l);
    expect(label && labelRole(label, DATA_SOURCES)).toBe("primary");
    const place = vectorStyle(basemapDef("dark")!, { labels: true }).layers.find(
      (layer) => layer.id === "places_locality",
    );
    expect(place && labelRole(place, DATA_SOURCES)).toBe("context");
  });

  it("leaves no text-bearing layer unstyled in any variant — the class, not one layer", () => {
    for (const variant of BASEMAP_VARIANTS) {
      const tokens = variantStyle(variant);
      const styled = applyVariantStyling(styleFor(variant), variant, DATA_SOURCES);
      const text = textLayers(styled);
      expect(text.length, `${variant}: no text layer found at all`).toBeGreaterThan(0);
      for (const layer of text) {
        const paint = paintOf(layer);
        const role = labelRole(layer, DATA_SOURCES);
        const expected = role === "primary" ? tokens.primary : tokens.context;
        expect(paint["text-color"], `${variant}/${layer.id} text-color`).toBe(expected.colour);
        expect(paint["text-halo-color"], `${variant}/${layer.id} halo`).toBe(expected.halo);
        expect(paint["text-halo-width"], `${variant}/${layer.id} halo width`).toBe(expected.haloWidth);
        const ratio = contrastRatio(String(paint["text-color"]), String(paint["text-halo-color"]));
        expect(ratio, `${variant}/${layer.id} measures ${ratio.toFixed(2)}:1`).toBeGreaterThanOrEqual(
          CONTRAST_FLOOR,
        );
      }
    }
  });

  it("recolours every context line the table names, in every variant that draws one", () => {
    for (const variant of BASEMAP_VARIANTS) {
      const tokens = variantStyle(variant);
      const styled = applyVariantStyling(styleFor(variant), variant, DATA_SOURCES);
      for (const layer of styled) {
        const role = CONTEXT_LINES[layer.id];
        if (!role) continue;
        expect(paintOf(layer)["line-color"], `${variant}/${layer.id}`).toBe(
          role === "graticule" ? tokens.graticule : tokens.boundary,
        );
        // The shipped county line was drawn at 0.7, so the rendered colour was a blend of the
        // token and whatever was under it, and the measured number was never the styled one.
        expect(paintOf(layer)["line-opacity"], `${variant}/${layer.id} opacity`).toBe(1);
      }
    }
    // The county line is the layer VF-5 names by hand; it must be in the swept set.
    const counties = applyVariantStyling(styleFor("light"), "light", DATA_SOURCES).find(
      (layer) => layer.id === "gw-boundaries-county",
    );
    expect(paintOf(counties!)["line-color"]).toBe(variantStyle("light").boundary);
  });

  it("bumps a plain text size on satellite and leaves a zoom-driven one alone", () => {
    // A zoom expression is only legal at the top of a property; ["+", <interpolate>, 1] puts
    // it one level down and MapLibre rejects the whole style, so those sizes are not bumped.
    const styled = applyVariantStyling(styleFor("satellite"), "satellite", DATA_SOURCES);
    const label = styled.find((layer) => layer.id === "spacing-units-label");
    const size = label && "layout" in label ? (label.layout as Record<string, unknown>) : {};
    expect(size["text-size"]).toBe(11);

    const zoomDriven = applyVariantStyling(styleFor("dark"), "dark", DATA_SOURCES).find(
      (layer) => layer.id === "places_locality",
    );
    const layout = zoomDriven && "layout" in zoomDriven ? (zoomDriven.layout as Record<string, unknown>) : {};
    expect(Array.isArray(layout["text-size"])).toBe(true);
  });

  it("leaves an icon-only symbol layer alone, so a data mark is not painted as a label", () => {
    const styled = applyVariantStyling(styleFor("dark"), "dark", DATA_SOURCES);
    const struck = styled.find((layer) => layer.id === "wells-struck");
    expect(struck?.type).toBe("symbol");
    expect(paintOf(struck!)["text-color"]).toBeUndefined();
    expect(textLayers(styled).map((layer) => layer.id)).not.toContain("wells-struck");
  });

  it("does not touch the layers it is handed, because the style is swapped not mutated", () => {
    const input = styleFor("light");
    const before = JSON.stringify(input);
    applyVariantStyling(input, "satellite", DATA_SOURCES);
    expect(JSON.stringify(input)).toBe(before);
  });

  it("is idempotent, so a re-applied pass on a style event cannot compound the size bump", () => {
    const once = applyVariantStyling(styleFor("satellite"), "satellite", DATA_SOURCES);
    const twice = applyVariantStyling(once, "satellite", DATA_SOURCES);
    expect(JSON.stringify(twice)).toBe(JSON.stringify(once));
  });
});
