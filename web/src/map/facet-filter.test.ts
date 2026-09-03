import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { featureFilter } from "@maplibre/maplibre-gl-style-spec";
import { describe, expect, it } from "vitest";

import {
  FACET_FILTERED_LAYERS,
  FACET_TILE_PROPERTY,
  TILE_FACET_PROPERTIES,
  dataLayers,
  facetTileProperty,
  facetUnfilteredLayers,
  statusStyledLayerIds,
} from "./style.ts";

const TILES_PY = fileURLToPath(new URL("../../../src/glasswell/marts/tiles.py", import.meta.url));

/**
 * The publication boundary, read rather than restated. `TILE_FACET_PROPERTIES` is a hand list in
 * a TypeScript file and `marts/tiles.py` is what actually decides which columns reach the wire,
 * so a copy of the tuples here would agree with itself while the tile server disagreed with
 * both. Parsing the constructor calls is what makes a column dropped in Python fail in the
 * browser suite instead of silently un-filtering a layer on the canvas.
 */
function publishedColumns(): Map<string, string[]> {
  const source = readFileSync(TILES_PY, "utf8");
  const layers = new Map<string, string[]>();
  for (const block of source.split("TileLayer(").slice(1)) {
    const name = /name="([^"]+)"/.exec(block)?.[1];
    const properties = /properties=\(([\s\S]*?)\n {8}\),/.exec(block)?.[1];
    if (!name || properties === undefined) continue;
    layers.set(name, [...properties.matchAll(/\("([a-z0-9_]+)",\s*"[a-z0-9]+"\)/g)].map((m) => m[1]!));
  }
  return layers;
}

describe("the tile columns a facet press can filter on", () => {
  const published = publishedColumns();

  it("parses every tile layer out of tiles.py, so an empty parse cannot pass as agreement", () => {
    // The parser is the assertion's evidence: if it silently matched nothing, every check
    // below would compare two empty sets and report a matrix that does not exist.
    expect(published.size).toBeGreaterThanOrEqual(15);
    expect(published.get("nd_wells")).toContain("status_canonical");
  });

  it("declares, per tile layer, exactly the facet columns tiles.py publishes", () => {
    const wanted = new Set(Object.values(FACET_TILE_PROPERTY));
    for (const [source, declared] of Object.entries(TILE_FACET_PROPERTIES)) {
      const columns = published.get(source);
      expect(columns, `${source} is not a published tile layer`).toBeDefined();
      expect([...declared].sort()).toEqual(columns!.filter((column) => wanted.has(column)).sort());
    }
  });

  it("covers every tile layer any well style layer reads, and no other", () => {
    expect([...new Set(FACET_FILTERED_LAYERS.map((layer) => layer.source))].sort()).toEqual(
      Object.keys(TILE_FACET_PROPERTIES).sort(),
    );
  });

  it("puts operator and status on every well and bore layer, which is what makes them free", () => {
    for (const { id } of FACET_FILTERED_LAYERS) {
      expect(facetTileProperty(id, "operator"), id).toBe("operator_name");
      expect(facetTileProperty(id, "status"), id).toBe("status_canonical");
    }
  });

  it("puts well type on every point layer and on no line layer", () => {
    const filterable = FACET_FILTERED_LAYERS.filter(
      (layer) => facetTileProperty(layer.id, "well_type") !== null,
    ).map((layer) => layer.source);

    expect([...new Set(filterable)].sort()).toEqual([
      "co_wells",
      "mt_wells",
      "nd_wells",
      "nm_wells",
      "tx_wells",
    ]);
  });

  it("puts county on the three jurisdictions whose tiles carry it", () => {
    const filterable = FACET_FILTERED_LAYERS.filter(
      (layer) => facetTileProperty(layer.id, "county") !== null,
    ).map((layer) => layer.source);

    // Colorado joins Texas and New Mexico: ECMC files the county segment of the API in its
    // own column, so the tile can carry it and a press can narrow on it.
    expect([...new Set(filterable)].sort()).toEqual([
      "co_wells",
      "nm_wells",
      "tx_laterals",
      "tx_wells",
    ]);
  });

  it("filters on no dimension the tiles publish no column for", () => {
    // completion_year rides one layer of thirteen and geometry_provenance three, so neither is
    // a canvas filter in this phase: a press that narrowed Montana and left Texas whole would
    // read as "Texas has no wells of this year".
    for (const dimension of ["completion_year", "geometry_provenance", "basin"]) {
      expect(FACET_TILE_PROPERTY[dimension]).toBeUndefined();
      for (const { id } of FACET_FILTERED_LAYERS) {
        expect(facetTileProperty(id, dimension), `${id}/${dimension}`).toBeNull();
      }
    }
  });
});

describe("the layers a facet press has to reach", () => {
  it("holds the status-gated seven, exactly as the style declares them", () => {
    const gated = FACET_FILTERED_LAYERS.filter((layer) => layer.gated).map((layer) => layer.id);
    expect(gated.sort()).toEqual([...statusStyledLayerIds()].sort());
  });

  it("holds the layers outside the status gate that would keep drawing filtered-out wells", () => {
    // The defect this list exists to prevent: each of these carries its own predicate, so a
    // press that only rewrote the status gate would leave struck plugs, disposal rings and
    // survey traces painted for every operator the reader just filtered away. One struck
    // overlay per registered jurisdiction, so a fifth adds one here and no line elsewhere.
    const ungated = FACET_FILTERED_LAYERS.filter((layer) => !layer.gated).map((layer) => layer.id);
    expect(ungated.sort()).toEqual([
      "co-wells-struck",
      "disposal-wells",
      "mt-wells-struck",
      "nm-wells-struck",
      "survey-traces",
      "tx-wells-struck",
      "wells-struck",
    ]);
  });

  it("names a real style layer for every entry, and every well layer the style builds", () => {
    const drawn = new Set(dataLayers({ labels: true }).map((layer) => layer.id));
    for (const { id } of FACET_FILTERED_LAYERS) expect(drawn.has(id), id).toBe(true);

    // The other direction: a well layer added to the style without an entry here is a layer a
    // press silently skips, which is exactly how the four ungated ones were missed.
    const sources = new Set(Object.keys(TILE_FACET_PROPERTIES));
    const wellLayers = dataLayers({ labels: true })
      .filter((layer) => "source" in layer && sources.has(layer.source))
      .map((layer) => layer.id);
    expect(wellLayers.sort()).toEqual(FACET_FILTERED_LAYERS.map((layer) => layer.id).sort());
  });

  it("names which layers a press would leave unfiltered, so the pill can say so", () => {
    expect(facetUnfilteredLayers("operator")).toEqual([]);
    // The line layers publish no well type, so a well-type press narrows the dots and not the
    // bores — a statement the pill owes the reader rather than a difference they must notice.
    expect(facetUnfilteredLayers("well_type")).toEqual([
      "laterals",
      "survey-traces",
      "mt-paths",
      "tx-laterals",
    ]);
    // The wells rows in registered draw order, then the disposal ring: the ring reads the
    // founding row's source and is declared after the rows it overlays rather than inside
    // them, which is where a per-jurisdiction list used to put it.
    expect(facetUnfilteredLayers("county")).toEqual([
      "laterals",
      "survey-traces",
      "mt-paths",
      "wells",
      "wells-struck",
      "mt-wells",
      "mt-wells-struck",
      "disposal-wells",
    ]);
  });
});

describe("the predicate a press writes", () => {
  const draws = (filter: unknown, properties: Record<string, unknown>, atZoom = 12): boolean =>
    featureFilter(filter as never).filter({ zoom: atZoom } as never, {
      type: 1,
      properties,
    } as never, undefined as never);

  it("keeps only the pressed value on a layer that carries the column", async () => {
    const { facetPredicate } = await import("./style.ts");
    const filter = facetPredicate("wells", { dimension: "operator", value: "CONTINENTAL" });

    expect(filter).not.toBeNull();
    expect(draws(filter, { operator_name: "CONTINENTAL" })).toBe(true);
    expect(draws(filter, { operator_name: "HESS" })).toBe(false);
    // Absent, not merely different: a feature with no operator on the wire is not this one.
    expect(draws(filter, {})).toBe(false);
  });

  it("is null on a layer the column is not on, rather than a predicate that drops everything", async () => {
    const { facetPredicate } = await import("./style.ts");
    // A missing property reads as null in a style expression, so `in` would answer false for
    // every lateral and erase the layer instead of leaving it unfiltered.
    expect(facetPredicate("laterals", { dimension: "well_type", value: "SWD" })).toBeNull();
  });

  it("is null with no press at all", async () => {
    const { facetPredicate } = await import("./style.ts");
    expect(facetPredicate("wells", null)).toBeNull();
  });
});
