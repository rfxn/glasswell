// @vitest-environment happy-dom
import { readFileSync } from "node:fs";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { toChartSeries } from "../chart/series.ts";
import type { ProductionData } from "../chart/series.ts";
import { seriesTable } from "./table.ts";

const CSS = readFileSync("src/card/table.css", "utf8");

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

  it("leaves the Lineage cell empty where the month has no output to explain", () => {
    // Dec 2025 reads `no report` for oil and the column's own handle is October's, so the
    // cell offered a ring that opened another month's chain (visual M5).
    const last = host.querySelectorAll("tbody tr")[2];
    const cells = [...(last?.querySelectorAll(".gw-table-handle") ?? [])];

    expect(cells[0]?.querySelector(".gw-handle")).toBeNull();
    expect(cells[1]?.querySelector(".gw-handle")).not.toBeNull();
  });

  it("names the month in the handle it offers, because the cell is a point", () => {
    const gas = host.querySelectorAll("tbody tr")[0]?.querySelectorAll(".gw-table-handle")[1];
    (gas?.querySelector(".gw-handle") as HTMLButtonElement).click();

    expect(callbacks.onExplain).toHaveBeenCalledWith(
      "drv_gas#api10=3305310451&col=gas_mcf&pm=2025-10",
    );
  });

  it("groups the columns by stream, three cells each", () => {
    const groups = [...host.querySelectorAll("thead tr:first-child th[scope='colgroup']")];

    expect(groups.map((each) => each.textContent)).toEqual(["Oil (bbl)", "Gas (mcf)"]);
    expect(groups.every((each) => each.getAttribute("colspan") === "3")).toBe(true);
  });
});

describe("what stays put when the streams scroll past", () => {
  it("pins the month header alone, never the second row's first Value header", () => {
    const frame = seriesTable(chart, callbacks);
    const rows = frame.querySelectorAll("thead tr");
    expect(rows).toHaveLength(2);
    const pinned = frame.querySelectorAll("thead th.gw-table-month");
    expect(pinned).toHaveLength(1);
    expect(pinned[0]?.closest("tr")).toBe(rows[0]);
    expect(rows[1]?.querySelector("th.gw-table-month")).toBeNull();
  });

  it("is pinned by the class and not by position, so both header rows cannot match", () => {
    // A rule on `thead th:first-child` matched the first cell of both header rows and pinned
    // the second row's Value header over the month column; a partially scrolled figure then
    // read as a whole one with its leading digits covered.
    expect(CSS).not.toMatch(/thead th:first-child/);
    const sticky = CSS.match(/\.gw-series-table thead th\.gw-table-month[^{]*\{[^}]*\}/)?.[0] ?? "";
    expect(sticky).toContain("position: sticky");
    expect(sticky).toContain("z-index");
  });

  it("marks the covered edge in a border model that travels with the pinned cell", () => {
    // Twice the marker was declared and twice Chromium painted nothing a reader could see: a
    // box-shadow, which it does not paint on the cells of a collapsed-border table at all, and
    // then a border, which it painted as the table's grid at the cell's laid-out position — so
    // the mark scrolled away with the columns while the cell stayed, and `10100.000 mcf` still
    // read `000 mcf` beside `May 2023`. The separated model paints the border in the cell's own
    // box. This assertion is the model; `tests/e2e/table-edge.mjs` reads the pixels, because a
    // regex over the stylesheet has now passed three times over an invisible mark.
    const pinned = CSS.match(/\.gw-series-table tbody th,[^{]*\{[^}]*\}/)?.[0] ?? "";
    const table = CSS.match(/\.gw-series-table table[^{]*\{[^}]*\}/)?.[0] ?? "";
    expect(pinned).toMatch(/border-right/);
    expect(pinned).not.toMatch(/box-shadow/);
    expect(table).toContain("border-collapse: separate");
    expect(table).toContain("border-spacing: 0");
  });

  it("keeps the shape the pixel gate's fixture is built to", () => {
    // `tests/e2e/table-edge.mjs` cannot import this module (plain node ESM, no TS loader), so
    // it rebuilds the table's shape by hand. These are the four things it addresses; a rename
    // here without one there would leave the pixel gate measuring an empty selector.
    const frame = seriesTable(chart, callbacks);

    expect(frame.className).toBe("gw-series-table");
    expect(frame.querySelector("thead th.gw-table-month")).not.toBeNull();
    expect(frame.querySelector("tbody tr:first-child > th")).not.toBeNull();
    expect(frame.querySelector("tbody tr:first-child .gw-table-value")).not.toBeNull();
  });
});

describe("where the table's own stylesheet lives", () => {
  it("ships with the module that draws the table, not with the chart's", () => {
    // On a pool-grain well the chart never loads, so `chart.css` never arrived and both New
    // Mexico pool tables overflowed the card with `overflow-x: visible` and no way to reach
    // the columns past its edge (visual M7). The table is drawn there by `pools.ts`.
    expect(readFileSync("src/card/table.ts", "utf8")).toContain('import "./table.css"');
    expect(readFileSync("src/chart/chart.css", "utf8")).not.toContain(".gw-series-table");
    expect(CSS.match(/\.gw-series-table\s*\{[^}]*\}/)?.[0]).toContain("overflow-x: auto");
  });
});
