import { describe, expect, it } from "vitest";

import { axisLabels } from "./axes.ts";
import type { ChartSeries, SeriesColumn } from "./series.ts";

function column(label: string, unit: string): SeriesColumn {
  return {
    key: `${label.toLowerCase()}_${unit}`,
    stream: label.toLowerCase(),
    label,
    unit,
    basis: null,
    handle: null,
    values: [],
    raw: [],
    vintages: [],
    nullSemantics: [],
    vintage: null,
    mixedVintages: false,
  };
}

function chart(columns: SeriesColumn[]): ChartSeries {
  return {
    api10: "3305310451",
    granularity: "well_observed",
    months: [],
    x: [],
    data: [],
    columns,
    scales: [...new Set(columns.map((entry) => entry.unit))],
  };
}

describe("axisLabels", () => {
  it("names the unit and the series on each side of a dual-axis chart", () => {
    // Without this a reader cannot tell which axis belongs to which series (UX P1-4).
    const labels = axisLabels(chart([column("Oil", "bbl"), column("Gas", "mcf"), column("Water", "bbl")]));

    expect(labels).toEqual([
      { unit: "bbl", side: "left", streams: ["Oil", "Water"] },
      { unit: "mcf", side: "right", streams: ["Gas"] },
    ]);
  });

  it("labels a single-scale chart on the left only", () => {
    const labels = axisLabels(chart([column("Oil", "bbl")]));

    expect(labels).toEqual([{ unit: "bbl", side: "left", streams: ["Oil"] }]);
  });

  it("says nothing about a chart with no columns", () => {
    expect(axisLabels(chart([]))).toEqual([]);
  });
});
