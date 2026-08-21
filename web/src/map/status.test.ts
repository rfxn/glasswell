import { describe, expect, it } from "vitest";

import {
  MEASURED_TX_WELL_COUNTS,
  MEASURED_WELL_COUNTS,
  SELECTION_COLOUR,
  STATUS_CLASSES,
  STATUS_VOCAB_RULE,
  STATUS_VOCAB_RULES,
  UNMAPPED_STATUS,
  statusClass,
  statusColour,
  measuredWellCount,
  statusIds,
  statusMinZoom,
} from "./status.ts";

// The canonical set as the two status rules state it, transcribed from the live rules:
// `cr_nd_status_vocab_1` gives active, plugged, dry, permitted, inactive, confidential,
// drilling, temporarily_abandoned and expired, with the permit-lifecycle terminal codes
// collapsing to expired; `cr_tx_status_vocab_1` adds service, which eleven of the RRC's
// twenty-three well types map to and which is not a producer.
const CANONICAL = [
  "active",
  "plugged",
  "dry",
  "permitted",
  "inactive",
  "confidential",
  "drilling",
  "temporarily_abandoned",
  "expired",
  "service",
];

describe("the status catalogue", () => {
  it("covers the canonical vocabulary exactly — no extras, no omissions", () => {
    // UX P1-5: the shipped legend listed `producing` (0 wells) and omitted dry, expired and
    // temporarily_abandoned — 12,339 of 43,817 wells rendering as an unlabelled grey.
    expect([...statusIds()].sort()).toEqual([...CANONICAL].sort());
    expect(statusIds()).not.toContain("producing");
  });

  it("cites the conformance rule that defines the vocabulary", () => {
    expect(STATUS_VOCAB_RULE).toBe("cr_nd_status_vocab_1");
    // A class carries the rule that put it in the vocabulary, and every one of those rules is
    // named in STATUS_VOCAB_RULES, which is what the legend prints.
    for (const status of STATUS_CLASSES) {
      expect(STATUS_VOCAB_RULES as readonly string[]).toContain(status.rule);
    }
    expect(statusClass("service").rule).toBe("cr_tx_status_vocab_1");
  });

  it("reserves the selection colour: no status may paint with it", () => {
    for (const status of [...STATUS_CLASSES, UNMAPPED_STATUS]) {
      expect(status.colour.toLowerCase()).not.toBe(SELECTION_COLOUR.toLowerCase());
    }
  });

  it("gives every class a distinct colour-and-glyph pair", () => {
    const seen = STATUS_CLASSES.map((status) => `${status.colour}/${status.glyph}`);
    expect(new Set(seen).size).toBe(seen.length);
  });

  it("labels every class and states its epistemic caveat", () => {
    for (const status of [...STATUS_CLASSES, UNMAPPED_STATUS]) {
      expect(status.label.length).toBeGreaterThan(0);
      expect(status.note.length).toBeGreaterThan(0);
    }
  });

  it("strikes through the terminal classes, per the ND DMR and RRC convention", () => {
    // Plugging is a modifier on the fluid glyph, not a colour of its own (market §3.1).
    expect(statusClass("plugged").glyph).toBe("struck");
    expect(statusClass("dry").glyph).toBe("struck-hollow");
  });

  it("routes an unknown status to a labelled quarantine class, never to a silent default", () => {
    const unknown = statusClass("horizontal-something-new");
    expect(unknown).toBe(UNMAPPED_STATUS);
    expect(unknown.label).toMatch(/unmapped/i);
    expect(unknown.note).toContain(STATUS_VOCAB_RULE);
  });

  it("gates the low-information classes to higher zooms and the rest to basin zoom", () => {
    // OpenInfraMap's importance predicate: cull by significance, never a blanket minzoom.
    expect(statusMinZoom("active")).toBeLessThanOrEqual(4);
    expect(statusMinZoom("drilling")).toBeLessThanOrEqual(4);
    expect(statusMinZoom("plugged")).toBeGreaterThan(statusMinZoom("active"));
    expect(statusMinZoom("expired")).toBeGreaterThan(statusMinZoom("permitted"));
    expect(statusMinZoom("horizontal-something-new")).toBeLessThanOrEqual(4);
  });

  it("resolves a colour for a known status and for anything else", () => {
    expect(statusColour("active")).toBe(statusClass("active").colour);
    expect(statusColour("")).toBe(UNMAPPED_STATUS.colour);
  });

  it("records the measured well counts for every canonical status", () => {
    // Per basin, and every class is measured somewhere: ND draws no service well and TX draws
    // no dry hole, so a single table would have had to claim a zero neither slice measured.
    for (const id of CANONICAL) expect(measuredWellCount(id)).toBeGreaterThan(0);
    expect(Object.values(MEASURED_WELL_COUNTS).reduce((sum, n) => sum + n, 0)).toBe(43_817);
    expect(Object.values(MEASURED_TX_WELL_COUNTS).reduce((sum, n) => sum + n, 0)).toBe(289_447);
    expect(MEASURED_WELL_COUNTS["service"]).toBeUndefined();
    expect(MEASURED_TX_WELL_COUNTS["dry"]).toBeUndefined();
  });
});
