import { coalesce, get, lower, match } from "./expr.ts";
import { DEFAULT_JURISDICTION, JURISDICTION_LIST, jurisdictionRule, rulesFor } from "./jurisdictions.generated.ts";
import type { Expr } from "./expr.ts";

/**
 * Well status symbology, served rather than declared here.
 *
 * The eleven classes and the twelfth absence constant stood in this file as object literals,
 * with their labels, colours, glyphs, zoom floors and notes. They agreed with the five
 * per-regulator maps by coincidence: nothing checked them, no gate could read them, and a class
 * a regulator added that this file had never heard of was painted as the absence class by
 * negation, counted as nothing and gone the moment a reader unticked one box.
 *
 * `lineage.status_classes` is the domain now, and `/v1/jurisdictions` serves it once in `meta`.
 * This module is the store the same `loadCensus()` fetch seeds, so `statusClass()` stays
 * synchronous for the eight surfaces that read it at draw time. Before it is seeded there is no
 * vocabulary and the right behaviour is to draw nothing, which is what the empty store does.
 */
/** The registry decision that names a jurisdiction's status vocabulary. */
const STATUS_VOCABULARY = "status_vocabulary";

function statusVocabularyRule(code: string): string {
  const rule = jurisdictionRule(code, STATUS_VOCABULARY);
  // A registry that names no status vocabulary for a jurisdiction it registers is a defect,
  // not a fallback: the class every well on the map is drawn with would have no rule to cite.
  if (rule === null) throw new Error(`no status vocabulary registered for ${code}`);
  return rule;
}

/**
 * Every registration's vocabulary rule, resolved at import. Four named constants stood here
 * and three of them were read by nothing: they were import-time assertions that each of four
 * hard-coded jurisdictions registered a vocabulary, which is a claim the registry can make for
 * however many it holds.
 */
export const STATUS_VOCAB_RULE_BY_CODE: Readonly<Record<string, string>> = Object.fromEntries(
  JURISDICTION_LIST.map((row) => [row.code, statusVocabularyRule(row.code)]),
);

/** The class list's own rule: the jurisdiction the explorer opens on, which is a registration. */
export const STATUS_VOCAB_RULE = STATUS_VOCAB_RULE_BY_CODE[DEFAULT_JURISDICTION.code]!;
/** One canonical class list, one vocabulary rule per source. Both are named where counts are. */
export const STATUS_VOCAB_RULES: readonly string[] = rulesFor(STATUS_VOCABULARY);

/** Reserved for selection. No layer and no status may paint with it (UX P1-5). */
export const SELECTION_COLOUR = "#5FD3E8";

export type StatusGlyph = "solid" | "hollow" | "bar" | "dashed" | "struck" | "struck-hollow";

export interface StatusClass {
  id: string;
  label: string;
  colour: string;
  glyph: StatusGlyph;
  note: string;
  /** Zoom at or above which this class renders. Low-information classes recede (market §2.8.3). */
  minZoom: number;
  /** The legend's row order, which is a decision the domain publishes rather than array order. */
  sortOrder: number;
  /** The one class no mapping produces: what a well with no resolvable status is served as. */
  isAbsence: boolean;
  /** The rule that declared the class, resolvable at /v1/conformance/{rule_id}. */
  rule: string;
}

/** One row of `meta.status_classes`, spelled as the wire spells it. */
export interface StatusClassRow {
  status_canonical: string;
  label: string;
  colour: string;
  glyph: string;
  min_zoom: number;
  sort_order: number;
  is_absence: boolean;
  note: string;
  rule_id: string;
}

/**
 * What a class reads as before the domain has been served. Not a placeholder the reader ever
 * sees: it paints `transparent`, carries no label and matches no served id, so a surface that
 * reads the store early draws nothing rather than a guess.
 */
const UNRESOLVED: StatusClass = {
  id: "",
  label: "",
  colour: "transparent",
  glyph: "hollow",
  note: "",
  minZoom: 0,
  sortOrder: 0,
  isAbsence: false,
  rule: "",
};

let resident: readonly StatusClass[] = [];
let byId: ReadonlyMap<string, StatusClass> = new Map();
let absence: StatusClass | null = null;

function toClass(row: StatusClassRow): StatusClass {
  return {
    id: row.status_canonical,
    label: row.label,
    colour: row.colour,
    glyph: row.glyph as StatusGlyph,
    note: row.note,
    minZoom: row.min_zoom,
    sortOrder: row.sort_order,
    isAbsence: row.is_absence,
    rule: row.rule_id,
  };
}

/** Seed the store from what `/v1/jurisdictions` served. Ordered by the domain's own order. */
export function setStatusVocabulary(rows: readonly StatusClassRow[]): void {
  const built = rows.map(toClass).sort((a, b) => a.sortOrder - b.sortOrder);
  resident = built;
  byId = new Map(built.map((status) => [status.id, status]));
  absence = built.find((status) => status.isAbsence) ?? null;
}

/** Test seam, and the state every surface starts in: no vocabulary, so nothing is drawn. */
export function resetStatusVocabulary(): void {
  resident = [];
  byId = new Map();
  absence = null;
}

/** The served domain in legend order, absence class included. Empty until it is served. */
export function statusVocabulary(): readonly StatusClass[] {
  return resident;
}

/** Whether the domain has been served at all. Empty is unknown, never "no classes exist". */
export function statusVocabularyResolved(): boolean {
  return resident.length > 0;
}

/** The one class no mapping produces, or null while the domain is unknown. */
export function absenceStatus(): StatusClass | null {
  return absence;
}

/** The classes a regulator's map can produce: the domain less the absence class. */
export function statusIds(): string[] {
  return resident.filter((status) => !status.isAbsence).map((status) => status.id);
}

/** Every class the legend filters, which is every class the domain holds. */
export function filterableStatusIds(): string[] {
  return resident.map((status) => status.id);
}

export function statusClass(id: string | null | undefined): StatusClass {
  return byId.get(String(id ?? "").toLowerCase()) ?? absence ?? UNRESOLVED;
}

export function statusColour(id: string | null | undefined): string {
  return statusClass(id).colour;
}

export function statusMinZoom(id: string | null | undefined): number {
  return statusClass(id).minZoom;
}

export function statusProperty(): Expr {
  // The coalesce guards the tile, not the store. Every serving path reads the resolver's
  // absence arm, and so does every wells mart, so a published tile carries a class for every
  // feature -- but a tile is a cache, and a reader panning across one built before the mart was
  // last refreshed is reading rows the resolver never touched. Those draw as the absence class
  // rather than as nothing, which is what this coalesce is for. Against an unresolved store it
  // yields the empty string, which matches no class in the filter, so nothing is painted.
  return lower(coalesce(get("status_canonical"), absence?.id ?? ""));
}

export function statusColourExpression(): Expr {
  return match(
    statusProperty(),
    resident.map((status) => [status.id, status.colour] as [string, string]),
    absence?.colour ?? UNRESOLVED.colour,
  );
}

/** Hollow classes are drawn as a ring: ink fill, status stroke. */
export function statusFillExpression(inkColour: string): Expr {
  return match(
    statusProperty(),
    resident.map(
      (status) =>
        [
          status.id,
          status.glyph === "hollow" || status.glyph === "struck-hollow"
            ? inkColour
            : status.colour,
        ] as [string, string],
    ),
    absence?.colour ?? UNRESOLVED.colour,
  );
}

/** Terminal classes carry the struck-through modifier, drawn from z11 where a well is legible. */
export function struckStatuses(): readonly string[] {
  return resident.filter((status) => status.glyph.startsWith("struck")).map((status) => status.id);
}
