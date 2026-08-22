import { describe, expect, it } from "vitest";

import {
  LIQUID_RAMP,
  METRIC_FILL_LAYERS,
  METRICS_HANDOFF_ZOOM,
  SUPPORT_ALPHA,
  TOWNSHIP_METRICS_MIN_ZOOM,
  frameOf,
  liquidFillColour,
  observedFilter,
} from "./thematics.ts";

/** sRGB relative luminance — the ramp's order must be the value's order. */
function luminance(hex: string): number {
  const channel = (offset: number): number => {
    const value = Number.parseInt(hex.slice(offset, offset + 2), 16) / 255;
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5);
}

describe("the liquid ramp", () => {
  it("is seven steps, one per bin between the eight percentile edges", () => {
    expect(LIQUID_RAMP).toHaveLength(7);
  });

  it("is sequential: lightness strictly rises with the value, never spectral", () => {
    const ordered = LIQUID_RAMP.map((step) => luminance(step));
    for (let index = 1; index < ordered.length; index += 1) {
      expect(ordered[index]).toBeGreaterThan(ordered[index - 1] ?? 0);
    }
  });

  it("is not a stream colour: no step is oil green, gas red or water blue", () => {
    // Amber throughout — the red channel leads and green leads blue on every step, which
    // no stream colour satisfies (oil is green-led, water and gas are not amber-ordered).
    for (const step of LIQUID_RAMP) {
      const [r, g, b] = [1, 3, 5].map((offset) =>
        Number.parseInt(step.slice(offset, offset + 2), 16),
      );
      expect(r).toBeGreaterThan(b ?? 0);
      expect(g).toBeGreaterThan(b ?? 0);
    }
  });
});

describe("the fill expression", () => {
  it("keys the hue to the bin and the ink to the support", () => {
    const expression = JSON.stringify(liquidFillColour());
    expect(expression).toContain("prod_well_count");
    expect(expression).toContain("liquid_bin");
    for (const [, alpha] of SUPPORT_ALPHA) {
      expect(expression).toContain(`${alpha})`);
    }
  });

  it("filters unobserved cells out of the paint rather than bottom-binning them", () => {
    expect(observedFilter()).toEqual([">=", ["to-number", ["get", "liquid_bin"]], 0]);
  });

  it("hands townships off to sections at one zoom, no gap and no overlap", () => {
    expect(TOWNSHIP_METRICS_MIN_ZOOM).toBeLessThan(METRICS_HANDOFF_ZOOM);
    expect(METRIC_FILL_LAYERS).toEqual([
      "land-township-metrics-fill",
      "land-section-metrics-fill",
    ]);
  });
});

describe("the frame reader", () => {
  const cell = {
    unit_type: "section",
    bin_edges: JSON.stringify([0, 1, 2, 3, 4, 5, 6, 7]),
    bin_population: 42,
    derivation_id: "drv_test",
  };

  it("reads the refresh-frozen frame off a rendered cell", () => {
    expect(frameOf([cell])).toEqual({
      grain: "section",
      edges: [0, 1, 2, 3, 4, 5, 6, 7],
      population: 42,
      handle: "drv_test",
    });
  });

  it("skips malformed frames rather than taking the key down", () => {
    expect(frameOf([{ bin_edges: "{not json" }, cell])?.population).toBe(42);
    expect(frameOf([{ bin_edges: JSON.stringify([1, 2]) }])).toBeNull();
    expect(frameOf([])).toBeNull();
  });
});
