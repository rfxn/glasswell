import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { filtersOf, withFilter } from "../explore/router.ts";
import { WELL_FILTER, crossTo } from "./router.ts";
import { DEFAULT_STATE, serializeState } from "./state.ts";
import type { AppState } from "./state.ts";

function state(over: Partial<AppState> = {}): AppState {
  return { ...DEFAULT_STATE, ...over };
}

describe("cross-surface routing", () => {
  it("keeps Map → Explore selection translation exact", () => {
    const explore = crossTo("explore", state({ well: "3305310451" }));

    expect(explore.view).toBe("explore");
    expect(explore.ds).toBe("wells");
    expect(explore.well).toBeNull();
    expect(explore.explain).toBeNull();
    expect(filtersOf(explore)).toEqual({ api10: ["3305310451"] });
  });

  it("keeps Explore → Map selection restoration exact", () => {
    const explore = withFilter(state({ view: "explore", ds: "wells" }), WELL_FILTER, ["3305310451"]);
    const map = crossTo("map", explore);

    expect(map.view).toBe("map");
    expect(map.well).toBe("3305310451");
    expect(filtersOf(map)).toEqual({});
  });

  it("carries as_of and the moved viewport across Map and Explore", () => {
    const map = state({
      map: { zoom: 11.5, lat: 47.9, lon: -103.1 },
      extra: { as_of: ["2026-08-01"] },
    });

    const explore = crossTo("explore", map);
    const back = crossTo("map", explore);

    expect(explore.extra["as_of"]).toEqual(["2026-08-01"]);
    expect(back.extra["as_of"]).toEqual(["2026-08-01"]);
    expect(new URLSearchParams(serializeState(explore)).get("map")).toBe(
      "11.50/47.90000/-103.10000",
    );
  });

  it("clears map overlays on entry to Status without mutating Explorer filters", () => {
    const explorer = withFilter(
      state({
        view: "explore",
        ds: "wells",
        well: "3305310451",
        explain: "drv_1",
        extra: { as_of: ["2026-08-01"] },
      }),
      "q",
      ["bakken federal"],
    );

    const status = crossTo("status", explorer);

    expect(status.view).toBe("status");
    expect(status.well).toBeNull();
    expect(status.explain).toBeNull();
    expect(filtersOf(status)).toEqual({ q: ["bakken federal"] });
    expect(status.extra["as_of"]).toEqual(["2026-08-01"]);
  });

  it("never reinterprets a retained Explorer query when Status crosses to Map", () => {
    const status = withFilter(state({ view: "status", ds: "wells" }), "q", ["3305310451"]);

    const map = crossTo("map", status);

    expect(map.view).toBe("map");
    expect(map.well).toBeNull();
    expect(filtersOf(map)).toEqual({ q: ["3305310451"] });
  });

  it("returns the same object when the selected surface is already current", () => {
    const status = state({ view: "status" });

    expect(crossTo("status", status)).toBe(status);
  });
});

/**
 * The crossing narrows by a parameter the served document takes, and by the one that names
 * the row. `f.q` was both a real parameter and the wrong one: `/v1/wells` accepts it and
 * answers a name search with nothing for every API-10 a reader clicked. The check runs
 * against the committed snapshot, which is what the deployment serves.
 */
describe("the parameter a Map → Explore crossing writes", () => {
  const SNAPSHOT = JSON.parse(readFileSync("../tests/contract/openapi_snapshot.json", "utf8")) as {
    paths: Record<string, Record<string, { parameters?: { name: string; schema?: unknown }[] }>>;
  };

  const parameterOf = (name: string): { name: string; schema?: unknown } | undefined =>
    SNAPSHOT.paths["/v1/wells"]?.["get"]?.parameters?.find((entry) => entry.name === name);

  it("is one /v1/wells declares, taken from the crossing rather than restated", () => {
    const explore = crossTo("explore", state({ well: "3305310451" }));
    const written = Object.keys(filtersOf(explore));

    expect(written).toEqual([WELL_FILTER]);
    expect(parameterOf(WELL_FILTER), `/v1/wells takes no ${WELL_FILTER}`).toBeDefined();
  });

  it("is the identity parameter, which matches an API-10 or the API-14 recorded for it", () => {
    const schema = parameterOf(WELL_FILTER)?.schema as { anyOf?: { pattern?: string }[] };
    const pattern = schema.anyOf?.map((member) => member.pattern).find((value) => value);

    expect(pattern, `${WELL_FILTER} declares no pattern`).toBeDefined();
    const matches = new RegExp(pattern as string);
    expect(matches.test("3305310451")).toBe(true);
    expect(matches.test("33053104510000")).toBe(true);
    // The defect this replaced: `q` is a name substring and takes anything, including a
    // literal that names no well, which is why "accepted" was never the question.
    expect(matches.test("bakken federal")).toBe(false);
  });

  it("restores the same selection on the way back, so the crossing is a round trip", () => {
    const there = crossTo("explore", state({ well: "3305310451" }));
    const back = crossTo("map", there);

    expect(back.well).toBe("3305310451");
    expect(filtersOf(back)).toEqual({});
  });
});
