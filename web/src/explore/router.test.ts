import { describe, expect, it } from "vitest";

import { DEFAULT_STATE, parseState, serializeState } from "../app/state.ts";
import type { AppState } from "../app/state.ts";
import type { CatalogueDataset } from "./catalogue.ts";
import { FILTER_PREFIX, filtersOf, requestFor, withFilter } from "./router.ts";

function state(over: Partial<AppState> = {}): AppState {
  return { ...DEFAULT_STATE, ...over };
}

function dataset(over: Partial<CatalogueDataset> = {}): CatalogueDataset {
  return {
    id: "production",
    title: "Production (per well)",
    group: "wells",
    collection_pointer: "",
    anchors: [],
    row_id: ["/pm"],
    facets: ["stream", "from", "to"],
    columns: { hidden: [], hidden_reason: {} },
    intro: "nb_dataset_production",
    order: 11,
    operationId: "get_well_production",
    path: "/v1/wells/{api10}/production",
    pathParameters: ["api10"],
    ...over,
  };
}

describe("the ?view= grammar round-trips every member a shared link carries (§2.1)", () => {
  // §8.1 acceptance 1: a link a reader shares reconstructs the surface, not an approximation
  // of it. Every parameter in §2.1's table is asserted here, repeated filters included.
  const url =
    "?view=explore&tab=datasets&ds=quarantine&row=qr_01contract0001" +
    "&api=req&pane=open&slug=w1&cursor=eyJrIjoi&as_of=2026-08-01" +
    "&f.stream=oil&f.stream=gas&f.reason_code=key_incomplete";

  it("reconstructs all of them exactly", () => {
    const parsed = parseState(url);

    expect(parsed.view).toBe("explore");
    expect(parsed.tab).toBe("datasets");
    expect(parsed.ds).toBe("quarantine");
    expect(parsed.row).toBe("qr_01contract0001");
    expect(parsed.slug).toBe("w1");
    expect(parsed.extra["api"]).toEqual(["req"]);
    expect(parsed.extra["pane"]).toEqual(["open"]);
    expect(parsed.extra["cursor"]).toEqual(["eyJrIjoi"]);
    expect(parsed.extra["as_of"]).toEqual(["2026-08-01"]);
    expect(parsed.extra["f.stream"]).toEqual(["oil", "gas"]);
  });

  it("survives the codec both ways, so a shared link is not a lossy copy", () => {
    const round = parseState(serializeState(parseState(url)));

    expect(round).toEqual(parseState(url));
    expect(filtersOf(round)).toEqual({ stream: ["oil", "gas"], reason_code: ["key_incomplete"] });
  });

  it("reads filters by prefix and leaves the hoisted parameters out of them", () => {
    const filters = filtersOf(parseState(url));

    expect(filters["as_of"]).toBeUndefined();
    expect(filters["cursor"]).toBeUndefined();
    expect(filters["pane"]).toBeUndefined();
  });
});

describe("withFilter is the only way a filter changes", () => {
  it("replaces every value of one filter and leaves the others alone", () => {
    const before = withFilter(state(), "stream", ["oil", "gas"]);

    const after = withFilter(withFilter(before, "reason_code", ["x"]), "stream", ["water"]);

    expect(filtersOf(after)).toEqual({ stream: ["water"], reason_code: ["x"] });
    expect(after.extra[`${FILTER_PREFIX}stream`]).toEqual(["water"]);
  });

  it("removes the parameter entirely when the last value goes", () => {
    const cleared = withFilter(withFilter(state(), "stream", ["oil"]), "stream", []);

    expect(serializeState(cleared)).not.toContain("f.stream");
    expect(filtersOf(cleared)).toEqual({});
  });

  it("never mutates the state it was given", () => {
    const before = state();

    withFilter(before, "stream", ["oil"]);

    expect(before.extra).toEqual({});
  });
});

describe("requestFor is the call the reader could paste into curl (§3.1)", () => {
  it("substitutes an anchor into the path and leaves the rest in the query", () => {
    const filtered = withFilter(withFilter(state(), "api10", ["3305310451"]), "stream", ["oil"]);

    const request = requestFor(dataset(), filtered);

    expect(request.operationId).toBe("get_well_production");
    expect(request.path).toBe("/v1/wells/3305310451/production");
    expect(request.query).toEqual({ stream: ["oil"] });
    expect(request.missing).toEqual([]);
  });

  it("names the anchors it has no value for rather than issuing a request that 404s", () => {
    const request = requestFor(dataset(), state());

    expect(request.missing).toEqual(["api10"]);
    expect(request.path).toContain("{api10}");
  });

  it("hoists as_of and cursor into the query and leaves the pane's own state out", () => {
    const browsing = state({
      extra: { as_of: ["2026-08-01"], cursor: ["eyJrIjoi"], pane: ["open"], api: ["req"] },
    });

    const request = requestFor(dataset({ path: "/v1/quarantine", pathParameters: [] }), browsing);

    expect(request.query).toEqual({ as_of: ["2026-08-01"], cursor: ["eyJrIjoi"] });
  });

  it("encodes an anchor value rather than pasting it into the path", () => {
    const filtered = withFilter(state(), "api10", ["a/b#c"]);

    expect(requestFor(dataset(), filtered).path).toBe("/v1/wells/a%2Fb%23c/production");
  });
});
