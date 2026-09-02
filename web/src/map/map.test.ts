// @vitest-environment happy-dom
import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { tileUrl } from "../api/client.ts";
import { IMAGERY_HOST, graticuleStyle, vectorStyle, basemapDef } from "./basemap.ts";
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

describe("when a basemap's tiles cannot be had", () => {
  const withFetch = async (
    id: string,
    handler: (url: string) => Response | Promise<Response>,
  ): Promise<{ resolved: Awaited<ReturnType<typeof resolveBasemapStyle>>; seen: string[] }> => {
    const seen: string[] = [];
    const original = globalThis.fetch;
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      const url = String(input);
      seen.push(url);
      return handler(url);
    }) as typeof fetch;
    try {
      return { resolved: await resolveBasemapStyle(id), seen };
    } finally {
      globalThis.fetch = original;
    }
  };

  const refuseImagery = (url: string): Response | Promise<Response> =>
    url.includes(IMAGERY_HOST)
      ? Promise.reject(new TypeError("Failed to fetch"))
      : new Response("{}", { status: 200, headers: { "content-type": "application/json" } });

  const layerIdsOf = (style: unknown): string[] =>
    (style as { layers: { id: string }[] }).layers.map((layer) => layer.id);

  it("falls back to the graticule, locally, when the archive cannot serve", async () => {
    // The coded fallback used to be https://tiles.openfreemap.org and it had never once
    // worked: `connect-src 'self'` refuses it, which is the correct posture. A fallback the
    // security policy forbids is a second failure, not a recovery.
    const { resolved } = await withFetch("dark", () => new Response(null, { status: 404 }));

    expect(layerIdsOf(resolved.style)).toEqual(["canvas", "graticule"]);
    expect(resolved.failure?.fallback).toBe("the graticule");
  });

  it("says so, and names the source that failed rather than the one that did not", async () => {
    const { resolved } = await withFetch("dark", () => new Response(null, { status: 404 }));

    expect(resolved.failure?.source).toContain("pmtiles");
  });

  it("takes the archive when it answers a ranged request", async () => {
    const { resolved, seen } = await withFetch("dark", (url) =>
      url.includes("manifest")
        ? new Response("{}", { status: 200, headers: { "content-type": "application/json" } })
        : new Response(null, { status: 206 }),
    );

    expect(resolved.failure).toBeUndefined();
    expect(seen.filter((url) => /^https?:\/\//i.test(url))).toEqual([]);
  });

  it("runs the declared graticule fallback rather than leaving an empty canvas", async () => {
    // The satellite option declared `fallback: "graticule"` and nothing executed it: under the
    // production CSP the gate measured 122 refusals and 97.4% bare app background (R3.1).
    const { resolved } = await withFetch("satellite", refuseImagery);

    expect(layerIdsOf(resolved.style)).toEqual(["canvas", "graticule"]);
    expect(resolved.failure).toEqual({
      source: IMAGERY_HOST,
      fallback: "the graticule",
    });
  });

  it("takes the attribution down with the imagery it belonged to", async () => {
    // R3.3: the imagery credit was rendering over a canvas with no imagery on it. The credit
    // ships with the style that carries the tiles, so it goes down with them.
    const { resolved } = await withFetch("satellite", refuseImagery);

    expect(JSON.stringify(resolved.style)).not.toContain("Earthstar");
  });

  it("asks the imagery origin one question before committing the reader to it", async () => {
    const { seen } = await withFetch("satellite", refuseImagery);
    const external = seen.filter((url) => url.includes(IMAGERY_HOST));

    expect(external).toHaveLength(1);
    expect(external[0]).not.toContain("{z}");
  });

  it("keeps the imagery, and its credit, when the origin answers", async () => {
    const { resolved } = await withFetch("satellite", (url) =>
      url.includes(IMAGERY_HOST)
        ? new Response(null, { status: 200 })
        : new Response("{}", { status: 200, headers: { "content-type": "application/json" } }),
    );

    expect(resolved.failure).toBeUndefined();
    expect(Object.keys((resolved.style as { sources: object }).sources)).toEqual(["satellite"]);
    expect(JSON.stringify(resolved.style)).toContain("Earthstar");
  });

  it("keeps every other basemap zero-external, in what it fetches and in what it hands back", async () => {
    // The archive is absent in this arm, which is the state that used to reach for
    // https://tiles.openfreemap.org — a hosted substitute `connect-src 'self'` refuses, so the
    // banner promised a recovery the reader could not receive. Asserting only on the requests
    // this function makes would miss it: the style it returns is fetched by MapLibre, not here.
    for (const id of ["dark", "light", "none"]) {
      const { resolved, seen } = await withFetch(id, () => new Response(null, { status: 404 }));

      expect(seen.filter((url) => /^https?:\/\//i.test(url)), id).toEqual([]);
      expect(JSON.stringify(resolved.style), id).not.toMatch(/https?:\/\/(?!www\.openstreetmap|protomaps\.com)/);
      expect(layerIdsOf(resolved.style), id).toEqual(["canvas", "graticule"]);
    }
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

/**
 * R3, handed back by the map-truth track. `createMap` needs a WebGL context, so the wiring is
 * pinned here and the resolution itself is tested in counts.test.ts, where it is a pure
 * function over rendered features.
 */
describe("the ⌾ a drawn layer row resolves", () => {
  const SOURCE = readFileSync("src/map/map.ts", "utf8");
  const body = (name: string): string =>
    new RegExp(`function ${name}\\(\\)[\\s\\S]*?\\n  }\\n`).exec(SOURCE)?.[0] ?? "";

  it("is fed from the coverage pass, which sees every drawn row and not only the wells", () => {
    const coverage = body("refreshCoverage");

    expect(coverage).toContain("rowDerivations(drawable, features)");
    expect(coverage).toContain("panel.setProvenance(id, handle)");
  });

  it("queries once and reads both answers off it, so coverage and provenance cannot disagree", () => {
    const coverage = body("refreshCoverage");

    expect(coverage.match(/queryRenderedFeatures/g)).toHaveLength(1);
  });

  it("gives each wells row its own tile's handle instead of the canvas-wide first one", () => {
    const drawn = body("refreshDrawn");

    expect(drawn).toContain("rowDerivations(");
    expect(drawn).not.toContain("census.derivation");
  });
});
