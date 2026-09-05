import { featureFilter } from "@maplibre/maplibre-gl-style-spec";
import { describe, expect, it } from "vitest";

import {
  DISPOSAL_COLOUR,
  disposalCodebook,
  DISPOSAL_WELL_TYPES,
  disposalFilter,
  disposalType,
} from "./disposal.ts";
import { SELECTION_COLOUR, statusVocabulary } from "./status.ts";
import { TRACE_COLOUR } from "./style.ts";

/** Whether a well carrying this `well_type_reported` is drawn — evaluated, not pattern-matched. */
const draws = (code: string | null): boolean =>
  featureFilter(disposalFilter() as never).filter({ zoom: 12 } as never, {
    type: 1,
    properties: { well_type_reported: code },
  } as never, undefined as never);

describe("the disposal class", () => {
  it("pins the eight codes cr_nd_well_type_disposal_1 classes, verbatim", () => {
    // The set is the conformance row's, not this file's to grow: a ninth code lands as a
    // superseding rule first, then here, citing it.
    expect([...DISPOSAL_WELL_TYPES]).toEqual([
      "SWD",
      "WI",
      "CO2I",
      "AI",
      "GI",
      "SFI",
      "MWUI",
      "INJP",
    ]);
    expect(disposalCodebook("3305300001")?.rule).toBe("cr_nd_well_type_disposal_1");
    // A jurisdiction that publishes no injection codebook has no class and no rule.
    expect(disposalCodebook("4230100001")).toBeNull();
  });

  it("draws every code in the class and nothing outside it", () => {
    for (const code of DISPOSAL_WELL_TYPES) expect(draws(code), code).toBe(true);
    // OG is 40,180 of 43,824 wells; GASD, GASC and WS are typed but not injection-class,
    // and the status-type composites NDIC's own tiles ship are statuses, not types.
    for (const code of ["OG", "GASD", "GASC", "WS", "ST", "Confidential", "EXP-SWD", ""]) {
      expect(draws(code), code).toBe(false);
    }
    expect(draws(null)).toBe(false);
  });

  it("never widens by case or whitespace — the code is matched as NDIC files it", () => {
    for (const near of ["swd", "SWD ", " WI", "wi"]) expect(draws(near), near).toBe(false);
  });

  it("extracts the verbatim code for the class, and null for everything else", () => {
    // The api10 is what resolves the registration whose codebook classes the code: the same
    // letters mean nothing under a regulator that publishes no injection list.
    expect(disposalType({ api10: "3305300001", well_type_reported: "SWD" })).toBe("SWD");
    expect(disposalType({ api10: "4230100001", well_type_reported: "SWD" })).toBeNull();
    expect(disposalType({ api10: "3305300001", well_type_reported: "OG" })).toBe(null);
    expect(disposalType({})).toBe(null);
    expect(disposalType({ api10: "3305300001", well_type_reported: 7 })).toBe(null);
  });

  it("takes a colour no status, the selection and the trace do not already spend", () => {
    for (const status of statusVocabulary()) {
      expect(status.colour, `${status.id} shares the disposal colour`).not.toBe(DISPOSAL_COLOUR);
    }
    expect(DISPOSAL_COLOUR).not.toBe(SELECTION_COLOUR);
    expect(DISPOSAL_COLOUR).not.toBe(TRACE_COLOUR);
  });
});
