import { describe, expect, it } from "vitest";

import { CONTRAST_FLOOR, NON_TEXT_FLOOR, contrastRatio, relativeLuminance } from "./contrast.ts";

describe("the contrast metric", () => {
  it("reproduces the two anchors of the WCAG scale", () => {
    expect(contrastRatio("#000000", "#FFFFFF")).toBeCloseTo(21, 2);
    expect(contrastRatio("#7F7F7F", "#7F7F7F")).toBeCloseTo(1, 5);
  });

  it("is symmetric, so a label and its halo may be named in either order", () => {
    expect(contrastRatio("#0B1014", "#9FB0BC")).toBeCloseTo(contrastRatio("#9FB0BC", "#0B1014"), 9);
  });

  it("reads the three-digit form and is case-insensitive", () => {
    expect(relativeLuminance("#fff")).toBeCloseTo(relativeLuminance("#FFFFFF"), 9);
    expect(relativeLuminance("#0b1014")).toBeCloseTo(relativeLuminance("#0B1014"), 9);
  });

  it("refuses a colour it cannot measure instead of scoring it 1:1", () => {
    // A token typo that silently scored as a pass would make every assertion below vacuous.
    expect(() => relativeLuminance("var(--paper)")).toThrow(/measurable/i);
    expect(() => relativeLuminance("#12345")).toThrow(/measurable/i);
  });

  it("states the floors it is measured against", () => {
    expect(CONTRAST_FLOOR).toBe(4.5);
    expect(NON_TEXT_FLOOR).toBe(3);
  });

  it("scores the reported defect below the floor and the shipped dark case above it", () => {
    // VF-5: the spacing-unit label was slate over every substrate. Over the light earth and
    // over mid-tone imagery that is what "almost unreadable" and "unreadable" measure as.
    expect(contrastRatio("#9FB0BC", "#F2F5F8")).toBeLessThan(CONTRAST_FLOOR);
    expect(contrastRatio("#9FB0BC", "#8A8A70")).toBeLessThan(CONTRAST_FLOOR);
    expect(contrastRatio("#9FB0BC", "#0B1014")).toBeGreaterThan(CONTRAST_FLOOR);
  });
});
