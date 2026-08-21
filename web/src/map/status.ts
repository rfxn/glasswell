import { coalesce, get, lower, match } from "./expr.ts";
import type { Expr } from "./expr.ts";

/**
 * Well status symbology, derived from the canonical vocabulary rather than invented here.
 * The vocabulary, the reported codes behind it and the row counts all come from
 * `cr_nd_status_vocab_1`; the glyph grammar follows the ND DMR `STATUS-TYPE` legend, where
 * plugging is a modifier struck through the fluid glyph rather than a colour of its own.
 */
export const STATUS_VOCAB_RULE = "cr_nd_status_vocab_1";

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

/**
 * `select status_canonical, count(*) from marts.nd_wells_tile group by 1` against the
 * deployed ND slice on 2026-08-20. Held in source so a legend row can never claim a class
 * the data does not contain, and so the zoom gates below can be argued from real counts.
 */
export const MEASURED_WELL_COUNTS: Readonly<Record<string, number>> = {
  active: 20_643,
  plugged: 7_316,
  dry: 6_347,
  expired: 5_769,
  inactive: 1_598,
  confidential: 968,
  permitted: 610,
  drilling: 343,
  temporarily_abandoned: 223,
};

export const STATUS_CLASSES: readonly StatusClass[] = [
  {
    id: "active",
    label: "Active",
    colour: "#3FA55E",
    glyph: "solid",
    note: "Producing or capable of production (NDIC code A).",
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
    note: "Withheld by the operator's tight-hole election — a status, not missing data.",
    minZoom: 6,
    rule: STATUS_VOCAB_RULE,
  },
  {
    id: "permitted",
    label: "Permitted",
    colour: "#9FB0BC",
    glyph: "hollow",
    note: "Approved location, not yet drilled (LOC).",
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
    note: "Suspended, not plugged (TA, TAO, TASC, TATD).",
    minZoom: 8,
    rule: STATUS_VOCAB_RULE,
  },
  {
    id: "plugged",
    label: "Plugged & abandoned",
    colour: "#7C8B96",
    glyph: "struck",
    note: "Wellbore permanently plugged (PA, AB, PANF).",
    minZoom: 9,
    rule: STATUS_VOCAB_RULE,
  },
  {
    id: "dry",
    label: "Dry hole",
    colour: "#7C8B96",
    glyph: "struck-hollow",
    note: "Drilled, no commercial completion (DRY).",
    minZoom: 9,
    rule: STATUS_VOCAB_RULE,
  },
  {
    id: "expired",
    label: "Expired permit",
    colour: "#55666F",
    glyph: "dashed",
    note: "Permit lapsed or cancelled before spud — no wellbore exists (PNC, PNS, EXP).",
    minZoom: 9,
    rule: STATUS_VOCAB_RULE,
  },
];

/**
 * Deep amber is BRAND.md's quarantine colour, and an unmapped status *is* a quarantine
 * condition — `cr_nd_status_vocab_1` sets `unmapped_action: quarantine`. Visible at every
 * zoom on purpose: a data defect must never be the thing that hides.
 */
export const UNMAPPED_STATUS: StatusClass = {
  id: "unmapped",
  label: "Unmapped status",
  colour: "#B57A18",
  glyph: "hollow",
  note: `Not in ${STATUS_VOCAB_RULE}: the tile carries a status this build cannot name.`,
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

/** Per-status zoom floor as a style expression, so the gate and the legend read one table. */
export function statusMinZoomExpression(): Expr {
  return match(
    statusProperty(),
    STATUS_CLASSES.map((status) => [status.id, status.minZoom] as [string, number]),
    UNMAPPED_STATUS.minZoom,
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
