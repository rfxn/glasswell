import type { ChartSeries } from "./series.ts";

export interface AxisLabel {
  unit: string;
  side: "left" | "right";
  streams: string[];
}

/**
 * SB-05 §5.6 requires a y-axis label with its unit. With two scales three orders of
 * magnitude apart, naming which series sits on which side is the difference between a
 * readable chart and a misleading one.
 */
export function axisLabels(chart: ChartSeries): AxisLabel[] {
  return chart.scales.map((unit, position) => ({
    unit,
    side: position === 0 ? "left" : "right",
    streams: chart.columns.filter((column) => column.unit === unit).map((column) => column.label),
  }));
}
