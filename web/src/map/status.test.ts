import { describe, expect, it } from "vitest";

import { census, censusOf, measuredWellCount, resetCensus } from "./census.ts";
import { JURISDICTIONS } from "./jurisdictions.generated.ts";
import {
  SELECTION_COLOUR,
  statusVocabulary,
  STATUS_VOCAB_RULE,
  STATUS_VOCAB_RULES,
  absenceStatus,
  statusClass,
  statusColour,
  statusIds,
  statusMinZoom,
} from "./status.ts";

// The canonical set as the status rules state it, transcribed from the live rules:
// `cr_nd_status_vocab_1` gives active, plugged, dry, permitted, inactive, confidential,
// drilling, temporarily_abandoned and expired, with the permit-lifecycle terminal codes
// collapsing to expired; `cr_tx_status_vocab_1` adds service, which eleven of the RRC's
// twenty-three well types map to and which is not a producer; `cr_nm_wellhistory_status_vocab_2`
// adds documented_unmapped, for the four OCD codes it maps to no equivalent rather than to null.
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
  "documented_unmapped",
];

describe("the status catalogue", () => {
  it("covers the canonical vocabulary exactly — no extras, no omissions", () => {
    // UX P1-5: the shipped legend listed `producing` (0 wells) and omitted dry, expired and
    // temporarily_abandoned — 12,339 of 43,817 wells rendering as an unlabelled grey.
    expect([...statusIds()].sort()).toEqual([...CANONICAL].sort());
    expect(statusIds()).not.toContain("producing");
  });

  it("cites the conformance rule that defines the vocabulary", () => {
    // The value is a registry row now, not a literal here: the generated module is rendered
    // from the same seed the parity gate holds to the migration's rows.
    expect(STATUS_VOCAB_RULE).toBe(JURISDICTIONS.ND.rules["status_vocabulary"]);
    // A class carries the rule that *declared* it, which is the domain's own, not the
    // per-regulator mapping rule it used to cite. Which codes reach a class is that regulator's
    // fact and resolves at /conformance; a class is not one jurisdiction's to own.
    const declaring = new Set(
      statusVocabulary().map((status) => status.rule),
    );
    expect(declaring.size).toBe(2);
    for (const rule of declaring) {
      expect(rule).toMatch(/^cr_status_/);
      expect(STATUS_VOCAB_RULES as readonly string[]).not.toContain(rule);
    }
    expect(statusClass("service").rule).toBe(statusClass("active").rule);
    expect(absenceStatus()!.rule).not.toBe(statusClass("active").rule);
    expect([...STATUS_VOCAB_RULES].sort()).toEqual(
      [
        ...new Set(Object.values(JURISDICTIONS).map((row) => row.rules["status_vocabulary"])),
      ].sort(),
    );
  });

  it("does not give absence the quarantine colour, or confidential's hue", () => {
    // TX has 65,685 wells the regulator gave no status: an absence, not a rule failure. In the
    // old amber it painted 19.7% of the canvas at z12 against active's 8.9%, in the same hue
    // family as ND's `confidential` — the colour for "withheld on purpose".
    expect(absenceStatus()!.colour).not.toBe("#B57A18");
    expect(statusClass("confidential").colour).toBe("#E4A33C");
    const hue = (hex: string): number => {
      const [r = 0, g = 0, b = 0] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
      const max = Math.max(r, g, b);
      const min = Math.min(r, g, b);
      if (max === min) return 0;
      const d = max - min;
      const h =
        max === r ? (g - b) / d + (g < b ? 6 : 0) : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
      return (h * 60) % 360;
    };
    expect(Math.abs(hue(absenceStatus()!.colour) - hue(statusClass("confidential").colour))).
      toBeGreaterThan(20);
  });

  it("still draws absence at every zoom, because a gap must not be what hides", () => {
    expect(absenceStatus()!.minZoom).toBe(0);
  });

  it("reserves the selection colour: no status may paint with it", () => {
    for (const status of statusVocabulary()) {
      expect(status.colour.toLowerCase()).not.toBe(SELECTION_COLOUR.toLowerCase());
    }
  });

  it("gives every class a distinct colour-and-glyph pair", () => {
    const seen = statusVocabulary().filter((s) => !s.isAbsence).map((status) => `${status.colour}/${status.glyph}`);
    expect(new Set(seen).size).toBe(seen.length);
  });

  it("labels every class and states its epistemic caveat", () => {
    for (const status of statusVocabulary()) {
      expect(status.label.length).toBeGreaterThan(0);
      expect(status.note.length).toBeGreaterThan(0);
    }
  });

  it("strikes through the terminal classes, per the ND DMR and RRC convention", () => {
    // Plugging is a modifier on the fluid glyph, not a colour of its own (market §3.1).
    expect(statusClass("plugged").glyph).toBe("struck");
    expect(statusClass("dry").glyph).toBe("struck-hollow");
  });

  it("routes an unknown status to a labelled absence class, never to a silent default", () => {
    const unknown = statusClass("horizontal-something-new");
    expect(unknown).toBe(absenceStatus()!);
    expect(unknown.label).toMatch(/unmapped/i);
    // The note names no rule and no regulator: it states both cases and says the filed code
    // beside the class is what tells them apart, which is the served text rather than a
    // sentence this file wrote about one jurisdiction's codebook.
    expect(unknown.note).toMatch(/filed no status/i);
    expect(unknown.note).not.toContain(STATUS_VOCAB_RULE);
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
    expect(statusColour("")).toBe(absenceStatus()!.colour);
  });

  it("takes its census from the served registry rather than from four undated maps", () => {
    // The four MEASURED_*_WELL_COUNTS tables were hand-read against the deployed database and
    // carried no date, so a legend built from them claimed whatever somebody last measured.
    // The census comes from /v1/jurisdictions now, which serves each count with the derivation
    // that produced it and the date it was measured on — and answers "unknown", never zero.
    resetCensus();
    expect(measuredWellCount("active")).toBeNull();

    resetCensus(
      censusOf([
        {
          well_count: { value: "40" },
          measured_on: "2026-09-01",
          well_counts_by_status: [
            { status_canonical: "active", wells: { value: "25" } },
            { status_canonical: "plugged", wells: { value: "15" } },
          ],
        },
        // Registered and never refreshed: absent, and absent is not a zero to be added in.
        { well_count: null, measured_on: null },
      ]),
    );

    expect(measuredWellCount("active")).toBe(25);
    expect(measuredWellCount("plugged")).toBe(15);
    // Absent from the census, not measured at zero in it. The registry serves a row for a
    // class it counted; a class no row names is one nothing has measured, and reading that as
    // a zero is what hid the absence class over Texas.
    expect(measuredWellCount("service")).toBeNull();
    expect(census().total).toBe(40);
    expect(census().measuredOn).toBe("2026-09-01");
    expect(census().degraded).toBe(false);
    resetCensus();
  });
});
