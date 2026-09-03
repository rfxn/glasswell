import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";

import {
  ABSENT_MARK,
  NULL_SEMANTICS_STATES,
  formatMonth,
  nullSemantics,
} from "../card/format.ts";
import { explainHandle } from "../chrome/handle.ts";
import { THEME_EVENT } from "../chrome/theme.ts";
import { labelElement } from "../glossary/gw-term.ts";
import { axisLabels } from "./axes.ts";
import { nearestIndex, readoutAt } from "./cursor.ts";
import type { Readout, ReadoutRow } from "./cursor.ts";
import { chartOptions, streamStroke } from "./options.ts";
import type { ChartSeries, SeriesColumn } from "./series.ts";
import { chartWindow, defaultSpan, describeWindow, spanChoices } from "./window.ts";

const PLOT_HEIGHT = 260;

export interface ChartCallbacks {
  onExplain(handle: string): void;
  labelTermFor(pointer: string): string | null;
}

export interface ChartOptions {
  /**
   * `served` draws exactly the months the response carried and offers no span control: the
   * explorer's window is its `from`/`to` facets, which ride the URL and are answered by the
   * server. `default` is the card's, where a back-loaded record is windowed client-side.
   */
  span?: "default" | "served";
}

/** One live chart per host: a repaint must not leave the last one's observers running. */
const teardowns = new WeakMap<HTMLElement, () => void>();

/** SB-05 §5.6: the frame is DOM, only the plot area is canvas, so every label is hoverable. */
export function renderChart(
  container: HTMLElement,
  chart: ChartSeries,
  callbacks: ChartCallbacks,
  options: ChartOptions = {},
): void {
  teardowns.get(container)?.();
  const outer = new AbortController();
  let repaint: AbortController | null = null;
  teardowns.set(container, () => {
    repaint?.abort();
    outer.abort();
  });

  const served = options.span === "served";
  const choices = served ? [] : spanChoices(chart.months);
  let span = served ? null : defaultSpan(chart.months);
  // The month, not its index: widening the window renumbers every point, and a reader who was
  // reading March must not silently end up reading some month five years earlier.
  let month = chart.months[chart.months.length - 1] ?? null;

  const draw = (): void => {
    repaint?.abort();
    repaint = new AbortController();
    const signal = repaint.signal;
    const view = chartWindow(chart, span);
    const months = view.chart.months;
    if (month === null || !months.includes(month)) month = months[months.length - 1] ?? null;

    container.replaceChildren();
    container.classList.add("gw-chart");

    container.append(
      legend(view.chart, callbacks),
      windowBar(view.window, choices, span, served, (next) => {
        span = next;
        draw();
      }),
    );
    // A window the record does not reach is served as an empty series. That is a fact about the
    // window, which the bar above has just stated — an empty axis under it would say nothing.
    if (months.length === 0) return;
    container.appendChild(yAxisLabels(view.chart));

    const plot = document.createElement("div");
    plot.className = "gw-chart-plot";
    container.appendChild(plot);

    const band = stateBand(view.chart);
    container.appendChild(band);

    const axis = document.createElement("p");
    axis.className = "gw-chart-axis";
    axis.appendChild(labelElement("Production month", callbacks.labelTermFor("/series/pm")));
    container.appendChild(axis);

    // Directly under the surface it answers for: a readout the reader has to scroll to find is
    // the two-pixel target again, wearing a different shape.
    const readout = document.createElement("section");
    readout.className = "gw-series-readout";
    readout.setAttribute("aria-live", "polite");
    container.append(readout, stateKey(view.chart, callbacks));
    const vintages = vintageDisclosure(view.chart);
    if (vintages) container.appendChild(vintages);

    const paint = (index: number): void => {
      const next = months[index];
      if (next === undefined) return;
      month = next;
      readout.replaceChildren(
        ...readoutContent(readoutAt(view.chart, index), index, months.length, callbacks, paint),
      );
      for (const cell of band.querySelectorAll(".gw-state-mark")) {
        cell.toggleAttribute("data-selected", Number(cell.getAttribute("data-index")) === index);
      }
    };

    const width = measure(plot, container);
    const instance = new uPlot(chartOptions(view.chart, width), view.chart.data as uPlot.AlignedData, plot);
    signal.addEventListener("abort", () => instance.destroy());
    align(band, instance.over, plot);
    track(plot, container, band, instance, signal);

    // The whole plot rectangle and the whole band answer the pointer, because at 131 months a
    // per-point target measured 2 CSS px across and the reader could not land on one.
    for (const surface of [plot, band]) {
      seek(surface, () => instance.over, view.chart, paint, signal);
    }
    paint(months.indexOf(month as string));
  };

  document.addEventListener(THEME_EVENT, draw, { signal: outer.signal });
  draw();
}

function measure(plot: HTMLElement, container: HTMLElement): number {
  return Math.max(320, plot.clientWidth || container.clientWidth || 640);
}

/** The plot was measured once and never again, so a resized window left it at its old width. */
function track(
  plot: HTMLElement,
  container: HTMLElement,
  band: HTMLElement,
  instance: uPlot,
  signal: AbortSignal,
): void {
  if (typeof ResizeObserver === "undefined") return;
  let last = measure(plot, container);
  const observer = new ResizeObserver(() => {
    const width = measure(plot, container);
    if (Math.abs(width - last) >= 8) {
      last = width;
      instance.setSize({ width, height: PLOT_HEIGHT });
    }
    align(band, instance.over, plot);
  });
  observer.observe(container);
  signal.addEventListener("abort", () => observer.disconnect());
}

/**
 * The band reads as the plot's own x axis only if it starts and ends where the plot area does,
 * so the gutters the y axes occupy are measured rather than assumed. Without layout — a test
 * environment with no box model — the CSS fallbacks stand and nothing is written.
 */
function align(band: HTMLElement, over: HTMLElement | undefined, plot: HTMLElement): void {
  if (!over) return;
  const outer = plot.getBoundingClientRect();
  const inner = over.getBoundingClientRect();
  if (outer.width <= 0 || inner.width <= 0) return;
  band.style.setProperty("--gw-band-left", `${Math.max(0, inner.left - outer.left)}px`);
  band.style.setProperty("--gw-band-right", `${Math.max(0, outer.right - inner.right)}px`);
}

/** Nearest-month-to-pointer over one wide surface, which is the model 131 points need. */
function seek(
  surface: HTMLElement,
  over: () => HTMLElement | undefined,
  chart: ChartSeries,
  paint: (index: number) => void,
  signal: AbortSignal,
): void {
  let last = -1;
  const resolve = (event: PointerEvent | MouseEvent): void => {
    const rect = (over() ?? surface).getBoundingClientRect();
    const area = rect.width > 0 ? rect : surface.getBoundingClientRect();
    if (area.width <= 0) return;
    const index = nearestIndex((event.clientX - area.left) / area.width, chart.x);
    if (index < 0 || index === last) return;
    last = index;
    paint(index);
  };
  surface.addEventListener("pointermove", resolve, { signal, passive: true });
  surface.addEventListener("click", resolve, { signal });
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

/**
 * R6 on the axis: a chart drawing 60 of 131 months while implying it draws the record is a
 * naked number wearing a time series, so the count and the way back to the rest sit together.
 */
function windowBar(
  window_: ReturnType<typeof chartWindow>["window"],
  choices: ReturnType<typeof spanChoices>,
  span: number | null,
  served: boolean,
  onSpan: (span: number | null) => void,
): HTMLElement {
  const bar = document.createElement("div");
  bar.className = "gw-window-bar";
  const note = document.createElement("p");
  note.className = "gw-window-note";
  note.setAttribute("data-no-glossary", "");
  note.textContent = describeWindow(window_, served);
  bar.appendChild(note);
  if (choices.length < 2) return bar;

  const control = document.createElement("div");
  control.className = "gw-window-control";
  control.setAttribute("role", "group");
  control.setAttribute("aria-label", "How much of the production record to draw");
  for (const choice of choices) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "gw-window-span";
    button.setAttribute("aria-pressed", String(choice.span === span));
    button.title =
      choice.span === null
        ? "Draw every month on record."
        : `Draw the last ${choice.label} of the record.`;
    button.textContent = choice.label;
    button.addEventListener("click", () => onSpan(choice.span));
    control.appendChild(button);
  }
  bar.appendChild(control);
  return bar;
}

function legend(chart: ChartSeries, callbacks: ChartCallbacks): HTMLElement {
  const wrapper = document.createElement("ul");
  wrapper.className = "gw-chart-legend";
  for (const column of chart.columns) {
    const item = document.createElement("li");
    const swatch = document.createElement("span");
    swatch.className = "gw-swatch";
    swatch.style.background = streamStroke(column.stream);
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
    if (column.handle) item.appendChild(handleButton(column.handle, column.label, callbacks));
    wrapper.appendChild(item);
  }
  return wrapper;
}

function handleButton(handle: string, label: string, callbacks: ChartCallbacks): HTMLElement {
  // The chart is mounted into hosts that route explain themselves, so it calls back rather
  // than raising the event its own way.
  return explainHandle({ handle, label, activate: (id) => callbacks.onExplain(id) });
}

/**
 * Which vintage each stream was read at, one layer down. It is routine provenance rather than
 * a defect, and on the surface it wore the warning vocabulary; read off the windowed columns,
 * so it describes the months on screen and not the ones the span dropped (window.ts).
 */
function vintageDisclosure(chart: ChartSeries): HTMLElement | null {
  const rows = chart.columns
    .map((column) => ({ column, drawn: distinctVintages(column) }))
    .filter((row) => row.drawn.length > 0);
  if (rows.length === 0) return null;

  const details = document.createElement("details");
  details.className = "gw-vintages";
  const summary = document.createElement("summary");
  summary.textContent = "Report vintages";
  details.appendChild(summary);

  const list = document.createElement("dl");
  list.className = "gw-vintage-list";
  for (const { column, drawn } of rows) {
    const term = document.createElement("dt");
    term.textContent = column.label;
    const value = document.createElement("dd");
    value.setAttribute("data-no-glossary", "");
    value.textContent = column.mixedVintages ? drawn.join(", ") : (column.vintage ?? drawn[0] ?? "");
    list.append(term, value);
  }
  details.appendChild(list);
  return details;
}

function distinctVintages(column: SeriesColumn): string[] {
  const present = column.vintages.filter((vintage): vintage is string => vintage !== null);
  return [...new Set(present)].sort();
}

/** Without a key the band is a strip of colour, and the gap it explains stays ambiguous. */
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

/**
 * The four null-semantics states as one band per stream, aligned under the plot: a gap in the
 * line could be any of them, and the band says which without collapsing them into each other.
 */
function stateBand(chart: ChartSeries): HTMLElement {
  const wrapper = document.createElement("div");
  wrapper.className = "gw-state-strip";
  for (const column of chart.columns) {
    const row = document.createElement("div");
    row.className = "gw-state-row";
    const name = document.createElement("span");
    name.className = "gw-state-name";
    name.textContent = column.label;
    const cells = document.createElement("div");
    cells.className = "gw-state-cells";
    cells.setAttribute("role", "img");
    cells.setAttribute(
      "aria-label",
      `${column.label}: what was reported in each of ${chart.months.length} months.` +
        " Use the month stepper below to read any one of them.",
    );
    for (const [index, month] of chart.months.entries()) {
      cells.appendChild(mark(column, index, month));
    }
    row.append(name, cells);
    wrapper.appendChild(row);
  }
  return wrapper;
}

function mark(column: SeriesColumn, index: number, month: string): HTMLElement {
  const described = nullSemantics(column.nullSemantics[index] ?? "");
  const cell = document.createElement("span");
  cell.className = `gw-state-mark ${described.className}`;
  cell.setAttribute("data-index", String(index));
  cell.setAttribute("data-no-glossary", "");
  cell.title = `${formatMonth(month)} · ${column.label} · ${described.label}`;
  return cell;
}

/**
 * The month the reader is on, as DOM. It replaces the per-point target the back-load shrank to
 * two pixels: every figure here is a real element with a real handle beside it, and the stepper
 * is the keyboard path a canvas hover never had.
 */
function readoutContent(
  readout: Readout | null,
  index: number,
  count: number,
  callbacks: ChartCallbacks,
  paint: (index: number) => void,
): HTMLElement[] {
  if (!readout) return [placeholder("No month is selected.")];
  const head = document.createElement("div");
  head.className = "gw-readout-head";

  const label = document.createElement("p");
  label.className = "gw-readout-month";
  label.setAttribute("data-no-glossary", "");
  label.textContent = readout.monthLabel;

  const steps = document.createElement("div");
  steps.className = "gw-readout-steps";
  steps.append(
    step("gw-readout-prev", "‹", "The month before this one", index > 0, () => paint(index - 1)),
    step("gw-readout-next", "›", "The month after this one", index < count - 1, () =>
      paint(index + 1),
    ),
  );
  head.append(label, steps);

  return [head, ...readout.rows.map((row) => readoutRow(row, callbacks))];
}

function step(
  className: string,
  glyph: string,
  label: string,
  enabled: boolean,
  onClick: () => void,
): HTMLButtonElement {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `gw-readout-step ${className}`;
  button.disabled = !enabled;
  button.setAttribute("aria-label", label);
  button.title = label;
  button.textContent = glyph;
  button.addEventListener("click", onClick);
  return button;
}

function readoutRow(row: ReadoutRow, callbacks: ChartCallbacks): HTMLElement {
  const element = document.createElement("div");
  element.className = "gw-readout-row";
  element.dataset["stream"] = row.stream;

  const swatch = document.createElement("span");
  swatch.className = "gw-swatch";
  swatch.style.background = streamStroke(row.stream);
  const name = document.createElement("span");
  name.className = "gw-readout-name";
  name.textContent = row.label;

  const value = document.createElement("span");
  value.className = "gw-readout-value";
  value.setAttribute("data-no-glossary", "");
  // A month nobody measured states the state instead of a number: a gap is not a zero, and a
  // withheld volume is not this well's production (SB-05 §3.2).
  value.textContent = row.value === null ? ABSENT_MARK : `${row.value} ${row.unit}`;

  const state = document.createElement("span");
  state.className = "gw-readout-state";
  state.title = row.mark.title;
  const stateMark = document.createElement("span");
  stateMark.className = `gw-state-mark ${row.mark.className}`;
  state.append(stateMark, document.createTextNode(` ${row.mark.label}`));

  // The facts wrap among themselves; the handle does not leave the row it explains, which at
  // 390 is the difference between a button beside a number and a button under the next one.
  const facts = document.createElement("div");
  facts.className = "gw-readout-facts";
  facts.append(swatch, name, value, state);

  element.appendChild(facts);
  if (row.handle) {
    element.appendChild(handleButton(row.handle, `${row.label} in ${row.mark.label}`, callbacks));
  } else {
    const missing = document.createElement("span");
    missing.className = "gw-readout-nohandle";
    missing.textContent = "no derivation handle on the wire";
    element.appendChild(missing);
  }
  return element;
}

function placeholder(text: string): HTMLElement {
  const element = document.createElement("p");
  element.className = "gw-placeholder";
  element.textContent = text;
  return element;
}
