// @vitest-environment happy-dom
import { readFileSync } from "node:fs";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { WellFacets } from "../explore/facets/wells-by.ts";
import { DEFAULT_JURISDICTION } from "./jurisdictions.generated.ts";
import { createWellsBySheet } from "./wells-by-sheet.ts";

const figure = (value: string, handle = "drv_test#col=wells") => ({
  value,
  unit: "wells",
  d: handle,
});

// The sheet renders whatever jurisdiction the panel opened on, and the panel opens on the
// registered explorer default — so the fixture reads it rather than pinning a second copy.
const ND: WellFacets = {
  state: DEFAULT_JURISDICTION.prefix,
  state_name: DEFAULT_JURISDICTION.name,
  dimension: "operator",
  dimension_title: "current operator, as the source reported it",
  sort: "count",
  order: "desc",
  q: null,
  top: 15,
  distinct_values: 1590,
  caption: "The 15 operator values with the most wells, of 1,590 operator values in North Dakota.",
  buckets: [
    {
      value: "CONTINENTAL RESOURCES INC",
      wells: figure("6621", "drv_test#operator=CONTINENTAL"),
      links: { wells: "/v1/wells?operator=CONTINENTAL+RESOURCES+INC&state=33" },
    },
    {
      value: "HESS CORP",
      wells: figure("3412", "drv_test#operator=HESS"),
      links: { wells: "/v1/wells?operator=HESS+CORP&state=33" },
    },
  ],
  remainder: {
    values: 1588,
    wells: figure("77601"),
    detail: "1,588 further operator values hold 77,601 wells between them, and are not in this list of 15.",
  },
  absence: null,
  wells: figure("87634"),
  matched_wells: null,
  jurisdictions: [
    { code: "33", name: "North Dakota", wells: figure("43817"), dimension: "carried", rule_id: null },
  ],
  states: [
    { code: "33", name: "North Dakota", loaded: true },
    { code: "42", name: "Texas", loaded: true },
  ],
  rules: [],
};

let search = "";
let picks: (string | null)[];
let panels: { values: Record<string, string | null>; mode: string }[];
let opens: number;

function respond(body: Partial<WellFacets> = {}): void {
  vi.stubGlobal("fetch", () =>
    Promise.resolve(
      new Response(
        JSON.stringify({
          data: { ...ND, ...body },
          meta: {
            request_id: "01M0JWJ6ASE1P30C37CVC61WYB",
            as_of: { requested: "latest", resolved: "2026-08-01" },
            source_freshness: {},
            labels: {},
            next_cursor: null,
            warnings: [],
          },
          links: {},
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    ),
  );
}

function sheet() {
  return createWellsBySheet({
    search: () => search,
    setPanel: (values, mode) => void panels.push({ values, mode }),
    onPick: (value) => void picks.push(value),
    onOpen: () => void (opens += 1),
  });
}

const settle = (): Promise<void> => new Promise((resolve) => setTimeout(resolve, 0));

describe("the Wells-By sheet on the map", () => {
  beforeEach(() => {
    picks = [];
    panels = [];
    opens = 0;
    search = "";
    document.body.replaceChildren();
    respond();
  });

  afterEach(() => vi.unstubAllGlobals());

  it("is the layer panel's sibling, on the same frame rather than a second one", () => {
    const wellsBy = sheet();

    expect(wellsBy.element.classList.contains("gw-sheet")).toBe(true);
    expect(wellsBy.element.id).toBe("gw-wells-by");
    expect(wellsBy.element.getAttribute("aria-label")).toBe("Wells by");
  });

  it("opens shut, and the control that opens it announces which state it is in", async () => {
    const wellsBy = sheet();
    document.body.append(wellsBy.element);
    const trigger = document.createElement("button");
    trigger.className = "gw-wells-by-button";
    document.body.append(trigger);
    // The MutationObserver is asynchronous, as layer-panel.ts's is; the first sync is deferred.
    await settle();

    expect(wellsBy.element.hidden).toBe(true);
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
    expect(trigger.getAttribute("aria-controls")).toBe("gw-wells-by");

    wellsBy.toggle();
    await settle();
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
  });

  it("asks its host to shut the other sheet before it appears", () => {
    // One column, one geometry: two open sheets are one sheet with the other's rows behind it.
    const wellsBy = sheet();
    wellsBy.open();

    expect(opens).toBe(1);
    expect(wellsBy.element.hidden).toBe(false);
  });

  it("renders the shared panel rather than a second one", async () => {
    const wellsBy = sheet();
    document.body.append(wellsBy.element);
    wellsBy.open();
    await settle();

    expect(wellsBy.element.querySelector(".gw-wells-by-rows")).not.toBeNull();
    expect(
      [...wellsBy.element.querySelectorAll(".gw-wells-by-name")].map((node) => node.textContent),
    ).toEqual(["CONTINENTAL RESOURCES INC", "HESS CORP"]);
  });

  it("states the population it counted over, and that panning does not move it", async () => {
    const wellsBy = sheet();
    wellsBy.open();
    await settle();

    const scope = wellsBy.element.querySelector<HTMLElement>(".gw-wells-by-scope");
    expect(scope?.textContent).toContain("every current well in North Dakota");
    expect(scope?.textContent).toContain("does not move when you pan");
  });

  it("names the other scope once, so the key and the sheet are not two answers", () => {
    const wellsBy = sheet();
    const crossref = wellsBy.element.querySelector<HTMLElement>(".gw-sheet-crossref");

    expect(crossref?.textContent).toMatch(/map view/i);
  });

  it("discloses the remainder a top-15 of 1,590 leaves, rather than footnoting it", async () => {
    const wellsBy = sheet();
    wellsBy.open();
    await settle();

    const row = wellsBy.element.querySelector<HTMLElement>(".gw-wells-by-remainder");
    expect(row?.querySelector(".gw-wells-by-remainder-detail")?.textContent).toBe("1,588 more values");
    expect(row?.title).toContain("1,588 further operator values");
  });

  it("presses a bucket into a pick rather than into a grid filter", async () => {
    const wellsBy = sheet();
    wellsBy.open();
    await settle();

    wellsBy.element.querySelectorAll<HTMLButtonElement>("button.gw-wells-by-value")[1]?.click();

    expect(picks).toEqual(["HESS CORP"]);
  });

  it("releases the pick when the pressed bucket is pressed again", async () => {
    search = "?wb.pick=HESS+CORP";
    const wellsBy = sheet();
    wellsBy.open();
    await settle();

    const pressed = wellsBy.element.querySelector<HTMLButtonElement>(
      'button.gw-wells-by-value[aria-pressed="true"]',
    );
    expect(pressed?.textContent).toContain("HESS CORP");
    pressed?.click();

    expect(picks).toEqual([null]);
  });

  it("refuses a bucket the tiles carry no column for, with the map's own reason", async () => {
    search = "?wb.by=completion_year";
    respond({
      dimension: "completion_year",
      buckets: [{ value: "2021", wells: figure("12"), links: {} }],
    });
    const wellsBy = sheet();
    wellsBy.open();
    await settle();

    const label = wellsBy.element.querySelector<HTMLElement>(".gw-wells-by-value");
    expect(label?.tagName).toBe("SPAN");
    expect(label?.title).toMatch(/tiles carry no column/i);
  });

  it("keeps the panel's own refusal surface when the state has not been loaded", async () => {
    vi.stubGlobal("fetch", () =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            type: "about:blank",
            title: "Unprocessable entity",
            status: 422,
            detail: "No wells are loaded for state 30.",
            states: [{ code: "33", name: "North Dakota", loaded: true }],
          }),
          { status: 422, headers: { "content-type": "application/problem+json" } },
        ),
      ),
    );
    const wellsBy = sheet();
    wellsBy.open();
    await settle();

    expect(wellsBy.element.querySelector(".gw-wells-by-empty-detail")?.textContent).toContain(
      "No wells are loaded for state 30.",
    );
  });
});

describe("the sheet frame both panels share", () => {
  it("is declared once in map.css, not copied per sheet", () => {
    const css = readFileSync("src/map.css", "utf8");

    expect(/\.gw-sheet\s*\{[^}]*position:\s*absolute/.test(css)).toBe(true);
    expect(/\.gw-sheet\[hidden\]\s*\{[^}]*display:\s*none/.test(css)).toBe(true);
    // The layer panel's own rule no longer carries the frame: one declaration, two sheets.
    expect(/(^|\})[^{}]*\.gw-layers\s*\{[^}]*position:\s*absolute/m.test(css)).toBe(false);
  });
});
