import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { buildCatalogue } from "../catalogue.ts";
import type { CatalogueDataset } from "../catalogue.ts";
import {
  emptyProductionEnvelope,
  healthEnvelope,
  pooledProductionEnvelope,
  productionEnvelope,
  quarantineEnvelope,
  serviceIndexEnvelope,
  wellsEnvelope,
} from "../fixtures.ts";
import { extractRows, namespaceFor, responsePointerFor } from "./rows.ts";

const SNAPSHOT = JSON.parse(readFileSync("../tests/contract/openapi_snapshot.json", "utf8"));
const CATALOGUE = buildCatalogue(SNAPSHOT);

function dataset(id: string): CatalogueDataset {
  const found = CATALOGUE.datasets.find((candidate) => candidate.id === id);
  if (!found) throw new Error(`the committed document declares no dataset ${id}`);
  return found;
}

function defaults(id: string): string[] {
  return dataset(id).columns.default ?? [];
}

describe("collection_pointer and row_projection turn an envelope into rows (G-1)", () => {
  it("reads a flat collection where data is the array itself", () => {
    const rows = extractRows(dataset("quarantine"), quarantineEnvelope.data, defaults("quarantine"));

    expect(rows).toHaveLength(quarantineEnvelope.data.length);
    expect(rows[0]?.id).toBe(quarantineEnvelope.data[0]?.quarantine_id);
    expect(rows[0]?.cells["/reason_code"]?.value).toBe(quarantineEnvelope.data[0]?.reason_code);
    // The data pointer indexes the row; the label pointer does not, because that is what the
    // router emits for a top-level collection (measured: meta.labels carries /reason_code).
    expect(rows[0]?.cells["/reason_code"]?.dataPointer).toBe("/0/reason_code");
    expect(rows[1]?.cells["/reason_code"]?.dataPointer).toBe("/1/reason_code");
  });

  it("reads a projection where the browsable array sits beside data rather than being it", () => {
    const rows = extractRows(dataset("sources"), healthEnvelope.data, defaults("sources"));
    const problems = extractRows(
      dataset("problems"),
      serviceIndexEnvelope.data,
      defaults("problems"),
    );

    expect(rows).toHaveLength(healthEnvelope.data.sources.length);
    expect(rows[0]?.cells["/source_id"]?.dataPointer).toBe("/sources/0/source_id");
    expect(problems).toHaveLength(serviceIndexEnvelope.data.error_codes.length);
    expect(problems[0]?.cells["/code"]?.value).toBe(serviceIndexEnvelope.data.error_codes[0]?.code);
  });

  it("pivots a series into one row per axis entry, with the axis as the row key", () => {
    const rows = extractRows(dataset("production"), productionEnvelope.data, defaults("production"));

    expect(rows).toHaveLength(productionEnvelope.data.series.pm.length);
    expect(rows.map((row) => row.id)).toEqual(productionEnvelope.data.series.pm);
    expect(rows[3]?.cells["/oil_bbl"]?.value).toBe(productionEnvelope.data.series.oil_bbl[3]);
    expect(rows[3]?.cells["/oil_bbl"]?.dataPointer).toBe("/series/oil_bbl/3");
  });

  it("attaches each suffix companion to its own value column, never as a column of its own", () => {
    const rows = extractRows(dataset("production"), productionEnvelope.data, defaults("production"));
    const oil = rows[3]?.cells["/oil_bbl"];

    expect(oil?.companions["_null_semantics"]).toBe(
      productionEnvelope.data.series.oil_bbl_null_semantics[3],
    );
    expect(oil?.companions["_report_vintage"]).toBe(
      productionEnvelope.data.series.oil_bbl_report_vintage[3],
    );
    // P6: `pm_report_vintage` does not exist, and asking for it is how a grid grows three
    // permanently empty columns. The axis is a key, not a value.
    expect(rows[3]?.cells["/pm"]?.companions).toEqual({});
    expect(defaults("production")).not.toContain("/oil_bbl_null_semantics");
  });

  it("holds the axis exempt even when a response does carry a companion for it", () => {
    // Against today's data the exemption is invisible: `pm_report_vintage` does not exist, so
    // asking for it and not asking for it look the same. This is the arm that can tell them
    // apart, and without it the rule is a comment rather than a behaviour.
    const invented = JSON.parse(JSON.stringify(productionEnvelope));
    invented.data.series.pm_report_vintage = invented.data.series.oil_bbl_report_vintage;

    const rows = extractRows(dataset("production"), invented.data, defaults("production"));

    expect(rows[0]?.cells["/pm"]?.companions).toEqual({});
    expect(rows[0]?.cells["/oil_bbl"]?.companions["_report_vintage"]).toBeDefined();
  });

  it("reads the suffix list per dataset — a pooled row is a filing, not a sum over pools", () => {
    const pooled = extractRows(
      dataset("production_pools"),
      pooledProductionEnvelope.data,
      defaults("production_pools"),
    );

    expect(dataset("production_pools").row_projection?.suffixes).not.toContain("_aggregation");
    expect(Object.keys(pooled[0]?.cells["/oil_bbl"]?.companions ?? {})).toEqual([
      "_report_vintage",
      "_null_semantics",
    ]);
  });

  it("takes the suffixes the dataset declares, not the ones the schema would permit", () => {
    // `ProductionSeries` is shared, so the pooled schema *permits* `*_aggregation` and the
    // router never emits it. Hardcoding three suffixes looks identical against today's bytes
    // and diverges the moment a response carries the fourth, which is what this injects.
    const generous = JSON.parse(JSON.stringify(pooledProductionEnvelope));
    for (const pool of generous.data.pools) {
      pool.series.oil_bbl_aggregation = pool.series.oil_bbl.map(() => "sum_over_pools");
    }
    const aggregated = JSON.parse(JSON.stringify(productionEnvelope));
    aggregated.data.series.oil_bbl_aggregation = aggregated.data.series.oil_bbl.map(
      () => "sum_over_pools",
    );

    const pooled = extractRows(
      dataset("production_pools"),
      generous.data,
      defaults("production_pools"),
    );
    const perWell = extractRows(dataset("production"), aggregated.data, defaults("production"));

    expect(pooled[0]?.cells["/oil_bbl"]?.companions).not.toHaveProperty("_aggregation");
    expect(perWell[0]?.cells["/oil_bbl"]?.companions["_aggregation"]).toBe("sum_over_pools");
  });

  it("pivots every element of a pooled collection and keys each row across two namespaces", () => {
    const pools = pooledProductionEnvelope.data.pools;
    const rows = extractRows(
      dataset("production_pools"),
      pooledProductionEnvelope.data,
      defaults("production_pools"),
    );

    const lastPool = pools[pools.length - 1];
    const lastMonth = lastPool?.series.pm[(lastPool.series.pm.length ?? 0) - 1];
    const last = rows[rows.length - 1];

    expect(rows).toHaveLength(pools.reduce((total, pool) => total + pool.series.pm.length, 0));
    // P7: the pool comes off the element, the month off the series. A builder that assumes one
    // namespace produces `undefined` for half of the key.
    expect(rows[0]?.id).toBe(`${pools[0]?.well_completion_pool}|${pools[0]?.series.pm[0]}`);
    expect(last?.id).toBe(`${lastPool?.well_completion_pool}|${lastMonth}`);
    expect(rows[0]?.cells["/oil_bbl"]?.dataPointer).toBe("/pools/0/series/oil_bbl/0");
    expect(last?.cells["/oil_bbl"]?.dataPointer).toBe(
      `/pools/${pools.length - 1}/series/oil_bbl/${(lastPool?.series.pm.length ?? 0) - 1}`,
    );
  });

  it("repeats an anchor onto every row, so a projected row can state its own granularity", () => {
    const rows = extractRows(dataset("production"), productionEnvelope.data, defaults("production"));

    expect(rows.every((row) => row.cells["/granularity"]?.value === "well_observed")).toBe(true);
    expect(rows[0]?.cells["/granularity"]?.namespace).toBe("root");
    expect(rows[0]?.cells["/granularity"]?.dataPointer).toBe("/granularity");
  });

  it("answers a well with no production with no rows and no throw", () => {
    const empty = extractRows(
      dataset("production"),
      emptyProductionEnvelope.data,
      defaults("production"),
    );
    // The recorded case is an axis that exists and is empty; the harsher one is an axis the
    // response omits entirely, which is what a 200 with a partial body looks like.
    const absent = extractRows(dataset("production"), { api10: "3305300003" }, defaults("production"));
    const wrongShape = extractRows(dataset("quarantine"), { not: "an array" }, ["/quarantine_id"]);

    expect(empty).toEqual([]);
    expect(absent).toEqual([]);
    expect(wrongShape).toEqual([]);
  });

  it("composes the label pointer from the declaration alone, so the floor test cannot diverge", () => {
    // B5a happened because the client composed one pointer and meta.labels carried another.
    expect(responsePointerFor(dataset("production"), "/oil_bbl")).toBe("/series/oil_bbl");
    expect(productionEnvelope.meta.labels).toHaveProperty("/series/oil_bbl");
    expect(responsePointerFor(dataset("production"), "/granularity")).toBe("/granularity");
    expect(responsePointerFor(dataset("quarantine"), "/reason_code")).toBe("/reason_code");
    expect(responsePointerFor(dataset("sources"), "/source_id")).toBe("/sources/0/source_id");
    // The pooled form carries an index, and its label pointer includes that row position.
    expect(responsePointerFor(dataset("production_pools"), "/oil_bbl")).toBe(
      "/pools/0/series/oil_bbl",
    );
    expect(pooledProductionEnvelope.meta.labels).toHaveProperty(
      "/pools/0/series/oil_bbl",
      "gt_liquids_policy",
    );
  });

  it("agrees with the data about which namespace every declared column lives in", () => {
    const bodies: Record<string, unknown> = {
      wells: wellsEnvelope.data,
      quarantine: quarantineEnvelope.data,
      production: productionEnvelope.data,
      production_pools: pooledProductionEnvelope.data,
      sources: healthEnvelope.data,
      problems: serviceIndexEnvelope.data,
    };
    let checked = 0;

    for (const [id, body] of Object.entries(bodies)) {
      const rows = extractRows(dataset(id), body, defaults(id));
      expect(rows.length, id).toBeGreaterThan(0);
      for (const column of defaults(id)) {
        // The declarative rule is what the label lookup and the C5 floor test use; the probe is
        // what the grid renders. They are two code paths and this is the assertion that they
        // are one answer.
        expect(rows[0]?.cells[column]?.namespace, `${id} ${column}`).toBe(
          namespaceFor(dataset(id), column),
        );
        checked += 1;
      }
    }
    expect(checked).toBeGreaterThan(30);
  });
});
