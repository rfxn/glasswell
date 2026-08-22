import { describe, expect, it } from "vitest";

import { normaliseBbox, sameBbox } from "./counts.ts";
import type { Bbox } from "./counts.ts";
import { WHOLE_WORLD, countedBbox, extentFilterOn } from "./extent.ts";

describe("?extent=0", () => {
  it("switches the node off on exactly that value", () => {
    expect(extentFilterOn("?extent=0")).toBe(false);
    expect(extentFilterOn("?base=satellite&extent=0&map=9/47/-102")).toBe(false);
  });

  it("leaves the node on when the parameter is absent", () => {
    expect(extentFilterOn("")).toBe(true);
    expect(extentFilterOn("?base=light")).toBe(true);
  });

  it("leaves the node on for a value it was not given, rather than guessing at intent", () => {
    // Off means every count silently covers two basins instead of the canvas; a mistyped
    // value must not widen the population under the reader.
    for (const value of ["", "1", "false", "off", "no", "00", " 0", "0 ", "O", "%00", "0,0"]) {
      expect(extentFilterOn(`?extent=${encodeURIComponent(value)}`), `extent=${value}`).toBe(true);
    }
  });

  it("is not satisfied by the substring of another parameter", () => {
    expect(extentFilterOn("?notextent=0")).toBe(true);
    expect(extentFilterOn("?extents=0")).toBe(true);
  });
});

describe("the box the counts are asked over", () => {
  const viewport: Bbox = [-104.5, 47.2, -102.1, 48.6];

  it("is the viewport while the node is on", () => {
    expect(countedBbox(true, viewport)).toBe(viewport);
  });

  it("is everything ingested when the node is off", () => {
    expect(countedBbox(false, viewport)).toBe(WHOLE_WORLD);
  });

  it("survives normalisation unchanged, so the off state asks one stable question", () => {
    // request() dedups by sameBbox on the normalised box: if normalisation moved the world
    // box, every pan while the node is off would re-ask a question whose answer cannot change.
    expect(sameBbox(normaliseBbox(WHOLE_WORLD), WHOLE_WORLD)).toBe(true);
  });
});
