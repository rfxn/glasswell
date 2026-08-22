import { describe, expect, it } from "vitest";

import { DISPOSAL_COLOUR } from "./disposal.ts";
import { LAYERS, defaultLayerSet, layerDef, layerIds, layerRowState } from "./registry.ts";
import { SELECTION_COLOUR, STATUS_CLASSES, UNMAPPED_STATUS, statusColour } from "./status.ts";
import { TRACE_COLOUR, dataLayers } from "./style.ts";

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
    // 525 of 43,824 wells carry a trace. Drawn by default it reads as "almost no wells",
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
    expect(subtitle).toMatch(/525 of 43,824/);
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
    expect(subtitle).toMatch(/1,989 of 43,824/);
    expect(subtitle).toMatch(/4\.5%/);
    expect(subtitle).toMatch(/as filed/i);
    expect(subtitle).not.toMatch(/saltwater|reserves/i);
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

  it("keeps a multi-colour swatch to the kind that can draw one", () => {
    // A dot has one ink. Handing three to it would silently drop two of them.
    for (const layer of LAYERS) {
      if (layer.swatch.colours.length > 1) expect(layer.swatch.kind).toBe("line");
    }
  });
});
