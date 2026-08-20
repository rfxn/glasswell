import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";

import {
  NULL_SEMANTICS_STATES,
  formatMonth,
  formatVolume,
  nullSemantics,
  pointMark,
} from "../card/format.ts";
import { labelElement } from "../glossary/gw-term.ts";
import { axisLabels } from "./axes.ts";
import { chartOptions, STREAM_STROKE } from "./options.ts";
import { handleAt } from "./series.ts";
import type { ChartSeries, SeriesColumn } from "./series.ts";

const PLOT_HEIGHT = 260;

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
  container.appendChild(yAxisLabels(chart));

  const plot = document.createElement("div");
  plot.className = "gw-chart-plot";
  container.appendChild(plot);

  const axis = document.createElement("p");
  axis.className = "gw-chart-axis";
  axis.appendChild(labelElement("Production month", callbacks.labelTermFor("/series/pm")));
  container.appendChild(axis);

  const width = measure(plot, container);
  const instance = new uPlot(chartOptions(chart, width), chart.data as uPlot.AlignedData, plot);
  trackWidth(plot, container, instance);

  container.appendChild(stateStrip(chart, callbacks));
}

function measure(plot: HTMLElement, container: HTMLElement): number {
  return Math.max(320, plot.clientWidth || container.clientWidth || 640);
}

/** The plot was measured once and never again, so a resized window left it at its old width. */
function trackWidth(plot: HTMLElement, container: HTMLElement, instance: uPlot): void {
  if (typeof ResizeObserver === "undefined") return;
  let last = measure(plot, container);
  const observer = new ResizeObserver(() => {
    const width = measure(plot, container);
    if (Math.abs(width - last) < 8) return;
    last = width;
    instance.setSize({ width, height: PLOT_HEIGHT });
  });
  observer.observe(container);
}

/** UX P1-4: two axes, three orders of magnitude apart, and neither said what it measured. */
function yAxisLabels(chart: ChartSeries): HTMLElement {
  const wrapper = document.createElement("p");
  wrapper.className = "gw-chart-yaxes";
  for (const label of axisLabels(chart)) {
    const side = document.createElement("span");
    side.className = `gw-axis-label gw-axis-${label.side}`;
    side.setAttribute("data-no-glossary", "");
    side.textContent = `${label.unit} · ${label.streams.join(", ")}`;
    wrapper.appendChild(side);
  }
  return wrapper;
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
  // The same sentence <gw-figure> uses: the raw handle string taught nobody what ⌾ does.
  button.title = `Show where this number came from: ${handle}`;
  button.textContent = "⌾";
  button.addEventListener("click", () => callbacks.onExplain(handle));
  return button;
}

/** Without a key the strip is 18 coloured squares, and the gap it explains stays ambiguous. */
function stateKey(chart: ChartSeries, callbacks: ChartCallbacks): HTMLElement {
  const wrapper = document.createElement("p");
  wrapper.className = "gw-state-key";
  const pointer = chart.columns[0] ? `/series/${chart.columns[0].key}_null_semantics` : "";
  for (const state of NULL_SEMANTICS_STATES) {
    const described = nullSemantics(state);
    const item = document.createElement("span");
    item.className = "gw-state-key-item";
    const swatch = document.createElement("span");
    swatch.className = `gw-state-mark ${described.className}`;
    swatch.title = described.title;
    item.appendChild(swatch);
    item.appendChild(labelElement(described.label, callbacks.labelTermFor(pointer)));
    wrapper.appendChild(item);
  }
  return wrapper;
}

/** The four null-semantics states as DOM marks: a gap in a chart could mean any of them. */
function stateStrip(chart: ChartSeries, callbacks: ChartCallbacks): HTMLElement {
  const wrapper = document.createElement("div");
  wrapper.className = "gw-state-strip";
  wrapper.appendChild(stateKey(chart, callbacks));
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
  const raw = column.raw[index];
  const button = document.createElement("button");
  button.type = "button";
  button.className = `gw-state-mark ${described.className}`;
  button.setAttribute("data-no-glossary", "");
  button.title =
    `${formatMonth(month)} · ${column.label} · ${described.label}` +
    (raw ? ` · ${formatVolume(raw)} ${column.unit}` : "") +
    (column.vintages[index] ? ` · vintage ${column.vintages[index]}` : "") +
    `\n${described.title}`;
  button.setAttribute("aria-label", button.title);
  const handle = handleAt(column, index, month);
  if (handle) {
    button.setAttribute("data-handle", handle);
    button.addEventListener("click", () => callbacks.onExplain(handle));
  }
  return button;
}
