import { describe, expect, it } from "vitest";

import { toChartSeries } from "./series.ts";
import type { ProductionData } from "./series.ts";
import {
  DEFAULT_SPAN,
  FULL_AT_OR_UNDER,
  chartWindow,
  defaultSpan,
  describeWindow,
  spanChoices,
} from "./window.ts";

function months(first: string, count: number): string[] {
  const [year, month] = first.split("-").map(Number);
  const start = (year as number) * 12 + ((month as number) - 1);
  return Array.from({ length: count }, (_, step) => {
    const index = start + step;
    return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, "0")}`;
  });
}

function series(pm: string[]): ProductionData {
  const values = pm.map((_, index) => String(1000 + index));
  return {
    api10: "3305305514",
    source_id: "nd_dmr_mpr",
    granularity: "well_observed",
    streams: ["oil", "gas"],
    series: {
      pm,
      oil_bbl: values,
      oil_bbl_report_vintage: pm.map((_, index) => (index === 0 ? "2026-07-01" : "2026-08-01")),
      oil_bbl_null_semantics: pm.map(() => "reported"),
      gas_mcf: values,
      gas_mcf_report_vintage: pm.map(() => "2026-08-01"),
      gas_mcf_null_semantics: pm.map(() => "reported"),
    },
    _lineage: Object.fromEntries(pm.map((_, index) => [`series.oil_bbl.${index}`, `drv_${index}`])),
    _units: { "series.oil_bbl": "bbl", "series.gas_mcf": "mcf" },
    _basis: { "series.oil_bbl": "oil+condensate" },
  };
}

// The owner's well as the ND back-load left it: 131 months, 2015-05 through 2026-03.
const dense = toChartSeries(series(months("2015-05", 131)));
const sparse = toChartSeries(series(months("2025-10", 6)));

describe("the default span", () => {
  it("windows a back-loaded series to the last five years", () => {
    expect(defaultSpan(dense.months)).toBe(DEFAULT_SPAN);
    expect(DEFAULT_SPAN).toBe(60);
  });

  it("never windows a series a reader can already take in whole", () => {
    expect(defaultSpan(sparse.months)).toBeNull();
    expect(defaultSpan(months("2020-01", FULL_AT_OR_UNDER))).toBeNull();
  });

  it("windows nothing when there are no months at all", () => {
    expect(defaultSpan([])).toBeNull();
  });
});

describe("the spans a reader is offered", () => {
  it("offers only spans shorter than the record, and always the whole record", () => {
    expect(spanChoices(dense.months).map((choice) => choice.span)).toEqual([12, 24, 60, null]);
  });

  it("offers nothing to choose between when the record is shorter than every span", () => {
    expect(spanChoices(sparse.months).map((choice) => choice.span)).toEqual([null]);
  });
});

describe("windowing a series", () => {
  const windowed = chartWindow(dense, DEFAULT_SPAN);

  it("keeps the last five calendar years and nothing older", () => {
    expect(windowed.chart.months).toHaveLength(60);
    expect(windowed.chart.months[0]).toBe("2021-04");
    expect(windowed.chart.months[windowed.chart.months.length - 1]).toBe("2026-03");
  });

  it("slices every parallel array in step, so a point keeps its own state and handle", () => {
    const [oil] = windowed.chart.columns;
    expect(oil?.values).toHaveLength(60);
    expect(oil?.raw).toHaveLength(60);
    expect(oil?.vintages).toHaveLength(60);
    expect(oil?.nullSemantics).toHaveLength(60);
    expect(oil?.handles).toHaveLength(60);
    // 2021-04 is index 71 of the full series; its handle must travel with it.
    expect(oil?.handles[0]).toBe("drv_71");
    expect(oil?.raw[0]).toBe(String(1000 + 71));
  });

  it("keeps uPlot's aligned data in step with the sliced columns", () => {
    expect(windowed.chart.data[0]).toHaveLength(60);
    expect(windowed.chart.data).toHaveLength(dense.data.length);
    expect(windowed.chart.data[1]).toEqual(windowed.chart.columns[0]?.values);
  });

  it("re-reads the vintage chip over what is drawn, not over what was hidden", () => {
    // The full series mixes a 2026-07 first point with 2026-08 everywhere else; the window
    // drops that point, so a "mixed report vintages" chip over the drawn points would be false.
    expect(dense.columns[0]?.mixedVintages).toBe(true);
    expect(windowed.chart.columns[0]?.mixedVintages).toBe(false);
    expect(windowed.chart.columns[0]?.vintage).toBe("2026-08-01");
  });

  it("hands back the whole series when no span is asked for", () => {
    const whole = chartWindow(dense, null);
    expect(whole.chart.months).toHaveLength(131);
    expect(whole.window.truncated).toBe(false);
  });

  it("counts what it shows against what is on record", () => {
    expect(windowed.window).toMatchObject({
      shown: 60,
      total: 131,
      from: "2021-04",
      to: "2026-03",
      firstOnRecord: "2015-05",
      lastOnRecord: "2026-03",
      truncated: true,
    });
  });

  it("anchors on the last month of the record, never on today", () => {
    // A well that stopped in 2019 must show its own last five years, not an empty window.
    const stopped = toChartSeries(series(months("2011-01", 108)));
    const view = chartWindow(stopped, DEFAULT_SPAN);
    expect(view.chart.months).toHaveLength(60);
    expect(view.chart.months[view.chart.months.length - 1]).toBe("2019-12");
  });

  it("windows by calendar span, so a gappy record reports fewer months than the span", () => {
    const gappy = toChartSeries(series(["2015-05", "2015-06", "2024-01", "2026-03"]));
    const view = chartWindow(gappy, 12);
    expect(view.chart.months).toEqual(["2026-03"]);
    expect(view.window).toMatchObject({ shown: 1, total: 4, truncated: true });
  });
});

describe("the sentence the window is disclosed as", () => {
  it("says how much of the record is on screen and where the rest is", () => {
    const sentence = describeWindow(chartWindow(dense, DEFAULT_SPAN).window);
    expect(sentence).toContain("60 of 131 months");
    expect(sentence).toContain("Apr 2021");
    expect(sentence).toContain("Mar 2026");
    expect(sentence).toContain("May 2015");
  });

  it("says so plainly when nothing is held back", () => {
    const sentence = describeWindow(chartWindow(sparse, null).window);
    expect(sentence).toContain("all 6 months on record");
    expect(sentence).not.toContain(" of 6 months");
  });

  it("never calls a narrowed response the whole record", () => {
    // The explorer's from/to facets narrow server-side, so the chart is handed part of the
    // record and has no way to count the rest. It says which it is drawing.
    const sentence = describeWindow(chartWindow(sparse, null).window, true);
    expect(sentence).toContain("all 6 months returned by this request");
    expect(sentence).not.toContain("on record");
  });
});
