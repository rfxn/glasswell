// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DEFAULTS_FOR_TEST, filterFor, mountWellsBy, panelState } from "./wells-by.ts";
import type { WellFacets } from "./wells-by.ts";
import type { Figure, Warning } from "../../api/envelope.ts";
import { DEFAULT_STATE } from "../../app/state.ts";
import type { AppState } from "../../app/state.ts";

/**
 * No visibility or layout assertion lives in this file. `web/src/style.css` carries a global
 * `[hidden] { display: none !important }`, and happy-dom computes no layout, so a `toBeVisible`
 * here passes with and without the rule it claims to guard. Those checks are in the browser
 * tier; this file holds the shape of the request and the content of the DOM.
 */

function figure(value: string, handle = "drv_test#col=wells"): Figure {
  return { value, unit: "wells", d: handle };
}

const RESPONSE: WellFacets = {
  state: "42",
  state_name: "Texas",
  dimension: "operator",
  dimension_title: "current operator, as the source reported it",
  sort: "count",
  order: "desc",
  q: null,
  top: 15,
  distinct_values: 9369,
  caption: "The 15 operator values with the most wells, of 9,369 operator values in Texas.",
  buckets: [
    { value: "PIONEER NATURAL RESOURCES USA INC", wells: figure("4312"), links: { wells: "/v1/wells?operator=PIONEER&state=42" } },
    { value: "DIAMONDBACK E&P LLC", wells: figure("2201"), links: { wells: "/v1/wells?operator=DIAMONDBACK&state=42" } },
  ],
  remainder: {
    values: 9367,
    wells: figure("212830"),
    detail: "9,367 further operator values hold 212,830 wells between them, and are not in this list of 15.",
  },
  absence: {
    label: "not reported",
    detail: "These wells carry no operator.",
    rule_id: "cr_tx_operator_absence_1",
    wells: figure("70039"),
    links: { rule: "/v1/conformance/cr_tx_operator_absence_1" },
  },
  wells: figure("359421"),
  matched_wells: null,
  states: [
    { code: "25", name: "Montana", loaded: true },
    { code: "30", name: "New Mexico", loaded: false },
    { code: "33", name: "North Dakota", loaded: true },
    { code: "42", name: "Texas", loaded: true },
  ],
  rules: ["cr_tx_operator_absence_1"],
};

let host: HTMLElement;
let requested: string[];
let panelCommits: Record<string, string | null>[];
let filterCommits: [string, string[]][];

function state(extra: Record<string, string[]> = {}): AppState {
  return { ...DEFAULT_STATE, view: "explore", ds: "wells", extra };
}

function hooks() {
  return {
    setPanel: (values: Record<string, string | null>) => void panelCommits.push(values),
    applyFilter: (name: string, values: string[]) => void filterCommits.push([name, values]),
  };
}

function respondWith(body: Partial<WellFacets>, warnings: Warning[] = []): void {
  vi.stubGlobal("fetch", (url: string) => {
    requested.push(String(url));
    return Promise.resolve(
      new Response(
        JSON.stringify({ data: { ...RESPONSE, ...body }, meta: { warnings }, links: {} }),
        { headers: { "content-type": "application/json" } },
      ),
    );
  });
}

beforeEach(() => {
  requested = [];
  panelCommits = [];
  filterCommits = [];
  document.body.innerHTML = '<div id="host"></div>';
  host = document.getElementById("host") as HTMLElement;
  respondWith({});
});

afterEach(() => vi.unstubAllGlobals());

describe("the panel reads its question off the URL", () => {
  it("defaults to the top 15 operators of one state rather than every state at once", () => {
    expect(panelState(state())).toMatchObject({
      state: DEFAULTS_FOR_TEST.state,
      by: "operator",
      sort: "count",
      order: "desc",
      top: "15",
      q: "",
    });
  });

  it("takes the dimension, state, search and ranking from the wb-prefixed keys", () => {
    const read = panelState(
      state({ "wb.by": ["county"], "wb.state": ["33"], "wb.q": ["hess"], "wb.order": ["asc"] }),
    );

    expect(read).toMatchObject({ by: "county", state: "33", q: "hess", order: "asc" });
  });

  it("asks the server for the state and dimension the URL names", async () => {
    await mountWellsBy(host, {
      state: state({ "wb.by": ["status"], "wb.state": ["25"] }),
      hooks: hooks(),
      signal: new AbortController().signal,
    });

    expect(requested).toHaveLength(1);
    expect(requested[0]).toContain("state=25");
    expect(requested[0]).toContain("by=status");
  });
});

describe("the served counts are rendered as figures, never as bare numbers", () => {
  it("gives every bucket a gw-figure carrying the handle the API served", async () => {
    await mountWellsBy(host, { state: state(), hooks: hooks(), signal: new AbortController().signal });

    const figures = host.querySelectorAll(".gw-wells-by-rows gw-figure");
    expect(figures).toHaveLength(2);
    expect(figures[0]?.getAttribute("handle")).toBe("drv_test#col=wells");
    expect(figures[0]?.getAttribute("value")).toBe("4312");
  });

  it("renders the remainder, the absence and the total as figures too", async () => {
    await mountWellsBy(host, { state: state(), hooks: hooks(), signal: new AbortController().signal });

    for (const selector of [".gw-wells-by-remainder", ".gw-wells-by-absence", ".gw-wells-by-total"]) {
      expect(host.querySelector(`${selector} gw-figure`), selector).not.toBeNull();
    }
  });
});

describe("what the list leaves out is on the surface, not inferred from it", () => {
  it("states the cut in the caption the server composed", async () => {
    await mountWellsBy(host, { state: state(), hooks: hooks(), signal: new AbortController().signal });

    expect(host.querySelector(".gw-wells-by-caption")?.textContent).toContain("of 9,369");
  });

  it("prints the remainder's own sentence, so the tail is counted rather than implied", async () => {
    await mountWellsBy(host, { state: state(), hooks: hooks(), signal: new AbortController().signal });

    expect(host.querySelector(".gw-wells-by-remainder-detail")?.textContent).toContain(
      "9,367 further operator values hold 212,830 wells",
    );
  });

  it("drops the remainder block entirely when the list is complete", async () => {
    respondWith({ remainder: null });
    await mountWellsBy(host, { state: state(), hooks: hooks(), signal: new AbortController().signal });

    expect(host.querySelector(".gw-wells-by-remainder")).toBeNull();
  });
});

describe("the absence bucket is named, counted and outside the ranking", () => {
  it("renders it as its own block and not as a row in the ranked list", async () => {
    await mountWellsBy(host, { state: state(), hooks: hooks(), signal: new AbortController().signal });

    const rows = [...host.querySelectorAll(".gw-wells-by-row .gw-wells-by-name")].map(
      (node) => node.textContent,
    );
    expect(rows).not.toContain("not reported");
    expect(host.querySelector(".gw-wells-by-absence-label")?.textContent).toBe("not reported");
  });

  it("carries the count and links the conformance rule that decided it", async () => {
    await mountWellsBy(host, { state: state(), hooks: hooks(), signal: new AbortController().signal });

    expect(host.querySelector(".gw-wells-by-absence gw-figure")?.getAttribute("value")).toBe("70039");
    expect(host.querySelector(".gw-wells-by-rule")?.getAttribute("href")).toBe(
      "/v1/conformance/cr_tx_operator_absence_1",
    );
  });

  it("omits the rule line rather than inventing one where none is registered", async () => {
    respondWith({
      absence: { ...RESPONSE.absence!, rule_id: null, links: {} },
    });
    await mountWellsBy(host, { state: state(), hooks: hooks(), signal: new AbortController().signal });

    expect(host.querySelector(".gw-wells-by-absence")).not.toBeNull();
    expect(host.querySelector(".gw-wells-by-rule")).toBeNull();
  });
});

describe("what the envelope warns about reaches the surface", () => {
  it("renders one panel per served warning rather than dropping all three", async () => {
    respondWith({ q: "usa", matched_wells: figure("6513") }, [
      {
        code: "list_truncated",
        detail: "This list is a ranked cut, not the population.",
        pointer: "/buckets",
      },
      {
        code: "search_scopes_the_ranking",
        detail: "The search ran over every value in the state before the cut.",
        pointer: "/buckets",
      },
    ]);
    await mountWellsBy(host, {
      state: state({ "wb.q": ["usa"] }),
      hooks: hooks(),
      signal: new AbortController().signal,
    });

    const warnings = [...host.querySelectorAll(".gw-wells-by-list .gw-warning")].map(
      (node) => node.textContent,
    );
    expect(warnings).toHaveLength(2);
    expect(warnings[0]).toContain("list_truncated");
    expect(warnings[1]).toContain("The search ran over every value in the state");
  });

  it("renders no warning line where the envelope carries none", async () => {
    await mountWellsBy(host, { state: state(), hooks: hooks(), signal: new AbortController().signal });

    expect(host.querySelector(".gw-warning")).toBeNull();
  });
});

describe("a bucket narrows the grid beside it", () => {
  it("commits the collection filter the dimension maps to", async () => {
    await mountWellsBy(host, { state: state(), hooks: hooks(), signal: new AbortController().signal });

    (host.querySelector("button.gw-wells-by-value") as HTMLButtonElement).click();

    expect(filterCommits).toEqual([["operator", ["PIONEER NATURAL RESOURCES USA INC"]]]);
  });

  it("renders a plain label, not a button, for a dimension the collection cannot filter", async () => {
    respondWith({ dimension: "completion_year" });
    await mountWellsBy(host, { state: state(), hooks: hooks(), signal: new AbortController().signal });

    expect(host.querySelector("button.gw-wells-by-value")).toBeNull();
    expect(host.querySelector("span.gw-wells-by-value")).not.toBeNull();
  });

  it("maps only the four dimensions the collection actually accepts", () => {
    expect(filterFor("operator")).toBe("operator");
    expect(filterFor("county")).toBe("county");
    expect(filterFor("status")).toBe("status");
    expect(filterFor("well_type")).toBe("well_type");
    expect(filterFor("completion_year")).toBeNull();
  });
});

describe("the state picker offers every state and says which have nothing behind them", () => {
  it("names each state in the layer panel's `Noun (Full state name)` convention", async () => {
    await mountWellsBy(host, { state: state(), hooks: hooks(), signal: new AbortController().signal });

    const labels = [...host.querySelectorAll(".gw-wells-by-state option")].map(
      (node) => node.textContent,
    );
    expect(labels).toContain("Wells (North Dakota)");
    expect(labels).toContain("Wells (Montana)");
  });

  it("offers an unloaded state as disabled rather than hiding that it exists", async () => {
    await mountWellsBy(host, { state: state(), hooks: hooks(), signal: new AbortController().signal });

    const newMexico = [...host.querySelectorAll<HTMLOptionElement>(".gw-wells-by-state option")].find(
      (node) => node.value === "30",
    );
    expect(newMexico?.disabled).toBe(true);
    expect(newMexico?.textContent).toContain("not loaded");
  });
});

describe("an empty answer is a sentence, never a blank panel", () => {
  it("says a search matched nothing and that the search covered the whole state", async () => {
    respondWith({ buckets: [], remainder: null, q: "zzz", caption: "No operator in Texas matches 'zzz'." });
    await mountWellsBy(host, { state: state({ "wb.q": ["zzz"] }), hooks: hooks(), signal: new AbortController().signal });

    expect(host.querySelector(".gw-wells-by-empty-title")?.textContent).toBe(
      "No value matches that search",
    );
    expect(host.querySelector(".gw-wells-by-empty-detail")?.textContent).toContain(
      "not over a page of them",
    );
  });

  it("renders the server's refusal for a state whose ingest has not run", async () => {
    vi.stubGlobal("fetch", () =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            title: "Validation failed",
            status: 422,
            detail: "the spine carries no well in state 30, so there is nothing to count by.",
          }),
          { status: 422, headers: { "content-type": "application/json" } },
        ),
      ),
    );
    await mountWellsBy(host, {
      state: state({ "wb.state": ["30"] }),
      hooks: hooks(),
      signal: new AbortController().signal,
    });

    expect(host.querySelector(".gw-wells-by-empty-title")?.textContent).toBe("Nothing to count here");
    expect(host.querySelector(".gw-wells-by-empty-detail")?.textContent).toContain(
      "no well in state 30",
    );
  });

  it("rebuilds the state picker from the refusal, so the empty state is not a dead end", async () => {
    vi.stubGlobal("fetch", () =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            title: "Validation failed",
            status: 422,
            detail: "nothing in state 30",
            states: RESPONSE.states,
          }),
          { status: 422, headers: { "content-type": "application/json" } },
        ),
      ),
    );
    await mountWellsBy(host, {
      state: state({ "wb.state": ["30"] }),
      hooks: hooks(),
      signal: new AbortController().signal,
    });

    const labels = [...host.querySelectorAll(".gw-wells-by-state option")].map(
      (node) => node.textContent,
    );
    expect(labels).toContain("Wells (Texas)");
    expect(labels).not.toEqual(["\u2026"]);
  });

  it("keeps the controls up under a refusal, so the reader can pick another state", async () => {
    vi.stubGlobal("fetch", () =>
      Promise.resolve(new Response(JSON.stringify({ status: 422, detail: "nope" }), { status: 422 })),
    );
    await mountWellsBy(host, { state: state(), hooks: hooks(), signal: new AbortController().signal });

    expect(host.querySelector(".gw-wells-by-controls")).not.toBeNull();
  });
});
