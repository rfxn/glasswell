// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from "vitest";

import { toChartSeries } from "../chart/series.ts";
import type { ProductionData } from "../chart/series.ts";
import { seriesTable } from "./table.ts";

const production: ProductionData = {
  api10: "3305310451",
  source_id: "nd_dmr_mpr",
  granularity: "well_observed",
  streams: ["oil", "gas"],
  series: {
    pm: ["2025-10", "2025-11", "2025-12"],
    oil_bbl: ["1000.000", "0.000", null],
    oil_bbl_report_vintage: ["2026-08-01", "2026-08-01", "2026-08-01"],
    oil_bbl_null_semantics: ["reported", "reported_zero", "no_report"],
    gas_mcf: ["2000.000", "2100.000", "2200.000"],
    gas_mcf_report_vintage: ["2026-08-01", "2026-08-01", "2026-08-01"],
    gas_mcf_null_semantics: ["reported", "reported", "reported"],
  },
  _lineage: {
    "series.oil_bbl.0": "drv_oil0#api10=3305310451&col=oil_bbl&pm=2025-10",
    "series.oil_bbl.1": "drv_oil1#api10=3305310451&col=oil_bbl&pm=2025-11",
    "series.gas_mcf": "drv_gas#api10=3305310451&col=gas_mcf",
  },
  _units: { "series.oil_bbl": "bbl", "series.gas_mcf": "mcf" },
  _basis: { "series.oil_bbl": "oil+condensate" },
};

const chart = toChartSeries(production);
const callbacks = { onExplain: vi.fn(), labelTermFor: () => null };
let host: HTMLElement;

beforeEach(() => {
  callbacks.onExplain.mockClear();
  host = document.createElement("div");
  document.body.replaceChildren(host);
  host.appendChild(seriesTable(chart, callbacks));
});

describe("the chart as a table", () => {
  it("captions itself with what it is and how much of it there is", () => {
    const caption = host.querySelector("caption")?.textContent ?? "";

    expect(caption).toContain("3 months shown");
    expect(caption).toContain("one row per month");
  });

  it("draws one row per month, keyed by the month", () => {
    const rows = [...host.querySelectorAll("tbody tr")];

    expect(rows.length).toBe(3);
    expect(rows.map((row) => row.querySelector("th")?.textContent)).toEqual([
      "Oct 2025",
      "Nov 2025",
      "Dec 2025",
    ]);
  });

  it("carries the unit on every cell, not only in the header", () => {
    const values = [...host.querySelectorAll("tbody tr:first-child .gw-table-value")];

    expect(values.map((cell) => cell.textContent)).toEqual(["1000.000 bbl", "2000.000 mcf"]);
  });

  it("says which absence an empty cell is, in the words the band uses", () => {
    const last = host.querySelectorAll("tbody tr")[2];
    const [value, state] = [
      last?.querySelector(".gw-table-value"),
      last?.querySelector(".gw-table-state"),
    ];

    expect(value?.textContent).toBe("");
    expect(state?.textContent).toBe("no report");
    const zero = host.querySelectorAll("tbody tr")[1]?.querySelector(".gw-table-state");
    expect(zero?.textContent).toBe("reported zero");
  });

  it("gives every point its own handle, which is the whole reason the table ships", () => {
    const first = host.querySelectorAll("tbody tr")[0];
    const rings = [...(first?.querySelectorAll(".gw-table-handle .gw-handle") ?? [])];

    expect(rings.length).toBe(2);
    expect(rings[0]?.getAttribute("aria-label")).toBe("Lineage for Oil for Oct 2025");
    (rings[0] as HTMLButtonElement).click();
    expect(callbacks.onExplain).toHaveBeenCalledWith(
      "drv_oil0#api10=3305310451&col=oil_bbl&pm=2025-10",
    );
  });

  it("groups the columns by stream, three cells each", () => {
    const groups = [...host.querySelectorAll("thead tr:first-child th[scope='colgroup']")];

    expect(groups.map((each) => each.textContent)).toEqual(["Oil (bbl)", "Gas (mcf)"]);
    expect(groups.every((each) => each.getAttribute("colspan") === "3")).toBe(true);
  });
});
