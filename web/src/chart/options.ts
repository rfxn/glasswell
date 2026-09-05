import type uPlot from "uplot";

import { formatMonth, formatValue } from "../card/format.ts";
import { epochToMonth } from "./series.ts";
import type { ChartSeries } from "./series.ts";

export const STREAM_STROKE: Record<string, string> = {
  oil: "#3FA55E",
  gas: "#D9534F",
  water: "#3D8BD4",
};

export const STREAM_DASH: Record<string, number[]> = { oil: [], gas: [6, 3], water: [2, 3] };

/** A canvas inherits no CSS, so the plot reads the theme's tokens itself at build time. */
function token(name: string, fallback: string): string {
  if (typeof document === "undefined") return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

export function streamStroke(stream: string): string {
  return token(`--${stream}`, STREAM_STROKE[stream] ?? "#5FD3E8");
}

/**
 * uPlot splits a time axis on its own scale, so a seven-month series across a wide card gets
 * sub-month ticks and every label collapses to the same month: the axis read "Sep 2025 Sep
 * 2025 Oct 2025 Oct 2025" at 820 px, which is two months claiming to be four. A repeat is
 * dropped rather than the tick, so the gridline still marks where the value sits.
 */
export function monthLabels(splits: readonly number[]): string[] {
  let previous: string | null = null;
  return splits.map((split) => {
    const month = formatMonth(epochToMonth(split));
    if (month === previous) return "";
    previous = month;
    return month;
  });
}

// A month either side of a single point. uPlot ranges a zero-width domain by inventing one,
// which drew a 31-month axis under a one-month record with its only point outside the labels
// (v0.78 N10). Two points already give it a domain to scale from, so the pin is for one.
const MONTH_SECONDS = 31 * 24 * 3600;

/** Kept in step with `--gw-band-left`'s fallback in `style.css`, which is what a test gets. */
const AXIS_SIZE = 68;

function xScale(chart: ChartSeries): uPlot.Scale {
  const points = chart.data[0] ?? [];
  if (points.length !== 1) return { time: true };
  const only = Number(points[0]);
  return { time: true, range: [only - MONTH_SECONDS, only + MONTH_SECONDS] };
}

export function chartOptions(chart: ChartSeries, width: number, log = false): uPlot.Options {
  const axisStroke = token("--slate", "#9FB0BC");
  const grid = { stroke: token("--hairline", "#1d2a33") };
  return {
    width,
    height: 260,
    padding: [8, 8, 0, 0],
    legend: { show: false },
    cursor: { drag: { x: false, y: false } },
    scales: {
      x: xScale(chart),
      // uPlot's log distribution, one per unit scale. A zero is already out of the drawn data
      // by then (chart.ts's `withoutZeros`), because a log scale has no place to put one.
      ...Object.fromEntries(chart.scales.map((unit) => [unit, log ? { distr: 3 } : {}])),
    },
    axes: [
      {
        stroke: axisStroke,
        grid,
        ticks: grid,
        values: (_: unknown, splits: number[]) => monthLabels(splits),
      },
      // uPlot's default axis size (50 px) clips a six-figure monthly volume. The band's row
      // names are laid out in the same gutter (`--gw-band-left`), and at 62 the widest of them
      // needed 61 px in a 58 px column and read `Water · re…`.
      ...chart.scales.map((unit, position) => ({
        scale: unit,
        side: position === 0 ? (3 as const) : (1 as const),
        size: AXIS_SIZE,
        stroke: axisStroke,
        grid,
        ticks: grid,
        // uPlot's log distribution nulls the splits it draws a minor tick for and does not
        // label; `String(null)` printed the word down both axes.
        values: (_: unknown, splits: (number | null)[]) =>
          splits.map((split) => (split === null ? "" : formatValue(String(split)))),
      })),
    ],
    series: [
      { label: "pm" },
      ...chart.columns.map((column) => ({
        label: column.label,
        scale: column.unit,
        stroke: streamStroke(column.stream),
        dash: STREAM_DASH[column.stream] ?? [],
        width: 2,
        // Never true on production data: a spanned gap is production that did not happen.
        spanGaps: false,
        points: { show: true, size: 4 },
      })),
    ],
  } as uPlot.Options;
}
