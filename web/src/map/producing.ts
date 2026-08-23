/**
 * Whether a well is actually producing — a different fact from the status the regulator
 * publishes, and one the conformance registry defines rather than this file. The labels and
 * notes below are the reader-facing rendering of `cr_producing_window_1`,
 * `cr_producing_streams_1` and `cr_producing_evidence_1`; the classes, the window and the
 * stream set all arrive from `/v1/wells/status-summary`, which reads those rows at serve time.
 */

/** The rules that decide this, named wherever a producing number is shown (R8). */
export const PRODUCING_RULES = [
  "cr_producing_evidence_1",
  "cr_producing_streams_1",
  "cr_producing_window_1",
] as const;

export interface ProducingClass {
  id: string;
  label: string;
  note: string;
}

/**
 * Ordered as a scale rather than by size: a key whose rows reshuffle between viewports is
 * harder to read than one whose rows stay put. No label reuses the status vocabulary's words
 * — "active" is what the regulator says about a permit, and merging the two is the failure
 * this whole class exists to avoid.
 */
export const PRODUCING_CLASSES: readonly ProducingClass[] = [
  {
    id: "producing",
    label: "Producing",
    note: "Filed a positive oil or gas month inside the window.",
  },
  {
    id: "not_producing",
    label: "Not producing",
    note:
      "Filed inside the window, but no positive oil or gas month — a reported zero, or water" +
      " only. Water is a byproduct and is not evidence of a producing well.",
  },
  {
    id: "unknown",
    label: "Not known",
    note:
      "No filing to read: the well filed nothing in the window, the regulator withheld the" +
      " months as confidential, or the jurisdiction reports at the lease and no well-level" +
      " series exists. An absence of evidence, which is not evidence of absence.",
  },
] as const;

export function producingLabel(id: string): ProducingClass {
  return (
    PRODUCING_CLASSES.find((entry) => entry.id === id) ?? {
      id,
      label: id,
      note: "A class this build does not know; the registry defines it.",
    }
  );
}

/** The window the classes were judged over, as `/v1/wells/status-summary` states it. */
export interface ProducingWindow {
  months: number;
  from: string;
  to: string;
  streams: string[];
  liquids_basis: string;
}

export interface ProducingCounts {
  counts: Record<string, number>;
  handles: Record<string, string>;
  window: ProducingWindow | null;
  bbox: string;
}

/**
 * The sentence that has to travel with the numbers: a producing count means nothing without
 * the window it was taken over and the basis its liquids are on (blueprint vocabulary rule).
 */
export function producingNote(window: ProducingWindow | null): string {
  if (!window) {
    return "The producing definition is not registered here, so these classes are not served.";
  }
  const streams = window.streams.join(" or ");
  return (
    `Judged over ${window.months} months, ${window.from} to ${window.to}, on filed ${streams}` +
    ` volume. Liquids are ${window.liquids_basis}. Water is served but never counts as` +
    " producing. Status is what the regulator calls the well; this is what it filed."
  );
}

/** Where the wells behind a count are listed, scoped to the box the count was taken over. */
export function producingHref(id: string, bbox: string): string {
  const query = new URLSearchParams({ producing: id, bbox, limit: "200" });
  return `/v1/wells?${query.toString()}`;
}
