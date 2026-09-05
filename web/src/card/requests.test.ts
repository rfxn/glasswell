import { describe, expect, it } from "vitest";

import { DEFAULT_STATE, parseState } from "../app/state.ts";
import { FORWARDED, cardQuery } from "./requests.ts";

describe("the one place the card builds a query", () => {
  it("forwards the whole known bag, not `as_of` alone", () => {
    const state = parseState("?well=3305310451&as_of=2026-07-01&normalization=per_lateral_ft");
    expect(cardQuery(state)).toEqual({
      as_of: "2026-07-01",
      normalization: "per_lateral_ft",
    });
  });

  it("carries a brushed window, which is what the brush needs to survive a reload", () => {
    const state = parseState("?well=3305310451&from=2024-01&to=2024-12");
    expect(cardQuery(state)).toEqual({ from: "2024-01", to: "2024-12" });
  });

  it("forwards nothing a reader did not ask for", () => {
    expect(cardQuery(DEFAULT_STATE)).toEqual({});
    // An unrecognised key round-trips through state.extra and is re-serialised into the URL,
    // but it is not a parameter this API has agreed to answer and it reaches no request.
    expect(cardQuery(parseState("?nonsense=1&hostile=%3Cscript%3E"))).toEqual({});
  });

  it("never forwards the section, which is app state and not a request parameter", () => {
    const state = parseState("?well=3305310451&section=neighbours");
    expect(state.section).toBe("neighbours");
    expect(cardQuery(state)).toEqual({});
    expect(FORWARDED).not.toContain("section");
  });

  it("lets a caller add its own parameter without reopening the list", () => {
    const state = parseState("?as_of=2026-07-01");
    expect(cardQuery(state, { limit: "5" })).toEqual({ as_of: "2026-07-01", limit: "5" });
  });

  it("drops a parameter present but empty, which is nobody's pin", () => {
    expect(cardQuery(parseState("?as_of="))).toEqual({});
  });
});
