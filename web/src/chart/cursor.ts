/**
 * One hit surface instead of 393 of them. At 131 months a per-point target measured 2 CSS px
 * across, so the pointer resolves to the month nearest it over the whole plot rectangle and the
 * answer is rendered as DOM — where a handle can be a real button rather than a two-pixel one.
 */
import { formatMonth, formatVolume, nullSemantics } from "../card/format.ts";
import type { NullSemanticsMark } from "../card/format.ts";
import { handleAt } from "./series.ts";
import type { ChartSeries } from "./series.ts";

export interface ReadoutRow {
  key: string;
  stream: string;
  label: string;
  unit: string;
  /** Formatted, or null where the month was never measured — a gap is not a zero (SB-05 §3.2). */
  value: string | null;
  mark: NullSemanticsMark;
  handle: string | null;
}

export interface Readout {
  index: number;
  month: string;
  monthLabel: string;
  rows: ReadoutRow[];
}

/** `fraction` is the pointer's position across the plot area, 0 at its left edge and 1 at its right. */
export function nearestIndex(fraction: number, xs: readonly number[]): number {
  const first = xs[0];
  const last = xs[xs.length - 1];
  if (first === undefined || last === undefined) return -1;
  const clamped = Math.min(1, Math.max(0, fraction));
  const target = first + clamped * (last - first);
  let nearest = 0;
  let best = Infinity;
  for (const [index, x] of xs.entries()) {
    const distance = Math.abs(x - target);
    if (distance < best) {
      best = distance;
      nearest = index;
    }
  }
  return nearest;
}

export function readoutAt(chart: ChartSeries, index: number): Readout | null {
  const month = chart.months[index];
  if (month === undefined) return null;
  return {
    index,
    month,
    monthLabel: formatMonth(month),
    rows: chart.columns.map((column) => {
      // `values` is already null for a withheld or unreported month, so reading the volume off
      // the wire here would print a number the card has just called unmeasured.
      const plotted = column.values[index] ?? null;
      const raw = column.raw[index] ?? null;
      return {
        key: column.key,
        stream: column.stream,
        label: column.label,
        unit: column.unit,
        value: plotted === null || raw === null ? null : formatVolume(raw),
        mark: nullSemantics(column.nullSemantics[index] ?? ""),
        handle: handleAt(column, index, month),
      };
    }),
  };
}
