// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ChartSeries } from "../chart/series.ts";
import { statusColour } from "../map/status.ts";

const renderChart = vi.fn<(container: HTMLElement, chart: ChartSeries) => void>();
const selectWell = vi.fn<(api10: string | null, source: string) => void>();
vi.mock("../chart/chart.ts", () => ({
  renderChart: (container: HTMLElement, chart: ChartSeries) => renderChart(container, chart),
}));
vi.mock("../bus.ts", () => ({
  selectWell: (api10: string | null, source: string) => selectWell(api10, source),
}));

const { renderWellCard } = await import("./card.ts");
const {
  API10,
  LENGTH_HANDLE,
  OIL_HANDLE,
  completionContextEnvelope,
  cumulativesEnvelope,
  neighborEnvelope,
  productionEnvelope,
  stubFetch,
  wellEnvelope,
} = await import("../test/fixtures.ts");

const callbacks = { onExplain: vi.fn(), onClose: vi.fn() };
let host: HTMLElement;

beforeEach(() => {
  window.history.replaceState(null, "", "/");
  document.body.innerHTML = "";
  host = document.createElement("aside");
  document.body.appendChild(host);
  renderChart.mockClear();
  selectWell.mockClear();
  vi.stubGlobal(
    "fetch",
    vi.fn(
      stubFetch({
        [`/v1/wells/${API10}/completions`]: completionContextEnvelope,
        [`/v1/wells/${API10}/cumulatives`]: cumulativesEnvelope,
        [`/v1/wells/${API10}/neighbors`]: neighborEnvelope,
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
  const RULE = "/v1/conformance/cr_tx_allocation_scope_1";

  function pendingWell(warnings: { code: string; detail: string; pointer: string }[]) {
    return {
      ...wellEnvelope,
      links: { ...wellEnvelope.links, reporting_rule: RULE },
      meta: { ...wellEnvelope.meta, warnings },
    };
  }

  it("says production is pending only while no allocation is served", async () => {
    // The disclosure is a served fact with two clocks behind it, and it is true until the
    // allocation is published. What must not happen is a card showing both.
    const pending = pendingWell([
      {
        code: "production_pending_allocation",
        detail:
          "This well's regulator reports production at the lease" +
          " (cr_tx_allocation_scope_1), so no well-level series has been observed.",
        pointer: "/production",
      },
    ]);
    // Only the well route is stubbed: a production request would 404 through stubFetch and
    // surface as an error panel, which is a failure the spy could not have shown — it matched
    // the well route first and was never reached.
    vi.stubGlobal("fetch", vi.fn(stubFetch({ [`/v1/wells/${API10}`]: pending })));

    await renderWellCard(host, API10, callbacks);

    const panel = host.querySelector<HTMLElement>("[data-state='production_pending_allocation']");
    expect(panel?.querySelector(".gw-frame-title")?.textContent).toBe(
      "Production pending allocation",
    );
    expect(panel?.textContent).toContain("cr_tx_allocation_scope_1");
    expect(panel?.querySelector(".gw-pending-rule")?.getAttribute("href")).toBe(RULE);
    expect(host.textContent).not.toContain("No production has been reported");
    expect(renderChart).not.toHaveBeenCalled();
  });

  it("draws the chart instead the moment the warning stops arriving", async () => {
    // The successor rule carries the third spec key, so the API stops emitting the warning.
    // Nothing in the card decides this: a jurisdiction test in the client would be a mapping
    // decision living in code, which is what R8 refuses.
    await renderWellCard(host, API10, callbacks);

    expect(host.querySelector("[data-state='production_pending_allocation']")).toBeNull();
    expect(renderChart).toHaveBeenCalled();
  });

  it("says it once: no raw warning line above the panel that renders the same sentence", async () => {
    const pending = pendingWell([
      {
        code: "production_pending_allocation",
        detail: "reports production at the lease (cr_tx_allocation_scope_1)",
        pointer: "/production",
      },
    ]);
    vi.stubGlobal("fetch", vi.fn(stubFetch({ [`/v1/wells/${API10}`]: pending })));

    await renderWellCard(host, API10, callbacks);

    for (const warning of host.querySelectorAll(".gw-warning")) {
      expect(warning.textContent).not.toContain("production_pending_allocation");
    }
    expect(host.textContent?.match(/pending allocation/gi)?.length).toBe(1);
  });

  it("still renders warnings that have no panel of their own", async () => {
    const both = pendingWell([
      { code: "production_pending_allocation", detail: "pending", pointer: "/production" },
      { code: "geometry_not_promoted", detail: "one segment held back", pointer: "/geometry" },
    ]);
    vi.stubGlobal("fetch", vi.fn(stubFetch({ [`/v1/wells/${API10}`]: both })));

    await renderWellCard(host, API10, callbacks);

    expect(host.textContent).toContain("geometry_not_promoted");
    expect(host.querySelector("[data-state='production_pending_allocation']")).not.toBeNull();
  });
});

describe("well card", () => {
  it("pins the well, completion, cumulative and production requests to the route as_of", async () => {
    const requested = vi.fn(
      stubFetch({
        [`/v1/wells/${API10}/completions`]: completionContextEnvelope,
        [`/v1/wells/${API10}/cumulatives`]: cumulativesEnvelope,
        [`/v1/wells/${API10}/neighbors`]: neighborEnvelope,
        [`/v1/wells/${API10}/production`]: productionEnvelope,
        [`/v1/wells/${API10}`]: wellEnvelope,
      }),
    );
    window.history.replaceState(null, "", `/?well=${API10}&as_of=2026-07-01`);
    vi.stubGlobal("fetch", requested);

    await renderWellCard(host, API10, callbacks);

    expect(requested.mock.calls.map(([input]) => String(input)).sort()).toEqual(
      [
        `/v1/wells/${API10}?as_of=2026-07-01`,
        `/v1/wells/${API10}/completions?as_of=2026-07-01`,
        `/v1/wells/${API10}/cumulatives?as_of=2026-07-01`,
        `/v1/wells/${API10}/neighbors?as_of=2026-07-01&limit=5`,
        `/v1/wells/${API10}/production?as_of=2026-07-01`,
      ].sort(),
    );
  });

  it("renders the header the operator would recognise", async () => {
    await renderWellCard(host, API10, callbacks);
    expect(host.querySelector("h2")?.textContent).toBe("Mandaree 50-2008H");
    const text = host.textContent ?? "";
    expect(text).toContain("EOG RESOURCES, INC.");
    expect(text).toContain("149N-94W-20");
  });

  it("renders lateral length through gw-figure, with its unit and its handle", async () => {
    await renderWellCard(host, API10, callbacks);
    const figure = host.querySelector(`gw-figure[handle="${LENGTH_HANDLE}"]`);
    expect(figure?.getAttribute("unit")).toBe("ft");
    expect(figure?.getAttribute("handle")).toBe(LENGTH_HANDLE);
    expect(figure?.textContent).toContain("15,065.44 ft");
  });

  it("renders physical neighbours as current-only proximity, not model analogs", async () => {
    await renderWellCard(host, API10, callbacks);

    const frame = host.querySelector<HTMLElement>(".gw-neighbor-context");
    const links = frame?.querySelectorAll<HTMLAnchorElement>(".gw-neighbor-link");
    expect(frame?.querySelector(".gw-frame-body")?.getAttribute("data-state")).toBe(
      "populated",
    );
    expect(frame?.textContent).toContain("Proximity, not analogs · current geometry");
    expect(links).toHaveLength(2);
    expect(links?.[0]?.getAttribute("href")).toBe("/?well=3305310998");
    expect(frame?.querySelector("gw-figure")?.textContent).toContain("1,320.25 ft");

    links?.[0]?.click();
    expect(selectWell).toHaveBeenCalledWith("3305310998", "card");
  });

  it("distinguishes no eligible neighbours from an unusable response", async () => {
    const empty = {
      ...neighborEnvelope,
      data: {
        ...neighborEnvelope.data,
        neighbors: [],
        coverage: {
          ...neighborEnvelope.data.coverage,
          eligible: { ...neighborEnvelope.data.coverage.eligible, value: "0" },
          returned: { ...neighborEnvelope.data.coverage.returned, value: "0" },
        },
      },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(
        stubFetch({
          [`/v1/wells/${API10}/completions`]: completionContextEnvelope,
          [`/v1/wells/${API10}/neighbors`]: empty,
          [`/v1/wells/${API10}/production`]: productionEnvelope,
          [`/v1/wells/${API10}`]: wellEnvelope,
        }),
      ),
    );

    await renderWellCard(host, API10, callbacks);

    const body = host.querySelector<HTMLElement>(".gw-neighbor-context .gw-frame-body");
    expect(body?.dataset["state"]).toBe("empty");
    expect(body?.textContent).toContain("None inside the radius");
    expect(body?.textContent).not.toContain("unavailable for this well");
  });

  it("keeps the rest of the card usable when neighbours are unavailable", async () => {
    const normal = stubFetch({
      [`/v1/wells/${API10}/completions`]: completionContextEnvelope,
      [`/v1/wells/${API10}/production`]: productionEnvelope,
      [`/v1/wells/${API10}`]: wellEnvelope,
    });
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        if (String(input).startsWith(`/v1/wells/${API10}/neighbors`)) {
          return Promise.resolve(problem(422, "current_only_geometry"));
        }
        return normal(input);
      }),
    );

    await renderWellCard(host, API10, callbacks);

    const body = host.querySelector<HTMLElement>(".gw-neighbor-context .gw-frame-body");
    expect(body?.dataset["state"]).toBe("unavailable");
    // The refusal the endpoint named, not the status family it shares with every other 422.
    expect(body?.textContent).toContain("Current geometry only");
    expect(renderChart).toHaveBeenCalledOnce();
  });

  it("opens the drawer from the figure's handle affordance", async () => {
    await renderWellCard(host, API10, callbacks);
    const button = host.querySelector<HTMLButtonElement>(
      `gw-figure[handle="${LENGTH_HANDLE}"] button`,
    );
    button?.click();
    expect(callbacks.onExplain).toHaveBeenCalledWith(LENGTH_HANDLE);
  });

  it("renders the cumulative row as three figures, each with its own handle", async () => {
    await renderWellCard(host, API10, callbacks);

    const frame = host.querySelector<HTMLElement>(".gw-well-cumulatives");
    expect(frame?.querySelector(".gw-frame-body")?.getAttribute("data-state")).toBe("populated");

    const cells = [...(frame?.querySelectorAll(".gw-cumulative-cell") ?? [])];
    expect(cells.map((cell) => cell.querySelector("dt")?.textContent)).toEqual([
      "Oil",
      "Gas",
      "Water",
    ]);
    expect(cells.map((cell) => cell.querySelector(".gw-figure-value")?.textContent)).toEqual([
      "21,000 bbl",
      "50,400 mcf",
      "12,000 bbl",
    ]);
    expect(
      cells.map((cell) => cell.querySelector("gw-figure")?.getAttribute("handle")),
    ).toEqual([
      "drv_ljbmyy7avces77lwdnfa#api10=3305310451&col=oil_bbl",
      "drv_ljbmyy7avces77lwdnfa#api10=3305310451&col=gas_mcf",
      "drv_ljbmyy7avces77lwdnfa#api10=3305310451&col=water_bbl",
    ]);
  });

  it("rounds a cumulative to whole units while the lateral length keeps its decimals", async () => {
    await renderWellCard(host, API10, callbacks);

    const cumulative = [
      ...host.querySelectorAll(".gw-well-cumulatives .gw-figure-value"),
    ].map((value) => value.textContent ?? "");
    expect(cumulative).toHaveLength(3);
    // The precision is per call, not global: no cumulative cell carries a fractional part.
    for (const text of cumulative) expect(text).not.toMatch(/\d\.\d/);
    expect(cumulative).toEqual(["21,000 bbl", "50,400 mcf", "12,000 bbl"]);

    // Same card, same element, untouched: two decimals are meaningful for a measured length.
    const lateral = host.querySelector(
      `gw-figure[handle="${LENGTH_HANDLE}"] .gw-figure-value`,
    )?.textContent;
    expect(lateral).toMatch(/\d\.\d/);
    expect(lateral).toBe("15,065.44 ft");
  });

  it("resolves a cumulative figure's handle through the explain affordance", async () => {
    await renderWellCard(host, API10, callbacks);

    callbacks.onExplain.mockClear();
    host
      .querySelector<HTMLButtonElement>(
        ".gw-well-cumulatives gw-figure[handle*='col=gas_mcf'] button",
      )
      ?.click();

    expect(callbacks.onExplain).toHaveBeenCalledWith(
      "drv_ljbmyy7avces77lwdnfa#api10=3305310451&col=gas_mcf",
    );
  });

  it("states the window, the months admitted and the snapshot beside the totals", async () => {
    await renderWellCard(host, API10, callbacks);

    const scope = host.querySelector<HTMLElement>(".gw-well-cumulatives .gw-scope");
    // 5-6 of 7, because the water stream carries one more withheld month than oil and gas:
    // a single admitted count would be wrong for two of the three streams. The clause after
    // it is what stops a rolling window being read as a life: where a regulator publishes
    // only recent months, the total is over those months and the card has to say so.
    expect(scope?.textContent).toBe(
      "Dec 2025 – Jun 2026 · 5–6 of 7 months admitted ·" +
        " over the months filed, not the well's life · snapshot 2026-08-01",
    );
  });

  // gate-v075 defect 4: the payload carries basis "oil+condensate" on the oil total and the
  // card stated it only in the chart frame, so the CUMULATIVE row showed a liquids number
  // without its policy. CLAUDE.md: state the policy wherever the number appears.
  it("states each cumulative's basis beside the figure, so oil says oil+condensate", async () => {
    await renderWellCard(host, API10, callbacks);

    const cells = [...host.querySelectorAll(".gw-well-cumulatives .gw-cumulative-cell")];
    const basisOf = (label: string): string | null => {
      const cell = cells.find((node) => node.querySelector("dt")?.textContent?.startsWith(label));
      return cell?.querySelector(".gw-cumulative-basis")?.textContent ?? null;
    };

    expect(basisOf("Oil")).toBe("oil+condensate");
    expect(basisOf("Water")).toBe("water");
    // Gas carries no basis in the payload, and an empty chip would be a naked qualifier.
    expect(basisOf("Gas")).toBeNull();
  });

  // gate-v075 defect 2: at 1024 and 390 the line wrapped at the vintage's own hyphen and read
  // "snapshot 2026-" / "08-23", which scans as a truncated year at the end of a line.
  it("keeps the snapshot vintage on one line without changing what the line says", async () => {
    await renderWellCard(host, API10, callbacks);

    const scope = host.querySelector<HTMLElement>(".gw-well-cumulatives .gw-scope");
    const held = scope?.querySelector<HTMLElement>(".gw-nowrap");

    expect(held?.textContent).toBe("snapshot 2026-08-01");
    // The date is a real hyphen still, so the line reads and copies exactly as before.
    expect(scope?.textContent).toContain("snapshot 2026-08-01");
  });

  it("renders a withheld stream as withheld and a no-report stream as no report, never as 0", async () => {
    const classes = {
      ...cumulativesEnvelope,
      data: {
        ...cumulativesEnvelope.data,
        cumulative: {
          ...cumulativesEnvelope.data.cumulative,
          gas_mcf: null,
          water_bbl: null,
        },
        coverage: {
          ...cumulativesEnvelope.data.coverage,
          gas_mcf: {
            ...cumulativesEnvelope.data.coverage.gas_mcf,
            months_reported: 0,
            months_no_report: 0,
            months_withheld: 7,
          },
          water_bbl: {
            ...cumulativesEnvelope.data.coverage.water_bbl,
            months_reported: 0,
            months_no_report: 7,
            months_withheld: 0,
          },
        },
      },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(
        stubFetch({
          [`/v1/wells/${API10}/completions`]: completionContextEnvelope,
          [`/v1/wells/${API10}/cumulatives`]: classes,
          [`/v1/wells/${API10}/neighbors`]: neighborEnvelope,
          [`/v1/wells/${API10}/production`]: productionEnvelope,
          [`/v1/wells/${API10}`]: wellEnvelope,
        }),
      ),
    );

    await renderWellCard(host, API10, callbacks);

    const cells = [...host.querySelectorAll(".gw-well-cumulatives .gw-cumulative-cell")];
    expect(
      cells.map((cell) => cell.querySelector(".gw-figure-value, .gw-absent")?.textContent),
    ).toEqual(["21,000 bbl", "unavailable: withheld", "unavailable: no report"]);
    // The whole point: an absent month is never summed as a zero.
    expect(cells[1]?.textContent).not.toMatch(/\b0\b/);
    expect(cells[2]?.textContent).not.toMatch(/\b0\b/);
    // Nothing is collapsed away — the four counts stay reachable on the cell.
    expect(cells[1]?.getAttribute("title")).toBe(
      "0 reported · 0 reported zero · 0 no report · 7 withheld of 7 months",
    );
  });

  it("says nothing was ever filed rather than showing a zero cumulative", async () => {
    const never = {
      ...cumulativesEnvelope,
      data: {
        ...cumulativesEnvelope.data,
        coverage_outcome: "never_reported",
        cumulative: null,
      },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(
        stubFetch({
          [`/v1/wells/${API10}/completions`]: completionContextEnvelope,
          [`/v1/wells/${API10}/cumulatives`]: never,
          [`/v1/wells/${API10}/neighbors`]: neighborEnvelope,
          [`/v1/wells/${API10}/production`]: productionEnvelope,
          [`/v1/wells/${API10}`]: wellEnvelope,
        }),
      ),
    );

    await renderWellCard(host, API10, callbacks);

    const frame = host.querySelector<HTMLElement>(".gw-well-cumulatives");
    expect(frame?.querySelector(".gw-frame-body")?.getAttribute("data-state")).toBe("empty");
    expect(frame?.textContent).toContain("No cumulative: nothing ever filed.");
    expect(frame?.querySelector("gw-figure")).toBeNull();
    expect(frame?.textContent).not.toMatch(/\b0 bbl\b/);
  });

  it("omits the section entirely for a well the mart does not cover", async () => {
    const unlinked = {
      ...wellEnvelope,
      links: Object.fromEntries(
        Object.entries(wellEnvelope.links).filter(([key]) => key !== "cumulatives"),
      ),
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(
        stubFetch({
          [`/v1/wells/${API10}/completions`]: completionContextEnvelope,
          [`/v1/wells/${API10}/neighbors`]: neighborEnvelope,
          [`/v1/wells/${API10}/production`]: productionEnvelope,
          [`/v1/wells/${API10}`]: unlinked,
        }),
      ),
    );

    await renderWellCard(host, API10, callbacks);

    // Not an empty section: "no cumulative" would say the well produced nothing, when the
    // fact is that this jurisdiction is not summed here at all.
    expect(host.querySelector(".gw-well-cumulatives")).toBeNull();
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

    const frame = host.querySelector(".gw-production-chart") as HTMLElement;
    const title = frame.querySelector(".gw-frame-title") as HTMLElement;
    // §2.6's crossing sits in this header too, so the label is the title's own text and not
    // everything the header carries.
    expect(title.firstElementChild?.textContent).toBe("Monthly production");
    expect(title.querySelector('[data-crossing="open-this-series"]')).not.toBeNull();
    expect(renderChart.mock.calls[0]?.[0]).toBe(frame.querySelector(".gw-frame-body"));
  });

  it("keeps the derivation disclosure outside the plot the chart redraws", async () => {
    // The chart redraws its own host whenever the span or the theme changes. A warning
    // appended into that host went with it, and that warning is the `series_spans_derivations`
    // line naming the derivations behind the column — R8's disclosure, not a decoration.
    await renderWellCard(host, API10, callbacks);

    const frame = host.querySelector(".gw-production-chart") as HTMLElement;
    const notes = frame.querySelector(".gw-chart-notes") as HTMLElement;
    expect(notes.textContent).toContain("series_spans_derivations");
    expect(frame.querySelector(".gw-frame-body .gw-warning")).toBeNull();
    // And it is inside the body that scrolls, so it stays reachable at every breakpoint.
    expect(host.querySelector(".gw-panel-body .gw-chart-notes")).toBeTruthy();
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

  it("carries the status in the head as the mark the map painted, with the code as filed", async () => {
    await renderWellCard(host, API10, callbacks);

    const chip = host.querySelector<HTMLElement>(".gw-panel-head .gw-card-status")!;
    expect(chip.dataset["status"]).toBe("active");
    expect(chip.textContent).toContain("Active");
    // The mapping is readable rather than hidden: the class and the code that produced it.
    expect(chip.querySelector(".gw-card-status-reported")?.textContent).toBe("filed A");
    // The map's own glyph grammar, not a second dialect of it.
    expect(chip.querySelector("svg circle")?.getAttribute("fill")).toBe(statusColour("active"));
  });

  it("reads the well in bands rather than as one flat list where a CRS outranks the operator", async () => {
    await renderWellCard(host, API10, callbacks);

    const bands = [...host.querySelectorAll<HTMLElement>(".gw-facts-band")];
    expect(bands.map((band) => band.querySelector(".gw-frame-title")?.textContent)).toEqual([
      "Location",
      "Drilling",
      "Record",
    ]);
    // Every band that renders carries rows; a heading over nothing is dropped, not left standing.
    for (const band of bands) expect(band.querySelectorAll("dt").length).toBeGreaterThan(0);
    const drilling = bands[1] as HTMLElement;
    expect([...drilling.querySelectorAll("dt")].map((dt) => dt.textContent)).toContain("Lateral length");
    expect(bands[2]?.textContent).toContain("CRS");
    // The operator is identity, so it reads in the header and never as a band of its own.
    expect(host.querySelector(".gw-panel-head .gw-card-operator")?.textContent).toContain(
      "EOG RESOURCES",
    );
  });

  it("drops a band whose every field is absent instead of heading an empty list", async () => {
    const bare = structuredClone(wellEnvelope);
    for (const field of ["basin", "county_code_at_permit", "land_unit_label", "surface_point"]) {
      (bare.data as Record<string, unknown>)[field] = null;
    }
    vi.stubGlobal("fetch", vi.fn(stubFetch({ [`/v1/wells/${API10}`]: bare })));
    await renderWellCard(host, API10, callbacks);

    const titles = [...host.querySelectorAll(".gw-facts-band .gw-frame-title")].map((n) => n.textContent);
    expect(titles).not.toContain("Location");
    expect(titles).toContain("Record");
  });

  it("marks an absent value so a skimmed column separates it from a measured one", async () => {
    await renderWellCard(host, API10, callbacks);

    // The neighbour rows used to print the raw enum token, so "alias unavailable" stood in the
    // Formation cell looking exactly like a formation name beside "bakken".
    const rows = [...host.querySelectorAll<HTMLElement>(".gw-neighbor-context .gw-context-list > li")];
    const absent = rows[1]!.querySelector<HTMLElement>(".gw-absent")!;
    expect(absent).toBeTruthy();
    expect(absent.textContent).toBe("unavailable: no registered alias");
    expect(rows[0]!.querySelector(".gw-absent")).toBeNull();
    // DR-H24: the mark is what a reader sees without reading. A figure never wears it.
    expect(host.querySelector("gw-figure.gw-absent")).toBeNull();
  });

  it("says so when the API refuses the request instead of rendering an empty card", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(
            JSON.stringify({
              type: "https://glasswell.example/v1/errors/unauthenticated",
              title: "Forbidden",
              status: 403,
            }),
            { status: 403, headers: { "content-type": "application/problem+json" } },
          ),
        ),
      ),
    );
    await renderWellCard(host, API10, callbacks);
    expect(host.textContent).toContain("no live session");
  });

  it("offers a way back into a session rather than a dead end", async () => {
    const onSignIn = vi.fn();
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(problem(403, "unauthenticated"))));

    await renderWellCard(host, API10, { ...callbacks, onSignIn });
    host.querySelector<HTMLButtonElement>(".gw-error-key")?.click();

    expect(onSignIn).toHaveBeenCalledOnce();
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

describe("completion and formation context", () => {
  it("renders source events and reported pool mappings without design or top claims", async () => {
    await renderWellCard(host, API10, callbacks);

    const frame = host.querySelector(".gw-completion-context") as HTMLElement;
    const body = frame.querySelector<HTMLElement>(".gw-frame-body");
    expect(frame.querySelector(".gw-frame-title")?.textContent).toBe("Completions & formations");
    expect(body?.dataset["state"]).toBe("populated");
    expect(body?.getAttribute("aria-busy")).toBe("false");
    const groups = frame.querySelectorAll<HTMLElement>(".gw-context-group");
    const eventFacts = factsOf(groups[0] as HTMLElement);
    const formationFacts = factsOf(groups[1] as HTMLElement);
    expect(eventFacts).toEqual({
      "Event": "Hydraulic frac job end",
      "Job start": "2025-04-11",
      "Job end": "2025-04-24",
      "Source": "fracfocus_csv · report 2026-08-20",
    });
    expect(frame.querySelector("time[datetime='2025-04-11']")?.textContent).toBe("2025-04-11");
    expect(frame.querySelector("time[datetime='2025-04-24']")?.textContent).toBe("2025-04-24");
    expect(formationFacts).toEqual({
      "Pool entity": "3305310451:BAKKEN",
      "Reported pool": "BAKKEN",
      "Canonical formation": "bakken",
      "Formation group": "bakken",
      "First observed month": "2025-10-01",
      "Last observed month": "2026-03-01",
      "Source": "nd_mpr_xlsx · report 2026-08-20",
    });
    const designFacts = factsOf(groups[2] as HTMLElement);
    expect(designFacts).toEqual({
      "Disclosure": "ff-3305310451-20250424",
      "Base fluid": "5,917,362.00 gal",
      "Lateral": "9,862.27 ft",
      "Fluid intensity": "600.00 gal/ft",
      "Source": "fracfocus_csv · report 2026-08-20",
    });
    expect(frame.textContent).toContain(
      "Design as disclosed, measured against computed geometry · Formation tops not served",
    );
    expect(frame.textContent).not.toMatch(/proppant|formation depth/i);

    callbacks.onExplain.mockClear();
    frame.querySelector<HTMLButtonElement>("button[data-handle*='col=completion_date']")?.click();
    expect(callbacks.onExplain).toHaveBeenCalledWith(
      "drv_context_event#disclosure_id=ff-3305310451-20250424&col=completion_date",
    );
    callbacks.onExplain.mockClear();
    frame.querySelector<HTMLButtonElement>("button[data-handle*='col=pool_reported']")?.click();
    expect(callbacks.onExplain).toHaveBeenCalledWith(
      "drv_context_pool#completion_key=3305310451:BAKKEN&col=pool_reported&pm=2026-03",
    );
  });

  it("does not substitute the frac job end when its start date is unavailable", async () => {
    const contextEvent = completionContextEnvelope.data.events[0]!;
    const noStart = {
      ...completionContextEnvelope,
      data: {
        ...completionContextEnvelope.data,
        events: [
          {
            ...contextEvent,
            job_start_date: null,
            _lineage: {
              completion_date: contextEvent._lineage.completion_date,
            },
          },
        ],
      },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(
        stubFetch({
          [`/v1/wells/${API10}/completions`]: noStart,
          [`/v1/wells/${API10}/production`]: productionEnvelope,
          [`/v1/wells/${API10}`]: wellEnvelope,
        }),
      ),
    );

    await renderWellCard(host, API10, callbacks);

    const event = host.querySelector(".gw-context-group") as HTMLElement;
    expect(factsOf(event)["Job start"]).toBe("unavailable");
    expect(factsOf(event)["Job end"]).toBe("2025-04-24");
    expect(event.querySelectorAll("time")).toHaveLength(1);
    expect(event.querySelectorAll("button[data-handle]")).toHaveLength(1);
  });

  it("keeps pool and alias absence distinct when only completion-pool observations exist", async () => {
    const mapped = completionContextEnvelope.data.pools[0];
    const partial = {
      ...completionContextEnvelope,
      data: {
        ...completionContextEnvelope.data,
        events: [],
        pools: [
          {
            ...mapped,
            pool_reported: null,
            formation: null,
            formation_group: null,
            formation_null_semantics: "pool_not_reported",
          },
          {
            ...mapped,
            completion_key: "3305310451:UNKNOWN",
            well_completion_pool: "3305310451:UNKNOWN",
            pool_reported: "UNKNOWN",
            formation: null,
            formation_group: null,
            formation_null_semantics: "alias_unavailable",
          },
        ],
      },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(
        stubFetch({
          [`/v1/wells/${API10}/completions`]: partial,
          [`/v1/wells/${API10}/production`]: productionEnvelope,
          [`/v1/wells/${API10}`]: wellEnvelope,
        }),
      ),
    );

    await renderWellCard(host, API10, callbacks);

    const frame = host.querySelector(".gw-completion-context") as HTMLElement;
    expect(frame.textContent).toContain("None reported");
    const pools = frame.querySelectorAll<HTMLElement>(".gw-context-list > li");
    expect(factsOf(pools[0] as HTMLElement)).toEqual({
      "Pool entity": "3305310451:BAKKEN",
      "Reported pool": "unavailable: pool not reported",
      "Canonical formation": "unavailable: pool not reported",
      "Formation group": "unavailable: pool not reported",
      "First observed month": "2025-10-01",
      "Last observed month": "2026-03-01",
      "Source": "nd_mpr_xlsx · report 2026-08-20",
    });
    expect(factsOf(pools[1] as HTMLElement)).toEqual({
      "Pool entity": "3305310451:UNKNOWN",
      "Reported pool": "UNKNOWN",
      "Canonical formation": "unavailable: no registered alias",
      "Formation group": "unavailable: no registered alias",
      "First observed month": "2025-10-01",
      "Last observed month": "2026-03-01",
      "Source": "nd_mpr_xlsx · report 2026-08-20",
    });
    expect(frame.textContent).not.toContain("Hydraulic frac job end");
  });

  it("renders a null intensity as its stated reason rather than as a zero", async () => {
    const withdrawn = {
      ...completionContextEnvelope,
      data: {
        ...completionContextEnvelope.data,
        design: {
          ...completionContextEnvelope.data.design,
          fluid_intensity: null,
          intensity_null_semantics: "lateral_length_implausible",
        },
      },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(
        stubFetch({
          [`/v1/wells/${API10}/completions`]: withdrawn,
          [`/v1/wells/${API10}/production`]: productionEnvelope,
          [`/v1/wells/${API10}`]: wellEnvelope,
        }),
      ),
    );

    await renderWellCard(host, API10, callbacks);

    const frame = host.querySelector(".gw-completion-context") as HTMLElement;
    const groups = frame.querySelectorAll<HTMLElement>(".gw-context-group");
    const designFacts = factsOf(groups[2] as HTMLElement);
    expect(designFacts["Fluid intensity"]).toBe(
      "unavailable \u2014 lateral too short to divide by",
    );
    expect(designFacts["Fluid intensity"]).not.toMatch(/\b0\b/);
  });

  it("keeps a withheld volume distinct from an undisclosed one on both design rows", async () => {
    const withheld = {
      ...completionContextEnvelope,
      data: {
        ...completionContextEnvelope.data,
        design: {
          ...completionContextEnvelope.data.design,
          base_water_volume: null,
          base_water_null_semantics: "withheld",
          fluid_intensity: null,
          intensity_null_semantics: "withheld",
        },
      },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(
        stubFetch({
          [`/v1/wells/${API10}/completions`]: withheld,
          [`/v1/wells/${API10}/production`]: productionEnvelope,
          [`/v1/wells/${API10}`]: wellEnvelope,
        }),
      ),
    );

    await renderWellCard(host, API10, callbacks);

    const frame = host.querySelector(".gw-completion-context") as HTMLElement;
    const designFacts = factsOf(frame.querySelectorAll<HTMLElement>(".gw-context-group")[2] as HTMLElement);
    expect(designFacts["Base fluid"]).toBe("unavailable \u2014 withheld by the regulator");
    expect(designFacts["Fluid intensity"]).toBe("unavailable \u2014 withheld by the regulator");
    expect(designFacts["Fluid intensity"]).not.toContain("no disclosed volume");
  });

  it("words an absent class identically on both design rows", async () => {
    const undisclosed = {
      ...completionContextEnvelope,
      data: {
        ...completionContextEnvelope.data,
        design: {
          ...completionContextEnvelope.data.design,
          base_water_volume: null,
          base_water_null_semantics: "no_report",
          fluid_intensity: null,
          intensity_null_semantics: "no_report",
        },
      },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(
        stubFetch({
          [`/v1/wells/${API10}/completions`]: undisclosed,
          [`/v1/wells/${API10}/production`]: productionEnvelope,
          [`/v1/wells/${API10}`]: wellEnvelope,
        }),
      ),
    );

    await renderWellCard(host, API10, callbacks);

    const frame = host.querySelector(".gw-completion-context") as HTMLElement;
    const designFacts = factsOf(
      frame.querySelectorAll<HTMLElement>(".gw-context-group")[2] as HTMLElement,
    );
    // One class, one string. Two wordings for one fact is drift waiting to become confusion,
    // and the volume is named so the sentence reads on the row that is it and the row that is
    // divided by it.
    expect(designFacts["Base fluid"]).toBe("unavailable \u2014 no disclosed volume");
    expect(designFacts["Fluid intensity"]).toBe(designFacts["Base fluid"]);
  });

  it("says a well carries no disclosure rather than showing an empty design row", async () => {
    const none = {
      ...completionContextEnvelope,
      data: {
        ...completionContextEnvelope.data,
        design: null,
        design_null_semantics: "no_report",
      },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(
        stubFetch({
          [`/v1/wells/${API10}/completions`]: none,
          [`/v1/wells/${API10}/production`]: productionEnvelope,
          [`/v1/wells/${API10}`]: wellEnvelope,
        }),
      ),
    );

    await renderWellCard(host, API10, callbacks);

    const frame = host.querySelector(".gw-completion-context") as HTMLElement;
    expect(frame.textContent).toContain("None disclosed");
    expect(frame.textContent).toContain(
      "No design disclosed: FracFocus is voluntary · Formation tops not served",
    );
    expect(frame.querySelector<HTMLElement>(".gw-frame-body")?.dataset["state"]).toBe(
      "populated",
    );
  });

  it("distinguishes an observed empty response from a failed request", async () => {
    const empty = {
      ...completionContextEnvelope,
      data: {
        ...completionContextEnvelope.data,
        design: null,
        design_null_semantics: "no_report",
        events: [],
        pools: [],
      },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(
        stubFetch({
          [`/v1/wells/${API10}/completions`]: empty,
          [`/v1/wells/${API10}/production`]: productionEnvelope,
          [`/v1/wells/${API10}`]: wellEnvelope,
        }),
      ),
    );

    await renderWellCard(host, API10, callbacks);

    const body = host.querySelector<HTMLElement>(".gw-completion-context .gw-frame-body");
    expect(body?.dataset["state"]).toBe("empty");
    expect(body?.textContent).toContain("No events, pools or design reported");
    expect(body?.textContent).not.toContain("could not be read");
  });

  it("shows source-history coverage warnings inside the context section", async () => {
    const partialHistory = {
      ...completionContextEnvelope,
      meta: {
        ...completionContextEnvelope.meta,
        warnings: [
          {
            code: "source_history_unavailable",
            detail: "fracfocus_csv begins after the requested cut.",
            pointer: "/events",
          },
        ],
      },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(
        stubFetch({
          [`/v1/wells/${API10}/completions`]: partialHistory,
          [`/v1/wells/${API10}/production`]: productionEnvelope,
          [`/v1/wells/${API10}`]: wellEnvelope,
        }),
      ),
    );

    await renderWellCard(host, API10, callbacks);

    // Summary reads on its own; the served detail and the code that raised it stay reachable
    // under it rather than being printed as a line of internal vocabulary.
    const note = host.querySelector<HTMLElement>(".gw-completion-context .gw-note-warning");
    expect(note?.dataset["code"]).toBe("source_history_unavailable");
    expect(note?.querySelector(".gw-note-summary")?.textContent).toBe("Source history unavailable");
    expect(note?.querySelector(".gw-note-line")?.textContent).toBe(
      "fracfocus_csv begins after the requested cut.",
    );
    expect(note?.querySelector(".gw-note-source")?.textContent).toContain("/events");
  });

  it("leaves the well and production usable when the context request fails", async () => {
    const normal = stubFetch({
      [`/v1/wells/${API10}/production`]: productionEnvelope,
      [`/v1/wells/${API10}`]: wellEnvelope,
    });
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        if (String(input).startsWith(`/v1/wells/${API10}/completions`)) {
          return Promise.resolve(problem(503, "context_unavailable"));
        }
        return normal(input);
      }),
    );

    await renderWellCard(host, API10, callbacks);

    const body = host.querySelector<HTMLElement>(".gw-completion-context .gw-frame-body");
    expect(body?.dataset["state"]).toBe("unavailable");
    expect(body?.textContent).toContain("could not be read");
    expect(host.querySelector("h2")?.textContent).toBe("Mandaree 50-2008H");
    expect(renderChart).toHaveBeenCalledOnce();
  });

  it("treats a malformed success body as unavailable rather than an empty observation", async () => {
    const malformed = {
      ...completionContextEnvelope,
      data: { api10: API10, design_availability: "not_promoted", events: [] },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(
        stubFetch({
          [`/v1/wells/${API10}/completions`]: malformed,
          [`/v1/wells/${API10}/production`]: productionEnvelope,
          [`/v1/wells/${API10}`]: wellEnvelope,
        }),
      ),
    );

    await renderWellCard(host, API10, callbacks);

    const body = host.querySelector<HTMLElement>(".gw-completion-context .gw-frame-body");
    expect(body?.dataset["state"]).toBe("unavailable");
    expect(body?.dataset["state"]).not.toBe("empty");
    expect(body?.textContent).toContain("could not be read");
  });

  it("refuses completion context echoed for a different well", async () => {
    const wrongWell = {
      ...completionContextEnvelope,
      data: { ...completionContextEnvelope.data, api10: "3305319999" },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(
        stubFetch({
          [`/v1/wells/${API10}/completions`]: wrongWell,
          [`/v1/wells/${API10}/production`]: productionEnvelope,
          [`/v1/wells/${API10}`]: wellEnvelope,
        }),
      ),
    );

    await renderWellCard(host, API10, callbacks);

    const body = host.querySelector<HTMLElement>(".gw-completion-context .gw-frame-body");
    expect(body?.dataset["state"]).toBe("unavailable");
    expect(body?.textContent).not.toContain("BAKKEN");
  });
});

function factsOf(root: HTMLElement): Record<string, string> {
  return Object.fromEntries(
    [...root.querySelectorAll("dt")].map((term) => {
      const definition = term.nextElementSibling?.cloneNode(true) as HTMLElement | undefined;
      definition?.querySelectorAll("button").forEach((button) => button.remove());
      return [term.textContent ?? "", definition?.textContent?.trim() ?? ""];
    }),
  );
}

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

describe("a cumulative total that some months were allocated into", () => {
  const EMPTY_COVERAGE = {
    coverage_complete: false,
    first_month: "2024-01",
    last_month: "2025-12",
    months_no_report: 0,
    months_reported: 0,
    months_reported_zero: 0,
    months_withheld: 0,
    span_months: 24,
  };

  function allocatedCumulatives() {
    const base = cumulativesEnvelope as unknown as {
      data: Record<string, unknown>;
      [key: string]: unknown;
    };
    return {
      ...base,
      data: {
        ...base.data,
        granularity: "lease_allocated",
        coverage_outcome: "observed_with_allocated",
        // The coverage block counts well-grain canonical months, and a lease-grain
        // jurisdiction has none: this is the shape the Texas arm actually serves, and the
        // one that put "0 of 24 months admitted" under a 7,200 bbl total.
        coverage: {
          ...(base.data["coverage"] as Record<string, unknown>),
          oil_bbl: EMPTY_COVERAGE,
          gas_mcf: EMPTY_COVERAGE,
          water_bbl: EMPTY_COVERAGE,
        },
        allocation: {
          basis: "allocated",
          model_id: "alloc_v0_2026_09",
          rule_id: "cr_tx_allocation_v0_1",
          months: {
            liquid: { value: "24", unit: "months", d: "drv_a#api10=x&stream=liquid" },
            gas: { value: "24", unit: "months", d: "drv_a#api10=x&stream=gas" },
          },
          share: {
            liquid: { value: "0.6700", unit: "share", d: "drv_a#api10=x&stream=liquid" },
          },
          shares_counted: { value: "9", unit: "shares", d: "drv_a#api10=x&col=shares_counted" },
        },
      },
    };
  }

  async function render(): Promise<void> {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        stubFetch({
          [`/v1/wells/${API10}/completions`]: completionContextEnvelope,
          [`/v1/wells/${API10}/cumulatives`]: allocatedCumulatives(),
          [`/v1/wells/${API10}/neighbors`]: neighborEnvelope,
          [`/v1/wells/${API10}/production`]: productionEnvelope,
          [`/v1/wells/${API10}`]: wellEnvelope,
        }),
      ),
    );
    await renderWellCard(host, API10, callbacks);
  }

  it("states the allocated share beside the total rather than after it", async () => {
    await render();
    const cells = [...host.querySelectorAll(".gw-cumulative-cell")];
    const oil = cells.find((cell) => cell.textContent?.startsWith("Oil"));

    expect(oil?.querySelector(".gw-alloc-share")?.textContent).toBe("67% allocated");
  });

  it("labels the coverage class as a chip, never as a footnote", async () => {
    await render();
    const chip = host.querySelector<HTMLElement>(".gw-alloc-coverage");

    expect(chip).not.toBeNull();
    expect(chip?.dataset["basis"]).toBe("allocated");
    expect(chip?.textContent).toContain("alloc_v0_2026_09");
    expect(chip?.getAttribute("title")).toContain("cr_tx_allocation_v0_1");
  });

  it("shows no chip on a stream nothing was allocated into", async () => {
    // A stream with no allocated month is not partly allocated, and a 0% chip trains a reader
    // to stop reading the chip on the stream that does carry one.
    await render();
    const cells = [...host.querySelectorAll(".gw-cumulative-cell")];
    const gas = cells.find((cell) => cell.textContent?.startsWith("Gas"));

    expect(gas?.querySelector(".gw-alloc-share")).toBeNull();
  });

  it("leaves an observed total alone", async () => {
    await renderWellCard(host, API10, callbacks);

    expect(host.querySelector(".gw-alloc-coverage")).toBeNull();
    expect(host.querySelector(".gw-alloc-share")).toBeNull();
    expect(host.querySelector(".gw-scope-allocated")).toBeNull();
    expect(host.textContent).toContain("months admitted");
  });

  it("counts the allocated months rather than reporting none admitted", async () => {
    // `months_reported` counts well-grain canonical months and there are none, so the scope
    // line said nothing was admitted directly under two non-null totals — a number the
    // surface contradicts in the next sentence, which is worse than a naked one.
    await render();
    const scope = host.querySelector<HTMLElement>(".gw-scope-allocated");

    expect(scope?.textContent).toBe("24 of 24 months allocated · 0 observed");
    expect(host.textContent).not.toContain("months admitted");
  });

  it("takes that count from the served figure, so it resolves like any other", async () => {
    await render();
    const scope = host.querySelector<HTMLElement>(".gw-scope-allocated");

    expect(scope?.dataset["handle"]).toBe("drv_a#api10=x&stream=liquid");
    expect(scope?.getAttribute("title")).toContain("cr_tx_allocation_v0_1");
  });
});
