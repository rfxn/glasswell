import { describe, expect, it } from "vitest";

import { LAYERS, defaultLayerSet, layerDef, layerIds, layerRowState } from "./registry.ts";

describe("the layer registry", () => {
  it("registers the three tiled layers this build actually serves", () => {
    for (const id of ["wells", "laterals", "spacing-units"]) {
      expect(layerIds()).toContain(id);
      expect(layerDef(id)?.pendingSource).toBeFalsy();
    }
  });

  it("marks a layer with no ingested source as a stub rather than shipping a dead toggle", () => {
    const play = layerDef("play-outline");
    expect(play?.pendingSource).toBe(true);
    expect(play?.defaultOn).toBe(false);
    expect(play?.provenance.kind).toBe("pending");
  });

  it("gives every layer a label, an epistemic subtitle and a provenance kind", () => {
    for (const layer of LAYERS) {
      expect(layer.label.length).toBeGreaterThan(0);
      expect(layer.subtitle.length).toBeGreaterThan(0);
      expect(["official", "derived", "basemap", "pending"]).toContain(layer.provenance.kind);
    }
  });

  it("shows wells at basin zoom — the minzoom-9 blackout is gone", () => {
    // Market research gap: `wells` was minzoom 9, so 43,817 wells were invisible at z7,
    // the app's own default viewport. Culling is per status now (see status.ts), not blanket.
    expect(layerDef("wells")?.minZoom).toBeLessThanOrEqual(4);
  });

  it("states the zoom hint on every zoom-gated layer", () => {
    for (const layer of LAYERS) {
      if (layer.minZoom > 0) expect(layer.zoomHint).toMatch(/zoom/i);
    }
  });

  it("derives the default set from the registry and nowhere else", () => {
    expect(defaultLayerSet()).toEqual(LAYERS.filter((l) => l.defaultOn).map((l) => l.id));
    expect(defaultLayerSet()).toContain("wells");
    expect(defaultLayerSet()).toContain("laterals");
  });

  it("reports a row for a retired layer as null instead of throwing", () => {
    expect(layerRowState("wells", new Set(["wells"]))).toBe(true);
    expect(layerRowState("wells", new Set())).toBe(false);
    expect(layerRowState("layer-from-a-later-release", new Set())).toBe(null);
  });

  it("names the style layers each row drives, so nothing is toggled by guesswork", () => {
    for (const layer of LAYERS) {
      if (layer.pendingSource) expect(layer.styleLayers).toEqual([]);
      else expect(layer.styleLayers.length).toBeGreaterThan(0);
    }
  });

  it("keeps the draw order the row order, so the panel mirrors the map", () => {
    const order = LAYERS.map((layer) => layer.drawOrder);
    expect(order).toEqual([...order].sort((a, b) => a - b));
  });
});
