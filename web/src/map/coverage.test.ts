import { describe, expect, it } from "vitest";

import { ND_SNAPSHOT, ndCoverage, ndWellCount } from "./coverage.ts";

describe("the served ND snapshot", () => {
  it("pins the v0.30 refresh's own numbers — the one deliberate place they are written", () => {
    // The mart is what the map draws; QUEUE-DISPATCH records 43,817 rows at this refresh
    // and visual-m17 confirmed 1,989 class rows in it. The FeatureServer's 43,824 belongs
    // to the R8 rules that measured it, not to the panel.
    expect(ND_SNAPSHOT).toEqual({
      wells: 43_817,
      disposal: 1_989,
      traced: 525,
      refresh: "drv_lp7yzfash7mft2cdohba",
    });
  });

  it("computes every coverage statement, so a percentage is never hand-written", () => {
    expect(ndCoverage(ND_SNAPSHOT.disposal)).toBe("1,989 of 43,817 wells (4.5%)");
    expect(ndCoverage(ND_SNAPSHOT.traced)).toBe("525 of 43,817 wells (1.2%)");
    expect(ndWellCount()).toBe("43,817");
  });
});
