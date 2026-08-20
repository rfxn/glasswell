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
    expect(parsed.extra).toEqual({ as_of: "2026-08-01" });
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
