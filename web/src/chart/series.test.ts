import { describe, expect, it } from "vitest";

import { handleAt, pointHandle, toChartSeries } from "./series.ts";
import type { ProductionData } from "./series.ts";

const production: ProductionData = {
  api10: "3305301234",
  source_id: "nd_dmr_mpr",
  granularity: "well_observed",
  streams: ["oil", "gas", "water"],
  series: {
    pm: ["2026-01", "2026-02", "2026-03"],
    oil_bbl: ["1000.000", "0.000", null],
    oil_bbl_report_vintage: ["2026-08-01", "2026-08-01", null],
    oil_bbl_null_semantics: ["reported", "reported_zero", "no_report"],
    gas_mcf: ["2500.000", null, "2400.000"],
    gas_mcf_report_vintage: ["2026-08-01", null, "2026-08-01"],
    gas_mcf_null_semantics: ["reported", "withheld", "reported"],
    water_bbl: ["800.000", "810.000", "820.000"],
    water_bbl_report_vintage: ["2026-08-01", "2026-08-01", "2026-08-01"],
    water_bbl_null_semantics: ["reported", "reported", "reported"],
  },
  _lineage: {
    "series.oil_bbl": "drv_oil1#api10=3305301234&col=oil_bbl",
    "series.gas_mcf": "drv_gas1#api10=3305301234&col=gas_mcf",
    "series.water_bbl": "drv_wat1#api10=3305301234&col=water_bbl",
  },
  _units: { "series.oil_bbl": "bbl", "series.gas_mcf": "mcf", "series.water_bbl": "bbl" },
  _basis: { "series.oil_bbl": "oil+condensate", "series.water_bbl": "water" },
};

describe("toChartSeries", () => {
  const chart = toChartSeries(production);

  it("keeps the shared month axis in order", () => {
    expect(chart.months).toEqual(["2026-01", "2026-02", "2026-03"]);
  });

  it("produces uPlot column-major aligned data, x first", () => {
    expect(chart.data).toHaveLength(4);
    expect(chart.data[0]).toEqual(chart.x);
    expect(chart.data[0]).toHaveLength(3);
    expect(chart.data[1]).toEqual([1000, 0, null]);
  });

  it("carries the unit from _units, never inferred from the column name", () => {
    expect(chart.columns.map((column) => [column.key, column.unit])).toEqual([
      ["oil_bbl", "bbl"],
      ["gas_mcf", "mcf"],
      ["water_bbl", "bbl"],
    ]);
  });

  it("carries the liquids basis where the API states one", () => {
    expect(chart.columns[0]?.basis).toBe("oil+condensate");
    expect(chart.columns[1]?.basis).toBeNull();
  });

  it("carries the in-band derivation handle for each column", () => {
    expect(chart.columns[1]?.handle).toBe("drv_gas1#api10=3305301234&col=gas_mcf");
  });

  it("preserves per-point report_vintage", () => {
    expect(chart.columns[0]?.vintages).toEqual(["2026-08-01", "2026-08-01", null]);
  });

  it("preserves per-point null_semantics — the states the card must distinguish", () => {
    expect(chart.columns[0]?.nullSemantics).toEqual(["reported", "reported_zero", "no_report"]);
    expect(chart.columns[1]?.nullSemantics).toEqual(["reported", "withheld", "reported"]);
  });

  it("keeps reported_zero as a plotted zero and no_report as a gap", () => {
    expect(chart.columns[0]?.values).toEqual([1000, 0, null]);
  });

  it("refuses to plot a withheld month, even when the wire carries a number for it", () => {
    // A withheld volume is not a measurement. Drawing the stored 0 would put a dip in the
    // curve that the regulator never reported, and the state strip already tells the truth.
    const withheld = toChartSeries({
      ...production,
      series: { ...production.series, gas_mcf: ["2500.000", "0.000", "2400.000"] },
    });

    expect(withheld.columns[1]?.values).toEqual([2500, null, 2400]);
    expect(withheld.columns[1]?.raw[1]).toBe("0.000");
  });

  it("refuses to plot a month with no report, even when the wire carries a number", () => {
    const absent = toChartSeries({
      ...production,
      series: { ...production.series, oil_bbl: ["1000.000", "0.000", "0.000"] },
    });

    expect(absent.columns[0]?.values).toEqual([1000, 0, null]);
  });

  it("keeps the raw decimal strings alongside the plotted floats", () => {
    expect(chart.columns[0]?.raw).toEqual(["1000.000", "0.000", null]);
  });

  it("reports the single report vintage of a series, or null when they differ", () => {
    expect(chart.columns[2]?.vintage).toBe("2026-08-01");
  });

  it("flags a series that mixes report vintages rather than smoothing it", () => {
    const mixed = toChartSeries({
      ...production,
      series: {
        ...production.series,
        water_bbl_report_vintage: ["2026-08-01", "2026-07-01", "2026-08-01"],
      },
    });
    expect(mixed.columns[2]?.vintage).toBeNull();
    expect(mixed.columns[2]?.mixedVintages).toBe(true);
  });

  it("skips a stream the response did not carry", () => {
    const oilOnly = toChartSeries({
      ...production,
      streams: ["oil"],
      series: {
        pm: ["2026-01", "2026-02", "2026-03"],
        oil_bbl: ["1000.000", "0.000", null],
        oil_bbl_report_vintage: ["2026-08-01", "2026-08-01", null],
        oil_bbl_null_semantics: ["reported", "reported_zero", "no_report"],
      },
    });
    expect(oilOnly.columns).toHaveLength(1);
    expect(oilOnly.data).toHaveLength(2);
  });

  it("groups columns by unit so bbl and mcf never share one scale", () => {
    expect(chart.scales).toEqual(["bbl", "mcf"]);
  });
});

describe("per-point lineage (SB-07 §9.3)", () => {
  // ND publishes one workbook a month, so a column whose months span promote derivations
  // carries `series.<col>.<index>` entries and no column entry at all. Reading only the
  // column key left every handle on the chart null.
  const perPoint: ProductionData = {
    ...production,
    _lineage: {
      "series.oil_bbl.0": "drv_jan#api10=3305301234&col=oil_bbl&pm=2026-01",
      "series.oil_bbl.1": "drv_feb#api10=3305301234&col=oil_bbl&pm=2026-02",
      "series.gas_mcf": "drv_gas1#api10=3305301234&col=gas_mcf",
      "series.water_bbl": "drv_wat1#api10=3305301234&col=water_bbl",
    },
  };

  it("resolves a handle per point when the column's months disagree", () => {
    const chart = toChartSeries(perPoint);
    expect(chart.columns[0]?.handles).toEqual([
      "drv_jan#api10=3305301234&col=oil_bbl&pm=2026-01",
      "drv_feb#api10=3305301234&col=oil_bbl&pm=2026-02",
      null,
    ]);
  });

  it("falls back to the first point's handle for the column-level control", () => {
    expect(toChartSeries(perPoint).columns[0]?.handle).toBe(
      "drv_jan#api10=3305301234&col=oil_bbl&pm=2026-01",
    );
  });

  it("repeats the column handle per point when one derivation produced the column", () => {
    const chart = toChartSeries(production);
    expect(chart.columns[1]?.handles).toEqual([
      "drv_gas1#api10=3305301234&col=gas_mcf",
      "drv_gas1#api10=3305301234&col=gas_mcf",
      "drv_gas1#api10=3305301234&col=gas_mcf",
    ]);
  });

  it("carries no handle for a column the response never explained", () => {
    const bare = toChartSeries({ ...production, _lineage: {} });
    expect(bare.columns[0]?.handle).toBeNull();
    expect(bare.columns[0]?.handles).toEqual([null, null, null]);
  });

  it("explains a point through its own month's derivation, not the column's first", () => {
    const column = toChartSeries(perPoint).columns[0];
    expect(column && handleAt(column, 1, "2026-02")).toBe(
      "drv_feb#api10=3305301234&col=oil_bbl&pm=2026-02",
    );
  });

  it("still adds the month to a shared column handle", () => {
    const column = toChartSeries(production).columns[0];
    expect(column && handleAt(column, 1, "2026-02")).toBe(
      "drv_oil1#api10=3305301234&col=oil_bbl&pm=2026-02",
    );
  });

  it("has nothing to explain when the point carries no handle", () => {
    const column = toChartSeries({ ...production, _lineage: {} }).columns[0];
    expect(column && handleAt(column, 1, "2026-02")).toBeNull();
  });

  it("offers no ring on a month the response served no output for", () => {
    // A withheld or unreported month has no `canonical.production_monthly` row, so the
    // composed selector names nothing and `/v1/explain` answers 404 `lineage_unresolved`.
    // The blueprint's rule is the other way round: a figure that cannot be explained is not
    // served as a figure, so the ring is not drawn (visual M5).
    const withheld = toChartSeries(production).columns[1];
    expect(withheld?.nullSemantics[1]).toBe("withheld");
    expect(withheld && handleAt(withheld, 1, "2026-02")).toBeNull();
    const unreported = toChartSeries(production).columns[0];
    expect(unreported && handleAt(unreported, 2, "2026-03")).toBeNull();
  });

  it("never lends one month's handle to another that has none", () => {
    // The column handle of a per-point column is its first point's, so falling back to it on
    // an unexplained month opened a different month's chain under this month's number.
    const column = toChartSeries(perPoint).columns[0];
    expect(column?.handles[2]).toBeNull();
    expect(column && handleAt(column, 2, "2026-03")).toBeNull();
  });
});

describe("pointHandle", () => {
  it("adds the point's production month to the series handle (SB-07 selector grammar)", () => {
    expect(pointHandle("drv_oil1#api10=3305301234&col=oil_bbl", "2026-02")).toBe(
      "drv_oil1#api10=3305301234&col=oil_bbl&pm=2026-02",
    );
  });

  it("does not add pm twice", () => {
    expect(pointHandle("drv_oil1#api10=1&col=oil_bbl&pm=2026-01", "2026-02")).toBe(
      "drv_oil1#api10=1&col=oil_bbl&pm=2026-01",
    );
  });

  it("adds a selector to a bare derivation id", () => {
    expect(pointHandle("drv_oil1", "2026-02")).toBe("drv_oil1#pm=2026-02");
  });
});
