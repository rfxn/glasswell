import { validateStyleMin } from "@maplibre/maplibre-gl-style-spec";
import type { StyleSpecification } from "maplibre-gl";
import { describe, expect, it } from "vitest";

import { basemapDef, vectorStyle } from "./basemap.ts";
import { dataLayers, sourceSpecs, statusFilter } from "./style.ts";
import { statusIds } from "./status.ts";
import { applyVariantStyling } from "./variant-style.ts";

/**
 * The hybrid is the most compositionally novel style here — a symbol-only Protomaps
 * complement over a raster source over a background, then the data layers, then the variant
 * pass — and `style-valid.test.ts` builds every style but this one. MapLibre drops a layer
 * that fails validation and reports it on `error`, so an invalid paint reads as "the well
 * layers just do not appear" rather than as a fault.
 */
const ORIGIN = "https://glasswell.example";

function assembled(base: StyleSpecification): StyleSpecification {
  const layers = dataLayers({ labels: Boolean(base.glyphs) }).map((layer) =>
    layer.id === "wells" || layer.id === "laterals"
      ? { ...layer, filter: statusFilter(9, new Set(statusIds())) }
      : layer,
  );
  return {
    ...base,
    sources: { ...base.sources, ...sourceSpecs(ORIGIN) },
    layers: [...base.layers, ...layers] as StyleSpecification["layers"],
  };
}

const hybrid = () => basemapDef("hybrid")!;

const STATES: [string, () => StyleSpecification][] = [
  ["imagery up", () => vectorStyle(hybrid(), { labels: true, origin: ORIGIN })],
  ["imagery down", () => vectorStyle(hybrid(), { labels: true, imagery: false, origin: ORIGIN })],
  ["labels absent", () => vectorStyle(hybrid(), { labels: false, origin: ORIGIN })],
];

describe("the assembled hybrid style", () => {
  for (const [state, build] of STATES) {
    it(`validates against the style spec with the ${state}`, () => {
      const errors = validateStyleMin(assembled(build()) as never);
      expect(errors.map((error) => `${state}: ${error.message}`)).toEqual([]);
    });

    it(`validates what transformStyle hands MapLibre with the ${state}`, () => {
      // The variant pass is the last thing to touch a layer, so validating before it runs
      // validates a style that never renders. The hybrid reads against the satellite row.
      const merged = assembled(build());
      const data = new Set(Object.keys(sourceSpecs(ORIGIN)));
      const styled = {
        ...merged,
        layers: applyVariantStyling(merged.layers, "satellite", data),
      } as StyleSpecification;
      const errors = validateStyleMin(styled as never);
      expect(errors.map((error) => `${state}: ${error.message}`)).toEqual([]);
    });
  }
});
