import { describe, expect, it } from "vitest";

import { PICKABLE_LAYERS, PICK_RADIUS_PX, pickBox, topHit } from "./click-router.ts";
import { layerDef } from "./registry.ts";

const hit = (layer: string, api10: string): { layer: { id: string }; properties: Record<string, unknown> } => ({
  layer: { id: layer },
  properties: { api10 },
});

describe("the click router", () => {
  it("queries a box around the pointer instead of the exact pixel", () => {
    // UX §2.3 measured 195 clicks → 12 selections (6.2%) because `map.on('click', layer)`
    // hit-tests one pixel against a 1.8 px stroke. SB-05 §2.4 technique 5 specifies a
    // picking radius; this is it.
    expect(PICK_RADIUS_PX).toBeGreaterThanOrEqual(6);
    expect(pickBox({ x: 100, y: 200 })).toEqual([
      [100 - PICK_RADIUS_PX, 200 - PICK_RADIUS_PX],
      [100 + PICK_RADIUS_PX, 200 + PICK_RADIUS_PX],
    ]);
  });

  it("dispatches one feature, the highest-priority one", () => {
    // A click near a wellhead hits the point and the lateral under it. Without a priority
    // sort that is two selections, or a nondeterministic one.
    const picked = topHit([hit("laterals", "3305300001"), hit("wells", "3305300002")]);
    expect(picked?.layer.id).toBe("wells");
  });

  it("keeps the query order when two hits share a layer", () => {
    const picked = topHit([hit("wells", "first"), hit("wells", "second")]);
    expect(picked?.properties["api10"]).toBe("first");
  });

  it("ignores a layer with no registered priority rather than selecting it", () => {
    // Basemap layers are in the render tree and must never win a click.
    expect(topHit([hit("gw-boundaries-county", "x")])).toBe(null);
    expect(topHit([])).toBe(null);
  });

  it("ranks wells above laterals above spacing units", () => {
    const order = ["spacing-units-line", "laterals", "wells"].map((id) => topHit([hit(id, "a")]));
    expect(order[0]).not.toBe(null);
    expect(topHit([hit("spacing-units-line", "a"), hit("laterals", "b")])?.layer.id).toBe("laterals");
  });

  it("picks a Texas lateral, since one row now says both of them are the same thing", () => {
    // Under two rows a reader could read "Laterals (TX)" as its own layer with its own
    // behaviour. Under one, a click that selects in North Dakota and does nothing in the
    // Permian is the row contradicting itself.
    expect(topHit([hit("tx-laterals", "4231733333")])?.properties["api10"]).toBe("4231733333");
    expect(topHit([hit("tx-laterals", "a"), hit("wells", "b")])?.layer.id).toBe("wells");
  });

  it("makes every style layer the laterals row drives pickable, not just the first", () => {
    for (const styleLayer of layerDef("lateral-bores")!.styleLayers) {
      expect(PICKABLE_LAYERS, `${styleLayer} is not pickable`).toContain(styleLayer);
    }
  });

  it("ranks a survey trace above the lateral it overlies, and below the wellhead", () => {
    // The trace draws on top of its lateral, so the click follows the ink; a wellhead under
    // the cursor stays the most specific thing there.
    expect(topHit([hit("survey-traces", "a"), hit("laterals", "b")])?.layer.id).toBe("survey-traces");
    expect(topHit([hit("survey-traces", "a"), hit("wells", "b")])?.layer.id).toBe("wells");
  });

  it("makes every style layer the survey-trace row drives pickable", () => {
    for (const styleLayer of layerDef("survey-traces")!.styleLayers) {
      expect(PICKABLE_LAYERS, `${styleLayer} is not pickable`).toContain(styleLayer);
    }
  });
});
