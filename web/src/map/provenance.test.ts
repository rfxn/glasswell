import { describe, expect, it } from "vitest";

import {
  PROVENANCE_CLASSES,
  PROVENANCE_RULE,
  geometryProvenance,
  provenanceLine,
} from "./provenance.ts";

describe("the geometry provenance vocabulary", () => {
  it("is the conformance row's, cited by id, not owned by web code", () => {
    expect(PROVENANCE_RULE).toBe("cr_nd_geometry_provenance_1");
    expect([...PROVENANCE_CLASSES]).toEqual(["surface", "lateral", "survey_trace"]);
  });

  it("reads the wire class verbatim and refuses anything outside the vocabulary", () => {
    expect(geometryProvenance({ geometry_provenance: "surface" })).toBe("surface");
    expect(geometryProvenance({ geometry_provenance: "lateral" })).toBe("lateral");
    expect(geometryProvenance({ geometry_provenance: "survey_trace" })).toBe("survey_trace");
    // A class the rule has not mapped is not restyled into one it has.
    expect(geometryProvenance({ geometry_provenance: "bottomhole" })).toBe(null);
    expect(geometryProvenance({ geometry_provenance: 7 })).toBe(null);
    // Texas: the property is absent by licence ruling (RF-1), which is not an error.
    expect(geometryProvenance({ api10: "4231733333" })).toBe(null);
  });

  it("speaks the class verbatim in each sentence, and decodes nothing into 'surveyed'", () => {
    expect(provenanceLine("surface")).toContain("geometry_provenance surface");
    expect(provenanceLine("lateral")).toContain("geometry_provenance lateral");
    expect(provenanceLine("lateral")).toContain("not a directional survey trace");
    for (const value of ["surface", "lateral"] as const) {
      expect(provenanceLine(value)?.toLowerCase()).not.toContain("surveyed");
      expect(provenanceLine(value)?.toLowerCase()).not.toContain("actual");
    }
  });

  it("leaves the survey trace to its own richer hover line", () => {
    expect(provenanceLine("survey_trace")).toBe(null);
  });
});
