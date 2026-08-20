import { describe, expect, it } from "vitest";
import type { LayerSpecification } from "maplibre-gl";

import type { BasemapVariant } from "./basemap.ts";
import { variantStyle } from "./variant-style.ts";
import {
  LATERALS_SOURCE,
  WELLS_SOURCE,
  dataLayers,
  sourceSpecs,
  statusFilter,
  visibleStatusesAt,
} from "./style.ts";
import { SELECTION_COLOUR, STATUS_CLASSES } from "./status.ts";

const ids = (): string[] => dataLayers().map((layer) => layer.id);

const paintOf = (layer?: LayerSpecification): Record<string, unknown> =>
  ((layer && "paint" in layer && layer.paint) || {}) as Record<string, unknown>;
const layoutOf = (layer?: LayerSpecification): Record<string, unknown> =>
  ((layer && "layout" in layer && layer.layout) || {}) as Record<string, unknown>;

describe("the data layers", () => {
  it("no longer ships a duplicate *-selected layer per source", () => {
    // Market Tier 1: `promoteId` + `feature-state` replaces the filter-layer pair, so a
    // selection is a state change on one feature, not a second layer of the same geometry.
    expect(ids().filter((id) => id.endsWith("-selected"))).toEqual([]);
  });

  it("promotes api10 to the feature id on both well sources", () => {
    const specs = sourceSpecs();
    const promoteId = (id: string): unknown => {
      const spec = specs[id];
      return spec && "promoteId" in spec ? spec.promoteId : undefined;
    };
    expect(promoteId(WELLS_SOURCE)).toEqual({ nd_wells: "api10" });
    expect(promoteId(LATERALS_SOURCE)).toEqual({ nd_laterals: "api10" });
  });

  it("paints selection from feature-state, in a colour no status uses", () => {
    const wells = dataLayers().find((layer) => layer.id === "wells");
    const paint = JSON.stringify(wells && "paint" in wells ? wells.paint : {});
    expect(paint).toContain("feature-state");
    expect(paint).toContain(SELECTION_COLOUR);
    for (const status of STATUS_CLASSES) {
      expect(status.colour).not.toBe(SELECTION_COLOUR);
    }
  });

  it("renders wells from basin zoom instead of blanking them below zoom 9", () => {
    const wells = dataLayers().find((layer) => layer.id === "wells");
    expect(wells?.minzoom).toBeLessThanOrEqual(4);
  });

  it("culls wells by status importance as the zoom falls, and keeps the active ones", () => {
    expect(visibleStatusesAt(4)).toContain("active");
    expect(visibleStatusesAt(4)).toContain("drilling");
    expect(visibleStatusesAt(4)).not.toContain("plugged");
    expect(visibleStatusesAt(4)).not.toContain("expired");
    expect(visibleStatusesAt(9).sort()).toEqual(STATUS_CLASSES.map((s) => s.id).sort());
  });

  it("keeps an unmapped status visible at every zoom, so a data defect cannot hide", () => {
    const filter = JSON.stringify(statusFilter(4, new Set(visibleStatusesAt(4))));
    expect(filter).toContain("unmapped");
  });

  it("intersects the zoom gate with the legend's own filter", () => {
    const filter = JSON.stringify(statusFilter(12, new Set(["active"])));
    expect(filter).toContain("active");
    expect(filter).not.toContain("plugged");
  });

  it("draws the struck-through modifier only where a single well is legible", () => {
    const struck = dataLayers().find((layer) => layer.id === "wells-struck");
    expect(struck?.type).toBe("symbol");
    expect(struck?.minzoom).toBeGreaterThanOrEqual(10);
    const layout = struck && "layout" in struck ? struck.layout : {};
    // Collision detection on 13,663 terminal wells is the hidden cost of a symbol layer.
    expect(layout).toMatchObject({ "icon-allow-overlap": true, "icon-ignore-placement": true });
  });

  it("grades lateral width by length and zoom rather than by hue", () => {
    const laterals = dataLayers().find((layer) => layer.id === "laterals");
    const width = JSON.stringify(laterals && "paint" in laterals ? laterals.paint : {});
    expect(width).toContain("lateral_length_ft");
    expect(width).toContain("zoom");
  });

  it("registers every style layer the registry claims to drive", () => {
    const rendered = new Set(ids());
    for (const id of ["wells", "wells-struck", "laterals", "spacing-units-fill", "spacing-units-line"]) {
      expect(rendered.has(id), `${id} missing from the style`).toBe(true);
    }
  });

  it("paints its own label for the basemap under it, not for the dark one only", () => {
    const label = (variant: BasemapVariant): LayerSpecification | undefined =>
      dataLayers({ labels: true, variant }).find((layer) => layer.id === "spacing-units-label");
    for (const variant of ["dark", "light", "satellite", "none"] as const) {
      const tokens = variantStyle(variant);
      expect(paintOf(label(variant))).toMatchObject({
        "text-color": tokens.primary.colour,
        "text-halo-color": tokens.primary.halo,
        "text-halo-width": tokens.primary.haloWidth,
      });
    }
    // VF-5 asks for the size bump where the substrate is imagery, and only there.
    expect(layoutOf(label("satellite"))["text-size"]).toBe(11);
    expect(layoutOf(label("dark"))["text-size"]).toBe(10);
  });

  it("keeps the selection branch over the variant colour on the spacing-unit outline", () => {
    // The variant keys the resting colour; feature-state still wins over it when selected.
    const line = dataLayers({ variant: "light" }).find((layer) => layer.id === "spacing-units-line");
    const colour = JSON.stringify(paintOf(line)["line-color"]);
    expect(colour).toContain("feature-state");
    expect(colour).toContain(SELECTION_COLOUR);
    expect(colour).toContain(variantStyle("light").spacing);
  });

  it("declares no layer property with an undefined value", () => {
    for (const layer of dataLayers()) {
      for (const [key, value] of Object.entries(layer)) {
        expect(value, `${layer.id}.${key} is undefined`).toBeDefined();
      }
    }
  });
});
