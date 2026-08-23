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
    expect(note).toContain("60 of 131 months");
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
    expect(host.querySelector(".gw-window-note")?.textContent).toContain("all 131 months");
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
    expect(host.querySelector(".gw-window-note")?.textContent).toContain("all 6 months");
  });
});

describe("the explorer's wider redraw", () => {
  it("opens on the whole served series, because the crossing is what asked for it", () => {
    renderChart(host, dense, callbacks, { span: "served" });
    expect(host.querySelector(".gw-state-row")?.querySelectorAll(".gw-state-mark").length).toBe(131);
    expect(host.querySelector(".gw-window-note")?.textContent).toContain(
      "all 131 months returned by this request",
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
