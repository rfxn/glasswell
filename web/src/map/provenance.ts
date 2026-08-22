/**
 * M1-3: coordinate-source provenance as a served fact, not a caption. Every ND tile layer
 * carries `geometry_provenance` verbatim from canonical geom_type; the membership and the
 * per-class source filings are `cr_nd_geometry_provenance_1`'s. Each layer is homogeneous
 * in the class, so the panel's layer toggles are the provenance filter and the per-layer
 * paints (status-keyed dots and lines, the trace orchid) are the style channel. TX features
 * carry no such property: the RRC's GIS_LOCATION_SOURCE is licence-gated (RF-1) and stays
 * unserved until that is answered — the legend says so where the vocabulary is stated.
 */
export const PROVENANCE_RULE = "cr_nd_geometry_provenance_1";

export const PROVENANCE_CLASSES = ["surface", "lateral", "survey_trace"] as const;

export type ProvenanceClass = (typeof PROVENANCE_CLASSES)[number];

/** The verbatim class when the feature carries one; null otherwise, TX included. */
export function geometryProvenance(
  properties: Record<string, unknown>,
): ProvenanceClass | null {
  const value = properties["geometry_provenance"];
  if (typeof value !== "string") return null;
  return (PROVENANCE_CLASSES as readonly string[]).includes(value)
    ? (value as ProvenanceClass)
    : null;
}

/**
 * The hover sentence for the two classes whose provenance was previously only a subtitle.
 * A survey trace states richer facts (stations, deepest MD) in its own hover line, so it
 * takes no sentence here.
 */
export function provenanceLine(value: ProvenanceClass): string | null {
  if (value === "surface") {
    return "Surface location as ND DMR filed it · geometry_provenance surface";
  }
  if (value === "lateral") {
    return "Filed bore centreline, not a directional survey trace · geometry_provenance lateral";
  }
  return null;
}
