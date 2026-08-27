import { describe, expect, it } from "vitest";

import { filtersOf, withFilter } from "../explore/router.ts";
import { crossTo } from "./router.ts";
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
    expect(filtersOf(explore)).toEqual({ q: ["3305310451"] });
  });

  it("keeps Explore → Map selection restoration exact", () => {
    const explore = withFilter(state({ view: "explore", ds: "wells" }), "q", ["3305310451"]);
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
