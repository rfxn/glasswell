// @vitest-environment happy-dom
import { beforeEach, describe, expect, it } from "vitest";

import { BASE_STORAGE_KEY } from "./persist.ts";
import {
  BASEMAPS,
  BASEMAP_SOURCE,
  BASEMAP_VARIANTS,
  DEFAULT_BASEMAP,
  PMTILES_PATH,
  applyBasemapVariant,
  basemapDef,
  basemapIds,
  basemapVariant,
  chooseBasemap,
  fallbackStyle,
  graticuleStyle,
  pmtilesUrl,
  rasterStyle,
  sourceLabel,
  vectorStyle,
} from "./basemap.ts";

describe("the basemap catalogue", () => {
  beforeEach(() => window.localStorage.clear());

  it("offers the four options the market bar expects", () => {
    expect(basemapIds()).toEqual(["dark", "light", "satellite", "none"]);
    expect(DEFAULT_BASEMAP).toBe("dark");
  });

  it("keeps every option keyless and states its attribution", () => {
    for (const base of BASEMAPS) {
      expect(base.attribution.length).toBeGreaterThan(0);
      expect(JSON.stringify(base)).not.toMatch(/api[_-]?key|access[_-]?token/i);
    }
  });

  it("prefers the query parameter, then storage, then the default", () => {
    expect(chooseBasemap("?base=light")).toBe("light");
    window.localStorage.setItem(BASE_STORAGE_KEY, "satellite");
    expect(chooseBasemap("")).toBe("satellite");
    expect(chooseBasemap("?base=light")).toBe("light");
  });

  it("ignores a basemap id this build does not offer, in the URL or in storage", () => {
    // A guarded lookup: stale storage from an older release must not blank the map.
    window.localStorage.setItem(BASE_STORAGE_KEY, "carto-dark-matter");
    expect(chooseBasemap("")).toBe(DEFAULT_BASEMAP);
    expect(chooseBasemap("?base=../../etc/passwd")).toBe(DEFAULT_BASEMAP);
  });

  it("declares no style property with an undefined value", () => {
    // Regression from P8: MapLibre validates any property that is *present*, so an
    // undefined one fails validation and the style — with every layer on it — never loads.
    for (const style of [graticuleStyle(), rasterStyle(basemapDef("satellite")!)]) {
      for (const [key, value] of Object.entries(style)) {
        expect(value, `style.${key} is undefined`).toBeDefined();
      }
    }
  });

  it("omits glyphs entirely when no label assets are served", () => {
    const style = vectorStyle(basemapDef("dark")!, { labels: false });
    expect("glyphs" in style).toBe(false);
    expect(style.layers.every((layer) => layer.type !== "symbol")).toBe(true);
  });

  it("serves labels from the app's own origin when the assets are present", () => {
    const style = vectorStyle(basemapDef("dark")!, { labels: true });
    expect(style.glyphs).toBe("/basemap/fonts/{fontstack}/{range}.pbf");
    // MapLibre refuses a relative sprite url, so this one carries the app's own origin.
    expect(style.sprite).toBe(`${window.location.origin}/basemap/sprites/dark`);
  });

  it("reads the basemap archive from the app's own origin, never a third party", () => {
    expect(pmtilesUrl()).toMatch(/^pmtiles:\/\/\//);
    const source = vectorStyle(basemapDef("dark")!, { labels: false }).sources["protomaps"];
    // The attribution text carries links by obligation; the tile locator must not.
    expect(source && "url" in source && source.url).toBe(pmtilesUrl());
    expect(source && "tiles" in source).toBe(false);
  });

  it("splits county boundaries out of the state line so both read as separate weights", () => {
    const ids = vectorStyle(basemapDef("dark")!, { labels: false }).layers.map((l) => l.id);
    expect(ids).toContain("gw-boundaries-county");
    expect(ids).toContain("gw-boundaries-state");
  });

  it("tunes the dark flavour to the brand ink so the basemap reads as part of the product", () => {
    const style = vectorStyle(basemapDef("dark")!, { labels: false });
    const background = style.layers.find((layer) => layer.type === "background");
    expect(background && "paint" in background && background.paint).toMatchObject({
      "background-color": "#0B1014",
    });
  });

  it("degrades the imagery basemap to the graticule, locally, when its tiles cannot be had", () => {
    // Not the declaration — the behaviour. The satellite option declared a graticule fallback
    // that nothing executed, and a green assertion on a field with no consumer read as
    // coverage for a recovery that never ran (gate-inc3 R3.1/R3.5).
    const fallback = fallbackStyle(basemapDef("satellite")!);

    expect(fallback?.style.layers.map((layer) => layer.id)).toEqual(["canvas", "graticule"]);
    expect(fallback?.failure).toEqual({
      source: "basemap.nationalmap.gov",
      fallback: "the graticule",
    });
    expect(JSON.stringify(fallback?.style)).not.toContain("USGS");
  });

  it("has nothing to fall back to where nothing was declared, and says so by returning null", () => {
    expect(fallbackStyle(basemapDef("none")!)).toBe(null);
    expect(fallbackStyle({ ...basemapDef("satellite")!, fallback: null })).toBe(null);
  });

  it("names the locator that failed, not the module that happens to serve the style", () => {
    // R3.2: the raster style reused the vector source id, so a USGS outage was reported as
    // "Tiles for protomaps did not load".
    expect(sourceLabel("satellite")).toBe("basemap.nationalmap.gov");
    expect(sourceLabel(BASEMAP_SOURCE)).toBe(PMTILES_PATH);
    expect(sourceLabel("nd_wells")).toBe("nd_wells");
  });

  it("gives the imagery style a source of its own, so an error can be attributed to it", () => {
    const style = rasterStyle(basemapDef("satellite")!);
    expect(Object.keys(style.sources)).toEqual(["satellite"]);
    expect(Object.keys(style.sources)).not.toContain(BASEMAP_SOURCE);
  });

  it("fetches its imagery from exactly one external origin, and names it", () => {
    // The CSP allow-lists this host by name (`glasswell.api.security`). Any second origin
    // added here is a request the browser will make and the policy will refuse.
    const origins = BASEMAPS.flatMap((base) => base.tiles ?? []).map((url) => new URL(url).origin);
    expect([...new Set(origins)]).toEqual(["https://basemap.nationalmap.gov"]);
  });

  it("draws the graticule when no basemap is chosen, so 'none' is a view not a blank", () => {
    const style = graticuleStyle();
    expect(style.layers.map((layer) => layer.id)).toEqual(["canvas", "graticule"]);
  });
});

describe("the basemap variant attribute", () => {
  beforeEach(() => delete document.documentElement.dataset["basemap"]);

  it("names one variant per offered basemap, and nothing else", () => {
    expect([...BASEMAP_VARIANTS]).toEqual(basemapIds());
  });

  it("publishes the active variant on the document, where any stylesheet can read it", () => {
    applyBasemapVariant("light");
    expect(document.documentElement.dataset["basemap"]).toBe("light");
    applyBasemapVariant("satellite");
    expect(document.documentElement.dataset["basemap"]).toBe("satellite");
  });

  it("mirrors the variant onto the map container, so map.css need not reach the root", () => {
    const container = document.createElement("div");
    applyBasemapVariant("none", container);
    expect(container.dataset["basemap"]).toBe("none");
    expect(document.documentElement.dataset["basemap"]).toBe("none");
  });

  it("falls back to the default variant rather than writing an id no stylesheet keys on", () => {
    expect(basemapVariant("carto-dark-matter")).toBe(DEFAULT_BASEMAP);
    applyBasemapVariant("carto-dark-matter");
    expect(document.documentElement.dataset["basemap"]).toBe(DEFAULT_BASEMAP);
  });
});
