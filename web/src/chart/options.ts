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

export function chartOptions(chart: ChartSeries, width: number): uPlot.Options {
  const axisStroke = token("--slate", "#9FB0BC");
  const grid = { stroke: token("--hairline", "#1d2a33") };
  return {
    width,
    height: 260,
    padding: [8, 8, 0, 0],
    legend: { show: false },
    cursor: { drag: { x: false, y: false } },
    scales: { x: { time: true } },
    axes: [
      {
        stroke: axisStroke,
        grid,
        ticks: grid,
        values: (_: unknown, splits: number[]) =>
          splits.map((split) => formatMonth(epochToMonth(split))),
      },
      // uPlot's default axis size (50 px) clips a six-figure monthly volume.
      ...chart.scales.map((unit, position) => ({
        scale: unit,
        side: position === 0 ? (3 as const) : (1 as const),
        size: 62,
        stroke: axisStroke,
        grid,
        ticks: grid,
        values: (_: unknown, splits: number[]) =>
          splits.map((split) => formatValue(String(split))),
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
