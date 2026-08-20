import { describe, expect, it } from "vitest";

import {
  MEASURED_WELL_COUNTS,
  SELECTION_COLOUR,
  STATUS_CLASSES,
  STATUS_VOCAB_RULE,
  UNMAPPED_STATUS,
  statusClass,
  statusColour,
  statusIds,
  statusMinZoom,
} from "./status.ts";

// The canonical set as `cr_nd_status_vocab_1` states it, transcribed from the live rule:
// "The canonical set is active, plugged, dry, permitted, inactive, confidential, drilling,
//  temporarily_abandoned and expired; the permit-lifecycle terminal codes collapse to expired."
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
    for (const status of STATUS_CLASSES) expect(status.rule).toBe(STATUS_VOCAB_RULE);
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
    expect([...Object.keys(MEASURED_WELL_COUNTS)].sort()).toEqual([...CANONICAL].sort());
    const total = Object.values(MEASURED_WELL_COUNTS).reduce((sum, n) => sum + n, 0);
    expect(total).toBe(43_817);
  });
});
