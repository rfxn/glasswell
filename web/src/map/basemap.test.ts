// @vitest-environment happy-dom
import { beforeEach, describe, expect, it } from "vitest";

import { BASE_STORAGE_KEY } from "./persist.ts";
import {
  BASEMAPS,
  DEFAULT_BASEMAP,
  basemapDef,
  basemapIds,
  chooseBasemap,
  graticuleStyle,
  pmtilesUrl,
  rasterStyle,
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

  it("names a coded fallback for every option that could fail to load", () => {
    expect(basemapDef("dark")?.fallback).toBe("openfreemap");
    expect(basemapDef("none")?.fallback).toBe(null);
  });

  it("draws the graticule when no basemap is chosen, so 'none' is a view not a blank", () => {
    const style = graticuleStyle();
    expect(style.layers.map((layer) => layer.id)).toEqual(["canvas", "graticule"]);
  });
});
