// @vitest-environment happy-dom
import { describe, expect, it } from "vitest";

import { popoverSpot } from "./popover.ts";

const VIEWPORT = { width: 390, height: 844 };
const anchor = (top: number, height = 18): DOMRect =>
  ({ top, bottom: top + height, left: 40, right: 120 }) as DOMRect;

describe("a popover is placed where all of it can be read", () => {
  it("sits under its anchor when there is room", () => {
    const spot = popoverSpot(anchor(200), { width: 240, height: 240 }, VIEWPORT);
    expect(spot.top).toBe(226);
    expect(spot.left).toBe(40);
  });

  it("flips above its anchor when below would run past the bottom", () => {
    const spot = popoverSpot(anchor(700), { width: 352, height: 240 }, VIEWPORT);
    expect(spot.top).toBe(700 - 240 - 8);
  });

  // The defect this function exists for: with neither side big enough, the old placement
  // pinned the top at 8 and let the rest run off the bottom — content below the fold with
  // nothing on screen saying it was there. Now it takes the larger side and states the room,
  // which is what makes the surface's own cap fold it.
  it("gives a popover too tall for either side the larger side's room and a fold", () => {
    const spot = popoverSpot(anchor(400), { width: 352, height: 1200 }, VIEWPORT);
    expect(spot.top).toBe(400 + 18 + 8);
    expect(spot.maxHeight).toBe(VIEWPORT.height - 8 - (400 + 18 + 8));
    expect(spot.top + spot.maxHeight).toBeLessThanOrEqual(VIEWPORT.height);
  });

  it("never reports a negative left for a popover wider than the viewport", () => {
    const spot = popoverSpot(anchor(200), { width: 600, height: 120 }, VIEWPORT);
    expect(spot.left).toBe(8);
  });

  it("pulls a popover back from the right edge", () => {
    const spot = popoverSpot(
      { top: 200, bottom: 218, left: 360, right: 384 } as DOMRect,
      { width: 352, height: 120 },
      VIEWPORT,
    );
    expect(spot.left).toBe(VIEWPORT.width - 352 - 8);
  });
});
