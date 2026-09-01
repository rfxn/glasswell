// @vitest-environment happy-dom
import { describe, expect, it } from "vitest";

import { chartOptions, monthLabels } from "./options.ts";
import { toChartSeries } from "./series.ts";
import type { ProductionData } from "./series.ts";

const production: ProductionData = {
  api10: "3305301234",
  source_id: "nd_dmr_mpr",
  granularity: "well_observed",
  streams: ["oil", "gas"],
  series: {
    pm: ["2025-10", "2025-11"],
    oil_bbl: ["70965.000", "73959.000"],
    oil_bbl_null_semantics: ["reported", "reported"],
    gas_mcf: ["76126.000", "85063.000"],
    gas_mcf_null_semantics: ["reported", "reported"],
  },
  _lineage: {},
  _units: { "series.oil_bbl": "bbl", "series.gas_mcf": "mcf" },
  _basis: {},
};

const chart = toChartSeries(production);
const options = chartOptions(chart, 640);

describe("the uPlot options", () => {
  it("never spans a gap: an unreported month must not be drawn through", () => {
    // Interpolating across downtime invents production that did not happen.
    for (const series of options.series.slice(1)) {
      expect((series as { spanGaps?: boolean }).spanGaps).toBe(false);
    }
  });

  it("gives every scale its own axis, left then right", () => {
    expect(options.axes?.[1]).toMatchObject({ scale: "bbl", side: 3 });
    expect(options.axes?.[2]).toMatchObject({ scale: "mcf", side: 1 });
  });

  it("renders six-figure tick labels with thousands separators", () => {
    const axis = options.axes?.[1] as { values?: unknown };
    const values = axis.values as (u: unknown, splits: number[]) => string[];

    expect(values(null, [0, 70965, 150000])).toEqual(["0", "70,965", "150,000"]);
  });

  it("renders month ticks as months, not as raw timestamps", () => {
    const axis = options.axes?.[0] as { values?: unknown };
    const values = axis.values as (u: unknown, splits: number[]) => string[];

    expect(values(null, [Date.UTC(2025, 9, 1) / 1000])).toEqual(["Oct 2025"]);
  });

  it("keeps the stream colours and the redundant dash encoding", () => {
    expect(options.series[1]).toMatchObject({ stroke: "#3FA55E", dash: [] });
    expect(options.series[2]).toMatchObject({ stroke: "#D9534F", dash: [6, 3] });
  });

  it("takes its palette from the theme tokens when the document has them", () => {
    // The plot is a canvas. Hard-coding the dark grid put near-black gridlines on the light
    // theme's white card, which is the same class of defect as VF-5 on the map.
    document.documentElement.style.setProperty("--oil", "#2F8A4B");
    document.documentElement.style.setProperty("--hairline", "#d8e1e8");

    const themed = chartOptions(chart, 640);

    expect(themed.series[1]).toMatchObject({ stroke: "#2F8A4B" });
    expect(themed.axes?.[0]?.grid).toMatchObject({ stroke: "#d8e1e8" });
    document.documentElement.removeAttribute("style");
  });

  it("takes the width it is given, so a re-measure can rebuild at a new size", () => {
    expect(chartOptions(chart, 420).width).toBe(420);
  });
});

describe("the month axis never shows one month as two", () => {
  it("drops a repeated label rather than the tick under it", () => {
    // uPlot's own splits for a 7-month series across a wide card: sub-month increments that
    // all format to the same month. Measured at 820 px, where the card is a full-width sheet.
    const september = Date.UTC(2025, 8, 1) / 1000;
    const midSeptember = Date.UTC(2025, 8, 16) / 1000;
    const october = Date.UTC(2025, 9, 1) / 1000;

    expect(monthLabels([september, midSeptember, october])).toEqual(["Sep 2025", "", "Oct 2025"]);
  });

  it("leaves a run of distinct months untouched", () => {
    const months = [Date.UTC(2025, 8, 1), Date.UTC(2025, 9, 1), Date.UTC(2025, 10, 1)].map(
      (ms) => ms / 1000,
    );

    expect(monthLabels(months)).toEqual(["Sep 2025", "Oct 2025", "Nov 2025"]);
  });
});
