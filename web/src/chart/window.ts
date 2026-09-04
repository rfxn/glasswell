/**
 * The ND back-load took a well from six months on the axis to 131, and the card's plot was
 * designed against six. A window is a view over the served series and never a second request:
 * every point keeps its own value, state and derivation handle, so widening costs nothing and
 * nothing is aggregated away. What is held back is stated in words — see `describeWindow`.
 */
import { formatMonth } from "../card/format.ts";
import type { ChartSeries, SeriesColumn } from "./series.ts";

export interface SpanChoice {
  /** Calendar months to keep, counting back from the last month on record; null is all of it. */
  span: number | null;
  label: string;
}

export interface SeriesWindow {
  shown: number;
  total: number;
  from: string | null;
  to: string | null;
  firstOnRecord: string | null;
  lastOnRecord: string | null;
  span: number | null;
  truncated: boolean;
}

export interface WindowedSeries {
  chart: ChartSeries;
  window: SeriesWindow;
}

export const DEFAULT_SPAN = 60;

/** A record this short is legible whole, so windowing it would hide months for nothing. */
export const FULL_AT_OR_UNDER = 36;

const SPANS: { span: number; label: string }[] = [
  { span: 12, label: "1 year" },
  { span: 24, label: "2 years" },
  { span: DEFAULT_SPAN, label: "5 years" },
];

const ALL: SpanChoice = { span: null, label: "All" };

function ordinal(month: string): number {
  const [year, index] = month.split("-");
  return Number(year) * 12 + (Number(index) - 1);
}

/** Calendar months from the first on record to the last, inclusive — not the count of points. */
export function recordSpan(months: readonly string[]): number {
  const first = months[0];
  const last = months[months.length - 1];
  if (first === undefined || last === undefined) return 0;
  return ordinal(last) - ordinal(first) + 1;
}

export function defaultSpan(months: readonly string[]): number | null {
  const span = recordSpan(months);
  if (span <= FULL_AT_OR_UNDER || span <= DEFAULT_SPAN) return null;
  return DEFAULT_SPAN;
}

/** Offering a span the record is already shorter than would draw the same chart twice. */
export function spanChoices(months: readonly string[]): SpanChoice[] {
  const span = recordSpan(months);
  return [...SPANS.filter((choice) => choice.span < span), ALL];
}

function sliced<T>(values: readonly T[], at: number): T[] {
  return values.slice(at);
}

function windowColumn(column: SeriesColumn, at: number): SeriesColumn {
  const vintages = sliced(column.vintages, at);
  // Re-read over what is drawn: a "mixed report vintages" chip is a claim about the points on
  // screen, and the window may have dropped the only point that made it true.
  const present = vintages.filter((vintage): vintage is string => vintage !== null);
  const distinct = new Set(present);
  const handles = sliced(column.handles, at);
  return {
    ...column,
    values: sliced(column.values, at),
    raw: sliced(column.raw, at),
    vintages,
    nullSemantics: sliced(column.nullSemantics, at),
    handles,
    handle: handles.find((handle) => handle !== null) ?? null,
    vintage: distinct.size === 1 ? (present[0] ?? null) : null,
    mixedVintages: distinct.size > 1,
  };
}

export function chartWindow(chart: ChartSeries, span: number | null): WindowedSeries {
  const total = chart.months.length;
  const firstOnRecord = chart.months[0] ?? null;
  const lastOnRecord = chart.months[chart.months.length - 1] ?? null;
  const at = span === null || lastOnRecord === null ? 0 : firstKept(chart.months, span);
  const months = sliced(chart.months, at);
  const columns = chart.columns.map((column) => windowColumn(column, at));
  const x = sliced(chart.x, at);

  return {
    chart: {
      ...chart,
      months,
      x,
      columns,
      data: [x, ...columns.map((column) => column.values)],
    },
    window: {
      shown: months.length,
      total,
      from: months[0] ?? null,
      to: months[months.length - 1] ?? null,
      firstOnRecord,
      lastOnRecord,
      span,
      truncated: months.length < total,
    },
  };
}

function firstKept(months: readonly string[], span: number): number {
  const last = months[months.length - 1];
  if (last === undefined) return 0;
  const cutoff = ordinal(last) - span + 1;
  const at = months.findIndex((month) => ordinal(month) >= cutoff);
  return at === -1 ? months.length : at;
}

/**
 * R6 applied to the axis itself: a chart drawing 60 of 131 months while implying it draws the
 * record is a naked number wearing a time series. The range, the count and the population it
 * is a count of are a label beside the span control, not two lines of prose above it — the
 * control itself is the "way back to the rest" the sentence used to spell out.
 */
/**
 * R-20, the reloaded link: the months on hand are the ones a narrowed request returned, so
 * "all" is all of what is shown and the sentence says so rather than describing a record it
 * cannot see. The way back to the record is the control beside it, not this sentence.
 */
export function describeShown(window: SeriesWindow): string {
  if (window.total === 0 || window.from === null || window.to === null) {
    return "No months on record";
  }
  return `All of the months shown · ${formatMonth(window.from)} – ${formatMonth(window.to)} · ${window.total} mo`;
}

export function describeWindow(window: SeriesWindow, served = false): string {
  if (window.total === 0 || window.from === null || window.to === null) {
    return "No months on record";
  }
  const shown = `${formatMonth(window.from)} – ${formatMonth(window.to)}`;
  if (!window.truncated) {
    // A request the reader narrowed with `from`/`to` returns part of the record, so a chart
    // drawing all of what it was handed must not call that all of what exists.
    const population = served ? "returned" : "on record";
    return `${shown} · all ${window.total} mo ${population}`;
  }
  const record = `${formatMonth(window.firstOnRecord ?? window.from)} – ${formatMonth(window.lastOnRecord ?? window.to)}`;
  return `${shown} · ${window.shown} of ${window.total} mo · record ${record}`;
}
