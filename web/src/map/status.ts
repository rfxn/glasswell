import { coalesce, get, lower, match } from "./expr.ts";
import { jurisdictionRule, rulesFor } from "./jurisdictions.generated.ts";
import type { Expr } from "./expr.ts";

/**
 * Well status symbology, derived from the canonical vocabulary rather than invented here.
 * The vocabulary, the reported codes behind it and the row counts all come from
 * `cr_nd_status_vocab_1`; the glyph grammar follows the ND DMR `STATUS-TYPE` legend, where
 * plugging is a modifier struck through the fluid glyph rather than a colour of its own.
 */
/** The registry decision that names a jurisdiction's status vocabulary. */
const STATUS_VOCABULARY = "status_vocabulary";

function statusVocabularyRule(code: string): string {
  const rule = jurisdictionRule(code, STATUS_VOCABULARY);
  // A registry that names no status vocabulary for a jurisdiction it registers is a defect,
  // not a fallback: the class every well is drawn with would have no rule to cite.
  if (rule === null) throw new Error(`no status vocabulary registered for ${code}`);
  return rule;
}

export const STATUS_VOCAB_RULE = statusVocabularyRule("ND");
/** One canonical class list, one vocabulary rule per source. Both are named where counts are. */
export const STATUS_VOCAB_RULES: readonly string[] = rulesFor(STATUS_VOCABULARY);
export const TX_STATUS_VOCAB_RULE = statusVocabularyRule("TX");
export const NM_STATUS_VOCAB_RULE = statusVocabularyRule("NM");
export const MT_STATUS_VOCAB_RULE = statusVocabularyRule("MT");

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
  rule: string;
}

export const STATUS_CLASSES: readonly StatusClass[] = [
  {
    id: "active",
    label: "Active",
    colour: "#3FA55E",
    glyph: "solid",
    note: "Producing or capable of production (NDIC A, OCD A).",
    minZoom: 4,
    rule: STATUS_VOCAB_RULE,
  },
  {
    id: "drilling",
    label: "Drilling",
    colour: "#3D8BD4",
    glyph: "bar",
    note: "Spudded, not yet completed (DRL).",
    minZoom: 4,
    rule: STATUS_VOCAB_RULE,
  },
  {
    id: "confidential",
    label: "Confidential",
    colour: "#E4A33C",
    glyph: "solid",
    note: "Withheld by the operator's tight-hole election: a status, not missing data.",
    minZoom: 6,
    rule: STATUS_VOCAB_RULE,
  },
  {
    id: "permitted",
    label: "Permitted",
    colour: "#9FB0BC",
    glyph: "hollow",
    note: "Approved location, not yet drilled (NDIC LOC, OCD N).",
    minZoom: 6,
    rule: STATUS_VOCAB_RULE,
  },
  {
    id: "inactive",
    label: "Inactive",
    colour: "#D9534F",
    glyph: "bar",
    note: "Shut in or on inactive-well waiver (IA).",
    minZoom: 8,
    rule: STATUS_VOCAB_RULE,
  },
  {
    id: "temporarily_abandoned",
    label: "Temporarily abandoned",
    colour: "#D9534F",
    glyph: "dashed",
    note: "Suspended, not plugged (TA, TAO, TASC, TATD; OCD T, E).",
    minZoom: 8,
    rule: STATUS_VOCAB_RULE,
  },
  {
    id: "service",
    label: "Service",
    colour: "#7A6FD0",
    glyph: "hollow",
    note:
      "Injection, disposal, storage, observation or water supply, not a producer" +
      " (cr_tx_status_vocab_1).",
    minZoom: 8,
    rule: TX_STATUS_VOCAB_RULE,
  },
  {
    id: "plugged",
    label: "Plugged & abandoned",
    colour: "#7C8B96",
    glyph: "struck",
    note: "Wellbore permanently plugged (PA, AB, PANF; OCD P, H).",
    minZoom: 9,
    rule: STATUS_VOCAB_RULE,
  },
  {
    id: "dry",
    label: "Dry hole",
    colour: "#7C8B96",
    glyph: "struck-hollow",
    note: "Drilled, no commercial completion (DRY, OCD D).",
    minZoom: 9,
    rule: STATUS_VOCAB_RULE,
  },
  {
    // Not the absence class and not a status: the regulator published a code, and glasswell
    // has no equivalent for what it says. Collapsing it into `unmapped` would erase the
    // difference between "nobody said" and "we have no word for what was said", and forcing
    // it into `plugged` would strike 507 New Mexico wells through on a claim the OCD never
    // made (cr_nm_wellhistory_status_vocab_2).
    id: "documented_unmapped",
    label: "Documented, no class",
    colour: "#8E6E9E",
    glyph: "hollow",
    note:
      "The regulator documents the code and glasswell has no equivalent class: zone-plugged"
      + " (OCD Q, Z) and reclamation-fund (OCD I, J).",
    minZoom: 9,
    rule: NM_STATUS_VOCAB_RULE,
  },
  {
    id: "expired",
    label: "Expired permit",
    colour: "#55666F",
    glyph: "dashed",
    note:
      "Permit lapsed or cancelled before spud: no wellbore exists (PNC, PNS, EXP;"
      + " OCD C, X).",
    minZoom: 9,
    rule: STATUS_VOCAB_RULE,
  },
];

/**
 * A low-salience neutral, and deliberately not BRAND.md's deep amber `#B57A18`.
 *
 * That amber is the quarantine colour, and it was the right read while ND was the only slice:
 * `cr_nd_status_vocab_1` quarantines an unmapped status, so an amber dot meant "a row failed a
 * rule". Texas broke both halves of that. Its 65,685 statusless wells are not quarantined —
 * the RRC reported no well type and filed no plugging date, which is an absence, not a defect —
 * and at z12 amber painted 19.7% of the canvas against active's 8.9%, so absence was the
 * loudest thing on the map. Worse, `#B57A18` is hue 37.5 and ND's `confidential` `#E4A33C` is
 * hue 36.8: the colour meaning "we do not know" was the colour meaning "the operator elected
 * to withhold", one lightness step apart. A reader who learned the palette on ND would misread
 * Texas.
 *
 * Still drawn at every zoom: absence must not be the thing that hides. It just should not
 * shout.
 */
export const UNMAPPED_STATUS: StatusClass = {
  id: "unmapped",
  label: "Unmapped status",
  colour: "#46525C",
  glyph: "hollow",
  note:
    `No status under ${STATUS_VOCAB_RULES.join(", ")}: the source reported none, or its `
    + "vocabulary has no published codebook to map. A code the regulator does publish and "
    + "glasswell has no class for is the class above, not this one.",
  minZoom: 0,
  rule: STATUS_VOCAB_RULE,
};

const BY_ID = new Map(STATUS_CLASSES.map((status) => [status.id, status]));

export function statusIds(): string[] {
  return STATUS_CLASSES.map((status) => status.id);
}

/** The canonical vocabulary plus the absence class, which the legend filters like any other. */
export function filterableStatusIds(): string[] {
  return [...statusIds(), UNMAPPED_STATUS.id];
}

export function statusClass(id: string | null | undefined): StatusClass {
  return BY_ID.get(String(id ?? "").toLowerCase()) ?? UNMAPPED_STATUS;
}

export function statusColour(id: string | null | undefined): string {
  return statusClass(id).colour;
}

export function statusMinZoom(id: string | null | undefined): number {
  return statusClass(id).minZoom;
}

export function statusProperty(): Expr {
  return lower(coalesce(get("status_canonical"), "unmapped"));
}

export function statusColourExpression(): Expr {
  return match(
    statusProperty(),
    STATUS_CLASSES.map((status) => [status.id, status.colour] as [string, string]),
    UNMAPPED_STATUS.colour,
  );
}

/** Hollow classes are drawn as a ring: ink fill, status stroke. */
export function statusFillExpression(inkColour: string): Expr {
  return match(
    statusProperty(),
    STATUS_CLASSES.map(
      (status) =>
        [status.id, status.glyph === "hollow" || status.glyph === "struck-hollow" ? inkColour : status.colour] as [
          string,
          string,
        ],
    ),
    UNMAPPED_STATUS.colour,
  );
}

/** Terminal classes carry the struck-through modifier, drawn from z11 where a well is legible. */
export const STRUCK_STATUSES: readonly string[] = STATUS_CLASSES.filter((status) =>
  status.glyph.startsWith("struck"),
).map((status) => status.id);
