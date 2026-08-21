// @vitest-environment happy-dom
import { describe, expect, it } from "vitest";

import { tileUrl } from "../api/client.ts";
import { graticuleStyle, vectorStyle, basemapDef } from "./basemap.ts";
import { resolveBasemapStyle } from "./map.ts";
import { absoluteTileUrl, dataLayers, sourceSpecs } from "./style.ts";

describe("every style this app can load", () => {
  const styles = [
    ["graticule", graticuleStyle()],
    ["pmtiles dark", vectorStyle(basemapDef("dark")!, { labels: false })],
    ["pmtiles light with labels", vectorStyle(basemapDef("light")!, { labels: true })],
  ] as const;

  it("declares no style property with an undefined value", () => {
    // MapLibre validates a property that is *present*, so `glyphs: undefined` fails
    // validation, the style never loads, `map.on("load")` never fires, and no source,
    // layer or tile request is ever created. The canvas is then blank with no error
    // visible to the user. Found by P8's browser smoke against the deployed instance.
    for (const [name, style] of styles) {
      for (const [key, value] of Object.entries(style)) {
        expect(value, `${name}: style.${key} is undefined`).toBeDefined();
      }
    }
  });

  it("survives the JSON round-trip MapLibre applies to a style object", () => {
    for (const [, style] of styles) {
      expect(JSON.parse(JSON.stringify(style))).toEqual(style);
    }
  });

  it("draws the graticule over the dark canvas and nothing else when no basemap is chosen", () => {
    const style = graticuleStyle();
    expect(style.layers.map((layer) => layer.id)).toEqual(["canvas", "graticule"]);
    expect(Object.keys(style.sources)).toEqual(["graticule"]);
  });
});

describe("when the basemap archive cannot serve", () => {
  const withFetch = async (handler: (url: string) => Response) => {
    const seen: string[] = [];
    const original = globalThis.fetch;
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      const url = String(input);
      seen.push(url);
      return handler(url);
    }) as typeof fetch;
    try {
      return { style: await resolveBasemapStyle("dark"), seen };
    } finally {
      globalThis.fetch = original;
    }
  };

  it("falls back to the graticule, locally, and asks no other origin for anything", async () => {
    // The coded fallback used to be https://tiles.openfreemap.org and it had never once
    // worked: `connect-src 'self'` refuses it, which is the correct posture. A fallback the
    // security policy forbids is a second failure, not a recovery.
    const { style, seen } = await withFetch(() => new Response(null, { status: 404 }));

    expect(typeof style.style).not.toBe("string");
    expect((style.style as { layers: { id: string }[] }).layers.map((l) => l.id)).toEqual([
      "canvas",
      "graticule",
    ]);
    expect(style.failure?.fallback).toBe("the graticule");
    expect(seen.filter((url) => /^https?:\/\//i.test(url))).toEqual([]);
  });

  it("says so, and names the source that failed rather than the one that did not", async () => {
    const { style } = await withFetch(() => new Response(null, { status: 404 }));

    expect(style.failure?.source).toContain("pmtiles");
  });

  it("takes the archive when it answers a ranged request", async () => {
    const { style, seen } = await withFetch((url) =>
      url.includes("manifest")
        ? new Response("{}", { status: 200, headers: { "content-type": "application/json" } })
        : new Response(null, { status: 206 }),
    );

    expect(style.failure).toBeUndefined();
    expect(seen.filter((url) => /^https?:\/\//i.test(url))).toEqual([]);
  });
});

describe("absoluteTileUrl", () => {
  it("keeps MapLibre's placeholders literal", () => {
    // `new URL()` percent-encodes the braces, and MapLibre then requests
    // /v1/tiles/nd_laterals/%7Bz%7D/... — every tile 422s and the map stays empty.
    // Found by P8's browser smoke against the deployed instance.
    const url = absoluteTileUrl(tileUrl("nd_laterals"));

    expect(url).toBe(`${window.location.origin}/v1/tiles/nd_laterals/{z}/{x}/{y}.pbf`);
    expect(url).not.toContain("%7B");
  });

  it("leaves an already-absolute tile origin alone", () => {
    const absolute = "https://tiles.example/v1/tiles/nd_wells/{z}/{x}/{y}.pbf";
    expect(absoluteTileUrl(absolute)).toBe(absolute);
  });

  it("keeps the placeholders literal on every published source", () => {
    for (const spec of Object.values(sourceSpecs())) {
      for (const template of ("tiles" in spec && spec.tiles) || []) {
        expect(template).not.toContain("%7B");
        expect(template).toContain("{z}/{x}/{y}");
      }
    }
  });
});

describe("the data layers over a basemap", () => {
  it("carry no source the basemap also defines, so a style swap cannot collide", () => {
    const basemapSources = Object.keys(vectorStyle(basemapDef("dark")!, { labels: false }).sources);
    for (const id of Object.keys(sourceSpecs())) expect(basemapSources).not.toContain(id);
  });

  it("name layer ids the basemap does not already use", () => {
    const basemapLayers = new Set(
      vectorStyle(basemapDef("dark")!, { labels: false }).layers.map((layer) => layer.id),
    );
    for (const layer of dataLayers({ labels: true })) expect(basemapLayers.has(layer.id)).toBe(false);
  });
});
