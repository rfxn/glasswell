// @vitest-environment happy-dom
import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { DEFAULT_STATE } from "../app/state.ts";
import { BASEMAPS } from "./basemap.ts";
import { MAP_MAX_BOUNDS, MAP_MAX_ZOOM, MAP_MIN_ZOOM } from "./map.ts";
import { BOUNDARY_MIN_ZOOM, dataLayers } from "./style.ts";

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

/**
 * The other end of the same envelope. The map declared a ceiling and no floor, so a pinch out
 * left the reader at z0 looking at a world this product publishes nothing into, with every
 * tile source fetching a pyramid nothing on it could be read at — and no bound stopped a pan
 * to the middle of the Pacific either.
 */
describe("the map's viewport envelope", () => {
  const [[west, south], [east, north]] = MAP_MAX_BOUNDS;
  const holds = (lon: number, lat: number): boolean =>
    lon >= west && lon <= east && lat >= south && lat <= north;

  it("declares a floor under its own ceiling", () => {
    expect(MAP_MIN_ZOOM).toBeLessThan(MAP_MAX_ZOOM);
    expect(MAP_MIN_ZOOM).toBeGreaterThan(0);
  });

  it("opens inside its own bounds, above its own floor", () => {
    expect(holds(DEFAULT_STATE.map.lon, DEFAULT_STATE.map.lat)).toBe(true);
    expect(DEFAULT_STATE.map.zoom).toBeGreaterThanOrEqual(MAP_MIN_ZOOM);
  });

  it("draws something at the shallowest zoom it allows, rather than an empty canvas", () => {
    // A floor below every layer's own floor is a zoom band with a basemap and no data on it.
    const floors = dataLayers({ labels: true }).map((layer) => layer.minzoom ?? 0);
    expect(Math.min(...floors)).toBe(MAP_MIN_ZOOM);
    expect(BOUNDARY_MIN_ZOOM).toBe(MAP_MIN_ZOOM);
  });

  it("holds every state this build serves, and the ones it is going to", () => {
    // Four served states by their extremes, then the corners of the contiguous forty-eight:
    // a bound that clipped any of them would refuse a pan to a well the API will answer for.
    const places: [string, number, number][] = [
      ["ND north-west", -104.05, 49.0],
      ["TX south", -97.14, 25.84],
      ["NM south-west", -109.05, 31.33],
      ["MT north-west", -116.05, 49.0],
      ["Key West", -81.8, 24.55],
      ["Cape Flattery", -124.73, 48.38],
      ["Quoddy Head", -66.95, 44.82],
    ];
    for (const [name, lon, lat] of places) expect(holds(lon, lat), name).toBe(true);
  });

  it("keeps Alaska and the Canadian margin inside, because the product is going there", () => {
    const places: [string, number, number][] = [
      ["Utqiagvik", -156.79, 71.29],
      ["Adak", -176.63, 51.88],
      ["Calgary", -114.07, 51.05],
      ["Fort McMurray", -111.38, 56.73],
      ["St John's", -52.71, 47.56],
    ];
    // Adak is the one that does not fit and is not meant to: the western Aleutians cross the
    // antimeridian, and a box drawn to hold them would hold the whole Pacific with them.
    expect(holds(-176.63, 51.88)).toBe(false);
    for (const [name, lon, lat] of places.filter(([label]) => label !== "Adak")) {
      expect(holds(lon, lat), name).toBe(true);
    }
  });

  it("stops short of the empty world a reader could otherwise pan into", () => {
    for (const [name, lon, lat] of [
      ["the Atlantic off Iberia", -20, 40],
      ["the western Pacific", 150, 20],
      ["the equator south of Mexico", -95, 0],
      ["the pole", -100, 88],
      ["Antarctica", -100, -70],
    ] as [string, number, number][]) {
      expect(holds(lon, lat), name).toBe(false);
    }
  });

  it("does not pretend to be tighter than a rectangle can be", () => {
    // The south-west corner is open Pacific and stays that way: any box holding both
    // Utqiagvik and Key West holds it too. Stated rather than asserted away, so nobody reads
    // the bound as a claim about where this product has data.
    expect(holds(-150, 25)).toBe(true);
  });

  it("declares the bounds in the order MapLibre reads them: south-west first", () => {
    expect(west).toBeLessThan(east);
    expect(south).toBeLessThan(north);
  });

  it("hands all three to MapLibre, because an exported constant nothing passes is a comment", () => {
    // `createMap` needs a canvas and a WebGL context, so the wiring is read off the source
    // the way bridge.test.ts reads its own. The ceiling shipped for releases as the only one
    // of the three that was passed; the other two would have looked equally declared here.
    const source = readFileSync("src/map/map.ts", "utf8");
    const options = /new maplibregl\.Map\(\{([\s\S]*?)\n {2}\}\)/.exec(source)?.[1] ?? "";

    expect(options, "no maplibregl.Map options block found").not.toBe("");
    expect(options).toMatch(/\bminZoom:\s*MAP_MIN_ZOOM\b/);
    expect(options).toMatch(/\bmaxZoom:\s*MAP_MAX_ZOOM\b/);
    expect(options).toMatch(/\bmaxBounds:\s*MAP_MAX_BOUNDS\b/);
  });
});
