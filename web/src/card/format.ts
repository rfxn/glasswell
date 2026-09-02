import type { Figure } from "../api/envelope.ts";

export interface NullSemanticsMark {
  label: string;
  className: string;
  title: string;
}

const MARKS: Record<string, NullSemanticsMark> = {
  reported: {
    label: "reported",
    className: "gw-state-reported",
    title: "The operator reported a volume for this month.",
  },
  reported_zero: {
    label: "reported zero",
    className: "gw-state-reported-zero",
    title: "The operator reported this month and the volume was zero.",
  },
  no_report: {
    label: "no report",
    className: "gw-state-no-report",
    title: "No report exists for this month. It is not a zero.",
  },
  withheld: {
    label: "withheld",
    className: "gw-state-withheld",
    title: "The regulator withheld this month, usually a confidential well.",
  },
};

/** The four states the API distinguishes; they are never collapsed into one another. */
export const NULL_SEMANTICS_STATES = [
  "reported",
  "reported_zero",
  "withheld",
  "no_report",
] as const;

/** Thousands separators without ever parsing the decimal as a float (SB-07 §4.4). */
export function formatValue(value: string): string {
  const match = /^(-?)(\d+)(\.\d+)?$/.exec(value);
  if (!match) return value;
  const [, sign = "", whole = "", fraction = ""] = match;
  return sign + whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",") + fraction;
}

/**
 * Half-up to `digits` fraction digits on the decimal string, never through a float (SB-07
 * §4.4) — the whole part is carried with BigInt, so a 21-digit volume rounds exactly.
 */
export function roundTo(value: string, digits: number): string {
  if (!Number.isInteger(digits) || digits < 0) {
    throw new Error(`roundTo: digits must be a non-negative integer, got ${String(digits)}`);
  }
  const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(value.trim());
  if (!match) return value;
  const [, sign = "", whole = "0", fraction = ""] = match;
  if (digits >= fraction.length) return sign + whole + (fraction ? `.${fraction}` : "");
  const kept = fraction.slice(0, digits);
  if (Number(fraction[digits] ?? "0") < 5) return sign + whole + (kept ? `.${kept}` : "");
  // Pad back to width: carrying 0.0 -> 1 loses the leading zero the whole part needs.
  const carried = (BigInt(whole + kept) + 1n).toString().padStart(whole.length + kept.length, "0");
  const split = carried.length - digits;
  return sign + carried.slice(0, split) + (digits ? `.${carried.slice(split)}` : "");
}

/** `digits` rounds the figure to at most that many decimals, never zero-padded; omitted, it renders as served. */
export function formatFigure(figure: Figure, digits?: number): string {
  if (!figure.unit) {
    throw new Error(`figure ${figure.value} has no unit; a naked number is a defect (R6)`);
  }
  if (!figure.d) {
    throw new Error(`figure ${figure.value} has no derivation handle; untraceable equals wrong`);
  }
  const value = digits === undefined ? figure.value : roundTo(figure.value, digits);
  return `${formatValue(value)} ${figure.unit}`;
}

export function nullSemantics(state: string): NullSemanticsMark {
  return MARKS[state] ?? { label: state, className: "gw-state-unknown", title: state };
}

export function pointMark(
  value: number | null,
  state: string,
): NullSemanticsMark & { plotted: boolean } {
  return { ...nullSemantics(state), plotted: value !== null };
}

const MONTH_NAMES = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

export function formatMonth(month: string): string {
  const match = /^(\d{4})-(\d{2})$/.exec(month);
  const name = match ? MONTH_NAMES[Number(match[2]) - 1] : undefined;
  return name ? `${name} ${match?.[1]}` : month;
}

/** A monthly volume is not measured to a thousandth of a barrel; tooltips said `70965.000`. */
export function formatVolume(value: string): string {
  return formatValue(roundTo(value, 0));
}

export function formatVintage(vintage: string | null): string {
  return vintage ?? "—";
}

/**
 * The one form an absent value takes, and the only place it is styled. DR-H24: absence and
 * measurement were the same colour, weight, family and font-style, so a skimmed column read as
 * uniform text and every row had to be parsed to be classified. The reason still carries the
 * distinction between what a regulator withheld and what was never reported; the mark is what
 * lets a reader see there is one without reading. Each caller keeps its own reason vocabulary:
 * two endpoints' null semantics are not asserted to mean the same thing here.
 */
export function absentValue(reason: string | null): HTMLElement {
  const element = document.createElement("span");
  element.className = "gw-absent";
  element.setAttribute("data-no-glossary", "");
  element.textContent = reason ? `unavailable: ${reason}` : "unavailable";
  return element;
}
