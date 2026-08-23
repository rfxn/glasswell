// @vitest-environment happy-dom
import { describe, expect, it } from "vitest";

import { IMAGERY_HOST, BASEMAP_SOURCE, PMTILES_PATH } from "./basemap.ts";
import { resolveBasemapStyle } from "./map.ts";
import { createTileBanner } from "./tile-banner.ts";

/**
 * The hybrid's two substrates fail apart, and the resolve path is the only place that can
 * tell the reader the imagery went: with no imagery source in the style MapLibre issues no
 * tile request, so the `error` handler that raises today's banner never fires.
 */
describe("when the hybrid's imagery cannot be had but its archive can", () => {
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

  const manifest = (): Response =>
    new Response(JSON.stringify({ archive: PMTILES_PATH, labels: true }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });

  const archiveServes = (url: string): Response | Promise<Response> =>
    url.includes("manifest") ? manifest() : new Response(null, { status: 206 });

  const imageryRefused = (url: string): Response | Promise<Response> =>
    url.includes(IMAGERY_HOST)
      ? Promise.reject(new TypeError("Failed to fetch"))
      : archiveServes(url);

  const sourcesOf = (style: unknown): string[] =>
    Object.keys((style as { sources: Record<string, unknown> }).sources);

  const layerIdsOf = (style: unknown): string[] =>
    (style as { layers: { id: string }[] }).layers.map((layer) => layer.id);

  it("asks the imagery origin whether it answers before drawing a credit for it", async () => {
    const { seen } = await withFetch("hybrid", imageryRefused);
    const external = seen.filter((url) => url.includes(IMAGERY_HOST));

    expect(external).toHaveLength(1);
    expect(external[0]).not.toContain("{z}");
  });

  it("takes the imagery credit down with the imagery, and keeps the labels and theirs", async () => {
    // R3.3: an attribution over a canvas with no imagery on it is a false statement about
    // what was drawn. The archive is a separate source, still drawn, and still obliges.
    const { resolved } = await withFetch("hybrid", imageryRefused);

    expect(sourcesOf(resolved.style)).toEqual([BASEMAP_SOURCE]);
    expect(JSON.stringify(resolved.style)).not.toContain("Earthstar");
    expect(JSON.stringify(resolved.style)).toContain("OpenStreetMap");
    expect(layerIdsOf(resolved.style)).not.toContain("hybrid");
    expect(
      (resolved.style as { layers: { type: string }[] }).layers.some((l) => l.type === "symbol"),
    ).toBe(true);
  });

  it("still says the imagery is gone, which no tile error can say once the source is absent", async () => {
    // Dropping the source is what makes the credit honest and is also what silences
    // MapLibre: no source, no tile request, no `error` event, no banner from that path.
    const { resolved } = await withFetch("hybrid", imageryRefused);

    expect(resolved.failure?.source).toBe(IMAGERY_HOST);
  });

  it("names the imagery without promising a substitution, because none was made", async () => {
    const { resolved } = await withFetch("hybrid", imageryRefused);
    const banner = createTileBanner();
    banner.report(resolved.failure!.source, resolved.failure!.fallback);

    expect(banner.element.hidden).toBe(false);
    expect(banner.element.textContent).toContain(`Tiles for ${IMAGERY_HOST} did not load.`);
    expect(banner.element.textContent).not.toContain("instead");
  });

  it("keeps the imagery, its layer and its credit when the origin answers", async () => {
    const { resolved } = await withFetch("hybrid", (url) =>
      url.includes(IMAGERY_HOST) ? new Response(null, { status: 200 }) : archiveServes(url),
    );

    expect(resolved.failure).toBeUndefined();
    expect(sourcesOf(resolved.style)).toEqual([BASEMAP_SOURCE, "hybrid"]);
    expect(JSON.stringify(resolved.style)).toContain("Earthstar");
  });

  it("reports the archive, not the imagery, when both are down", async () => {
    // The archive is checked first and its failure is the more total one: no labels, no
    // imagery, the graticule. Naming the imagery there would name the lesser loss.
    const { resolved } = await withFetch("hybrid", (url) =>
      url.includes(IMAGERY_HOST)
        ? Promise.reject(new TypeError("Failed to fetch"))
        : url.includes("manifest")
          ? manifest()
          : new Response(null, { status: 404 }),
    );

    expect(resolved.failure?.source).toBe(PMTILES_PATH);
    expect(resolved.failure?.fallback).toBe("the graticule");
    expect(layerIdsOf(resolved.style)).toEqual(["canvas", "graticule"]);
  });

  it("asks nothing of the imagery origin for the options that draw none", async () => {
    for (const id of ["dark", "light"]) {
      const { seen } = await withFetch(id, archiveServes);

      expect(seen.filter((url) => /^https?:\/\//i.test(url)), id).toEqual([]);
    }
  });
});
