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

export function formatMonth(month: string): string {
  return month;
}

export function formatVintage(vintage: string | null): string {
  return vintage ?? "—";
}
