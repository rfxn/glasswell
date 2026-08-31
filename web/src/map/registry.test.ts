import { describe, expect, it } from "vitest";

import { LAND_SNAPSHOT, ND_SNAPSHOT, landCellCount, ndCoverage, ndWellCount } from "./coverage.ts";
import { DISPOSAL_COLOUR } from "./disposal.ts";
import { LAYER_FAMILIES, LAYER_GROUPS, layerFamily } from "./groups.ts";
import {
  LAYERS,
  defaultLayerSet,
  familyMembers,
  familyState,
  groupEntries,
  groupedLayers,
  layerDef,
  layerIds,
  layerRowState,
} from "./registry.ts";
import { SELECTION_COLOUR, STATUS_CLASSES, UNMAPPED_STATUS, statusColour } from "./status.ts";
import { TRACE_COLOUR, WELL_POINT_LAYERS, dataLayers } from "./style.ts";

describe("the layer registry", () => {
  it("registers the four tiled rows this build actually serves", () => {
    for (const id of ["wells", "lateral-bores", "spacing-units", "tx-wells"]) {
      expect(layerIds()).toContain(id);
      expect(layerDef(id)?.pendingSource).toBeFalsy();
    }
  });

  it("marks a layer with no ingested source as a stub rather than shipping a dead toggle", () => {
    const play = layerDef("play-outline");
    expect(play?.pendingSource).toBe(true);
    expect(play?.defaultOn).toBe(false);
    expect(play?.provenance[0]?.kind).toBe("pending");
  });

  it("gives every layer a label, an epistemic subtitle and a provenance kind", () => {
    for (const layer of LAYERS) {
      expect(layer.label.length).toBeGreaterThan(0);
      expect(layer.subtitle.length).toBeGreaterThan(0);
      expect(layer.provenance.length).toBeGreaterThan(0);
      for (const source of layer.provenance) {
        expect(["official", "derived", "basemap", "pending"]).toContain(source.kind);
      }
    }
  });

  it("keeps one provenance kind per row, which is what the badge claims for all of them", () => {
    // The row shows a single badge. A row whose sources disagreed about their kind would be
    // making a claim about the second one that only the first supports.
    for (const layer of LAYERS) {
      const kinds = new Set(layer.provenance.map((source) => source.kind));
      expect([...kinds], `${layer.id} carries ${kinds.size} provenance kinds`).toHaveLength(1);
    }
  });

  it("shows wells at basin zoom — the minzoom-9 blackout is gone", () => {
    // Market research gap: `wells` was minzoom 9, so 43,817 wells were invisible at z7,
    // the app's own default viewport. Culling is per status now (see status.ts), not blanket.
    expect(layerDef("wells")?.minZoom).toBeLessThanOrEqual(4);
  });

  it("states the zoom hint on every zoom-gated layer, in the row's own numbers", () => {
    for (const layer of LAYERS) {
      if (layer.minZoom === 0) continue;
      expect(layer.zoomHint).toMatch(/zoom/i);
      // The hint is what the panel says while the row is out of scale. A hint that named a
      // different zoom than the gate would be the one statement the reader could act on.
      expect(layer.zoomHint, `${layer.id} hint omits its own minZoom`).toContain(
        String(layer.minZoom),
      );
    }
  });

  it("derives the default set from the registry and nowhere else", () => {
    expect(defaultLayerSet()).toEqual(LAYERS.filter((l) => l.defaultOn).map((l) => l.id));
    expect(defaultLayerSet()).toContain("wells");
  });

  it("puts Texas wells on by default so panning there shows them without hunting the panel", () => {
    // The default viewport stays over North Dakota; a reader who moves to the Permian gets
    // the same point layer, drawn from the same expressions, with no toggle in between.
    expect(defaultLayerSet()).toContain("tx-wells");
    expect(layerDef("tx-wells")?.provenance[0]?.source).toBe("marts.tx_wells_tile");
  });

  it("draws both basins' laterals from one row, without blurring whose file each came from", () => {
    const laterals = layerDef("lateral-bores")!;
    expect(laterals.styleLayers).toEqual(["laterals", "tx-laterals"]);
    expect(laterals.provenance.map((source) => source.source)).toEqual([
      "marts.nd_laterals_tile",
      "marts.tx_laterals_tile",
    ]);
    // Two regulators, two lines. One toggle may not cost the reader the ability to say which
    // file a line on the canvas came out of.
    expect(laterals.provenance[0]?.label).toMatch(/ND DMR/);
    expect(laterals.provenance[1]?.label).toMatch(/TX RRC/);
  });

  it("labels every source on a row that carries more than one", () => {
    for (const layer of LAYERS) {
      if (layer.provenance.length < 2) continue;
      for (const source of layer.provenance) {
        expect(source.label?.length, `${layer.id}/${source.source} is unlabelled`).toBeGreaterThan(0);
      }
    }
  });

  it("says what a lateral is once, rather than once per state", () => {
    const laterals = layerDef("lateral-bores")!;
    expect(laterals.subtitle).toMatch(/not a directional survey/i);
    expect(laterals.subtitle.match(/directional survey/gi)).toHaveLength(1);
  });

  it("keeps laterals off until the reader asks for them", () => {
    // The owner's cut: 93,125 lines drawn over the whole basin on first paint is the map's
    // largest unrequested cost. Wells stay on — they are what the default viewport is for.
    expect(layerDef("lateral-bores")?.defaultOn).toBe(false);
    expect(defaultLayerSet()).not.toContain("lateral-bores");
    expect(defaultLayerSet()).toContain("wells");
  });

  it("gates laterals at the zoom the tile tier stops sampling them", () => {
    // marts/tiles.py THIN_MAX_ZOOM is 7: at and below it the tile keeps one feature per half
    // CSS pixel, so the layer below z8 is a sample of itself and not what the row claims.
    expect(layerDef("lateral-bores")?.minZoom).toBe(8);
    expect(layerDef("lateral-bores")?.zoomHint).toMatch(/zoom 8 and above/i);
  });

  it("registers the ND survey traces as a served row, off until the reader asks for it", () => {
    // 525 of the snapshot's 43,817 wells carry a trace. Drawn by default it reads as "almost no wells",
    // which is the coverage hole presented as a drilling fact.
    const traces = layerDef("survey-traces")!;
    expect(traces.pendingSource).toBeFalsy();
    expect(traces.defaultOn).toBe(false);
    expect(defaultLayerSet()).not.toContain("survey-traces");
    expect(traces.provenance).toEqual([
      { kind: "official", source: "marts.nd_survey_traces_tile" },
    ]);
    expect(traces.styleLayers).toEqual(["survey-traces"]);
  });

  it("states the trace coverage and its reason on the row itself", () => {
    // Obligations 1 and 2 of the seam contract (m15d-status §7): absence is the layer's
    // commonest fact, and the hole has a reason — confidential surveys never enter the
    // public extract. A row that said neither would overstate what ND filed.
    const subtitle = layerDef("survey-traces")!.subtitle;
    expect(subtitle).toContain(ndCoverage(ND_SNAPSHOT.traced));
    expect(subtitle).toMatch(/1\.2%/);
    expect(subtitle).toMatch(/confidential wells excluded/i);
    expect(subtitle).toMatch(/MD\/INC\/AZI\/TVD/);
  });

  it("never labels the trace row with a length", () => {
    // Obligation 3: the trace is the plan view of a 3-D path, so any length over it
    // measures horizontal travel, not hole length. The mart publishes no length column
    // and the row may not invent one.
    expect(layerDef("survey-traces")!.subtitle).not.toMatch(/length|\bmi\b|\bft\b/i);
  });

  it("holds the traces to the laterals' gate, so the two line layers share one scale", () => {
    // The tiles publish from z4, but at z≤7 the layer draws 586 features against ~43.8k
    // laterals. Gating at the laterals' own floor is the UI call §7 left to this track.
    expect(layerDef("survey-traces")?.minZoom).toBe(8);
    expect(layerDef("survey-traces")?.zoomHint).toMatch(/zoom 8 and above/i);
  });

  it("paints the trace by provenance, in a colour neither a status nor the selection uses", () => {
    const swatch = layerDef("survey-traces")!.swatch;
    expect(swatch.kind).toBe("line");
    expect(swatch.colours).toEqual([TRACE_COLOUR]);
    for (const status of [...STATUS_CLASSES, UNMAPPED_STATUS]) {
      expect(status.colour, `${status.id} shares the trace colour`).not.toBe(TRACE_COLOUR);
    }
    expect(TRACE_COLOUR).not.toBe(SELECTION_COLOUR);
  });

  it("registers the disposal ring as a served ND row, off until the reader asks for it", () => {
    // 4.5% of the basin drawn unasked would read as emphasis; the class is one row away.
    const disposal = layerDef("disposal-wells")!;
    expect(disposal.pendingSource).toBeFalsy();
    expect(disposal.defaultOn).toBe(false);
    expect(defaultLayerSet()).not.toContain("disposal-wells");
    expect(disposal.provenance).toEqual([{ kind: "official", source: "marts.nd_wells_tile" }]);
    expect(disposal.styleLayers).toEqual(["disposal-wells"]);
  });

  it("states the disposal coverage in the regulator's codes, never a decode of them", () => {
    // A well_type fact, not an interpretation: the row names the eight codes verbatim and
    // the count they carry. Expanding SWD in prose would be a vocabulary decision the
    // conformance register has not made (cr_nd_well_type_disposal_1 asserts no decode).
    const subtitle = layerDef("disposal-wells")!.subtitle;
    expect(subtitle).toMatch(/SWD, WI, CO2I, AI, GI, SFI, MWUI or INJP/);
    expect(subtitle).toContain(ndCoverage(ND_SNAPSHOT.disposal));
    expect(subtitle).toMatch(/4\.5%/);
    expect(subtitle).toMatch(/as filed/i);
    expect(subtitle).not.toMatch(/saltwater|reserves/i);
  });

  it("reads every ND count on the panel from one served snapshot, so two rows cannot disagree", () => {
    // gate-m17 R-6: "1,989 of 43,824" sat beside "43,817 points" in the same panel — a
    // FeatureServer vintage against the served mart. The mart is what the map draws, so its
    // snapshot is the one denominator, named with the refresh it was read from, and no row
    // may carry a hand-written wells total of its own.
    expect(ND_SNAPSHOT.refresh).toMatch(/^drv_[a-z0-9]+$/);
    expect(layerDef("wells")!.subtitle).toContain(`${ndWellCount()} points`);
    for (const id of ["survey-traces", "disposal-wells"]) {
      expect(layerDef(id)!.subtitle).toContain(`of ${ndWellCount()} wells`);
    }
    for (const layer of LAYERS) {
      const denominator = layer.subtitle.match(/of ([\d,]+) wells/);
      if (denominator) expect(denominator[1]).toBe(ndWellCount());
    }
  });

  it("holds the disposal ring to the thinning gate, like every layer the tile tier samples", () => {
    // Below z8 the wells tile keeps one feature per half CSS pixel with no regard for type,
    // so the class down there would be a random sample presented as its geography.
    expect(layerDef("disposal-wells")?.minZoom).toBe(8);
    expect(layerDef("disposal-wells")?.zoomHint).toMatch(/zoom 8 and above/i);
  });

  it("draws the disposal swatch as the ring the canvas draws, in a colour statuses do not use", () => {
    const swatch = layerDef("disposal-wells")!.swatch;
    expect(swatch.kind).toBe("ring");
    expect(swatch.colours).toEqual([DISPOSAL_COLOUR]);
    for (const status of [...STATUS_CLASSES, UNMAPPED_STATUS]) {
      expect(status.colour, `${status.id} shares the disposal colour`).not.toBe(DISPOSAL_COLOUR);
    }
    expect(DISPOSAL_COLOUR).not.toBe(SELECTION_COLOUR);
  });

  it("registers both Montana rows against the marts they read", () => {
    const wells = layerDef("mt-wells")!;
    const paths = layerDef("mt-paths")!;

    expect(wells.pendingSource).toBeFalsy();
    expect(wells.provenance).toEqual([{ kind: "official", source: "marts.mt_wells_tile" }]);
    expect(wells.styleLayers).toEqual(["mt-wells", "mt-wells-struck"]);
    expect(paths.provenance).toEqual([{ kind: "official", source: "marts.mt_paths_tile" }]);
    expect(paths.styleLayers).toEqual(["mt-paths"]);
  });

  it("puts Montana wells on by default, like the two basins beside it", () => {
    expect(defaultLayerSet()).toContain("mt-wells");
    expect(defaultLayerSet()).not.toContain("mt-paths");
  });

  it("predicts the Montana canvas rather than borrowing North Dakota's green", () => {
    // 63% of the state's mapped wells are plugged. A swatch is a prediction about the canvas.
    expect(layerDef("mt-wells")!.swatch).toEqual({
      kind: "dot",
      colours: [statusColour("plugged")],
    });
  });

  it("says on the path row that the geometry is a centreline and not a survey", () => {
    // cr_mt_paths_geometry_class_1 requires the distinction wherever the geometry is served,
    // and the layer panel is where a reader meets it before the tile properties.
    const subtitle = layerDef("mt-paths")!.subtitle;

    expect(subtitle).toMatch(/cartographic centrelines/i);
    expect(subtitle).toMatch(/never a survey/i);
    expect(subtitle).toContain("cr_mt_paths_geometry_class_1");
  });

  it("states the Montana path coverage against the wells that actually produced", () => {
    // cr_mt_paths_coverage_1: 2,836 of 20,021, not of the 42,026 surface points. A coverage
    // figure stated against the point count would overstate it sevenfold.
    const subtitle = layerDef("mt-paths")!.subtitle;

    expect(subtitle).toContain("2,836");
    expect(subtitle).toContain("20,021");
    expect(subtitle).toContain("cr_mt_paths_coverage_1");
  });

  it("puts no length figure on either Montana row, and says on the path row why not", () => {
    // The mart publishes no length column (cr_mt_paths_length_scope_1). A row carrying a
    // number in feet or miles would be the only place in the app claiming a figure nothing
    // serves — and the absence is stated rather than left for the reader to notice.
    for (const id of ["mt-paths", "mt-wells"]) {
      expect(layerDef(id)!.subtitle).not.toMatch(/[\d,.]+\s*(ft|mi|feet|miles)\b/i);
    }
    const paths = layerDef("mt-paths")!.subtitle;
    expect(paths).toMatch(/no length is served/i);
    expect(paths).toContain("cr_mt_paths_length_scope_1");
  });

  it("says on the wells row that Montana carries no basin, and why", () => {
    // The peer-ladder guard, stated where a reader can act on it: Bakken is 4.6% of the state.
    const subtitle = layerDef("mt-wells")!.subtitle;

    expect(subtitle).toMatch(/no basin/i);
    expect(subtitle).toContain("cr_mt_basin_scope_1");
    expect(subtitle).not.toMatch(/williston|bakken play/i);
  });

  it("says the Montana wells row carries a completion year and never a spud one", () => {
    expect(layerDef("mt-wells")!.subtitle).toMatch(/completion year, never a spud/i);
  });

  it("reports a row for a retired layer as null instead of throwing", () => {
    expect(layerRowState("wells", new Set(["wells"]))).toBe(true);
    expect(layerRowState("wells", new Set())).toBe(false);
    expect(layerRowState("layer-from-a-later-release", new Set())).toBe(null);
  });

  it("answers for the ids the combination retired, rather than resurrecting either", () => {
    // A shared link or a stored set from before the combination still carries `laterals` and
    // `tx-laterals`. The tri-state is the answer every consumer already guards on — the pill
    // strip skips an id it cannot resolve, the panel has no row to patch — so nothing needs an
    // alias table, and neither id can become a row that toggles half the geometry.
    for (const retired of ["laterals", "tx-laterals"]) {
      expect(layerIds()).not.toContain(retired);
      expect(layerDef(retired)).toBeUndefined();
      expect(layerRowState(retired, new Set([retired]))).toBe(null);
    }
  });

  it("names the style layers each row drives, so nothing is toggled by guesswork", () => {
    for (const layer of LAYERS) {
      if (layer.pendingSource) expect(layer.styleLayers).toEqual([]);
      else expect(layer.styleLayers.length).toBeGreaterThan(0);
    }
  });

  it("gives every built style layer exactly one owning row", () => {
    // Visibility, the opacity slider and Reset all reach a style layer through the row that
    // claims it. A layer no row claims is drawn by nothing the reader can switch off, and a
    // layer two rows claim takes whichever answer the loop reached last.
    for (const built of dataLayers({ labels: true })) {
      const owners = LAYERS.filter((layer) => layer.styleLayers.includes(built.id));
      expect(owners.map((owner) => owner.id), `${built.id} owners`).toHaveLength(1);
    }
  });

  it("censuses every wells row, so a state added later cannot be left out of the count", () => {
    // The legend's rendered-wells census reads this list (map.ts refreshDrawn). New Mexico was
    // a registered row for four states' worth of releases and never reached it, so an NM-only
    // canvas reported no census at all and a mixed one understated by every NM well drawn.
    expect([...WELL_POINT_LAYERS]).toEqual(familyMembers("wells").map((layer) => layer.id));
  });

  it("censuses each wells row through a style layer that row actually draws", () => {
    // refreshDrawn spends the same string twice — once on the switched-on set, which is keyed
    // by row id, and once on `getLayer`, which is keyed by style layer. A row whose id is not
    // also one of its style layers would census nothing and say so as a blank line.
    for (const id of WELL_POINT_LAYERS) {
      expect(layerDef(id)?.styleLayers, `${id} census layer`).toContain(id);
    }
  });

  it("keeps the draw order the row order, so the panel mirrors the map", () => {
    const order = LAYERS.map((layer) => layer.drawOrder);
    expect(order).toEqual([...order].sort((a, b) => a - b));
  });

  it("paints a swatch that predicts the canvas rather than one colour of it", () => {
    // A row drawn from `statusColourExpression()` has no colour of its own, and the two rows
    // this one replaced each predicted a canvas the other contradicted — ND green against TX
    // grey. Both survive in the combined mark, which is the only claim the data supports: the
    // row is keyed to status. The colours are read from status.ts so they cannot drift from it.
    const swatch = layerDef("lateral-bores")!.swatch;
    expect(swatch.kind).toBe("line");
    expect(swatch.colours).toEqual([statusColour("active"), statusColour("plugged")]);
    expect(swatch.colours).not.toContain(UNMAPPED_STATUS.colour);
  });

  it("keeps a multi-colour swatch to the kinds that can draw one", () => {
    // A dot has one ink. Handing three to it would silently drop two of them; the line
    // divides into segments and the fill into bands (M2-3), so only those two may carry more.
    for (const layer of LAYERS) {
      if (layer.swatch.colours.length > 1) expect(["line", "fill"]).toContain(layer.swatch.kind);
    }
  });
});

describe("the registry declares no vocabulary nothing reads", () => {
  it("files every layer under a group the panel actually renders", () => {
    // The field was removed once for being required, assigned twelve times and read by
    // nothing. It is back because `groupedLayers()` reads it and the panel draws a header per
    // group; these two assertions are what keep that true rather than the field drifting dead
    // again. A group nothing declares would render an empty band.
    const declared = new Set(LAYER_GROUPS.map((group) => group.id));
    for (const layer of LAYERS) expect(declared, layer.id).toContain(layer.group);
    expect(groupedLayers().map((entry) => entry.group.id)).toEqual([...declared]);
  });

  it("cuts the groups by what a layer is of, not by how it was derived", () => {
    // The taxonomy this field carried the first time was a lineage cut: it sat the land-grid
    // choropleth beside the well points because both are well-derived. They answer different
    // questions and a reader looking for one never wants the other, so the cut that survives
    // is the task one.
    expect(layerDef("land-metrics")!.group).not.toBe(layerDef("wells")!.group);
    expect(layerDef("land-metrics")!.group).not.toBe(layerDef("land-grid")!.group);
    expect(layerDef("wells")!.group).toBe(layerDef("lateral-bores")!.group);
    expect(layerDef("land-grid")!.group).toBe(layerDef("spacing-units")!.group);
  });

  it("hands the rows that state a snapshot's counts that snapshot's own handle", () => {
    // Both handles resolved against the deployed instance before they were wired:
    // /v1/explain?h=...&depth=full returns a chain of depth 3 for each.
    expect(layerDef("land-metrics")!.snapshot).toBe(LAND_SNAPSHOT.refresh);
    for (const id of ["wells", "disposal-wells", "survey-traces"]) {
      expect(layerDef(id)!.snapshot, id).toBe(ND_SNAPSHOT.refresh);
    }
    // A row whose numbers are literals with nothing behind them claims no handle.
    expect(layerDef("tx-wells")!.snapshot).toBeUndefined();
    expect(layerDef("land-grid")!.snapshot).toBeUndefined();
  });

  it("states the land mart's cell count on the row drawn from it, from the snapshot", () => {
    expect(layerDef("land-metrics")!.subtitle).toContain(`${landCellCount()} binned cells`);
  });
});

describe("the wells family", () => {
  it("holds the four state well-point rows and nothing else", () => {
    // The boundary is "one point per well, surface hole, differing only by which regulator
    // filed it". A path is not a well: mt-paths and survey-traces draw bore geometry, and
    // disposal-wells cuts the same points by well_type rather than by state — nesting either
    // under a parent whose children are states would read as a fifth state.
    expect(familyMembers("wells").map((layer) => layer.id)).toEqual([
      "wells", "tx-wells", "nm-wells", "mt-wells",
    ]);
    for (const sibling of ["mt-paths", "survey-traces", "disposal-wells", "lateral-bores"]) {
      expect(layerDef(sibling)!.family, `${sibling} was nested`).toBeUndefined();
    }
  });

  it("gives every member the same swatch kind, since one parent governs all of them", () => {
    for (const layer of familyMembers("wells")) expect(layer.swatch.kind).toBe("dot");
  });

  it("declares a family label wherever it declares a family, and never one without the other", () => {
    for (const layer of LAYERS) {
      expect(Boolean(layer.family), `${layer.id}`).toBe(Boolean(layer.familyLabel));
      if (layer.family) expect(LAYER_FAMILIES.map((f) => f.id)).toContain(layer.family);
    }
  });

  it("names each member by the axis it divides on, with the parent carrying the noun", () => {
    expect(layerFamily("wells")!.label).toBe("Wells");
    expect(layerFamily("wells")!.childAxis).toBe("state");
    expect(familyMembers("wells").map((layer) => layer.familyLabel)).toEqual([
      "North Dakota", "Texas", "New Mexico", "Montana",
    ]);
    // The standalone name still says what the row is: a pill reading "Texas" alone would not.
    for (const layer of familyMembers("wells")) {
      expect(layer.label).toBe(`Wells (${layer.familyLabel})`);
    }
  });

  it("keeps every member on by default, so the parent opens as one switch and not as mixed", () => {
    for (const layer of familyMembers("wells")) expect(layer.defaultOn).toBe(true);
    expect(familyState("wells", new Set(defaultLayerSet()))).toBe(true);
  });

  it("reports the parent as a readout of its members and never as a stored bit", () => {
    expect(familyState("wells", new Set())).toBe(false);
    expect(familyState("wells", new Set(["wells"]))).toBe("mixed");
    expect(familyState("wells", new Set(["wells", "tx-wells", "nm-wells"]))).toBe("mixed");
    expect(familyState("wells", new Set(["wells", "tx-wells", "nm-wells", "mt-wells"]))).toBe(true);
    // A layer outside the family cannot move the parent, in either direction.
    expect(familyState("wells", new Set(["mt-paths"]))).toBe(false);
  });
});

describe("every row states its state the same way", () => {
  // North Dakota was the unmarked default only because it was ingested first — an accident of
  // build order presented to the reader as a distinction, which gets worse with every state.
  const STATES = ["North Dakota", "Texas", "New Mexico", "Montana"];

  it("spells the state out rather than shipping a postal code the panel alone would use", () => {
    // The status page names all four in full across seventeen dataset rows and the glossary
    // does the same; the parenthesised code lived in this file and nowhere else. Spelling it
    // is the existing suffix convention with the abbreviation removed, not a third one.
    for (const layer of LAYERS) {
      expect(layer.label, `${layer.id}`).not.toMatch(/\((ND|TX|NM|MT)\)/);
    }
  });

  it("qualifies every single-state row, so no state is the unmarked default", () => {
    for (const layer of LAYERS) {
      const states = STATES.filter((state) => layer.subtitle.includes(state));
      const codes = [...layer.subtitle.matchAll(/\b(ND|TX|NM|MT)\b/g)].map((match) => match[1]);
      const single = new Set([...codes, ...states.map((state) => state.slice(0, 2))]).size === 1;
      if (!single || layer.pendingSource) continue;
      expect(layer.label, `${layer.id} names no state`).toMatch(/\(North Dakota|Texas|New Mexico|Montana\)$/);
    }
  });

  it("puts the noun first, so a scan down the list reads layers rather than states", () => {
    for (const layer of LAYERS) {
      for (const state of STATES) expect(layer.label).not.toMatch(new RegExp(`^${state}\\b`));
    }
  });
});

describe("the panel's reading order", () => {
  it("lists every layer exactly once, whether it is nested or not", () => {
    const listed = groupEntries().flatMap((entry) =>
      entry.entries.flatMap((row) => (row.kind === "family" ? row.layers : [row.layer])),
    );
    expect(listed.map((layer) => layer.id).sort()).toEqual([...layerIds()].sort());
  });

  it("stands the family where its first member stood, and lists its members inside it", () => {
    const spine = groupEntries().find((entry) => entry.group.id === "spine")!;
    expect(
      spine.entries.map((row) => (row.kind === "family" ? `family:${row.family.id}` : row.layer.id)),
    ).toEqual(["lateral-bores", "survey-traces", "mt-paths", "family:wells", "disposal-wells"]);
    const family = spine.entries.find((row) => row.kind === "family")!;
    expect(family.kind === "family" && family.layers.map((layer) => layer.id)).toEqual([
      "wells", "tx-wells", "nm-wells", "mt-wells",
    ]);
  });

  it("leaves a group with no family exactly as the flat order had it", () => {
    for (const { group, entries } of groupEntries()) {
      if (entries.some((row) => row.kind === "family")) continue;
      const flat = groupedLayers().find((entry) => entry.group.id === group.id)!;
      expect(entries.map((row) => row.kind === "layer" && row.layer.id)).toEqual(
        flat.layers.map((layer) => layer.id),
      );
    }
  });
});
