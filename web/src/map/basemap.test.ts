// @vitest-environment happy-dom
import { beforeEach, describe, expect, it } from "vitest";

import { BASE_STORAGE_KEY } from "./persist.ts";
import {
  BASEMAPS,
  BASEMAP_SOURCE,
  BASEMAP_VARIANTS,
  DEFAULT_BASEMAP,
  IMAGERY_HOST,
  PMTILES_PATH,
  applyBasemapVariant,
  basemapDef,
  basemapIds,
  basemapVariant,
  chooseBasemap,
  fallbackStyle,
  firstLabelLayerId,
  graticuleStyle,
  GLYPHS_URL,
  pmtilesUrl,
  rasterStyle,
  sourceLabel,
  vectorStyle,
} from "./basemap.ts";

describe("the basemap catalogue", () => {
  beforeEach(() => window.localStorage.clear());

  it("offers the five options the market bar expects", () => {
    expect(basemapIds()).toEqual(["dark", "light", "satellite", "hybrid", "none"]);
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
    expect(fallback?.failure).toEqual({ source: IMAGERY_HOST, fallback: "the graticule" });
    // R3.3: the credit ships with the style that carries the tiles, so it goes down with them.
    expect(JSON.stringify(fallback?.style)).not.toContain("Earthstar");
  });

  it("has nothing to fall back to where nothing was declared, and says so by returning null", () => {
    expect(fallbackStyle(basemapDef("none")!)).toBe(null);
    expect(fallbackStyle({ ...basemapDef("satellite")!, fallback: null })).toBe(null);
  });

  it("names the locator that failed, not the module that happens to serve the style", () => {
    // R3.2: the raster style reused the vector source id, so an imagery outage was reported
    // as "Tiles for protomaps did not load".
    expect(sourceLabel("satellite")).toBe(IMAGERY_HOST);
    expect(sourceLabel(BASEMAP_SOURCE)).toBe(PMTILES_PATH);
    expect(sourceLabel("nd_wells")).toBe("nd_wells");
  });

  it("gives the imagery-only style one source, so an outage is attributed to the imagery", () => {
    // R3.2, unchanged for the option that draws imagery and nothing else: reusing the vector
    // source id here made an imagery outage report itself as a Protomaps one.
    const style = rasterStyle(basemapDef("satellite")!);
    expect(Object.keys(style.sources)).toEqual(["satellite"]);
    expect(Object.keys(style.sources)).not.toContain(BASEMAP_SOURCE);
  });

  it("keeps the hybrid's two substrates on separate sources, each attributable on its own", () => {
    // The same rule as above, for the one option that legitimately composes both: two
    // substrates that fail independently must not collapse into one name in the banner.
    const style = vectorStyle(basemapDef("hybrid")!, { labels: true, origin: "https://x" });
    expect(Object.keys(style.sources).sort()).toEqual(["hybrid", BASEMAP_SOURCE].sort());
    expect(sourceLabel("hybrid")).toBe(IMAGERY_HOST);
    expect(sourceLabel(BASEMAP_SOURCE)).toBe(PMTILES_PATH);
  });

  it("fetches its imagery from exactly one external origin, and names it", () => {
    // The CSP allow-lists this host by name (`glasswell.api.security`, and the Caddy
    // restatement of the same header). A second origin here is a request the policy refuses.
    const origins = BASEMAPS.flatMap((base) => base.tiles ?? []).map((url) => new URL(url).origin);
    expect([...new Set(origins)]).toEqual([`https://${IMAGERY_HOST}`]);
  });

  it("names no external tile origin anywhere in the basemap module", () => {
    const external = Object.values(BASEMAPS)
      .flatMap((base) => ("tiles" in base && base.tiles) || [])
      .filter((url) => !url.includes(IMAGERY_HOST));

    expect(external).toEqual([]);
  });

  it("stops the imagery at the last zoom that carries any, not the one the service advertises", () => {
    // Measured: z20 is a byte-identical grey "no data" placeholder everywhere it was probed,
    // while the service metadata advertises 24 levels. Declaring 20 would paint that across
    // the basin; declaring 19 makes MapLibre overzoom real pixels instead.
    for (const base of BASEMAPS.filter((candidate) => candidate.tiles?.length)) {
      expect(base.maxzoom, `${base.id} imagery ceiling`).toBe(19);
    }
  });

  it("draws the graticule when no basemap is chosen, so 'none' is a view not a blank", () => {
    const style = graticuleStyle();
    expect(style.layers.map((layer) => layer.id)).toEqual(["canvas", "graticule"]);
  });
});

describe("the hybrid basemap", () => {
  const hybrid = () => vectorStyle(basemapDef("hybrid")!, { labels: true, origin: "https://x" });

  it("takes the archive path, so the protocol and the 206 check are the ones already run", () => {
    // The imagery is raster but the labels are PMTiles, and only the vector branch of
    // resolveStyle registers the pmtiles protocol. A raster-kinded hybrid would ask MapLibre
    // for a `pmtiles://` url through a protocol nothing had registered.
    const base = basemapDef("hybrid")!;
    expect(base.kind).toBe("vector");
    expect(base.tiles?.length).toBeGreaterThan(0);
    const source = hybrid().sources[BASEMAP_SOURCE];
    expect(source && "url" in source && source.url).toBe(pmtilesUrl());
  });

  it("draws imagery under labels, so the names sit on the picture and not beneath it", () => {
    const ids = hybrid().layers.map((layer) => layer.id);
    expect(ids.slice(0, 2)).toEqual(["canvas", "hybrid"]);
    expect(firstLabelLayerId(hybrid())).toBe(ids[2]);
  });

  it("composes labels and nothing else over the imagery, so no flavour fill hides it", () => {
    // The vector flavours paint earth, water and landuse. Over imagery those are opaque
    // rectangles where the picture should be, so the hybrid takes the symbol complement only.
    const layers = hybrid().layers;
    const nonSymbol = layers.filter((layer) => layer.id !== "canvas" && layer.id !== "hybrid");
    expect(nonSymbol.every((layer) => layer.type === "symbol")).toBe(true);
    expect(layers.map((layer) => layer.id)).toContain("roads_labels_major");
    expect(layers.map((layer) => layer.id)).toContain("places_locality");
  });

  it("drops the two symbol layers the variant pass cannot reach or the imagery cannot carry", () => {
    // `roads_oneway` has an icon and no text-field, so `textLayers()` never selects it and it
    // would draw an unstyled arrow; `pois` turns dense at z17 over aerial. Both are omitted
    // rather than left to render outside the contrast machinery.
    const ids = hybrid().layers.map((layer) => layer.id);
    expect(ids).not.toContain("roads_oneway");
    expect(ids).not.toContain("pois");
  });

  it("serves glyphs and sprites, without which every symbol layer is silently dropped", () => {
    const style = hybrid();
    expect(style.glyphs).toBe(GLYPHS_URL);
    expect(style.sprite).toBe("https://x/basemap/sprites/dark");
  });

  it("falls back to imagery alone where the archive ships no label assets", () => {
    // A pre-label archive is a real deploy state. The honest degradation is the picture with
    // no names — local, and what Satellite gives — not a graticule over working imagery.
    const style = vectorStyle(basemapDef("hybrid")!, { labels: false });
    expect(style.layers.map((layer) => layer.id)).toEqual(["canvas", "hybrid"]);
    expect("glyphs" in style).toBe(false);
    expect("sprite" in style).toBe(false);
  });

  it("drops the imagery and its credit together when the imagery cannot be had", () => {
    // R3.3, for the substrate that can fail without taking the option down with it: a credit
    // over a canvas with no imagery on it is a false statement about what was drawn. The
    // labels are a separate source and stay, because they are still drawn and still oblige.
    const style = vectorStyle(basemapDef("hybrid")!, {
      labels: true,
      imagery: false,
      origin: "https://x",
    });
    expect(Object.keys(style.sources)).toEqual([BASEMAP_SOURCE]);
    expect(JSON.stringify(style)).not.toContain("Earthstar");
    expect(JSON.stringify(style)).toContain("OpenStreetMap");
    expect(style.layers.map((layer) => layer.id)).not.toContain("hybrid");
    expect(style.layers.some((layer) => layer.type === "symbol")).toBe(true);
  });

  it("credits both substrates, because both are drawn and both oblige", () => {
    // MapLibre's AttributionControl aggregates per-source strings, so the obligation is met
    // by putting each credit on the source that carries the bytes it covers.
    const sources = hybrid().sources;
    const imagery = sources["hybrid"]!;
    const archive = sources[BASEMAP_SOURCE]!;
    expect("attribution" in imagery && imagery.attribution).toContain("Esri");
    expect("attribution" in archive && archive.attribution).toContain("OpenStreetMap");
  });

  it("degrades to the graticule, locally, when the archive that carries its labels cannot", () => {
    expect(fallbackStyle(basemapDef("hybrid")!)?.style.layers.map((layer) => layer.id)).toEqual([
      "canvas",
      "graticule",
    ]);
  });
});

describe("the basemap variant attribute", () => {
  beforeEach(() => delete document.documentElement.dataset["basemap"]);

  it("makes every option declare the substrate it is read against, so none can infer one", () => {
    // The trap this replaces: `basemapVariant` resolved an id by name and fell to the default
    // for anything it did not recognise, so a fifth option shipped dark slate labels over
    // bright imagery with no error anywhere. A declared variant cannot be forgotten silently.
    for (const base of BASEMAPS) {
      expect([...BASEMAP_VARIANTS], `${base.id} declares no substrate`).toContain(base.variant);
      expect(basemapVariant(base.id), `${base.id} resolves away from its declaration`).toBe(
        base.variant,
      );
    }
  });

  it("reads the hybrid against the imagery substrate, not the ink one under its own name", () => {
    expect(basemapVariant("hybrid")).toBe("satellite");
    applyBasemapVariant("hybrid");
    // map.css keys chrome surfaces on the substrate, so the attribute is the substrate's name.
    expect(document.documentElement.dataset["basemap"]).toBe("satellite");
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
