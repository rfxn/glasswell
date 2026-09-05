import { BY_PREFIX, JURISDICTION_LIST, rulesFor } from "./jurisdictions.generated.ts";

/**
 * M1-3: coordinate-source provenance as a served fact, not a caption. A tile layer carries
 * `geometry_provenance` verbatim from canonical geom_type; the membership and the per-class
 * source filings belong to the registration's own rule, resolved here rather than pinned to one
 * jurisdiction. Each layer is homogeneous in the class, so the panel's layer toggles are the
 * provenance filter and the per-layer paints (status-keyed dots and lines, the trace orchid) are
 * the style channel. A registration that publishes no such rule serves no such property: Texas
 * is that case, because the RRC's GIS_LOCATION_SOURCE is licence-gated (RF-1) and stays unserved
 * until that is answered — the legend says so where the vocabulary is stated.
 */
/** The registry decision that says how a jurisdiction's recorded geometry is classed. */
const GEOMETRY_PROVENANCE = "geometry_provenance";

/**
 * The rule the feature's own registration published, or null where none is registered. Texas is
 * the null case and it is a fact rather than a gap: the RRC's coordinate-source attribute is
 * licence-gated (RF-1). A single constant here put a rule about North Dakota geometry on every
 * feature of every jurisdiction, which is a served falsehood on four maps out of five.
 */
export function provenanceRuleFor(api10: string | null | undefined): string | null {
  const registration = BY_PREFIX[String(api10 ?? "").slice(0, 2)];
  return registration ? (registration.rules[GEOMETRY_PROVENANCE] ?? null) : null;
}

/** Every geometry-provenance rule the registry serves, for a legend that names them all. */
export function provenanceRules(): readonly string[] {
  return rulesFor(GEOMETRY_PROVENANCE);
}

/** The registrations that publish no provenance rule, named where the legend says why. */
export function provenanceUnregistered(): readonly string[] {
  return JURISDICTION_LIST.filter((row) => !row.rules[GEOMETRY_PROVENANCE]).map((row) => row.code);
}

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
 * takes no sentence here. The regulator named is the feature's own, from the registration its
 * API-10 prefix resolves to, rather than the one jurisdiction the sentence used to name.
 */
export function provenanceLine(
  value: ProvenanceClass,
  api10?: string | null,
): string | null {
  const registration = BY_PREFIX[String(api10 ?? "").slice(0, 2)];
  const filer = registration ? registration.code : null;
  if (value === "surface") {
    const who = filer ? `as ${filer} filed it` : "as filed";
    return `Surface location ${who} · geometry_provenance surface`;
  }
  if (value === "lateral") {
    return "Filed bore centreline, not a directional survey trace · geometry_provenance lateral";
  }
  return null;
}
