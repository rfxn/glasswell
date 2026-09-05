// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";

import { toChartSeries } from "../chart/series.ts";
import type { ProductionData } from "../chart/series.ts";
import { exportControls, toCsv, toJson } from "./export.ts";

const production: ProductionData = {
  api10: "3305310451",
  source_id: "nd_dmr_mpr",
  granularity: "well_observed",
  streams: ["oil"],
  series: {
    pm: ["2025-10", "2025-11"],
    oil_bbl: ["1000.000", null],
    oil_bbl_report_vintage: ["2026-08-01", "2026-08-01"],
    oil_bbl_null_semantics: ["reported", "no_report"],
  },
  _lineage: { "series.oil_bbl.0": "drv_a#api10=3305310451&col=oil_bbl&pm=2025-10" },
  _units: { "series.oil_bbl": "bbl" },
  _basis: { "series.oil_bbl": "oil+condensate" },
};

const chart = toChartSeries(production);
const context = {
  api10: "3305310451",
  url: "https://glasswell.example/?well=3305310451&from=2025-10&to=2025-11",
  asOfResolved: "2026-08-01",
  normalization: null,
  grain: "well_observed",
};

describe("the CSV an analyst takes away", () => {
  const csv = toCsv(chart, context);

  it("carries the handle of every point it reports", () => {
    expect(csv).toContain("month,stream,value,unit,null_semantics,report_vintage,handle");
    expect(csv).toContain("drv_a#api10=3305310451&col=oil_bbl&pm=2025-10");
  });

  it("leaves the handle column empty on a month with no output of its own", () => {
    // The row carried October's handle under November's absence, because the column handle of
    // a per-point column is its first point's. A file is where that survives longest.
    const rows = csv.split("\n").filter((line) => line.startsWith("2025-11"));

    expect(rows[0]).not.toContain("drv_a");
    expect(rows[0]?.endsWith(",")).toBe(true);
  });

  it("says which absence an empty value is, rather than writing a zero", () => {
    const rows = csv.split("\n").filter((line) => line.startsWith("2025-11"));

    expect(rows[0]).toContain("no_report");
    expect(rows[0]).not.toMatch(/,0(\.0+)?,/);
  });

  it("heads the file with what reproduces it", () => {
    expect(csv).toContain("# api10=3305310451");
    expect(csv).toContain("# as_of_resolved=2026-08-01");
    expect(csv).toContain(`# reproduce=${context.url}`);
  });

  it("heads the file with the basis of every stream that has one", () => {
    // The policy rides wherever the number does: a file of oil figures that does not say oil
    // means oil plus condensate has dropped the sentence the chart frame shows beside them.
    expect(csv).toContain("# basis oil=oil+condensate");
  });

  it("has no running-total column, and says why", () => {
    // M-7's other half: a client sum in a file beside a handle column would read as a figure
    // with provenance.
    expect(csv).not.toContain("running_total");
    expect(csv).toContain("deliberately not a column");
  });
});

describe("the JSON an agent takes away", () => {
  it("is the served envelope, unmodified", () => {
    const envelope = { data: { api10: "3305310451" }, meta: { warnings: [] }, links: {} };

    expect(JSON.parse(toJson(envelope as never))).toEqual(envelope);
  });
});

describe("the controls", () => {
  it("offers both formats and says what they carry", () => {
    const group = exportControls({
      series: () => chart,
      envelope: () => ({ data: {}, meta: {}, links: {} }) as never,
      context: () => context,
    });

    expect(group.querySelector(".gw-export-csv")?.textContent).toBe("CSV");
    expect(group.querySelector(".gw-export-json")?.textContent).toBe("JSON");
    expect(group.textContent).toContain("derivation handle of every point");
    expect(group.textContent).toContain("running total on the page is not a column");
  });

  it("writes a file named for the well when the reader asks", () => {
    const click = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(click);
    vi.stubGlobal("URL", { createObjectURL: () => "blob:x", revokeObjectURL: () => {} });

    const group = exportControls({
      series: () => chart,
      envelope: () => null,
      context: () => context,
    });
    group.querySelector<HTMLButtonElement>(".gw-export-csv")?.click();

    expect(click).toHaveBeenCalledOnce();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });
});
