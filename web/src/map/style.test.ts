import { featureFilter } from "@maplibre/maplibre-gl-style-spec";
import { describe, expect, it } from "vitest";
import type { LayerSpecification } from "maplibre-gl";

import type { BasemapVariant } from "./basemap.ts";
import { DISPOSAL_COLOUR } from "./disposal.ts";
import { LAYERS } from "./registry.ts";
import { METRICS_SECTIONS_SOURCE, METRICS_TOWNSHIPS_SOURCE } from "./thematics.ts";
import { variantStyle } from "./variant-style.ts";
import {
  LATERALS_SOURCE,
  OPACITY_OVERRIDE,
  SECTIONS_SOURCE,
  SOURCE_ID,
  SPACING_SOURCE,
  TOWNSHIPS_SOURCE,
  TRACES_SOURCE,
  TRACE_COLOUR,
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

  it("draws the survey trace as its own line, selection branch over the provenance colour", () => {
    const trace = dataLayers().find((layer) => layer.id === "survey-traces");
    expect(trace?.type).toBe("line");
    expect(trace?.minzoom).toBe(8);
    const colour = JSON.stringify(paintOf(trace)["line-color"]);
    expect(colour).toContain("feature-state");
    expect(colour).toContain(SELECTION_COLOUR);
    expect(colour).toContain(TRACE_COLOUR);
  });

  it("keeps the trace outside the status gate: it paints provenance, not status", () => {
    // Deliberate, not an omission: what the layer distinguishes is the filed survey path
    // from the GIS centreline, and a status-keyed trace would vanish into its own lateral.
    expect(statusStyledLayerIds()).not.toContain("survey-traces");
    const trace = dataLayers().find((layer) => layer.id === "survey-traces");
    expect(JSON.stringify(paintOf(trace))).not.toContain("status_canonical");
  });

  it("rings the disposal class from the wells source, filtered on the regulator's codes", () => {
    const ring = dataLayers().find((layer) => layer.id === "disposal-wells");
    expect(ring?.type).toBe("circle");
    expect(ring && "source" in ring ? ring.source : "").toBe(WELLS_SOURCE);
    expect(ring?.minzoom).toBe(8);
    const inClass = (code: string | null): boolean =>
      featureFilter((ring && "filter" in ring ? ring.filter : ["==", 1, 2]) as never).filter(
        { zoom: 12 } as never,
        { type: 1, properties: { well_type_reported: code } } as never,
        undefined as never,
      );
    expect(inClass("SWD")).toBe(true);
    expect(inClass("WI")).toBe(true);
    expect(inClass("OG")).toBe(false);
    expect(inClass(null)).toBe(false);
  });

  it("keeps the ring hollow with the selection branch on its stroke, over a visible status dot", () => {
    const ring = dataLayers().find((layer) => layer.id === "disposal-wells");
    const paint = paintOf(ring);
    // The fill is transparent by design: the wells row's status colour stays legible inside.
    expect(paint["circle-color"]).toBe("rgba(0, 0, 0, 0)");
    const stroke = JSON.stringify(paint["circle-stroke-color"]);
    expect(stroke).toContain("feature-state");
    expect(stroke).toContain(SELECTION_COLOUR);
    expect(stroke).toContain(DISPOSAL_COLOUR);
  });

  it("hands the opacity slider the ring's stroke, because its default slot paints nothing", () => {
    // OPACITY_PROPERTY maps circle to circle-opacity — the transparent fill. The metadata
    // override is what keeps the panel's slider from being a control that does nothing.
    const ring = dataLayers().find((layer) => layer.id === "disposal-wells");
    const metadata = (ring && "metadata" in ring ? ring.metadata : {}) as Record<string, unknown>;
    expect(metadata[OPACITY_OVERRIDE]).toBe("circle-stroke-opacity");
  });

  it("pins the ring's stroke weights, so base drift fails a test (gate-webpolish R3)", () => {
    // Selection adds weight, not just the cyan (visual-m17 judgment 3); both registers are
    // load-bearing, so both ladders are pinned, not only the hue.
    const ring = dataLayers().find((layer) => layer.id === "disposal-wells");
    const width = paintOf(ring)["circle-stroke-width"] as unknown[];
    expect(width.slice(0, 3)).toEqual(["interpolate", ["linear"], ["zoom"]]);
    const stops = width.slice(3);
    const zooms: unknown[] = [];
    const selected: unknown[] = [];
    const bases: unknown[] = [];
    for (let at = 0; at < stops.length; at += 2) {
      zooms.push(stops[at]);
      const value = stops[at + 1] as unknown[];
      expect(value[0]).toBe("case");
      selected.push(value[2]);
      bases.push(value[3]);
    }
    expect(zooms).toEqual([8, 12, 15]);
    expect(bases).toEqual([1.2, 1.6, 2.2]);
    expect(selected).toEqual([2.4, 3, 3.8]);
  });

  it("keeps the ring outside the status gate: it paints a well type, not a status", () => {
    // Deliberate, the trace's own reasoning one layer over: the filter slot carries the
    // class, and the status filter has no claim on it.
    expect(statusStyledLayerIds()).not.toContain("disposal-wells");
    const ring = dataLayers().find((layer) => layer.id === "disposal-wells");
    expect(JSON.stringify(paintOf(ring))).not.toContain("status_canonical");
  });

  it("promotes api10 on the traces source, so selecting a well lights its trace too", () => {
    const spec = sourceSpecs()[TRACES_SOURCE];
    expect(spec && "promoteId" in spec ? spec.promoteId : undefined).toEqual({
      nd_survey_traces: "api10",
    });
  });

  it("registers every style layer the registry claims to drive", () => {
    const rendered = new Set(dataLayers({ labels: true }).map((layer) => layer.id));
    for (const layer of LAYERS) {
      for (const id of layer.styleLayers) {
        expect(rendered.has(id), `${id} missing from the style`).toBe(true);
      }
    }
    expect(rendered.has("tx-laterals")).toBe(true);
  });

  it("draws each row at the zoom its own registry entry advertises", () => {
    // The panel's out-of-scale mark and the canvas read one number each, declared in two
    // files. They were only ever equal by hand: a row that says "visible at zoom 8" over a
    // layer with no floor is a promise the map does not keep, in the direction the reader
    // cannot see.
    for (const layer of LAYERS) {
      if (layer.styleLayers.length === 0) continue;
      const floors = dataLayers({ labels: true })
        .filter((built) => layer.styleLayers.includes(built.id))
        .map((built) => built.minzoom ?? 0);
      expect(Math.min(...floors), `${layer.id} draws below its own minZoom`).toBe(layer.minZoom);
    }
  });

  it("holds both basins' laterals to the same gate, so one toggle means one thing", () => {
    const floors = dataLayers()
      .filter((layer) => layer.id === "laterals" || layer.id === "tx-laterals")
      .map((layer) => layer.minzoom);
    expect(floors).toEqual([8, 8]);
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
    // The z7 laterals tile is 2,037,023 B (api/routers/tiles.py), and z0-z7 is where the tile
    // tier thins the layer to a sample. The gate takes both basins' lateral tiles off the wire
    // below z8 rather than paying for geometry the canvas cannot resolve.
    expect(floor(LATERALS_SOURCE)).toBe(8);
    expect(floor(TX_LATERALS_SOURCE)).toBe(8);
    // The traces publish from z4 server-side; the client draws from z8, so it fetches from z8.
    expect(floor(TRACES_SOURCE)).toBe(8);
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

describe("the land grid (M1-4)", () => {
  it("draws the grid beneath every data layer — reference linework, never over", () => {
    const built = ids();
    // The thematic wash sits under even the reference grid (M2-3): the grid must stay
    // readable over the fill, and the fill is context beneath everything.
    expect(built[0]).toBe("land-township-metrics-fill");
    expect(built[1]).toBe("land-section-metrics-fill");
    expect(built[2]).toBe("land-townships-line");
    expect(built[3]).toBe("land-sections-line");
  });

  it("gates sections two zooms deeper than the townships they subdivide", () => {
    const byId = new Map(dataLayers().map((layer) => [layer.id, layer]));
    expect(byId.get("land-townships-line")?.minzoom).toBe(8);
    expect(byId.get("land-sections-line")?.minzoom).toBe(10);
  });

  it("paints both grid layers the variant's neutral, not one constant for every substrate", () => {
    // The M2-4 / VF-5 class fix: the one colour that cleared dark and light measured ~1.1:1
    // over the satellite mid-tone, so the grid keys to the variant like every other line.
    for (const id of ["land-townships-line", "land-sections-line"]) {
      for (const variant of ["dark", "light", "satellite", "none"] as BasemapVariant[]) {
        const layer = dataLayers({ variant }).find((built) => built.id === id);
        const paint = (layer?.paint ?? {}) as Record<string, unknown>;
        expect(paint["line-color"], `${id} on ${variant}`).toBe(variantStyle(variant).grid);
      }
    }
  });

  it("splits geometry and labels: the label layers exist only when glyphs do", () => {
    const withoutLabels = ids();
    expect(withoutLabels).not.toContain("land-townships-label");
    expect(withoutLabels).not.toContain("land-sections-label");
    const withLabels = dataLayers({ labels: true }).map((layer) => layer.id);
    expect(withLabels).toContain("land-townships-label");
    expect(withLabels).toContain("land-sections-label");
  });

  it("derives each land source's floor from its own layers, not a shared gate", () => {
    const specs = sourceSpecs("https://gw.example", "?");
    expect((specs[TOWNSHIPS_SOURCE] as { minzoom?: number }).minzoom).toBe(8);
    expect((specs[SECTIONS_SOURCE] as { minzoom?: number }).minzoom).toBe(10);
  });

  it("promotes the land unit id, not a well spine key, as the feature id", () => {
    const specs = sourceSpecs("https://gw.example", "?");
    const townships = specs[TOWNSHIPS_SOURCE] as { promoteId?: Record<string, string> };
    const sections = specs[SECTIONS_SOURCE] as { promoteId?: Record<string, string> };
    expect(townships.promoteId).toEqual({ [TOWNSHIPS_SOURCE]: "land_unit_id" });
    expect(sections.promoteId).toEqual({ [SECTIONS_SOURCE]: "land_unit_id" });
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
      "&tx_wells=..%2F..%2Fetc%2Fshadow&tx_laterals=gw-evil-layer&traces=..%2F..%2Fetc%2Fpasswd" +
      "&townships=..%2F..%2Fetc%2Fpasswd&sections=gw-evil-layer" +
      "&township_metrics=..%2F..%2Fetc%2Fpasswd&section_metrics=gw-evil-layer";
    const specs = sourceSpecs("https://gw.example", search);
    expect(Object.keys(specs).sort()).toEqual(
      [
        WELLS_SOURCE,
        LATERALS_SOURCE,
        SPACING_SOURCE,
        TX_WELLS_SOURCE,
        TX_LATERALS_SOURCE,
        TRACES_SOURCE,
        TOWNSHIPS_SOURCE,
        SECTIONS_SOURCE,
        METRICS_TOWNSHIPS_SOURCE,
        METRICS_SECTIONS_SOURCE,
      ].sort(),
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

describe("the disposal ring's selected state", () => {
  it("adds weight over the base ring at every zoom stop (visual-m17 judgment 3)", () => {
    // The cyan flip alone is a close hue pair against teal at small radii; width is the
    // register hue does not carry, so selection must outweigh the base at each stop.
    const ring = dataLayers().find((layer) => layer.id === "disposal-wells");
    const width = paintOf(ring)["circle-stroke-width"] as unknown[];
    expect(width[0]).toBe("interpolate");
    const outputs = width.slice(3).filter((_, index) => index % 2 === 1) as unknown[][];
    expect(outputs.length).toBeGreaterThanOrEqual(3);
    for (const output of outputs) {
      const [kind, , selected, base] = output as [string, unknown, number, number];
      expect(kind).toBe("case");
      expect(typeof selected).toBe("number");
      expect(typeof base).toBe("number");
      expect(selected).toBeGreaterThan(base);
    }
  });
});
