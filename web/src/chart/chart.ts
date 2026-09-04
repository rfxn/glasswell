import "./chart.css";

import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";

import {
  ABSENT_MARK,
  ALLOCATION_CLASSES,
  NULL_SEMANTICS_STATES,
  allocationClass,
  formatMonth,
  nullSemantics,
  shareDetail,
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

/** The served class a log axis cannot place, named once. */
const REPORTED_ZERO = "reported_zero";

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
  const hidden = new Set<string>();
  let log = false;
  // The month, not its index: widening the window renumbers every point, and a reader who was
  // reading March must not silently end up reading some month five years earlier.
  let month = chart.months[chart.months.length - 1] ?? null;

  const draw = (): void => {
    repaint?.abort();
    repaint = new AbortController();
    const signal = repaint.signal;
    const windowed = chartWindow(chart, span);
    const visible = shown(windowed.chart, hidden);
    // Two views of the same window: the band and the readout read every month the record has,
    // and the plot reads the line the axis can actually draw.
    const view = { window: windowed.window, chart: log ? withoutZeros(visible) : visible };
    const months = view.chart.months;
    if (month === null || !months.includes(month)) month = months[months.length - 1] ?? null;

    container.replaceChildren();
    container.classList.add("gw-chart");

    container.append(
      legend(windowed.chart, callbacks, hidden, (stream) => {
        if (hidden.has(stream)) hidden.delete(stream);
        else hidden.add(stream);
        draw();
      }),
      windowBar(view.window, choices, span, served, (next) => {
        span = next;
        draw();
      }),
    );
    // A window the record does not reach is served as an empty series. That is a fact about the
    // window, which the bar above has just stated — an empty axis under it would say nothing.
    if (months.length === 0) return;
    const axes = yAxisLabels(view.chart);
    axes.appendChild(
      scaleControl(visible, log, (next) => {
        log = next;
        draw();
      }),
    );
    container.appendChild(axes);

    const plot = document.createElement("div");
    plot.className = "gw-chart-plot";
    container.appendChild(plot);

    // The band reads the window, never the log view: a month that read zero is a fact about
    // the month, and the axis it cannot be drawn on is a fact about the drawing.
    const band = stateBand(visible);
    container.appendChild(band);
    const zeros = log ? logZeros(visible) : null;
    if (zeros) container.appendChild(zeros);

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
    const key = allocationKey(view.chart, callbacks);
    if (key) container.appendChild(key);
    const vintages = vintageDisclosure(view.chart);
    if (vintages) container.appendChild(vintages);

    const paint = (index: number): void => {
      const next = months[index];
      if (next === undefined) return;
      month = next;
      readout.replaceChildren(
        ...readoutContent(readoutAt(visible, index), index, months.length, callbacks, paint),
      );
      for (const cell of band.querySelectorAll(".gw-state-mark")) {
        cell.toggleAttribute("data-selected", Number(cell.getAttribute("data-index")) === index);
      }
    };

    const width = measure(plot, container);
    const instance = new uPlot(
      chartOptions(view.chart, width, log),
      view.chart.data as uPlot.AlignedData,
      plot,
    );
    signal.addEventListener("abort", () => instance.destroy());
    align(band, instance.over, plot);
    track(plot, container, band, instance, signal);

    // The whole plot rectangle and the whole band answer the pointer, because at 131 months a
    // per-point target measured 2 CSS px across and the reader could not land on one.
    for (const surface of [plot, band]) {
      seek(surface, () => instance.over, visible, paint, signal);
    }
    paint(months.indexOf(month as string));
  };

  document.addEventListener(THEME_EVENT, draw, { signal: outer.signal });
  draw();
}

/**
 * The series as the reader has it set: hidden streams dropped from the columns, the scales and
 * the drawn data together, so the plot, the band and the readout cannot disagree about which
 * streams are on. A stream is never dropped from the legend -- a toggle a reader cannot undo
 * is a delete.
 */
function shown(chart: ChartSeries, hidden: ReadonlySet<string>): ChartSeries {
  const columns = chart.columns.filter((column) => !hidden.has(column.stream));
  if (columns.length === chart.columns.length) return chart;
  const kept = chart.columns.map((column) => !hidden.has(column.stream));
  return {
    ...chart,
    columns,
    scales: [...new Set(columns.map((column) => column.unit))],
    data: [chart.data[0] as number[], ...chart.data.slice(1).filter((_, index) => kept[index])],
    allocated: columns.some((column) => column.allocationClasses.some(Boolean)),
  };
}

/**
 * A log axis cannot place a zero, and `reported_zero` is 15,641,969 of the spine's 47,178,269
 * production rows -- 33.2 % -- against 1,461 `no_report` rows in the whole system. So on log a
 * zero leaves the line and stays in the band and the readout, and the chart says so per stream:
 * a well can be zero on water and not on oil, and one combined count would be wrong for two of
 * the three.
 */
function isZero(column: SeriesColumn, index: number): boolean {
  return column.nullSemantics[index] === REPORTED_ZERO || column.values[index] === 0;
}

function withoutZeros(chart: ChartSeries): ChartSeries {
  return {
    ...chart,
    data: [
      chart.data[0] as number[],
      ...chart.data.slice(1).map((values, position) => {
        const column = chart.columns[position];
        return values.map((value, index) =>
          column && isZero(column, index) ? null : value,
        );
      }),
    ],
  };
}

function zeroMonths(column: SeriesColumn): number {
  return column.values.filter((_, index) => isZero(column, index)).length;
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

function legend(
  chart: ChartSeries,
  callbacks: ChartCallbacks,
  hidden: ReadonlySet<string>,
  onToggle: (stream: string) => void,
): HTMLElement {
  const wrapper = document.createElement("ul");
  wrapper.className = "gw-chart-legend";
  const showing = chart.columns.filter((column) => !hidden.has(column.stream)).length;
  for (const column of chart.columns) {
    const item = document.createElement("li");
    const on = !hidden.has(column.stream);
    // The legend is the control: a swatch that only reports is a second thing to look at, and
    // the reader's question here is "show me this one alone".
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "gw-stream-toggle";
    toggle.setAttribute("aria-pressed", String(on));
    const swatch = document.createElement("span");
    swatch.className = "gw-swatch";
    swatch.style.background = streamStroke(column.stream);
    toggle.appendChild(swatch);
    toggle.appendChild(
      labelElement(
        `${column.label} (${column.unit})`,
        callbacks.labelTermFor(`/series/${column.key}`),
      ),
    );
    if (on && showing === 1) {
      toggle.disabled = true;
      toggle.title = "The only stream on the plot: an axis with nothing on it says nothing.";
    } else {
      toggle.title = on ? `Hide ${column.label}.` : `Show ${column.label}.`;
      toggle.addEventListener("click", () => onToggle(column.stream));
    }
    item.appendChild(toggle);
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

/** Linear or log, beside the axes it rescales. Log is off by default, and the 33.2 % is why. */
function scaleControl(
  chart: ChartSeries,
  log: boolean,
  onScale: (log: boolean) => void,
): HTMLElement {
  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "gw-scale-toggle";
  toggle.setAttribute("aria-pressed", String(log));
  toggle.textContent = "Log";
  const drawable = chart.columns.some((column) =>
    column.values.some((value) => value !== null && value > 0),
  );
  if (!drawable) {
    toggle.disabled = true;
    toggle.title = "Every month shown reads zero, and a log axis cannot place a zero.";
    return toggle;
  }
  toggle.title = log ? "Draw the axes linearly." : "Draw the axes logarithmically.";
  toggle.addEventListener("click", () => onScale(!log));
  return toggle;
}

/** What log costs, per stream, in the months on screen. */
function logZeros(chart: ChartSeries): HTMLElement | null {
  const counted = chart.columns
    .map((column) => ({ label: column.label, zeros: zeroMonths(column) }))
    .filter((row) => row.zeros > 0);
  if (counted.length === 0) return null;
  const note = document.createElement("p");
  note.className = "gw-note gw-log-zeros";
  note.setAttribute("data-no-glossary", "");
  note.textContent =
    counted
      .map((row) => `${row.label}: ${row.zeros} month${row.zeros === 1 ? "" : "s"} read zero`)
      .join("; ") +
    ". A log axis cannot place a zero, so those months are in the band and the readout and not" +
    " on the line.";
  return note;
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
/**
 * The four the API distinguishes, drawn whether or not this well hit them -- they are the
 * vocabulary, and a reader learns it from the key -- plus any state a served series actually
 * carries beyond them. A mark on the band with nothing in the key to read it by is a colour
 * the reader has to guess at.
 */
function keyStates(chart: ChartSeries): string[] {
  const states = new Set<string>(NULL_SEMANTICS_STATES);
  for (const column of chart.columns) {
    for (const state of column.nullSemantics) if (state) states.add(state);
  }
  return [...states];
}

function stateKey(chart: ChartSeries, callbacks: ChartCallbacks): HTMLElement {
  const wrapper = document.createElement("p");
  wrapper.className = "gw-state-key";
  const pointer = chart.columns[0] ? `/series/${chart.columns[0].key}_null_semantics` : "";
  for (const state of keyStates(chart)) {
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
    name.textContent = bandSubject(column);
    if (leaseGrain(column)) {
      name.title =
        `What the lease filed for ${column.label.toLowerCase()} each month. This well's` +
        " number is its share of that filing, and the row below says how the share was made.";
    }
    const cells = document.createElement("div");
    cells.className = "gw-state-cells";
    cells.setAttribute("role", "img");
    cells.setAttribute(
      "aria-label",
      (leaseGrain(column)
        ? `${column.label}: what the lease filed in each of ${chart.months.length} months.`
        : `${column.label}: what was reported in each of ${chart.months.length} months.`) +
        " Use the month stepper below to read any one of them.",
    );
    for (const [index, month] of chart.months.entries()) {
      cells.appendChild(mark(column, index, month));
    }
    row.append(name, cells);
    wrapper.appendChild(row);
  }
  // The allocation rows go inside this wrapper, not beside it. `align` sets --gw-band-left and
  // --gw-band-right on the element it is handed, and a sibling strip inherits neither -- which
  // is a band drawn to a different width from the plot it sits under, and which was exactly
  // what the first shot showed.
  for (const row of allocationRows(chart)) wrapper.appendChild(row);
  return wrapper;
}

/** Whether the series was filed at the lease and this well's points are its shares. */
function leaseGrain(column: SeriesColumn): boolean {
  return column.allocationClasses.some((state) => state !== "");
}

/**
 * The first band's subject, in words, on screen. Two bands under one chart that both read
 * `Oil` are one claim to a reader; the filing and the share are two. Two words, because the
 * name sits in the plot's own left gutter: `lease filing` measured 77 px against 58 px of
 * column and truncated to `Oil · leas...`, and a subject a reader cannot read is not one.
 */
function bandSubject(column: SeriesColumn): string {
  return leaseGrain(column) ? `${column.label} · lease` : column.label;
}

function mark(column: SeriesColumn, index: number, month: string): HTMLElement {
  const described = nullSemantics(column.nullSemantics[index] ?? "");
  const cell = document.createElement("span");
  cell.className = `gw-state-mark ${described.className}`;
  if (column.incomplete[index]) cell.classList.add("gw-month-incomplete");
  cell.setAttribute("data-index", String(index));
  cell.setAttribute("data-no-glossary", "");
  cell.title = `${formatMonth(month)} · ${column.label} · ${described.label}`;
  return cell;
}

/**
 * The allocation band: a second strip under the first, in its own vocabulary and its own CSS
 * prefix. Drawn only where a class reached the wire, so an observed jurisdiction's chart is
 * unchanged and a Texas well never shows a share without saying it is one.
 */
function allocationRows(chart: ChartSeries): HTMLElement[] {
  if (!chart.allocated) return [];
  const rows: HTMLElement[] = [];
  for (const column of chart.columns) {
    if (column.allocationClasses.every((state) => state === "")) continue;
    const row = document.createElement("div");
    row.className = "gw-state-row gw-alloc-row";
    const name = document.createElement("span");
    name.className = "gw-state-name";
    name.textContent = `${column.label} · how`;
    const cells = document.createElement("div");
    cells.className = "gw-state-cells gw-alloc-cells";
    cells.setAttribute("role", "img");
    cells.setAttribute(
      "aria-label",
      `${column.label}: how each of ${chart.months.length} months was arrived at:` +
        " observed where the lease had one eligible well, allocated where it had more.",
    );
    for (const [index, month] of chart.months.entries()) {
      cells.appendChild(allocationMark(column, index, month));
    }
    row.append(name, cells);
    rows.push(row);
  }
  return rows;
}

function allocationMark(column: SeriesColumn, index: number, month: string): HTMLElement {
  const state = column.allocationClasses[index] ?? "";
  const described = allocationClass(state);
  const cell = document.createElement("span");
  cell.className = `gw-alloc-mark ${described.className}`;
  if (column.incomplete[index]) cell.classList.add("gw-month-incomplete");
  cell.setAttribute("data-index", String(index));
  cell.setAttribute("data-no-glossary", "");
  const detail = shareDetail(column.eligibleWells[index] ?? null, column.shares[index] ?? null);
  cell.title = `${formatMonth(month)} · ${column.label} · ${described.label}${detail}`;
  return cell;
}

/**
 * The allocation band's own key, in its own vocabulary and only for what this well's band
 * drew. Six entries under a band showing one class made the band read as a component that
 * had failed to draw the other five.
 */
function allocationKey(chart: ChartSeries, callbacks: ChartCallbacks): HTMLElement | null {
  if (!chart.allocated) return null;
  const wrapper = document.createElement("p");
  wrapper.className = "gw-alloc-key";
  const first = chart.columns.find((entry) =>
    entry.allocationClasses.some((state) => state !== ""),
  );
  const pointer = first ? `/series/${first.key}_allocation_class_by_month` : "";
  for (const state of servedClasses(chart)) {
    const described = allocationClass(state);
    const item = document.createElement("span");
    item.className = "gw-state-key-item";
    const swatch = document.createElement("span");
    swatch.className = `gw-alloc-mark ${described.className}`;
    swatch.title = described.title;
    item.appendChild(swatch);
    item.appendChild(labelElement(described.label, callbacks.labelTermFor(pointer)));
    wrapper.appendChild(item);
  }
  return wrapper;
}

/**
 * The classes this series actually carries, in the order the vocabulary lists them, plus any
 * the vocabulary does not know: a mark on the band with no entry in the key is a texture the
 * reader has to guess at, which is the opposite failure to keying five classes nothing drew.
 */
function servedClasses(chart: ChartSeries): string[] {
  const served = new Set(
    chart.columns.flatMap((column) => column.allocationClasses).filter((state) => state !== ""),
  );
  const known: string[] = ALLOCATION_CLASSES.filter((state) => served.has(state));
  return [...known, ...[...served].filter((state) => !known.includes(state))];
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

  // How the number was arrived at, in the one place a reader reads one number. The band says
  // it across the whole series and the readout is where a share would otherwise sit beside the
  // word "reported" with nothing to say it is an estimate.
  const how = document.createElement("span");
  if (row.allocation) {
    how.className = "gw-readout-alloc";
    how.title = row.allocation.title;
    const allocMark = document.createElement("span");
    allocMark.className = `gw-alloc-mark ${row.allocation.className}`;
    const detail = shareDetail(row.eligibleWells, row.shares);
    how.append(allocMark, document.createTextNode(` ${row.allocation.label}${detail}`));
  }

  // The facts wrap among themselves; the handle does not leave the row it explains, which at
  // 390 is the difference between a button beside a number and a button under the next one.
  const facts = document.createElement("div");
  facts.className = "gw-readout-facts";
  facts.append(swatch, name, value, state);
  if (row.allocation) facts.appendChild(how);

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
