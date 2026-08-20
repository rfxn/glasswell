import { describe, expect, it } from "vitest";

import { all, get, inSet, interpolate, lower, match, step, when, zoom } from "./expr.ts";

describe("the expression DSL", () => {
  it("builds the style-spec arrays MapLibre expects", () => {
    expect(get("api10")).toEqual(["get", "api10"]);
    expect(lower(get("status_canonical"))).toEqual(["downcase", ["get", "status_canonical"]]);
    expect(zoom).toEqual(["zoom"]);
  });

  it("flattens match pairs so the fallback stays last", () => {
    expect(
      match(get("s"), [
        ["a", 1],
        ["b", 2],
      ], 0),
    ).toEqual(["match", ["get", "s"], "a", 1, "b", 2, 0]);
  });

  it("flattens interpolate and step stops in order", () => {
    expect(interpolate(zoom, [[6, 1], [14, 4]])).toEqual([
      "interpolate",
      ["linear"],
      ["zoom"],
      6,
      1,
      14,
      4,
    ]);
    expect(step(zoom, 0.5, [[9, 2]])).toEqual(["step", ["zoom"], 0.5, 9, 2]);
  });

  it("wraps set membership in a literal so the array is data, not an expression", () => {
    expect(inSet(get("s"), ["a", "b"])).toEqual(["in", ["get", "s"], ["literal", ["a", "b"]]]);
  });

  it("keeps `when` and `all` in case/all shape", () => {
    expect(when([[true, 1]], 0)).toEqual(["case", true, 1, 0]);
    expect(all(true, false)).toEqual(["all", true, false]);
  });

  it("survives the JSON round-trip MapLibre applies to a style", () => {
    const expression = match(lower(get("status_canonical")), [["active", "#3FA55E"]], "#7C8B96");
    expect(JSON.parse(JSON.stringify(expression))).toEqual(expression);
  });
});
