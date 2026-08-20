import { validateStyleMin } from "@maplibre/maplibre-gl-style-spec";
import type { StyleSpecification } from "maplibre-gl";
import { describe, expect, it } from "vitest";

import { basemapDef, graticuleStyle, rasterStyle, vectorStyle } from "./basemap.ts";
import { dataLayers, sourceSpecs, statusFilter } from "./style.ts";
import { statusIds } from "./status.ts";

/**
 * MapLibre drops a layer that fails style validation and reports it on the `error` event.
 * With an `error` listener installed the browser console stays clean, so an invalid paint
 * expression reads as "the well layers just do not appear" — which is exactly how the
 * feature-state selection ramps shipped broken during this phase. The official validator
 * is the cheapest guard against that, and it runs on every assembled style.
 */
function assembled(base: StyleSpecification): StyleSpecification {
  const layers = dataLayers({ labels: Boolean(base.glyphs) }).map((layer) => {
    if (layer.id === "wells" || layer.id === "laterals") {
      return { ...layer, filter: statusFilter(9, new Set(statusIds())) };
    }
    return layer;
  });
  return {
    ...base,
    sources: { ...base.sources, ...sourceSpecs("https://glasswell.example") },
    layers: [...base.layers, ...layers] as StyleSpecification["layers"],
  };
}

const CASES: [string, StyleSpecification][] = [
  ["graticule", graticuleStyle()],
  ["satellite", rasterStyle(basemapDef("satellite")!)],
  ["pmtiles dark", vectorStyle(basemapDef("dark")!, { labels: false })],
  ["pmtiles light with labels", vectorStyle(basemapDef("light")!, { labels: true })],
];

describe("the assembled style", () => {
  for (const [name, base] of CASES) {
    it(`validates against the style spec over the ${name} basemap`, () => {
      const errors = validateStyleMin(assembled(base) as never);
      expect(errors.map((error) => `${error.message}`)).toEqual([]);
    });
  }

  it("validates the well layers on their own, with no basemap under them", () => {
    const errors = validateStyleMin({
      version: 8,
      sources: sourceSpecs("https://glasswell.example"),
      layers: dataLayers(),
    } as never);
    expect(errors.map((error) => `${error.message}`)).toEqual([]);
  });
});
