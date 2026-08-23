import { describe, expect, it } from "vitest";

import { nearestIndex, readoutAt } from "./cursor.ts";
import { toChartSeries } from "./series.ts";
import type { ProductionData } from "./series.ts";

const production: ProductionData = {
  api10: "3305305514",
  source_id: "nd_dmr_mpr",
  granularity: "well_observed",
  streams: ["oil", "gas", "water"],
  series: {
    pm: ["2026-01", "2026-02", "2026-03", "2026-04"],
    oil_bbl: ["1000.400", "0.000", "900.000", "800.000"],
    oil_bbl_report_vintage: ["2026-08-01", "2026-08-01", "2026-08-01", "2026-08-01"],
    oil_bbl_null_semantics: ["reported", "reported_zero", "withheld", "no_report"],
    gas_mcf: ["2500.000", "2400.000", "2300.000", "2200.000"],
    gas_mcf_report_vintage: ["2026-08-01", "2026-08-01", "2026-08-01", "2026-08-01"],
    gas_mcf_null_semantics: ["reported", "reported", "reported", "reported"],
    water_bbl: ["800.000", "810.000", "820.000", "830.000"],
    water_bbl_report_vintage: ["2026-08-01", "2026-08-01", "2026-08-01", "2026-08-01"],
    water_bbl_null_semantics: ["reported", "reported", "reported", "reported"],
  },
  _lineage: {
    "series.oil_bbl": "drv_oil#api10=3305305514&col=oil_bbl",
    "series.gas_mcf": "drv_gas#api10=3305305514&col=gas_mcf",
    "series.water_bbl": "drv_wat#api10=3305305514&col=water_bbl",
  },
  _units: { "series.oil_bbl": "bbl", "series.gas_mcf": "mcf", "series.water_bbl": "bbl" },
  _basis: { "series.oil_bbl": "oil+condensate" },
};

const chart = toChartSeries(production);

describe("resolving a pointer to the month nearest it", () => {
  it("takes the whole band either side of a point, not the point itself", () => {
    expect(nearestIndex(0, chart.x)).toBe(0);
    expect(nearestIndex(0.1, chart.x)).toBe(0);
    expect(nearestIndex(0.9, chart.x)).toBe(3);
    expect(nearestIndex(1, chart.x)).toBe(3);
  });

  it("clamps a pointer that left the plot area rather than reporting no month", () => {
    expect(nearestIndex(-4, chart.x)).toBe(0);
    expect(nearestIndex(9, chart.x)).toBe(3);
  });

  it("resolves against the real month positions, so a gap does not shift the answer", () => {
    const gappy = toChartSeries({
      ...production,
      series: { ...production.series, pm: ["2015-01", "2026-01", "2026-02", "2026-03"] },
    });
    // One early month then a recent cluster: halfway across the plot is nearer 2026-01 than
    // 2015-01, and index 1 is the answer an evenly-spaced assumption would never give.
    expect(nearestIndex(0.5, gappy.x)).toBe(1);
    expect(Math.round(0.5 * (gappy.x.length - 1))).toBe(2);
  });

  it("has no month to resolve to on an empty axis", () => {
    expect(nearestIndex(0.5, [])).toBe(-1);
  });

  it("resolves to the only month there is", () => {
    expect(nearestIndex(0.5, [chart.x[0] as number])).toBe(0);
  });
});

describe("the readout for one month", () => {
  const readout = readoutAt(chart, 0);

  it("names the month once, for every stream on the axis", () => {
    expect(readout?.month).toBe("2026-01");
    expect(readout?.monthLabel).toBe("Jan 2026");
    expect(readout?.rows.map((row) => row.label)).toEqual(["Oil", "Gas", "Water"]);
  });

  it("carries a derivation handle on every figure it states (R6)", () => {
    for (const row of readout?.rows ?? []) {
      if (row.value !== null) expect(row.handle).toBeTruthy();
    }
    expect(readout?.rows[0]?.handle).toBe("drv_oil#api10=3305305514&col=oil_bbl&pm=2026-01");
  });

  it("rounds a volume the way the rest of the card does", () => {
    expect(readout?.rows[0]?.value).toBe("1,000");
    expect(readout?.rows[0]?.unit).toBe("bbl");
  });

  it("keeps a reported zero as a stated zero, never as an absence", () => {
    const zero = readoutAt(chart, 1)?.rows[0];
    expect(zero?.value).toBe("0");
    expect(zero?.mark.label).toBe("reported zero");
  });

  it("states no volume for a month nobody measured, and says which kind it was", () => {
    const withheld = readoutAt(chart, 2)?.rows[0];
    expect(withheld?.value).toBeNull();
    expect(withheld?.mark.label).toBe("withheld");
    const absent = readoutAt(chart, 3)?.rows[0];
    expect(absent?.value).toBeNull();
    expect(absent?.mark.label).toBe("no report");
  });

  it("carries the report vintage each point was read at", () => {
    expect(readout?.rows[0]?.vintage).toBe("2026-08-01");
  });

  it("reports a missing handle as missing rather than inventing one", () => {
    const unhandled = toChartSeries({ ...production, _lineage: {} });
    expect(readoutAt(unhandled, 0)?.rows[0]?.handle).toBeNull();
  });

  it("has nothing to read out beyond the axis", () => {
    expect(readoutAt(chart, -1)).toBeNull();
    expect(readoutAt(chart, 4)).toBeNull();
  });
});
