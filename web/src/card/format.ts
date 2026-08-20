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

export function formatFigure(figure: Figure): string {
  if (!figure.unit) {
    throw new Error(`figure ${figure.value} has no unit; a naked number is a defect (R6)`);
  }
  if (!figure.d) {
    throw new Error(`figure ${figure.value} has no derivation handle; untraceable equals wrong`);
  }
  return `${formatValue(figure.value)} ${figure.unit}`;
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
  const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(value.trim());
  if (!match) return value;
  const [, sign = "", whole = "0", fraction = ""] = match;
  const rounded = Number(fraction[0] ?? "0") >= 5 ? (BigInt(whole) + 1n).toString() : whole;
  return sign + formatValue(rounded);
}

export function formatVintage(vintage: string | null): string {
  return vintage ?? "—";
}
