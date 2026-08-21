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

describe("a well whose regulator reports at the lease", () => {
  it("says production is pending allocation instead of drawing an empty chart", async () => {
    const pending = {
      ...wellEnvelope,
      meta: {
        ...wellEnvelope.meta,
        warnings: [
          {
            code: "production_pending_allocation",
            detail:
              "This well's regulator reports production at the lease" +
              " (cr_tx_allocation_scope_1), so no well-level series has been observed.",
            pointer: "/production",
          },
        ],
      },
    };
    const production = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn(
        stubFetch({
          [`/v1/wells/${API10}`]: pending,
          [`/v1/wells/${API10}/production`]: () => {
            production();
            return productionEnvelope;
          },
        }),
      ),
    );

    await renderWellCard(host, API10, callbacks);

    const panel = host.querySelector<HTMLElement>("[data-state='production_pending_allocation']");
    expect(panel?.querySelector(".gw-frame-title")?.textContent).toBe(
      "Production pending allocation",
    );
    expect(panel?.textContent).toContain("cr_tx_allocation_scope_1");
    expect(panel?.querySelector(".gw-pending-rule")?.getAttribute("href")).toBe("/v1/conformance");
    expect(host.textContent).not.toContain("No production has been reported");
    expect(renderChart).not.toHaveBeenCalled();
    expect(production).not.toHaveBeenCalled();
  });
});

describe("well card", () => {
  it("renders the header the operator would recognise", async () => {
    await renderWellCard(host, API10, callbacks);
    expect(host.querySelector("h2")?.textContent).toBe("Mandaree 50-2008H");
    const text = host.textContent ?? "";
    expect(text).toContain("EOG RESOURCES, INC.");
    expect(text).toContain("149N-94W-20");
  });

  it("renders lateral length through gw-figure, with its unit and its handle", async () => {
    await renderWellCard(host, API10, callbacks);
    const figure = host.querySelector("gw-figure");
    expect(figure?.getAttribute("unit")).toBe("ft");
    expect(figure?.getAttribute("handle")).toBe(LENGTH_HANDLE);
    expect(figure?.textContent).toContain("15,065.44 ft");
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
    // Every recorded month is `reported`; the other three states are covered against
    // constructed series in chart/series.test.ts and card/format.test.ts.
    expect(chart.columns[0]?.nullSemantics).toEqual(Array(6).fill("reported"));
    expect(chart.columns[2]?.values).toEqual([47601, 45428, 24918, 30985, 24753, 22452]);
  });

  it("frames the chart with a title the plot cannot overwrite when it arrives", async () => {
    // The section went straight from a facts list to an unlabelled plot, and every state of
    // it — placeholder, chart, error — used to replaceChildren() the whole frame.
    await renderWellCard(host, API10, callbacks);

    const frame = host.querySelector(".gw-card-chart") as HTMLElement;
    expect(frame.querySelector(".gw-frame-title")?.textContent).toBe("Monthly production");
    expect(renderChart.mock.calls[0]?.[0]).toBe(frame.querySelector(".gw-frame-body"));
  });

  it("splits into a fixed head and a scrolling body, so a long card cannot overrun", async () => {
    await renderWellCard(host, API10, callbacks);

    const card = host.querySelector(".gw-card") as HTMLElement;
    expect(card.children).toHaveLength(2);
    expect(card.children[0]?.className).toContain("gw-panel-head");
    expect(card.children[1]?.className).toContain("gw-panel-body");
    // Everything that grows — facts, warnings, chart — belongs to the scroller.
    expect(card.querySelector(".gw-panel-body .gw-facts")).toBeTruthy();
    expect(card.querySelector(".gw-panel-body .gw-card-chart")).toBeTruthy();
  });

  it("keeps the close button in the head, where it stays reachable while the body scrolls", async () => {
    await renderWellCard(host, API10, callbacks);

    expect(host.querySelector(".gw-panel-head .gw-close")).toBeTruthy();
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

  it("offers a way to fix a rejected key rather than a dead end", async () => {
    const onFixKey = vi.fn();
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(problem(403, "unauthenticated"))));

    await renderWellCard(host, API10, { ...callbacks, onFixKey });
    host.querySelector<HTMLButtonElement>(".gw-error-key")?.click();

    expect(onFixKey).toHaveBeenCalledOnce();
  });

  it("links errors to a path that resolves on this deployment, not to a dead host", async () => {
    // problem.type is https://glasswell.rpx.sh/v1/errors/{code}; that host does not resolve.
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(problem(404, "not_found"))));

    await renderWellCard(host, API10, callbacks);
    const link = host.querySelector("a") as HTMLAnchorElement;

    expect(link.getAttribute("href")).toBe("/v1/errors/not_found");
    expect(link.textContent).toContain("not_found");
    expect(link.textContent).not.toContain("https://");
  });
});

function problem(status: number, code: string): Response {
  return new Response(
    JSON.stringify({
      type: `https://glasswell.rpx.sh/v1/errors/${code}`,
      title: code === "not_found" ? "Not found" : "Not authenticated",
      status,
    }),
    { status, headers: { "content-type": "application/problem+json" } },
  );
}
