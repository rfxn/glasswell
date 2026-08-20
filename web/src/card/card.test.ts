// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ChartSeries } from "../chart/series.ts";

const renderChart = vi.fn<(container: HTMLElement, chart: ChartSeries) => void>();
vi.mock("../chart/chart.ts", () => ({
  renderChart: (container: HTMLElement, chart: ChartSeries) => renderChart(container, chart),
}));

const { renderWellCard } = await import("./card.ts");
const { API10, LENGTH_HANDLE, OIL_HANDLE, productionEnvelope, stubFetch, wellEnvelope } =
  await import("../test/fixtures.ts");

const callbacks = { onExplain: vi.fn(), onClose: vi.fn() };
let host: HTMLElement;

beforeEach(() => {
  document.body.innerHTML = "";
  host = document.createElement("aside");
  document.body.appendChild(host);
  renderChart.mockClear();
  vi.stubGlobal(
    "fetch",
    vi.fn(
      stubFetch({
        [`/v1/wells/${API10}/production`]: productionEnvelope,
        [`/v1/wells/${API10}`]: wellEnvelope,
      }),
    ),
  );
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("well card", () => {
  it("renders the header the operator would recognise", async () => {
    await renderWellCard(host, API10, callbacks);
    expect(host.querySelector("h2")?.textContent).toBe("SPOTTED HORSE 14-23H");
    const text = host.textContent ?? "";
    expect(text).toContain("CONTINENTAL RESOURCES");
    expect(text).toContain("150N-96W-14");
  });

  it("renders lateral length through gw-figure, with its unit and its handle", async () => {
    await renderWellCard(host, API10, callbacks);
    const figure = host.querySelector("gw-figure");
    expect(figure?.getAttribute("unit")).toBe("ft");
    expect(figure?.getAttribute("handle")).toBe(LENGTH_HANDLE);
    expect(figure?.textContent).toContain("9,853.24 ft");
  });

  it("opens the drawer from the figure's handle affordance", async () => {
    await renderWellCard(host, API10, callbacks);
    const button = host.querySelector<HTMLButtonElement>("gw-figure button");
    button?.click();
    expect(callbacks.onExplain).toHaveBeenCalledWith(LENGTH_HANDLE);
  });

  it("links labels the API named in meta.labels straight to their term (DIR-8)", async () => {
    await renderWellCard(host, API10, callbacks);
    const terms = [...host.querySelectorAll("gw-term")].map((term) => term.getAttribute("term-id"));
    expect(terms).toContain("gt_api_10_api_12_api_14");
    expect(terms).toContain("gt_wellbore");
  });

  it("hands the chart a series carrying each stream's handle, unit and null semantics", async () => {
    await renderWellCard(host, API10, callbacks);
    expect(renderChart).toHaveBeenCalledTimes(1);
    const chart = renderChart.mock.calls[0]?.[1] as ChartSeries;
    expect(chart.columns.map((column) => column.key)).toEqual([
      "oil_bbl",
      "gas_mcf",
      "water_bbl",
    ]);
    expect(chart.columns[0]?.handle).toBe(OIL_HANDLE);
    expect(chart.columns[0]?.unit).toBe("bbl");
    expect(chart.columns[0]?.nullSemantics).toEqual(["reported", "withheld"]);
    expect(chart.columns[2]?.values).toEqual([800, 0]);
  });

  it("says so when the API refuses the request instead of rendering an empty card", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(
            JSON.stringify({
              type: "https://glasswell.rpx.sh/v1/errors/key_required",
              title: "An API key is required",
              status: 403,
            }),
            { status: 403, headers: { "content-type": "application/problem+json" } },
          ),
        ),
      ),
    );
    await renderWellCard(host, API10, callbacks);
    expect(host.textContent).toContain("owner key");
  });
});
