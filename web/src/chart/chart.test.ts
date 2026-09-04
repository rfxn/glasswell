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

function allocated(pm: string[]): ProductionData {
  const base = production(pm);
  return {
    ...base,
    granularity: "lease_allocated",
    series: {
      ...base.series,
      // What the allocated arm serves: the subject of the state band is the lease-month,
      // and the well's own month was never reported at all.
      oil_bbl_null_semantics: pm.map(() => "lease_reported"),
      gas_mcf_null_semantics: pm.map(() => "lease_reported"),
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
      oil_bbl_shares_by_month: pm.map(() => "1"),
      gas_mcf_granularity_by_month: pm.map(() => "well_observed"),
      gas_mcf_allocation_class_by_month: pm.map(() => "observed_gas_well"),
      gas_mcf_eligible_wells_by_month: pm.map(() => "1"),
      gas_mcf_shares_by_month: pm.map(() => "1"),
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

const allocatedChart = toChartSeries(allocated(months("2024-01", 6)));

describe("the allocation band", () => {

  it("draws no second band on a jurisdiction that reports at the well", () => {
    renderChart(host, dense, callbacks);

    expect(host.querySelector(".gw-alloc-row")).toBeNull();
    expect(host.querySelector(".gw-alloc-key")).toBeNull();
  });

  it("draws a second band in its own vocabulary where a class reached the wire", () => {
    renderChart(host, allocatedChart, callbacks);
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
    renderChart(host, allocatedChart, callbacks);
    const row = host.querySelectorAll(".gw-alloc-row")[0];
    const marks = [...(row?.querySelectorAll(".gw-alloc-mark") ?? [])];

    expect(marks[0]?.className).toContain("gw-alloc-observed-single-well");
    expect(marks[1]?.className).toContain("gw-alloc-after-status-change");
    expect(marks[2]?.className).toContain("gw-alloc-excluded-after-plug");
    expect(marks[3]?.className).toContain("gw-alloc-equal-share");
  });

  it("names the divisor on a mark, so a share is never a bare number", () => {
    renderChart(host, allocatedChart, callbacks);
    const marks = [...host.querySelectorAll(".gw-alloc-row .gw-alloc-mark")];

    expect(marks[3]?.getAttribute("title")).toContain("over 3 wells");
    // One eligible well is not a division, so nothing is claimed about one.
    expect(marks[0]?.getAttribute("title")).not.toContain("over");
  });

  it("keys the classes this well's band drew, and not the ones it never hit", () => {
    // Six entries under a band showing one class made the band read as a component that had
    // failed to draw the other five.
    renderChart(host, allocatedChart, callbacks);
    const key = host.querySelector(".gw-alloc-key");

    // Four on the oil row and one on the gas row; `unallocated` is the sixth and no month
    // of this well is one.
    expect(key?.querySelectorAll(".gw-alloc-mark").length).toBe(5);
    expect(key?.textContent).toContain("excluded after plug");
    expect(key?.textContent).not.toContain("unallocated");
  });

  it("keys one class where the series carries one, not the whole vocabulary", () => {
    const gasLease = toChartSeries(observedGasLease(months("2024-01", 6)));
    renderChart(host, gasLease, callbacks);
    const key = host.querySelector(".gw-alloc-key");

    expect(key?.querySelectorAll(".gw-alloc-mark").length).toBe(1);
    expect(key?.textContent).toContain("observed · gas lease");
  });

  it("writes no em-dash into a label a reader is served", () => {
    renderChart(host, allocatedChart, callbacks);
    const labelled = [...host.querySelectorAll("[title], [aria-label]")].flatMap((node) => [
      node.getAttribute("title") ?? "",
      node.getAttribute("aria-label") ?? "",
    ]);

    expect(labelled.filter((text) => text.includes("\u2014"))).toEqual([]);
    expect(host.querySelector(".gw-alloc-cells")?.getAttribute("aria-label")).toContain(
      "arrived at:",
    );
  });

  it("shades the months inside the completeness lag in both bands", () => {
    renderChart(host, allocatedChart, callbacks);
    const shaded = host.querySelectorAll(".gw-month-incomplete");

    // The last month of each of the four rows: two streams, each with a state band and an
    // allocation band. The gas column is observed and still carries a class, because
    // "observed" is one of the six things the band has to be able to say.
    expect(shaded.length).toBe(4);
  });

  it("says a plugged well's month is a share rather than letting it read as reported", () => {
    renderChart(host, allocatedChart, callbacks);
    const marks = [...host.querySelectorAll(".gw-alloc-row .gw-alloc-mark")];

    expect(marks[1]?.getAttribute("title")).toContain("allocated, status changed");
  });

  it("says it in the readout too, which is where a reader reads one number", () => {
    // The band says it across the whole series. The readout is where a share would otherwise
    // sit beside the word "reported" with nothing to say it is an estimate, and that is the
    // one place a reader is looking hardest.
    renderChart(host, allocatedChart, callbacks);
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

/** A gas lease with one well on it: every month observed, one class in the whole series. */
function observedGasLease(pm: string[]): ProductionData {
  const base = allocated(pm);
  return {
    ...base,
    series: {
      ...base.series,
      oil_bbl_granularity_by_month: pm.map(() => "well_observed"),
      oil_bbl_allocation_class_by_month: pm.map(() => "observed_gas_well"),
      oil_bbl_eligible_wells_by_month: pm.map(() => "1"),
      gas_mcf_allocation_class_by_month: pm.map(() => "observed_gas_well"),
    },
  };
}

/** The 21.9 percent of Texas API-10s that carry more than one lease record. */
function dualLease(pm: string[]): ProductionData {
  const base = allocated(pm);
  return {
    ...base,
    series: {
      ...base.series,
      // What the wire serves for a summed point: the class collapses to the safe one, and
      // there is no divisor, because no one division produced the number.
      gas_mcf_granularity_by_month: pm.map(() => "lease_allocated"),
      gas_mcf_allocation_class_by_month: pm.map(() => "allocated_equal_share"),
      gas_mcf_eligible_wells_by_month: pm.map(() => null),
      gas_mcf_shares_by_month: pm.map(() => "2"),
    },
  };
}

describe("a wellbore whose month is the sum of two leases", () => {
  const dual = toChartSeries(dualLease(months("2024-01", 6)));

  it("counts the shares instead of stating a divisor that divided nothing", () => {
    renderChart(host, dual, callbacks);
    const rows = [...host.querySelectorAll(".gw-readout-row")];
    const gas = rows.find((row) => (row as HTMLElement).dataset["stream"] === "gas");
    const how = gas?.querySelector(".gw-readout-alloc")?.textContent ?? "";

    expect(how).toContain("2 shares summed");
    expect(how).not.toContain("over");
  });

  it("says the same thing in the band's tooltip, which is where a month is read", () => {
    renderChart(host, dual, callbacks);
    const rows = [...host.querySelectorAll(".gw-alloc-row")];
    const marks = [...(rows[1]?.querySelectorAll(".gw-alloc-mark") ?? [])];

    expect(marks[0]?.getAttribute("title")).toContain("2 shares summed");
    expect(marks[0]?.getAttribute("title")).not.toContain("wells");
  });

  it("keeps the divisor where one lease really was divided", () => {
    renderChart(host, dual, callbacks);
    const rows = [...host.querySelectorAll(".gw-readout-row")];
    const oil = rows.find((row) => (row as HTMLElement).dataset["stream"] === "oil");

    expect(oil?.querySelector(".gw-readout-alloc")?.textContent).toContain("over 3 wells");
  });
});

describe("the two bands name two subjects", () => {
  it("says the first band is the lease's filing, not this well's month", () => {
    renderChart(host, allocatedChart, callbacks);
    const names = [...host.querySelectorAll(".gw-state-row .gw-state-name")].map(
      (node) => node.textContent,
    );

    // Two rows per stream: what the lease filed, and how this well's share was arrived at.
    expect(names).toEqual(["Oil · lease", "Gas · lease", "Oil · how", "Gas · how"]);
    // The gutter is 58 px wide and clips with an ellipsis, so the subject is two words and
    // the sentence rides in the title.
    const subject = host.querySelector(".gw-state-row .gw-state-name");
    expect(subject?.getAttribute("title")).toContain("share of that filing");
  });

  it("never stands the bare word reported beside a share in the readout", () => {
    renderChart(host, allocatedChart, callbacks);
    const rows = [...host.querySelectorAll(".gw-readout-row")];
    const oil = rows.find((row) => (row as HTMLElement).dataset["stream"] === "oil");

    expect(oil?.querySelector(".gw-readout-state")?.textContent?.trim()).toBe("lease reported");
    expect(oil?.querySelector(".gw-readout-alloc")?.textContent).toContain("allocated");
  });

  it("keys the state it drew, so no mark on the band is a colour to guess at", () => {
    renderChart(host, allocatedChart, callbacks);
    const key = host.querySelector(".gw-state-key");

    expect(key?.textContent).toContain("lease reported");
    expect(key?.querySelectorAll(".gw-state-mark").length).toBe(5);
  });

  it("leaves the four-state key and the plain row name on an observed jurisdiction", () => {
    renderChart(host, dense, callbacks);
    const names = [...host.querySelectorAll(".gw-state-row .gw-state-name")].map(
      (node) => node.textContent,
    );

    expect(names).toEqual(["Oil", "Gas"]);
    expect(host.querySelectorAll(".gw-state-key .gw-state-mark").length).toBe(4);
  });
});

describe("the stream toggles", () => {
  beforeEach(() => renderChart(host, sparse, callbacks));

  it("makes every stream a two-state control that says which state it is in", () => {
    const toggles = [...host.querySelectorAll<HTMLButtonElement>(".gw-stream-toggle")];

    expect(toggles.map((each) => each.textContent)).toEqual(["Oil (bbl)", "Gas (mcf)"]);
    expect(toggles.every((each) => each.getAttribute("aria-pressed") === "true")).toBe(true);
  });

  it("takes a stream off the plot, the band and the readout together", () => {
    const oil = host.querySelector<HTMLButtonElement>(".gw-stream-toggle");
    oil?.click();

    expect(host.querySelector(".gw-stream-toggle")?.getAttribute("aria-pressed")).toBe("false");
    expect(host.querySelectorAll(".gw-state-row").length).toBe(1);
    expect(host.querySelector(".gw-series-readout")?.textContent).not.toContain("Oil");
  });

  it("brings it back, because a toggle a reader cannot undo is a delete", () => {
    host.querySelector<HTMLButtonElement>(".gw-stream-toggle")?.click();
    host.querySelector<HTMLButtonElement>(".gw-stream-toggle")?.click();

    expect(host.querySelectorAll(".gw-state-row").length).toBe(2);
    expect(host.querySelector(".gw-stream-toggle")?.getAttribute("aria-pressed")).toBe("true");
  });

  it("refuses to hide the last stream on the plot rather than drawing an empty axis", () => {
    const toggles = [...host.querySelectorAll<HTMLButtonElement>(".gw-stream-toggle")];
    toggles[0]?.click();
    const last = host.querySelectorAll<HTMLButtonElement>(".gw-stream-toggle")[1];

    expect(last?.disabled).toBe(true);
    expect(last?.title).toContain("only stream");
  });
});

describe("the log control, and the zero it cannot draw", () => {
  beforeEach(() => renderChart(host, sparse, callbacks));

  it("is a two-state control that starts linear", () => {
    const scale = host.querySelector<HTMLButtonElement>(".gw-scale-toggle");

    expect(scale?.getAttribute("aria-pressed")).toBe("false");
    expect(scale?.textContent).toContain("Log");
  });

  it("states per stream how many drawn months read zero once log is on", () => {
    host.querySelector<HTMLButtonElement>(".gw-scale-toggle")?.click();
    const note = host.querySelector(".gw-log-zeros")?.textContent ?? "";

    // Per stream, because a well can be zero on water and not on oil, and one combined count
    // would be wrong for two of the three.
    expect(note).toContain("Oil");
    expect(note).toContain("1 month");
    expect(note).toContain("log axis cannot place");
    expect(note).not.toContain("withheld");
  });

  it("keeps a zero month in the band and out of the line", () => {
    host.querySelector<HTMLButtonElement>(".gw-scale-toggle")?.click();

    // The band still carries every month of the window, zero included: the state is a fact
    // about the month, and the log axis is a fact about the drawing.
    expect(host.querySelector(".gw-state-row")?.querySelectorAll(".gw-state-mark").length).toBe(6);
    const marks = [...(host.querySelector(".gw-state-row")?.querySelectorAll(".gw-state-mark") ?? [])];
    expect(marks[0]?.className).toContain("reported-zero");
  });

  it("goes back to linear, where the zero is a point again", () => {
    const scale = () => host.querySelector<HTMLButtonElement>(".gw-scale-toggle");
    scale()?.click();
    scale()?.click();

    expect(scale()?.getAttribute("aria-pressed")).toBe("false");
    expect(host.querySelector(".gw-log-zeros")).toBeNull();
  });
});

describe("brushing a range, and the total that follows it", () => {
  const brushed = vi.fn();
  beforeEach(() => {
    brushed.mockClear();
    renderChart(host, sparse, { ...callbacks, onBrush: brushed });
  });

  const band = (): HTMLElement => host.querySelector(".gw-state-cells") as HTMLElement;
  const cells = (): HTMLElement[] => [...band().querySelectorAll<HTMLElement>(".gw-state-mark")];
  const drag = (from: number, to: number): void => {
    const marks = cells();
    marks[from]?.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
    marks[to]?.dispatchEvent(new PointerEvent("pointerenter", { bubbles: true }));
    marks[to]?.dispatchEvent(new PointerEvent("pointerup", { bubbles: true }));
  };

  it("narrows the window to the months the reader dragged over", () => {
    drag(1, 3);

    const note = host.querySelector(".gw-window-note")?.textContent ?? "";
    expect(note).toContain("Nov 2025");
    expect(note).toContain("Jan 2026");
    expect(host.querySelector(".gw-state-row")?.querySelectorAll(".gw-state-mark").length).toBe(3);
  });

  it("says the window is a selection and offers the way out of it", () => {
    drag(1, 3);

    const selected = host.querySelector(".gw-window-selected");
    expect(selected?.textContent).toContain("Selected");
    const clear = host.querySelector<HTMLButtonElement>(".gw-window-clear");
    expect(clear).not.toBeNull();
    clear?.click();
    expect(host.querySelector(".gw-window-selected")).toBeNull();
    expect(host.querySelector(".gw-state-row")?.querySelectorAll(".gw-state-mark").length).toBe(6);
  });

  it("hands the range to the card, so the URL can carry it and the server can answer it", () => {
    drag(1, 3);

    expect(brushed).toHaveBeenCalledWith("2025-11", "2026-01");
    host.querySelector<HTMLButtonElement>(".gw-window-clear")?.click();
    expect(brushed).toHaveBeenLastCalledWith(null, null);
  });

  it("draws a running total over the selection, with its own scope on the same line", () => {
    drag(1, 3);
    const total = host.querySelector(".gw-running-total")?.textContent ?? "";

    expect(total).toContain("Running total");
    expect(total).toContain("3 months shown");
    expect(total).toContain("3 reported");
    expect(total).not.toContain("withheld");
  });

  it("gives the running total no handle at all, and says where provenance is", () => {
    drag(1, 3);
    const row = host.querySelector(".gw-running-total") as HTMLElement;

    // M-7, the owner's ruling: a client sum that borrowed one point's ⌾ would name the sum's
    // provenance and open a different number's chain.
    expect(row.querySelectorAll(".gw-handle").length).toBe(0);
    expect(row.querySelector("gw-figure")).toBeNull();
    expect(row.textContent).toContain("computed on this page from the 3 points shown");
    expect(row.textContent).toContain("each point's ⌾ is beside it");
  });

  it("sums normalised points on the decimal string, never through a float", () => {
    // Three three-decimal points whose float sum is 99.45100000000001: the total is a figure
    // on the page and has to read like one.
    const raw = ["7.462", "10.113", "81.876"];
    const normalised: ProductionData = {
      ...production(months("2025-01", 3)),
      streams: ["oil"],
      series: {
        pm: months("2025-01", 3),
        oil_bbl: raw,
        oil_bbl_report_vintage: raw.map(() => "2026-08-01"),
        oil_bbl_null_semantics: raw.map(() => "reported"),
      },
      _lineage: Object.fromEntries(raw.map((_, index) => [`series.oil_bbl.${index}`, `drv_oil${index}`])),
      _units: { "series.oil_bbl": "bbl/kft" },
    };
    renderChart(host, toChartSeries(normalised), callbacks);
    drag(0, 2);

    const total = host.querySelector(".gw-running-value")?.textContent ?? "";
    expect(total).toBe("Oil 99.451 bbl/kft");
  });

  it("counts the classes of the months it summed, not the ones it did not", () => {
    // The first month of the fixture reads zero, so a brush that includes it says so.
    drag(0, 2);
    const total = host.querySelector(".gw-running-total")?.textContent ?? "";

    expect(total).toContain("1 reported zero");
  });
});

describe("the per-lateral-foot control", () => {
  const changed = vi.fn();
  const control = (over: Record<string, unknown> = {}) => ({
    normalization: { on: false, available: true, onChange: changed, ...over },
  });

  beforeEach(() => changed.mockClear());

  it("asks the server for the arm rather than dividing here", () => {
    renderChart(host, sparse, callbacks, control());
    const toggle = host.querySelector<HTMLButtonElement>(".gw-normalize-toggle");

    expect(toggle?.getAttribute("aria-pressed")).toBe("false");
    toggle?.click();
    expect(changed).toHaveBeenCalledWith(true);
  });

  it("says which state it is in, so a normalised plot is never a surprise", () => {
    renderChart(host, sparse, callbacks, control({ on: true }));

    expect(host.querySelector(".gw-normalize-toggle")?.getAttribute("aria-pressed")).toBe("true");
  });

  it("states the reason where no divisor is served rather than offering a dead control", () => {
    renderChart(
      host,
      sparse,
      callbacks,
      control({
        available: false,
        reason: "cr_mt_paths_length_scope_1 withholds it",
        rule: "/v1/conformance/cr_mt_paths_length_scope_1",
      }),
    );
    const toggle = host.querySelector<HTMLButtonElement>(".gw-normalize-toggle");

    expect(toggle?.disabled).toBe(false);
    expect(toggle?.getAttribute("aria-disabled")).toBe("true");
    expect(toggle?.tabIndex).toBeGreaterThanOrEqual(0);
    const reason = host.querySelector(".gw-normalize-reason");
    expect(reason?.textContent).toContain("cr_mt_paths_length_scope_1 withholds it");
    expect(reason?.querySelector("a")?.getAttribute("href")).toBe(
      "/v1/conformance/cr_mt_paths_length_scope_1",
    );
    toggle?.click();
    expect(changed).not.toHaveBeenCalled();
  });

  it("is absent where the card offers no control at all", () => {
    renderChart(host, sparse, callbacks);

    expect(host.querySelector(".gw-normalize-toggle")).toBeNull();
  });
});

describe("as filed versus as restated, stated rather than toggled", () => {
  const restated = (): ReturnType<typeof toChartSeries> => {
    const pm = months("2026-01", 4);
    const data = production(pm);
    return toChartSeries({
      ...data,
      series: {
        ...data.series,
        oil_bbl_report_vintage: pm.map((_, index) => (index === 0 ? "2026-07-01" : "2026-08-20")),
      },
    });
  };

  it("says how many vintages the window holds and over what range", () => {
    renderChart(host, restated(), callbacks);
    const summary = host.querySelector("details.gw-vintages summary")?.textContent ?? "";

    expect(summary).toContain("2");
    expect(summary).toContain("2026-07-01");
    expect(summary).toContain("2026-08-20");
  });

  it("says one vintage means no restatement was captured, not that none happened", () => {
    renderChart(host, sparse, callbacks);
    const summary = host.querySelector("details.gw-vintages summary")?.textContent ?? "";

    expect(summary).toContain("one");
    expect(summary).toContain("no restatement captured");
  });

  it("names the earliest vintage as glasswell's own capture rather than the filing", () => {
    renderChart(host, restated(), callbacks);
    const details = host.querySelector("details.gw-vintages")?.textContent ?? "";

    expect(details).toContain("when glasswell first captured this month");
    expect(details).not.toContain("as first filed");
  });

  it("marks the month read at an older capture, in its own row and its own prefix", () => {
    renderChart(host, restated(), callbacks);
    const row = host.querySelector(".gw-restate-row");

    // Three vocabularies, three records, three prefixes: `gw-state-*`, `gw-alloc-*` and this.
    expect(row).not.toBeNull();
    expect(row?.querySelectorAll(".gw-restate-earlier").length).toBe(1);
    expect(row?.querySelectorAll(".gw-vintage-earlier").length).toBe(0);
    expect(row?.querySelectorAll(".gw-restate-latest").length).toBe(3);
  });

  it("says which capture it means, and never that the operator re-filed the month", () => {
    // The wire carries one report vintage per drawn point, so a month filed twice and a month
    // pulled twice are the same shape: a mark reading "restated" would assert what it cannot
    // see, which is the failure the whole section is written against.
    renderChart(host, restated(), callbacks);
    const mark = host.querySelector(".gw-restate-earlier");

    expect(mark?.getAttribute("title")).toContain("older report vintage");
    expect(mark?.getAttribute("title")).toContain("not that the operator re-filed it");
    expect(host.querySelector(".gw-restate-row")?.textContent).not.toContain("restated");
  });

  it("draws no capture row where every month came from one pull", () => {
    renderChart(host, sparse, callbacks);

    expect(host.querySelector(".gw-restate-row")).toBeNull();
  });
});

describe("the table alternative", () => {
  // Fetched on the press: the chart chunk rides the explorer route, and a table nobody opened
  // is not something every Explore reader should download.
  const press = async (): Promise<void> => {
    // Warmed first: the press imports the module, and a cold transform under a loaded
    // machine outlasts the ticks below, which made this a race rather than a test.
    await import("../card/table.ts");
    const before = host.querySelector(".gw-table-toggle")?.getAttribute("aria-pressed");
    host.querySelector<HTMLButtonElement>(".gw-table-toggle")?.click();
    for (let tick = 0; tick < 20; tick += 1) {
      if (host.querySelector(".gw-table-toggle")?.getAttribute("aria-pressed") !== before) return;
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
  };

  beforeEach(() => renderChart(host, sparse, callbacks));

  it("offers the same months as rows, and says which view is on", async () => {
    expect(host.querySelector(".gw-table-toggle")?.getAttribute("aria-pressed")).toBe("false");

    await press();

    expect(host.querySelector(".gw-table-toggle")?.getAttribute("aria-pressed")).toBe("true");
    expect(host.querySelectorAll(".gw-series-table tbody tr").length).toBe(6);
    expect(host.querySelector(".gw-chart-plot")).toBeNull();
  });

  it("keeps the state key beside the table, because the words are the same words", async () => {
    await press();

    expect(host.querySelector(".gw-state-key")).not.toBeNull();
  });

  it("goes back to the plot", async () => {
    await press();
    await press();

    expect(host.querySelector(".gw-chart-plot")).not.toBeNull();
    expect(host.querySelector(".gw-series-table")).toBeNull();
  });

  it("carries the window's own months, not the whole record", async () => {
    renderChart(host, dense, callbacks);
    await press();

    expect(host.querySelectorAll(".gw-series-table tbody tr").length).toBe(60);
  });
});

describe("a reloaded brushed link on the card", () => {
  // R-20: on reload the server answers the brushed window, so the client holds only those
  // months and the bar's "All" would describe the window rather than the record. It says
  // which it is describing and carries the way back to the record.
  it("says it is showing all of the months it was handed, and offers the whole record", () => {
    const widened = vi.fn();
    renderChart(host, sparse, callbacks, { span: "served", onWiden: widened });

    expect(host.querySelector(".gw-window-note")?.textContent).toContain("All of the months shown");
    expect(host.querySelector(".gw-window-note")?.textContent).not.toContain("on record");
    const widen = host.querySelector<HTMLButtonElement>(".gw-window-widen");
    expect(widen?.textContent).toBe("Widen to the whole record");
    widen?.click();
    expect(widened).toHaveBeenCalledTimes(1);
  });

  it("offers no widening where nothing narrowed the request", () => {
    renderChart(host, sparse, callbacks);
    expect(host.querySelector(".gw-window-widen")).toBeNull();
    expect(host.querySelector(".gw-window-note")?.textContent).toContain("on record");
  });
});
