import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";

import { pointMark } from "../card/format.ts";
import { labelElement } from "../glossary/gw-term.ts";
import { pointHandle } from "./series.ts";
import type { ChartSeries, SeriesColumn } from "./series.ts";

const STREAM_STROKE: Record<string, string> = {
  oil: "#3FA55E",
  gas: "#D9534F",
  water: "#3D8BD4",
};

const STREAM_DASH: Record<string, number[]> = { oil: [], gas: [6, 3], water: [2, 3] };

export interface ChartCallbacks {
  onExplain(handle: string): void;
  labelTermFor(pointer: string): string | null;
}

/** SB-05 §5.6: the frame is DOM, only the plot area is canvas, so every label is hoverable. */
export function renderChart(
  container: HTMLElement,
  chart: ChartSeries,
  callbacks: ChartCallbacks,
): void {
  container.replaceChildren();
  container.classList.add("gw-chart");

  const title = document.createElement("h3");
  title.appendChild(labelElement("Monthly production", callbacks.labelTermFor("/series")));
  container.appendChild(title);

  container.appendChild(legend(chart, callbacks));

  const plot = document.createElement("div");
  plot.className = "gw-chart-plot";
  container.appendChild(plot);

  const axis = document.createElement("p");
  axis.className = "gw-chart-axis";
  axis.appendChild(labelElement("Production month", callbacks.labelTermFor("/series/pm")));
  container.appendChild(axis);

  const width = Math.max(320, plot.clientWidth || container.clientWidth || 640);
  const options: uPlot.Options = {
    width,
    height: 260,
    padding: [8, 8, 0, 0],
    legend: { show: false },
    cursor: { drag: { x: false, y: false } },
    scales: { x: { time: true } },
    axes: [
      { stroke: "#9FB0BC", grid: { stroke: "#1d2a33" }, ticks: { stroke: "#1d2a33" } },
      // uPlot's default axis size (50 px) clips a six-figure monthly volume.
      ...chart.scales.map((unit, position) => ({
        scale: unit,
        side: position === 0 ? (3 as const) : (1 as const),
        size: 62,
        stroke: "#9FB0BC",
        grid: { stroke: "#1d2a33" },
        ticks: { stroke: "#1d2a33" },
      })),
    ],
    series: [
      { label: "pm" },
      ...chart.columns.map((column) => ({
        label: column.label,
        scale: column.unit,
        stroke: STREAM_STROKE[column.stream] ?? "#5FD3E8",
        dash: STREAM_DASH[column.stream] ?? [],
        width: 2,
        spanGaps: false,
        points: { show: true, size: 4 },
      })),
    ],
  };
  new uPlot(options, chart.data as uPlot.AlignedData, plot);

  container.appendChild(stateStrip(chart, callbacks));
}

function legend(chart: ChartSeries, callbacks: ChartCallbacks): HTMLElement {
  const wrapper = document.createElement("ul");
  wrapper.className = "gw-chart-legend";
  for (const column of chart.columns) {
    const item = document.createElement("li");
    const swatch = document.createElement("span");
    swatch.className = "gw-swatch";
    swatch.style.background = STREAM_STROKE[column.stream] ?? "#5FD3E8";
    item.appendChild(swatch);
    item.appendChild(
      labelElement(
        `${column.label} (${column.unit})`,
        callbacks.labelTermFor(`/series/${column.key}`),
      ),
    );
    if (column.basis) {
      const basis = document.createElement("span");
      basis.className = "gw-chip";
      basis.textContent = column.basis;
      item.appendChild(basis);
    }
    if (column.mixedVintages) {
      const warning = document.createElement("span");
      warning.className = "gw-chip gw-chip-warn";
      warning.textContent = "mixed report vintages";
      item.appendChild(warning);
    } else if (column.vintage) {
      const chip = document.createElement("span");
      chip.className = "gw-chip gw-chip-vintage";
      chip.textContent = `vintage ${column.vintage}`;
      item.appendChild(chip);
    }
    if (column.handle) item.appendChild(handleButton(column.handle, column.label, callbacks));
    wrapper.appendChild(item);
  }
  return wrapper;
}

function handleButton(handle: string, label: string, callbacks: ChartCallbacks): HTMLElement {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "gw-handle";
  button.setAttribute("data-handle", handle);
  button.setAttribute("aria-label", `Lineage for ${label}`);
  button.title = handle;
  button.textContent = "⌾";
  button.addEventListener("click", () => callbacks.onExplain(handle));
  return button;
}

/** The four null-semantics states as DOM marks: a gap in a chart could mean any of them. */
function stateStrip(chart: ChartSeries, callbacks: ChartCallbacks): HTMLElement {
  const wrapper = document.createElement("div");
  wrapper.className = "gw-state-strip";
  for (const column of chart.columns) {
    const row = document.createElement("div");
    row.className = "gw-state-row";
    const name = document.createElement("span");
    name.className = "gw-state-name";
    name.textContent = column.label;
    row.appendChild(name);
    for (const [index, month] of chart.months.entries()) {
      row.appendChild(mark(column, index, month, callbacks));
    }
    wrapper.appendChild(row);
  }
  return wrapper;
}

function mark(
  column: SeriesColumn,
  index: number,
  month: string,
  callbacks: ChartCallbacks,
): HTMLElement {
  const state = column.nullSemantics[index] ?? "";
  const described = pointMark(column.values[index] ?? null, state);
  const button = document.createElement("button");
  button.type = "button";
  button.className = `gw-state-mark ${described.className}`;
  button.setAttribute("data-no-glossary", "");
  button.title =
    `${month} · ${column.label} · ${described.label}` +
    (column.raw[index] ? ` · ${column.raw[index]} ${column.unit}` : "") +
    (column.vintages[index] ? ` · vintage ${column.vintages[index]}` : "") +
    `\n${described.title}`;
  button.setAttribute("aria-label", button.title);
  if (column.handle) {
    const handle = pointHandle(column.handle, month);
    button.setAttribute("data-handle", handle);
    button.addEventListener("click", () => callbacks.onExplain(handle));
  }
  return button;
}
