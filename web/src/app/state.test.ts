import { describe, expect, it } from "vitest";

import { DEFAULT_STATE, parseState, serializeState } from "./state.ts";

describe("URL state codec", () => {
  it("round-trips viewport, selection and drawer state", () => {
    const state = {
      ...DEFAULT_STATE,
      map: { zoom: 9.25, lat: 47.81234, lon: -102.84567 },
      well: "3305301234",
      explain: "drv_oil1#api10=3305301234&col=oil_bbl",
    };
    expect(parseState(serializeState(state))).toEqual(state);
  });

  it("defaults to the Williston basin view when the URL says nothing", () => {
    expect(parseState("")).toEqual(DEFAULT_STATE);
  });

  it("rounds the viewport so a re-serialize does not churn history", () => {
    const once = serializeState({
      ...DEFAULT_STATE,
      map: { zoom: 9.256789, lat: 47.812345678, lon: -102.845678901 },
    });
    expect(once).toBe(serializeState(parseState(once)));
    expect(new URLSearchParams(once).get("map")).toBe("9.26/47.81235/-102.84568");
  });

  it("preserves unknown parameters, so a newer link survives an older bundle", () => {
    const parsed = parseState("?well=3305301234&as_of=2026-08-01");
    expect(parsed.extra).toEqual({ as_of: ["2026-08-01"] });
    expect(new URLSearchParams(serializeState(parsed)).get("as_of")).toBe("2026-08-01");
  });

  it("ignores a malformed viewport instead of throwing", () => {
    expect(parseState("?map=not-a-viewport").map).toEqual(DEFAULT_STATE.map);
  });

  it("omits empty selections from the URL", () => {
    expect(serializeState(DEFAULT_STATE)).not.toContain("well=");
    expect(serializeState(DEFAULT_STATE)).not.toContain("explain=");
  });
});

describe("three surfaces, one URL grammar (SB-08 §2.1)", () => {
  it("keeps a repeated filter, which a single-valued extra collapses", () => {
    const parsed = parseState("?view=explore&ds=quarantine&f.stream=oil&f.stream=gas");

    expect(parsed.extra["f.stream"]).toEqual(["oil", "gas"]);
    expect(serializeState(parsed)).toContain("f.stream=oil&f.stream=gas");
  });

  it("round-trips the explorer members and omits them at their defaults", () => {
    const state = {
      ...DEFAULT_STATE,
      view: "explore" as const,
      tab: "learn" as const,
      ds: "quarantine",
      row: "3305301234",
      slug: "reason-codes",
    };

    expect(parseState(serializeState(state))).toEqual(state);
    expect(serializeState(DEFAULT_STATE)).not.toContain("view=");
    expect(serializeState(DEFAULT_STATE)).not.toContain("tab=");
  });

  it("omits the viewport from an explorer link at the default view", () => {
    expect(serializeState({ ...DEFAULT_STATE, view: "explore", ds: "wells" })).not.toContain("map=");
    expect(serializeState(DEFAULT_STATE)).toContain("map=");
  });

  it("round-trips a Status deep link without inventing a viewport", () => {
    const status = serializeState({ ...DEFAULT_STATE, view: "status" });

    expect(new URLSearchParams(status).get("view")).toBe("status");
    expect(new URLSearchParams(status).has("map")).toBe(false);
    expect(parseState(status).view).toBe("status");
  });

  // B2: the reader pans, crosses to the explorer, and comes back. popstate rebuilds state from
  // the URL, so a viewport the URL dropped is a viewport the back button cannot restore.
  it("keeps a moved viewport on an explorer link, so the crossing is reversible", () => {
    const panned = {
      ...DEFAULT_STATE,
      view: "explore" as const,
      ds: "wells",
      map: { zoom: 11.5, lat: 47.9, lon: -103.1 },
    };

    const url = serializeState(panned);

    expect(new URLSearchParams(url).get("map")).toBe("11.50/47.90000/-103.10000");
    expect(parseState(url).map).toEqual(panned.map);
  });

  // m3: a hostile or stale link must not put the app in a state it cannot render.
  it("falls back to the defaults when view or tab is not one of the declared values", () => {
    const parsed = parseState("?view=banana&tab=nope");

    expect(parsed.view).toBe("map");
    expect(parsed.tab).toBe("datasets");
    expect(parsed.extra).toEqual({});
  });

  it("leaves every existing map URL byte-identical", () => {
    // The shipped codec percent-encodes the viewport separator; byte identity is against what
    // the app emits, not against a hand-written pretty form.
    const before = "?map=9.26%2F47.81235%2F-102.84568&well=3305301234";

    expect(serializeState(parseState(before))).toBe(before);
  });
});
