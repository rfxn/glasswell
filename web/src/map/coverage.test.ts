import { describe, expect, it } from "vitest";

import { LAND_SNAPSHOT, ND_SNAPSHOT, ndCoverage, ndWellCount } from "./coverage.ts";

describe("the served ND snapshot", () => {
  it("pins the v0.37 refresh's own numbers — the one deliberate place they are written", () => {
    // The mart is what the map draws, so the mart's counts are the denominators: read from
    // marts.nd_wells_tile on VM 111 at v0.37+dd49f63 (2026-08-22), matching visual-m23's
    // judged canvas. The FeatureServer's 43,824 belongs to the R8 rules that measured it,
    // not to the panel.
    expect(ND_SNAPSHOT).toEqual({
      wells: 43_817,
      disposal: 1_989,
      traced: 525,
      refresh: "drv_gh5zhnea4trtofypofbq",
    });
  });

  it("pins the promoted land grid and its metric cells to the same discipline", () => {
    expect(LAND_SNAPSHOT).toEqual({
      townships: 2_057,
      sections: 71_455,
      cells: 13_952,
      refresh: "drv_u6ntpnulcqf7kfij3t5a",
    });
    // The cells are cut over the promoted grid, so they can never outnumber it.
    expect(LAND_SNAPSHOT.cells).toBeLessThan(LAND_SNAPSHOT.townships + LAND_SNAPSHOT.sections);
  });

  it("computes every coverage statement, so a percentage is never hand-written", () => {
    expect(ndCoverage(ND_SNAPSHOT.disposal)).toBe("1,989 of 43,817 wells (4.5%)");
    expect(ndCoverage(ND_SNAPSHOT.traced)).toBe("525 of 43,817 wells (1.2%)");
    expect(ndWellCount()).toBe("43,817");
  });
});
