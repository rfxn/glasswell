// @vitest-environment happy-dom
import { describe, expect, it } from "vitest";

import { BASEMAPS } from "./basemap.ts";
import { MAP_MAX_ZOOM } from "./map.ts";

/**
 * Two ceilings that drift apart silently: a source `maxzoom` below the map's leaves the
 * reader overzoomed pixels where native ones exist, and above it paints the service's grey
 * "no data" placeholder across the basin. Both look like imagery, so only this catches them.
 */
describe("the map's zoom ceiling against the imagery it draws", () => {
  const declared = BASEMAPS.filter((base) => base.tiles?.length).map((base) => base.maxzoom);

  it("agrees with every option that draws imagery, so no option is the odd one out", () => {
    expect(new Set(declared).size).toBe(1);
  });

  it("never asks for a zoom above the deepest level the imagery was measured to carry", () => {
    // Above the source ceiling the service answers 200 with a placeholder, not a 404, so
    // nothing in the client can tell that apart from imagery. Re-probe before raising it.
    for (const ceiling of declared) expect(MAP_MAX_ZOOM).toBeLessThanOrEqual(ceiling!);
  });

  it("reaches that level rather than stopping short of imagery already being served", () => {
    for (const ceiling of declared) expect(MAP_MAX_ZOOM).toBe(ceiling!);
  });
});
