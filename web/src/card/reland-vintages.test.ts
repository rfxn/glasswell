// @vitest-environment happy-dom
//
// H-34, from the p57 sentinel and seen on screen by the visual gate: the one disclosure in the
// card whose summary is written from the served figures is the one the re-land controls change,
// so it was the one the re-land did not re-open. `card.test.ts` cannot see it — it mocks
// `chart/chart.ts`, and every summary that survives that mock is a static string. This file
// mocks `uplot` only, exactly as `chart/chart.test.ts` does, so the real vintages disclosure is
// rendered by the real chart into the real card.
import { beforeEach, describe, expect, it, vi } from "vitest";

// uPlot draws to a 2d context happy-dom does not provide; the frame is what matters here.
vi.mock("uplot", () => ({
  default: class {
    over = document.createElement("div");
    setSize(): void {}
    destroy(): void {}
  },
}));
vi.mock("../bus.ts", () => ({ selectWell: vi.fn() }));

const { renderWellCard } = await import("./card.ts");
const { resetSections } = await import("./sections.ts");
const {
  API10,
  completionContextEnvelope,
  cumulativesEnvelope,
  neighborEnvelope,
  productionEnvelope,
  stubFetch,
  wellEnvelope,
} = await import("../test/fixtures.ts");

const callbacks = { onExplain: vi.fn(), onClose: vi.fn() };
let host: HTMLElement;

/** The same series read at a second capture, which is what `Read at …` and `Widen` produce. */
function restated(): unknown {
  const body = structuredClone(productionEnvelope) as {
    data: { series: Record<string, unknown> };
  };
  const vintages = body.data.series["oil_bbl_report_vintage"] as string[];
  body.data.series["oil_bbl_report_vintage"] = vintages.map((vintage, index) =>
    index === 0 ? "2026-06-01" : vintage,
  );
  return body;
}

function serve(production: unknown): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      stubFetch({
        [`/v1/wells/${API10}/completions`]: completionContextEnvelope,
        [`/v1/wells/${API10}/cumulatives`]: cumulativesEnvelope,
        [`/v1/wells/${API10}/neighbors`]: neighborEnvelope,
        [`/v1/wells/${API10}/production`]: production,
        [`/v1/wells/${API10}`]: wellEnvelope,
      }),
    ),
  );
}

const vintages = (): HTMLDetailsElement | null =>
  host.querySelector<HTMLDetailsElement>("details.gw-vintages");

beforeEach(() => {
  window.history.replaceState(null, "", "/");
  resetSections();
  document.body.innerHTML = "";
  host = document.createElement("aside");
  document.body.appendChild(host);
  serve(productionEnvelope);
});

describe("the disclosure whose summary the figures write", () => {
  it("is the one the chart renders, and its summary does name the served vintages", async () => {
    await renderWellCard(host, API10, callbacks);

    const summary = vintages()?.querySelector("summary")?.textContent ?? "";
    expect(summary).toContain("Report vintages");
    expect(summary).toContain("2026-08-20");
  });

  it("re-opens across a re-land that changes the vintages its summary names", async () => {
    await renderWellCard(host, API10, callbacks);
    const before = vintages();
    expect(before, "the chart rendered no vintages disclosure").not.toBeNull();
    before!.open = true;
    const said = before!.querySelector("summary")?.textContent;

    serve(restated());
    await renderWellCard(host, API10, callbacks);

    const after = vintages();
    expect(after?.querySelector("summary")?.textContent).not.toBe(said);
    expect(after?.open, "the disclosure the reader had open closed on the re-land").toBe(true);
  });

  it("keys a warning note on the code it carries, not on the sentence it prints", async () => {
    // `warningNotes` already stamps `data-code`; the key reads it, so a note whose summary
    // gains a `×2` count or whose wording is re-served keeps its identity.
    await renderWellCard(host, API10, callbacks);

    const note = host.querySelector<HTMLDetailsElement>(".gw-card-notes details[data-code]");
    expect(note, "the fixture serves no coded warning note").not.toBeNull();
    note!.open = true;

    await renderWellCard(host, API10, callbacks);

    expect(host.querySelector<HTMLDetailsElement>(".gw-card-notes details")?.open).toBe(true);
  });
});
