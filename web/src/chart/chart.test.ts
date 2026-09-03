// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from "vitest";

// uPlot draws to a 2d context happy-dom does not provide. The frame around the plot is the
// subject here; `options.test.ts` is what holds the plot's own options to account.
vi.mock("uplot", () => ({
  default: class {
    over = document.createElement("div");
    setSize(): void {}
    destroy(): void {}
  },
}));

const { renderChart } = await import("./chart.ts");
const { toChartSeries } = await import("./series.ts");
type ProductionData = import("./series.ts").ProductionData;

function months(first: string, count: number): string[] {
  const [year, month] = first.split("-").map(Number);
  const start = (year as number) * 12 + ((month as number) - 1);
  return Array.from({ length: count }, (_, step) => {
    const index = start + step;
    return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, "0")}`;
  });
}

function production(pm: string[]): ProductionData {
  return {
    api10: "3305305514",
    source_id: "nd_dmr_mpr",
    granularity: "well_observed",
    streams: ["oil", "gas"],
    series: {
      pm,
      oil_bbl: pm.map((_, index) => String(1000 + index)),
      oil_bbl_report_vintage: pm.map(() => "2026-08-01"),
      oil_bbl_null_semantics: pm.map((_, index) => (index === 0 ? "reported_zero" : "reported")),
      gas_mcf: pm.map((_, index) => String(2000 + index)),
      gas_mcf_report_vintage: pm.map(() => "2026-08-01"),
      gas_mcf_null_semantics: pm.map(() => "reported"),
    },
    _lineage: Object.fromEntries(
      pm.flatMap((_, index) => [
        [`series.oil_bbl.${index}`, `drv_oil${index}`],
        [`series.gas_mcf.${index}`, `drv_gas${index}`],
      ]),
    ),
    _units: { "series.oil_bbl": "bbl", "series.gas_mcf": "mcf" },
    _basis: { "series.oil_bbl": "oil+condensate" },
  };
}

const dense = toChartSeries(production(months("2015-05", 131)));
const sparse = toChartSeries(production(months("2025-10", 6)));

const callbacks = { onExplain: vi.fn(), labelTermFor: () => null };
let host: HTMLElement;

beforeEach(() => {
  document.body.innerHTML = "";
  host = document.createElement("div");
  document.body.appendChild(host);
  callbacks.onExplain.mockClear();
});

describe("a back-loaded series on the card", () => {
  beforeEach(() => renderChart(host, dense, callbacks));

  it("draws the last five years rather than all 131 months", () => {
    expect(host.querySelectorAll(".gw-state-row").length).toBe(2);
    expect(host.querySelector(".gw-state-row")?.querySelectorAll(".gw-state-mark").length).toBe(60);
  });

  it("says on the surface how much of the record it is drawing", () => {
    const note = host.querySelector(".gw-window-note")?.textContent ?? "";
    expect(note).toContain("60 of 131 mo");
    expect(note).toContain("May 2015");
  });

  it("offers the whole record, and says which span is on", () => {
    const control = host.querySelector(".gw-window-control");
    const labels = [...(control?.querySelectorAll("button") ?? [])].map((b) => b.textContent);
    expect(labels).toEqual(["1 year", "2 years", "5 years", "All"]);
    const pressed = control?.querySelector('button[aria-pressed="true"]');
    expect(pressed?.textContent).toBe("5 years");
  });

  it("draws every month on record once the reader asks for it", () => {
    const spans = host.querySelectorAll<HTMLButtonElement>(".gw-window-control button");
    const all = spans[spans.length - 1];
    all?.click();
    expect(host.querySelector(".gw-state-row")?.querySelectorAll(".gw-state-mark").length).toBe(131);
    expect(host.querySelector(".gw-window-note")?.textContent).toContain("all 131 mo");
  });

  it("leaves the month marks as marks: one hit surface per band, not one per month", () => {
    expect(host.querySelectorAll(".gw-state-row button").length).toBe(0);
    expect(host.querySelectorAll(".gw-state-row .gw-state-mark").length).toBe(120);
  });

  it("keeps the four-state key beside the band it explains", () => {
    const key = host.querySelector(".gw-state-key")?.textContent ?? "";
    for (const state of ["reported", "reported zero", "withheld", "no report"]) {
      expect(key).toContain(state);
    }
  });
});

describe("the readout that replaced the per-point target", () => {
  beforeEach(() => renderChart(host, dense, callbacks));

  it("opens on the most recent month in the window rather than on nothing", () => {
    expect(host.querySelector(".gw-readout-month")?.textContent).toContain("Mar 2026");
  });

  it("states every stream for that month, with its unit", () => {
    const rows = host.querySelectorAll(".gw-readout-row");
    expect(rows.length).toBe(2);
    expect(rows[0]?.textContent).toContain("bbl");
    expect(rows[1]?.textContent).toContain("mcf");
  });

  it("carries a reachable derivation handle on every figure it states (R6, R8)", () => {
    const handles = host.querySelectorAll(".gw-readout-row button.gw-handle");
    expect(handles.length).toBe(2);
    expect(handles[0]?.getAttribute("data-handle")).toBe("drv_oil130#pm=2026-03");
    (handles[0] as HTMLButtonElement).click();
    expect(callbacks.onExplain).toHaveBeenCalledWith("drv_oil130#pm=2026-03");
  });

  it("steps month by month from the keyboard, which a canvas hover cannot", () => {
    const previous = host.querySelector<HTMLButtonElement>(".gw-readout-prev");
    previous?.click();
    expect(host.querySelector(".gw-readout-month")?.textContent).toContain("Feb 2026");
    const next = host.querySelector<HTMLButtonElement>(".gw-readout-next");
    next?.click();
    expect(host.querySelector(".gw-readout-month")?.textContent).toContain("Mar 2026");
  });

  it("stops at the ends of the window instead of stepping off the axis", () => {
    const next = host.querySelector<HTMLButtonElement>(".gw-readout-next");
    expect(next?.disabled).toBe(true);
    host.querySelector<HTMLButtonElement>(".gw-readout-prev")?.click();
    expect(host.querySelector<HTMLButtonElement>(".gw-readout-next")?.disabled).toBe(false);
  });

  it("keeps a reported zero readable as a reported zero", () => {
    const spans = host.querySelectorAll<HTMLButtonElement>(".gw-window-control button");
    const all = spans[spans.length - 1];
    all?.click();
    for (let step = 0; step < 130; step += 1) {
      host.querySelector<HTMLButtonElement>(".gw-readout-prev")?.click();
    }
    const row = host.querySelector(".gw-readout-row");
    expect(row?.textContent).toContain("reported zero");
    expect(row?.textContent).toContain("1,000");
  });
});

describe("a well the back-load never reached", () => {
  beforeEach(() => renderChart(host, sparse, callbacks));

  it("draws all six months and offers no span to choose between", () => {
    expect(host.querySelector(".gw-state-row")?.querySelectorAll(".gw-state-mark").length).toBe(6);
    expect(host.querySelector(".gw-window-control")).toBeNull();
  });

  it("still states what it is drawing, because a count is never assumed", () => {
    expect(host.querySelector(".gw-window-note")?.textContent).toContain("all 6 mo");
  });
});

describe("the explorer's wider redraw", () => {
  it("opens on the whole served series, because the crossing is what asked for it", () => {
    renderChart(host, dense, callbacks, { span: "served" });
    expect(host.querySelector(".gw-state-row")?.querySelectorAll(".gw-state-mark").length).toBe(131);
    expect(host.querySelector(".gw-window-note")?.textContent).toContain(
      "all 131 mo returned",
    );
    expect(host.querySelector(".gw-window-control")).toBeNull();
  });
});

describe("a series the wire carried no lineage for", () => {
  it("says the handle is missing rather than dropping the disclosure silently", () => {
    const unhandled = toChartSeries({ ...production(months("2026-01", 3)), _lineage: {} });
    renderChart(host, unhandled, callbacks);
    expect(host.querySelector(".gw-readout-row button.gw-handle")).toBeNull();
    expect(host.querySelector(".gw-readout-row")?.textContent).toContain("no derivation handle");
  });
});

describe("re-rendering the same host", () => {
  it("leaves one plot behind, not one per repaint", () => {
    renderChart(host, dense, callbacks);
    renderChart(host, dense, callbacks);
    expect(host.querySelectorAll(".gw-chart-plot").length).toBe(1);
    expect(host.querySelectorAll(".gw-series-readout").length).toBe(1);
  });
});

/**
 * Report vintage is routine provenance, not a warning. On the reading surface it was a chip in
 * the warning vocabulary, which read as something being wrong with the series; it belongs one
 * layer down, and it has to stay true to the window that is actually drawn.
 */
describe("report vintage, one layer down", () => {
  const mixed = (): ReturnType<typeof toChartSeries> => {
    const pm = months("2026-01", 4);
    const data = production(pm);
    return toChartSeries({
      ...data,
      series: {
        ...data.series,
        // The oldest month is the only one on the earlier vintage, so a window that drops it
        // drops the mixing with it (window.ts:76).
        oil_bbl_report_vintage: pm.map((_, index) => (index === 0 ? "2026-07-01" : "2026-08-20")),
      },
    });
  };

  it("paints no vintage or mixed-vintage chip on the surface", () => {
    renderChart(host, mixed(), callbacks);

    expect(host.querySelector(".gw-chip-warn")).toBeNull();
    expect(host.querySelector(".gw-chip-vintage")).toBeNull();
    expect(host.querySelector(".gw-chart-legend")?.textContent).not.toContain("vintage");
    expect(host.querySelector(".gw-series-readout")?.textContent).not.toContain("vintage");
  });

  it("keeps it reachable behind a disclosure that is closed by default", () => {
    renderChart(host, mixed(), callbacks);
    const details = host.querySelector<HTMLDetailsElement>("details.gw-vintages");

    expect(details).not.toBeNull();
    expect(details?.open).toBe(false);
    expect(details?.querySelector("summary")?.textContent).toContain("Report vintages");
    expect(details?.textContent).toContain("2026-07-01");
    expect(details?.textContent).toContain("2026-08-20");
  });

  it("reports the vintages the drawn window still holds, not the ones it dropped", () => {
    const pm = months("2020-01", 70);
    const data = production(pm);
    const long = toChartSeries({
      ...data,
      series: {
        ...data.series,
        oil_bbl_report_vintage: pm.map((_, index) => (index === 0 ? "2026-07-01" : "2026-08-20")),
      },
    });

    renderChart(host, long, callbacks);

    // The default span draws the last 60 of 70 months, which drops the only month on the
    // earlier vintage. Naming it over the drawn points would be false (window.ts:76).
    const details = host.querySelector("details.gw-vintages");
    expect(details?.textContent).toContain("2026-08-20");
    expect(details?.textContent).not.toContain("2026-07-01");
  });

  it("says nothing at all where the series carried no vintage", () => {
    const data = production(months("2026-01", 3));
    const bare = toChartSeries({
      ...data,
      series: { ...data.series, oil_bbl_report_vintage: [], gas_mcf_report_vintage: [] },
    });

    renderChart(host, bare, callbacks);

    expect(host.querySelector("details.gw-vintages")).toBeNull();
  });
});

describe("the allocation band", () => {
  function allocated(pm: string[]): ProductionData {
    const base = production(pm);
    return {
      ...base,
      granularity: "lease_allocated",
      series: {
        ...base.series,
        oil_bbl_granularity_by_month: pm.map((_, index) =>
          index === 0 ? "well_observed" : "lease_allocated",
        ),
        oil_bbl_allocation_class_by_month: pm.map((_, index) => {
          if (index === 0) return "observed_single_well_lease";
          if (index === 1) return "allocated_after_status_change";
          if (index === 2) return "excluded_after_plug";
          return "allocated_equal_share";
        }),
        oil_bbl_eligible_wells_by_month: pm.map((_, index) => (index === 0 ? "1" : "3")),
        gas_mcf_granularity_by_month: pm.map(() => "well_observed"),
        gas_mcf_allocation_class_by_month: pm.map(() => "observed_gas_well"),
        gas_mcf_eligible_wells_by_month: pm.map(() => "1"),
      },
      allocation: {
        model_id: "alloc_v0_2026_09",
        rule_id: "cr_tx_production_grain_1",
        leases: ["G-08-000303", "O-08-000101"],
        membership_vintage: "2026-08-27",
        incomplete_from: pm[pm.length - 1] ?? null,
        error_bounds: { outcome: "not_measured", measured_by_rule: "cr_alloc_v0_error_bounds_1" },
      },
    };
  }

  const chart = toChartSeries(allocated(months("2024-01", 6)));

  it("draws no second band on a jurisdiction that reports at the well", () => {
    renderChart(host, dense, callbacks);

    expect(host.querySelector(".gw-alloc-row")).toBeNull();
    expect(host.querySelector(".gw-alloc-key")).toBeNull();
  });

  it("draws a second band in its own vocabulary where a class reached the wire", () => {
    renderChart(host, chart, callbacks);
    // Inside the state strip, not beside it: `align` writes the plot's gutters onto that
    // element as custom properties, and a sibling inherits neither — which is a band drawn to
    // a different width from the plot it sits under.
    const strip = host.querySelector(".gw-state-strip");
    const rows = strip?.querySelectorAll(".gw-alloc-row") ?? [];

    expect(rows.length).toBe(2);
    // A second record, a second lookup and a second prefix: one string-keyed record for two
    // vocabularies collides on the first shared token.
    expect(strip?.querySelectorAll(".gw-alloc-mark").length).toBe(12);
  });

  it("gives each month the class it was actually arrived at under", () => {
    renderChart(host, chart, callbacks);
    const row = host.querySelectorAll(".gw-alloc-row")[0];
    const marks = [...(row?.querySelectorAll(".gw-alloc-mark") ?? [])];

    expect(marks[0]?.className).toContain("gw-alloc-observed-single-well");
    expect(marks[1]?.className).toContain("gw-alloc-after-status-change");
    expect(marks[2]?.className).toContain("gw-alloc-excluded-after-plug");
    expect(marks[3]?.className).toContain("gw-alloc-equal-share");
  });

  it("names the divisor on a mark, so a share is never a bare number", () => {
    renderChart(host, chart, callbacks);
    const marks = [...host.querySelectorAll(".gw-alloc-row .gw-alloc-mark")];

    expect(marks[3]?.getAttribute("title")).toContain("over 3 wells");
    // One eligible well is not a division, so nothing is claimed about one.
    expect(marks[0]?.getAttribute("title")).not.toContain("over");
  });

  it("keys the band with all six classes, including the ones this well never hit", () => {
    renderChart(host, chart, callbacks);
    const key = host.querySelector(".gw-alloc-key");

    expect(key?.querySelectorAll(".gw-alloc-mark").length).toBe(6);
    expect(key?.textContent).toContain("excluded after plug");
    expect(key?.textContent).toContain("unallocated");
  });

  it("shades the months inside the completeness lag in both bands", () => {
    renderChart(host, chart, callbacks);
    const shaded = host.querySelectorAll(".gw-month-incomplete");

    // The last month of each of the four rows: two streams, each with a state band and an
    // allocation band. The gas column is observed and still carries a class, because
    // "observed" is one of the six things the band has to be able to say.
    expect(shaded.length).toBe(4);
  });

  it("says a plugged well's month is a share rather than letting it read as reported", () => {
    renderChart(host, chart, callbacks);
    const marks = [...host.querySelectorAll(".gw-alloc-row .gw-alloc-mark")];

    expect(marks[1]?.getAttribute("title")).toContain("allocated, status changed");
  });

  it("says it in the readout too, which is where a reader reads one number", () => {
    // The band says it across the whole series. The readout is where a share would otherwise
    // sit beside the word "reported" with nothing to say it is an estimate, and that is the
    // one place a reader is looking hardest.
    renderChart(host, chart, callbacks);
    const rows = [...host.querySelectorAll(".gw-readout-row")];
    const oil = rows.find((row) => (row as HTMLElement).dataset["stream"] === "oil");

    expect(oil?.querySelector(".gw-readout-alloc")?.textContent).toContain("allocated");
    expect(oil?.querySelector(".gw-readout-alloc")?.textContent).toContain("over 3 wells");
  });

  it("leaves the readout alone on a jurisdiction that reports at the well", () => {
    renderChart(host, dense, callbacks);

    expect(host.querySelector(".gw-readout-alloc")).toBeNull();
  });
});
