// @vitest-environment happy-dom
//
// REG-WC-4, measured on the deployed shape by the status-truth visual gate: the capture band
// spanned 1144→1584 against a drawing area of 1144→1508, a month off its ticks, because the
// band was aligned to the layout that existed one tick earlier. The band was only ever correct
// where something mounting after the chart nudged its container and the ResizeObserver fired a
// second time; on an ND card whose neighbours and type curve 404, nothing does.
//
// The uPlot mock here is the one thing this file needs the real chart to meet: a drawing area
// that spans the whole plot until the axes are placed, and narrows a tick later. Nothing in
// this file ever resizes the chart.
import { beforeEach, describe, expect, it, vi } from "vitest";

const OUTER = { left: 1100, right: 1584 };
const AXES = { left: 1144, right: 1508 };

function rect(element: HTMLElement, box: { left: number; right: number }): void {
  element.getBoundingClientRect = () =>
    ({
      left: box.left,
      right: box.right,
      width: box.right - box.left,
      top: 0,
      bottom: 260,
      height: 260,
      x: box.left,
      y: 0,
      toJSON: () => ({}),
    }) as DOMRect;
}

vi.mock("uplot", () => ({
  default: class {
    over = document.createElement("div");
    constructor(_options: unknown, _data: unknown, plot: HTMLElement) {
      plot.appendChild(this.over);
      rect(plot, OUTER);
      rect(this.over, { left: AXES.left, right: OUTER.right });
      queueMicrotask(() => rect(this.over, AXES));
    }
    setSize(): void {}
    destroy(): void {}
  },
}));

const { renderChart } = await import("./chart.ts");
const { toChartSeries } = await import("./series.ts");
type ProductionData = import("./series.ts").ProductionData;

const pm = ["2025-10", "2025-11", "2025-12", "2026-01", "2026-02", "2026-03"];
const production: ProductionData = {
  api10: "3305305514",
  source_id: "nd_dmr_mpr",
  granularity: "well_observed",
  streams: ["oil", "gas"],
  series: {
    pm,
    oil_bbl: pm.map((_, index) => String(1000 + index)),
    oil_bbl_report_vintage: pm.map(() => "2026-08-01"),
    oil_bbl_null_semantics: pm.map(() => "reported"),
    gas_mcf: pm.map((_, index) => String(2000 + index)),
    gas_mcf_report_vintage: pm.map(() => "2026-08-01"),
    gas_mcf_null_semantics: pm.map(() => "reported"),
  },
  _lineage: {},
  _units: { "series.oil_bbl": "bbl", "series.gas_mcf": "mcf" },
  _basis: {},
};

const callbacks = { onExplain: vi.fn(), labelTermFor: () => null };
let host: HTMLElement;

const frame = (): Promise<void> => new Promise((resolve) => requestAnimationFrame(() => resolve()));
const band = (): HTMLElement => host.querySelector(".gw-state-strip") as HTMLElement;
const inset = (name: string): string => band().style.getPropertyValue(name);

beforeEach(() => {
  document.body.innerHTML = "";
  host = document.createElement("div");
  document.body.appendChild(host);
});

describe("the capture band against the plot it captions", () => {
  it("takes the gutter the axes ended up with, on a mount nothing resizes afterwards", async () => {
    renderChart(host, toChartSeries(production), callbacks);

    await frame();

    // The second y axis takes 76 px on the right; a band that keeps them reads a month off its
    // ticks and clips the focused month at the card's edge.
    expect(inset("--gw-band-right")).toBe(`${OUTER.right - AXES.right}px`);
    expect(inset("--gw-band-left")).toBe(`${AXES.left - OUTER.left}px`);
  });

  it("writes both insets from one layout, so they describe the same drawing area", async () => {
    renderChart(host, toChartSeries(production), callbacks);

    await frame();

    const left = Number.parseFloat(inset("--gw-band-left"));
    const right = Number.parseFloat(inset("--gw-band-right"));
    expect(OUTER.right - OUTER.left - left - right).toBe(AXES.right - AXES.left);
  });
});
