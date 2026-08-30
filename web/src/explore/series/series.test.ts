// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("uplot", () => ({
  default: class {
    over = document.createElement("div");
    setSize(): void {}
    destroy(): void {}
  },
}));

const { EXPLAIN_EVENT } = await import("../../chrome/handle.ts");
const { productionSeries, renderSeriesPanel } = await import("./series.ts");
const { pooledProductionEnvelope, productionEnvelope, wellsEnvelope } = await import(
  "../fixtures.ts"
);

type Envelope = Parameters<typeof renderSeriesPanel>[1]["envelope"];

let host: HTMLElement;

beforeEach(() => {
  document.body.innerHTML = "";
  host = document.createElement("div");
  document.body.appendChild(host);
});

describe("recognising a series payload", () => {
  it("takes the sidecar series a well's production is served as", () => {
    const series = productionSeries(productionEnvelope.data);
    expect(series?.streams).toEqual(["oil", "gas", "water"]);
    expect(series?.series.pm.length).toBeGreaterThan(0);
  });

  it("refuses a pooled response, whose series sit one level down and are not this shape", () => {
    expect(productionSeries(pooledProductionEnvelope.data)).toBeNull();
  });

  it("refuses a plain collection, which has no axis to draw against", () => {
    expect(productionSeries(wellsEnvelope.data)).toBeNull();
  });

  it("refuses anything that is not an object", () => {
    expect(productionSeries(null)).toBeNull();
    expect(productionSeries("/series")).toBeNull();
    expect(productionSeries([{ series: { pm: [] } }])).toBeNull();
  });
});

describe("the panel the crossing lands on", () => {
  it("draws the series the request returned, at the panel's own width", () => {
    expect(renderSeriesPanel(host, { envelope: productionEnvelope as unknown as Envelope })).toBe(
      true,
    );
    expect(host.querySelector(".gw-explore-series")).not.toBeNull();
    expect(host.querySelector(".gw-chart-plot")).not.toBeNull();
    const months = (productionEnvelope.data.series.pm as string[]).length;
    expect(host.querySelector(".gw-state-row")?.querySelectorAll(".gw-state-mark").length).toBe(
      months,
    );
  });

  it("draws everything it was handed, because the facets above it are the window", () => {
    renderSeriesPanel(host, { envelope: productionEnvelope as unknown as Envelope });
    expect(host.querySelector(".gw-window-control")).toBeNull();
    expect(host.querySelector(".gw-window-note")?.textContent).toContain("returned by this request");
  });

  it("names the facets as the way to narrow it, rather than implying it cannot be", () => {
    renderSeriesPanel(host, { envelope: productionEnvelope as unknown as Envelope });
    const note = host.querySelector(".gw-explore-series-note")?.textContent ?? "";
    expect(note).toContain("from");
    expect(note).toContain("to");
    expect(note).toContain("stream");
  });

  it("routes a handle to the lineage drawer the rest of the app already opens", () => {
    const seen: string[] = [];
    document.addEventListener(EXPLAIN_EVENT, (event) => {
      seen.push((event as CustomEvent<{ handle: string }>).detail.handle);
    });
    renderSeriesPanel(host, { envelope: productionEnvelope as unknown as Envelope });
    const handle = host.querySelector<HTMLButtonElement>(".gw-readout-row button.gw-handle");
    handle?.click();
    expect(seen).toHaveLength(1);
    expect(seen[0]).toContain("#");
  });

  it("renders nothing at all for a response that is not a series", () => {
    expect(renderSeriesPanel(host, { envelope: wellsEnvelope as unknown as Envelope })).toBe(false);
    expect(host.children).toHaveLength(0);
  });

  it("says a window returned nothing rather than drawing an empty axis", () => {
    // `?from=2027-01` on a well whose record ends in 2026 is served as an empty series. It is
    // a fact about the window the reader set, not about the well.
    const empty = {
      ...productionEnvelope,
      data: { ...productionEnvelope.data, streams: [], series: { pm: [] } },
    };
    expect(renderSeriesPanel(host, { envelope: empty as unknown as Envelope })).toBe(true);
    expect(host.querySelector(".gw-chart-plot")).toBeNull();
    expect(host.querySelector(".gw-explore-series")?.textContent).toContain(
      "No production months",
    );
  });

  it("carries the 390 refusal in the page, so it is absent rather than hidden", () => {
    renderSeriesPanel(host, { envelope: productionEnvelope as unknown as Envelope });
    const narrow = host.querySelector(".gw-explore-series-narrow");
    expect(narrow?.textContent).toContain("The well card draws the same series");
  });
});
