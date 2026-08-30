// @vitest-environment happy-dom
import { readFileSync } from "node:fs";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_STATE } from "../../app/state.ts";
import { buildCatalogue } from "../catalogue.ts";
import type { CatalogueDataset } from "../catalogue.ts";
import { columnsFor } from "../grid/columns.ts";
import { extractRows } from "../grid/rows.ts";
import type { Row } from "../grid/rows.ts";
import { resetTrail } from "./chips.ts";
import { mountDetail, setPointerLabels } from "./detail.ts";
import { containsFigure, figureTree } from "./figures.ts";

/**
 * Two rendered defects the visual gate found on `/v1/type-curves`, pinned as tests.
 *
 * The row is `(api10, origin)`, so `row_id` is composite — and the detail pane refused to
 * fetch anything at all, telling the reader "this row supplies no value for it" beside the
 * api10 it supplies. And every label declared as a projected column rendered as a figure with
 * no handle, which is the naked-number badge on the one surface whose subject is provenance.
 */

const SNAPSHOT = JSON.parse(readFileSync("../tests/contract/openapi_snapshot.json", "utf8"));
const CATALOGUE = buildCatalogue(SNAPSHOT);

const ENVELOPE = {
  data: {
    publication_id: "p3pub_" + "0".repeat(32),
    stream: "oil",
    normalization: "typecurve_absolute",
    horizon_months: 24,
    origin_requested: null,
    relation: "control_type_curve_not_a_forecast",
    quantile_convention: "statistical_ascending",
    series: {
      api10: ["3305310451", "3305300003"],
      origin: ["2021-01-01", "2021-01-01"],
      split_id: ["spl_20210101_24", "spl_20210101_24"],
      fallback_level: ["formation_area_length", "control_unavailable"],
      control_unavailable_reasons: [[], ["missing_lateral_length"]],
      formation_group: ["bakken", "bakken"],
      area: ["025", "025"],
      lateral_length_bucket: ["8000_to_lt_10000", null],
      peer_count: [34, 0],
      cumulative_peer_count: [34, 0],
    },
    _lineage: {
      "series.peer_count": "drv_page#col=peer_count",
      "series.cumulative_peer_count": "drv_page#col=cumulative_peer_count",
    },
    _units: { "series.peer_count": "wells", "series.cumulative_peer_count": "wells" },
  },
  meta: { labels: {} },
};

function typeCurves(): CatalogueDataset {
  const found = CATALOGUE.datasets.find((candidate) => candidate.id === "type_curves");
  if (!found) throw new Error("the document declares no type_curves dataset");
  return found;
}

function gridRow(index: number) {
  const dataset = typeCurves();
  const columns = columnsFor(dataset, SNAPSHOT, ENVELOPE, { includeHidden: true });
  const rows = extractRows(
    dataset,
    ENVELOPE.data,
    columns.map((column) => column.pointer),
  );
  return { dataset, columns, row: rows[index] as Row };
}

let host: HTMLElement;
let requested: string[];

beforeEach(() => {
  requested = [];
  setPointerLabels(false);
  resetTrail();
  document.body.innerHTML = '<div id="host"></div>';
  host = document.getElementById("host") as HTMLElement;
  window.history.replaceState(null, "", "/?view=explore");
  vi.stubGlobal("fetch", (url: string) => {
    requested.push(String(url).split("?")[0] as string);
    return Promise.resolve(
      new Response(JSON.stringify({ data: { api10: "x" }, meta: {}, links: {} }), {
        headers: { "content-type": "application/json" },
      }),
    );
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("a composite row identity is still addressable by its detail operation", () => {
  it("calls the detail operation with the pointer its single path parameter names", async () => {
    const { dataset, columns, row } = gridRow(0);

    await mountDetail(host, {
      dataset,
      document: SNAPSHOT,
      datasets: CATALOGUE.datasets,
      state: { ...DEFAULT_STATE, view: "explore", ds: "type_curves", row: row.id },
      row,
      rowId: row.id,
      columns,
      data: ENVELOPE.data,
      request: { path: "/v1/type-curves", query: {} },
      navigate: vi.fn(),
      close: vi.fn(),
      signal: new AbortController().signal,
    });
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(row.id).toBe("3305310451|2021-01-01");
    expect(requested).toEqual(["/v1/wells/3305310451/type-curve"]);
    expect(host.textContent).not.toContain("supplies no value for it");
  });
});

describe("a projected column is a figure by declaration, so a label may not be one", () => {
  it("types every label column as something other than a figure", () => {
    const dataset = typeCurves();
    const columns = columnsFor(dataset, SNAPSHOT, ENVELOPE, { includeHidden: true });
    const kindOf = (pointer: string) =>
      columns.find((column) => column.pointer === pointer)?.kind;

    expect(dataset.row_projection?.columns).toEqual(["/peer_count", "/cumulative_peer_count"]);
    expect(kindOf("/peer_count")).toBe("figure");
    expect(kindOf("/api10")).toBe("identifier");
    for (const label of ["/origin", "/fallback_level", "/formation_group", "/split_id"]) {
      expect(kindOf(label), label).not.toBe("figure");
    }
  });

  it("still resolves every label per row, because the series probe does not need the projection", () => {
    const { row } = gridRow(1);

    expect(row.cells["/fallback_level"]?.value).toBe("control_unavailable");
    expect(row.cells["/control_unavailable_reasons"]?.value).toEqual(["missing_lateral_length"]);
    expect(row.cells["/origin"]?.value).toBe("2021-01-01");
    expect(row.cells["/peer_count"]?.value).toBe(0);
  });

  it("carries the reasons in the default columns, so the outcome is visible without scrolling", () => {
    expect(typeCurves().columns.default).toContain("/control_unavailable_reasons");
  });
});


describe("a handle nobody can click is not an explain affordance", () => {
  const COVERAGE = {
    acceptance: {
      pooled_rung1_share: {
        observed: { value: "0.875", unit: "share", d: "drv_pub#col=gate_observed" },
        minimum: "0.600000",
        status: "pass",
      },
    },
    support: {
      fallback_by_level: {
        control_unavailable: { value: "1", unit: "subject_instances", d: "drv_pub#l=cu" },
        formation_area_length: { value: "5", unit: "subject_instances", d: "drv_pub#l=fal" },
      },
      test_subject_instances: { value: "8", unit: "subject_instances", d: "drv_pub#col=tsi" },
    },
    control_contract: { min_peers: 20, vintage_window_months: 36 },
  };

  it("finds a figure nested at any depth, and none where there is none", () => {
    expect(containsFigure(COVERAGE)).toBe(true);
    expect(containsFigure(COVERAGE.control_contract)).toBe(false);
    expect(containsFigure({ spec: { min_peers: 20 } })).toBe(false);
    expect(containsFigure([[{ value: "1", unit: "wells", d: "drv#x" }]])).toBe(true);
  });

  it("renders every nested figure as an addressable figure rather than a line of JSON", () => {
    const tree = figureTree(COVERAGE);

    const figures = [...tree.querySelectorAll("gw-figure")];
    expect(figures).toHaveLength(4);
    expect(figures.map((figure) => figure.getAttribute("handle")).sort()).toEqual([
      "drv_pub#col=gate_observed",
      "drv_pub#col=tsi",
      "drv_pub#l=cu",
      "drv_pub#l=fal",
    ]);
    expect(figures.map((figure) => figure.getAttribute("unit"))).toContain("share");
    // The threshold beside the observed share is not a figure and does not pretend to be.
    expect(tree.textContent).toContain("0.600000");
    expect(tree.textContent).toContain("pass");
    expect(tree.querySelector(".gw-json-block")).toBe(null);
  });

  it("leaves the build parameters to the JSON block they belong in", () => {
    expect([...figureTree(COVERAGE.control_contract).querySelectorAll("gw-figure")]).toHaveLength(0);
  });
});
