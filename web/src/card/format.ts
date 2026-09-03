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
  // The subject is the lease-month, not this well's month. A series of shares labelled
  // `reported` says the opposite of the mark three words to its right (M1).
  lease_reported: {
    label: "lease reported",
    className: "gw-state-lease-reported",
    title:
      "The operator filed this month for the lease. This well's number is its share of that" +
      " filing, not a report about this well.",
  },
};

/** The four states the API distinguishes; they are never collapsed into one another. */
export const NULL_SEMANTICS_STATES = [
  "reported",
  "reported_zero",
  "withheld",
  "no_report",
] as const;

export interface AllocationMark {
  label: string;
  className: string;
  title: string;
  allocated: boolean;
}

/**
 * A second record, a second lookup and a second CSS prefix, deliberately.
 *
 * One string-keyed record for two vocabularies collides on the first shared token, and
 * `withheld` is already in the null-semantics one and is a plausible allocation-class name in
 * a later jurisdiction. Two vocabularies that can never be told apart in the DOM is the defect
 * this shape exists against.
 */
const ALLOCATION_MARKS: Record<string, AllocationMark> = {
  observed_gas_well: {
    label: "observed · gas lease",
    className: "gw-alloc-observed-gas-well",
    title: "One gas well on the lease, so the lease volume is this well's. Not allocated.",
    allocated: false,
  },
  observed_single_well_lease: {
    label: "observed · one well",
    className: "gw-alloc-observed-single-well",
    title: "One eligible well on the lease that month, so the lease volume is this well's.",
    allocated: false,
  },
  allocated_equal_share: {
    label: "allocated",
    className: "gw-alloc-equal-share",
    title:
      "An equal share of the lease volume among the wells eligible that month. An estimate," +
      " not a reported figure (cr_tx_allocation_v0_1).",
    allocated: true,
  },
  allocated_after_status_change: {
    label: "allocated, status changed",
    className: "gw-alloc-after-status-change",
    title:
      "The regulator records this well as plugged but filed no plugging date, so it still" +
      " takes a share and the month says so rather than disappearing (cr_tx_allocation_v0_1).",
    allocated: true,
  },
  excluded_after_plug: {
    label: "excluded after plug",
    className: "gw-alloc-excluded-after-plug",
    title:
      "The month is after this well's filed plugging date, so it takes no share and the" +
      " share was redistributed among the wells still eligible (cr_tx_allocation_v0_1).",
    allocated: true,
  },
  unallocated: {
    label: "unallocated",
    className: "gw-alloc-unallocated",
    title:
      "Lease volume with no eligible well to carry it. It is in the conservation ledger with" +
      " its cause, and is served as no well's production.",
    allocated: true,
  },
};

/** The six classes the allocation serves, in the order the legend lists them. */
export const ALLOCATION_CLASSES = [
  "observed_gas_well",
  "observed_single_well_lease",
  "allocated_equal_share",
  "allocated_after_status_change",
  "excluded_after_plug",
  "unallocated",
] as const;

/**
 * The mark for one allocation class. A class this record does not know is labelled with its own
 * name rather than silently dropped: an unlabelled band reads as an observation.
 */
export function allocationClass(state: string): AllocationMark {
  return (
    ALLOCATION_MARKS[state] ?? {
      label: state,
      className: "gw-alloc-unknown",
      title: state,
      allocated: true,
    }
  );
}

/**
 * How a figure was arrived at, in one word, wherever a granularity reaches the DOM.
 *
 * An allocation estimate that reads as an observation is the defect the whole track exists
 * against, so this is a primitive rather than a sentence written at each call site.
 */
export function granularityLabel(granularity: string | null): string {
  if (granularity === "lease_allocated") return "allocated";
  if (granularity === "well_observed") return "observed";
  if (granularity === "lease_reported") return "reported at the lease";
  return granularity ?? "";
}

/** Whether a served granularity means the figure is an estimate rather than an observation. */
export function isAllocated(granularity: string | null): boolean {
  return granularity === "lease_allocated";
}

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
