import { featureFilter } from "@maplibre/maplibre-gl-style-spec";
import { describe, expect, it } from "vitest";
import type { LayerSpecification } from "maplibre-gl";

import type { BasemapVariant } from "./basemap.ts";
import { variantStyle } from "./variant-style.ts";
import {
  LATERALS_SOURCE,
  SOURCE_ID,
  SPACING_SOURCE,
  TX_LATERALS_SOURCE,
  TX_WELLS_SOURCE,
  WELLS_SOURCE,
  dataLayers,
  publishedSource,
  sourceSpecs,
  statusFilter,
  statusStyledLayerIds,
  visibleStatusesAt,
} from "./style.ts";
import {
  SELECTION_COLOUR,
  STATUS_CLASSES,
  UNMAPPED_STATUS,
  filterableStatusIds,
  statusIds,
} from "./status.ts";

const ids = (): string[] => dataLayers().map((layer) => layer.id);

/** Whether a well carrying this `status_canonical` is drawn — evaluated, not pattern-matched. */
const draws = (filter: unknown, status: string | null, atZoom = 12): boolean =>
  featureFilter(filter as never).filter({ zoom: atZoom } as never, {
    type: 1,
    properties: { status_canonical: status },
  } as never, undefined as never);

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

  it("keeps an unmapped status in scale at every zoom, so a data defect cannot hide", () => {
    const on = new Set([...visibleStatusesAt(4), UNMAPPED_STATUS.id]);
    expect(draws(statusFilter(4, on), null, 4)).toBe(true);
    expect(draws(statusFilter(4, on), "plugged", 4)).toBe(false);
  });

  it("withdraws the unmapped class when the reader filters it off, like any other class", () => {
    // On the Permian slice it is the largest class on the canvas; a row nobody can switch off
    // is the one class whose ink the reader cannot answer for.
    expect(draws(statusFilter(12, new Set(statusIds())), null)).toBe(false);
    expect(draws(statusFilter(12, new Set(filterableStatusIds())), null)).toBe(true);
  });

  it("draws a status it cannot name as the absence class, rather than not at all", () => {
    // The count path routes any unrecognised code to `unmapped` (statusClass), so a filter that
    // matched only the literal id disagreed with it: a well whose status was present but not in
    // `cr_nd_status_vocab_1` was dropped from the canvas, the count and the key at once.
    const all = statusFilter(12, new Set(filterableStatusIds()));
    expect(draws(all, "wildcat_unknown")).toBe(true);
    expect(draws(all, "")).toBe(true);
    expect(draws(all, "ACTIVE")).toBe(true);
    expect(draws(statusFilter(12, new Set(statusIds())), "wildcat_unknown")).toBe(false);
  });

  it("gates every layer the status vocabulary paints, and only where the filter slot is free", () => {
    // 4.1's live half: the gate used to be applied to a hand-written pair of layer ids at
    // style-build time, so a second basin's layers drew every class at every zoom until the
    // reader happened to zoom. `wells-struck` is excluded because it carries its own filter,
    // and setting the gate on it would replace the strike-through's own one.
    const gated = new Set(statusStyledLayerIds());
    for (const layer of dataLayers({ labels: true })) {
      const paintsStatus = JSON.stringify(paintOf(layer)).includes("status_canonical");
      const ownFilter = "filter" in layer;
      expect(gated.has(layer.id), `${layer.id} gated=${gated.has(layer.id)}`).toBe(
        paintsStatus && !ownFilter,
      );
    }
    expect(gated.size).toBeGreaterThan(0);
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

  it("fetches no tile below the zoom its own layers start drawing at", () => {
    // Track T measured the z7 spacing tile at 568 KB against a layer that starts at z8, and
    // z7 alone is 31% of tile traffic. The source floor follows the layers, not a hand list.
    const specs = sourceSpecs();
    const floor = (source: string): unknown => {
      const spec = specs[source];
      return spec && "minzoom" in spec ? spec.minzoom : undefined;
    };
    expect(floor(SPACING_SOURCE)).toBe(8);
    expect(floor(WELLS_SOURCE)).toBe(4);
    // Laterals draw from z0, so their source still has to serve z0 — no free win there.
    expect(floor(LATERALS_SOURCE)).toBe(0);
    for (const layer of dataLayers({ labels: true })) {
      const source = "source" in layer ? String(layer.source) : "";
      expect(Number(floor(source)), `${layer.id} draws below its source floor`).toBeLessThanOrEqual(
        layer.minzoom ?? 0,
      );
    }
  });

  it("holds the tile ceiling to the mart's, because a disclosure is computed against it", () => {
    // Item 4 of work-output/tileperf-client-handoff.md. Dropping this to 13 would delete
    // 432 of 5,903 requests, but glasswell.marts.tiles.TILE_MAX_ZOOM is what the well card's
    // `below_tile_resolution` disclosure (audit A3-F5) is computed against: lowering it here
    // alone makes that disclosure understate, and a feature that only resolves at z14 would
    // silently never render. It moves as a paired change with Track T or not at all.
    for (const spec of Object.values(sourceSpecs())) {
      expect("maxzoom" in spec ? spec.maxzoom : undefined).toBe(14);
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
    // VF-5's size bump is applyVariantStyling's to apply — to this label and the basemap's
    // alike — so what is built here is the base size in every variant. variant-style.test.ts
    // holds the bump itself: 11 on satellite, 10 elsewhere, applied once.
    expect(layoutOf(label("satellite"))["text-size"]).toBe(10);
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

describe("the ?wells= / ?laterals= / ?spacing= source override (N-5)", () => {
  const named = (search: string, parameter = "wells"): string =>
    publishedSource(parameter, WELLS_SOURCE, search);

  it("takes a martin source id that matches the published shape", () => {
    expect(named("?wells=nd_wells_v2")).toBe("nd_wells_v2");
    expect(named("?laterals=a", "laterals")).toBe("a");
    expect(named(`?wells=${"a".repeat(64)}`)).toBe("a".repeat(64));
  });

  it("refuses a value that would leave the /v1/tiles/ namespace", () => {
    // Track O reproduced this in a browser: `?wells=..%2F..%2Fetc%2Fpasswd` made the app
    // request GET /etc/passwd/{z}/{x}/{y}.pbf. It 404s only because there is no SPA
    // fallback, and DR-57 would turn that 404 into index.html served to a tile parser.
    for (const hostile of [
      "../../etc/passwd",
      "..%2F..%2Fetc%2Fpasswd",
      "/etc/passwd",
      "nd_wells/../../etc/passwd",
      "http://evil.example/x",
      "//evil.example/x",
      "nd_wells?x=1",
      "nd_wells#frag",
    ]) {
      const search = `?wells=${encodeURIComponent(hostile)}`;
      expect(named(search), `${hostile} reached the source id`).toBe(WELLS_SOURCE);
      expect(sourceSpecs("https://gw.example", search)[WELLS_SOURCE]).toBeDefined();
    }
  });

  it("refuses a value that stays in the namespace but is not a published id", () => {
    for (const hostile of [
      "",
      " ",
      "gw-evil-layer",
      "ND_WELLS",
      "1nd_wells",
      "_nd_wells",
      "nd wells",
      "nd_wells\n",
      "nd_wells\nevil",
      "nd_wells;drop",
      "nd_wells'",
      '"nd_wells"',
      "a".repeat(65),
      " nd_wells",
      "nd_wells‮",
      "ndـwells",
    ]) {
      expect(named(`?wells=${encodeURIComponent(hostile)}`), `${hostile} accepted`).toBe(
        WELLS_SOURCE,
      );
    }
  });

  it("carries the refusal into every place the id is interpolated, not just the url", () => {
    // The id is the tile path, the MVT `source-layer`, and the promoteId key. A validator
    // that only guarded the url would still hand the other two an attacker's string.
    const search =
      "?wells=..%2F..%2Fetc%2Fpasswd&laterals=gw-evil-layer&spacing=%2Fetc%2Fpasswd" +
      "&tx_wells=..%2F..%2Fetc%2Fshadow&tx_laterals=gw-evil-layer";
    const specs = sourceSpecs("https://gw.example", search);
    expect(Object.keys(specs).sort()).toEqual(
      [WELLS_SOURCE, LATERALS_SOURCE, SPACING_SOURCE, TX_WELLS_SOURCE, TX_LATERALS_SOURCE].sort(),
    );
    const serialised = JSON.stringify(specs);
    expect(serialised).not.toContain("etc/passwd");
    expect(serialised).not.toContain("etc/shadow");
    expect(serialised).not.toContain("gw-evil-layer");
    for (const layer of dataLayers({ labels: true, search })) {
      const source = "source" in layer ? String(layer.source) : "";
      expect(SOURCE_ID.test(source), `${layer.id} draws from ${source}`).toBe(true);
      expect(specs[source], `${layer.id} draws from an undeclared source`).toBeDefined();
    }
  });

  it("falls back rather than throwing when there is no window to read", () => {
    expect(publishedSource("wells", WELLS_SOURCE)).toBe(WELLS_SOURCE);
  });
});
