import { derivationFor, isFigure, sidecarFor } from "../../api/envelope.ts";
import { formatValue, nullSemantics } from "../../card/format.ts";
import "../../card/gw-figure.ts";
import "../gw-count.ts";
import type { Column } from "./columns.ts";
import type { Cell, Row } from "./rows.ts";

const ABSENT =
  "This field was absent from the response. That is not the same as a zero and not the same" +
  " as a value the source withheld.";
/** The three labels whose volume is a NOT NULL placeholder rather than a measurement. */
const PLACEHOLDER_SEMANTICS = new Set(["no_report", "withheld", "multi_pool_pending"]);

const NO_SEMANTICS =
  "The response carried no value here and stated no null semantics for it, so what the blank" +
  " means is unknown rather than zero.";

export interface CellContext {
  /** The envelope's `data`, because every sidecar lookup is rooted there. */
  data: unknown;
  row: Row;
  /**
   * True when every figure in this response reports at the same vintage. The chip is then
   * stated once above the grid instead of eighteen times inside it — a chip on every row
   * teaches nothing, and the one that appears on the row that was restated teaches everything.
   */
  uniformVintage?: boolean;
}

export function renderCell(column: Column, context: CellContext): HTMLElement {
  const cell = context.row.cells[column.pointer];
  const container = document.createElement("div");
  container.className = `gw-cell gw-cell-${column.kind}`;
  container.dataset["pointer"] = cell?.dataPointer ?? column.pointer;

  if (cell === undefined || cell.value === undefined) {
    container.append(missing(ABSENT));
    return container;
  }
  if (cell.value === null) {
    container.append(nullCell(cell));
    return container;
  }
  container.append(...body(column, cell, context));
  return container;
}

function body(column: Column, cell: Cell, context: CellContext): Node[] {
  switch (column.kind) {
    case "figure":
      return figureCell(column, cell, context);
    case "count":
      return countCell(column, cell, context);
    case "identifier":
      return [identifier(String(cell.value))];
    case "enum":
      return enumCell(column, cell);
    case "timestamp":
      return timestamp(String(cell.value));
    case "geometry":
      return [geometry()];
    case "prose":
      return [prose(cell.value)];
  }
}

/**
 * The pivot's value columns are bare strings with a dotted `_lineage` sidecar (C2 MUST-KNOW P1),
 * so the handle comes from the pointer's longest prefix rather than from the value's own `d`.
 */
function figureCell(column: Column, cell: Cell, context: CellContext): Node[] {
  const source = isFigure(cell.value) ? cell.value : null;
  const served = String(source?.value ?? cell.value);
  const unit = source?.unit ?? sidecarFor(context.data, cell.dataPointer, "_units") ?? "";
  const state = cell.companions["_null_semantics"];
  // `canonical.volume` is NOT NULL, so the ingest carries an absent volume as zero and the
  // label is the only thing distinguishing it from a reported zero (`ingest/nd_mpr.py:89-93`).
  // Rendering the placeholder beside the label is that collapse in reverse, and `0.000 bbl`
  // reading as a filed zero is the misread the whole vocabulary exists to prevent.
  if (typeof state === "string" && PLACEHOLDER_SEMANTICS.has(state)) {
    return [stateChip(state, served, unit)];
  }

  const handle = source?.d ?? derivationFor(context.data, cell.dataPointer) ?? "";
  const figure = document.createElement("gw-figure");
  figure.setAttribute("value", withoutEmptyFraction(served));
  figure.setAttribute("unit", unit);
  figure.setAttribute("handle", handle);
  figure.setAttribute("label", column.name);
  figure.setAttribute("label-hidden", "");
  figure.title = `${served}${unit ? ` ${unit}` : ""} as served`;

  const granularity = granularityOf(context.row) ?? source?.granularity ?? null;
  if (granularity) figure.setAttribute("granularity", granularity);
  const vintage = cell.companions["_report_vintage"] ?? source?.report_vintage ?? null;
  if (typeof vintage === "string" && context.uniformVintage !== true) {
    figure.setAttribute("vintage", vintage);
  }

  return [figure, ...marks(cell)];
}

/**
 * C1: `1,000.000 bbl` invites a 1000x misread — comma thousands beside a three-place dot
 * decimal, on a value that is an exact thousand. Nothing is rounded and no precision is
 * claimed away: only a fraction that is entirely zeros is dropped, and the served string stays
 * on the element. `card/format.ts:formatVolume` already ruled that a monthly volume is not
 * measured to a thousandth; this is the same finding without rounding anything.
 */
export function withoutEmptyFraction(value: string): string {
  const match = /^(-?\d+)\.0+$/.exec(value.trim());
  return match ? (match[1] as string) : value;
}

/**
 * T1's coupling, made mechanical: the moment an operation carries `_lineage` and `_units` for a
 * counted column, the same cell renders as a handled figure with no client change. A handle
 * without a unit cannot become a figure — `formatFigure` refuses it — so the handle rides the
 * count instead of being dropped (O-1, `x-glasswell-unit`, is the missing half).
 */
function countCell(column: Column, cell: Cell, context: CellContext): Node[] {
  const handle = derivationFor(context.data, cell.dataPointer);
  const unit = sidecarFor(context.data, cell.dataPointer, "_units");
  if (handle && unit) return figureCell(column, cell, context);

  const count = document.createElement("gw-count");
  count.setAttribute("value", String(cell.value));
  if (column.reason) count.setAttribute("reason", column.reason);
  else count.setAttribute("no-reason", "");
  if (handle) count.setAttribute("data-handle", handle);
  return [count];
}

/**
 * §3.2: `reported_zero`, `no_report`, `withheld` and `multi_pool_pending` are different facts.
 *
 * F2: the marks live in the cell's own second track, not in the number's, so a row that carries
 * one cannot push its value off the column's right edge. A numeric column is right-aligned so
 * magnitudes compare down the column by eye; one indented row breaks exactly that read.
 */
function marks(cell: Cell): Node[] {
  const slot = document.createElement("span");
  slot.className = "gw-cell-marks";
  const state = cell.companions["_null_semantics"];
  if (typeof state === "string" && state !== "reported") slot.append(stateChip(state));
  slot.append(...aggregation(cell));
  return [slot];
}

/** Every report vintage this response carries, so the grid can state one once or chip many. */
export function vintagesIn(rows: readonly Row[]): Set<string> {
  const found = new Set<string>();
  for (const row of rows) {
    for (const cell of Object.values(row.cells)) {
      const vintage = cell.companions["_report_vintage"];
      if (typeof vintage === "string") found.add(vintage);
      else if (isFigure(cell.value) && typeof cell.value.report_vintage === "string") {
        found.add(cell.value.report_vintage);
      }
    }
  }
  return found;
}

/** The chart's own swatch classes carry the palette; the grid adds the word beside the mark. */
function stateChip(state: string, replaced?: string, unit?: string): HTMLElement {
  const mark = nullSemantics(state);
  const chip = document.createElement("span");
  chip.className = "gw-state";
  chip.dataset["state"] = state;
  // Naming the placeholder it stands in for keeps the substitution auditable rather than
  // silent: a reader who wonders what the API actually sent can read it here.
  chip.title = replaced
    ? `${mark.title} The response carried ${replaced}${unit ? ` ${unit}` : ""} here, which is a placeholder rather than a measurement.`
    : mark.title;
  const swatch = document.createElement("span");
  swatch.className = `gw-state-mark ${mark.className}`;
  chip.append(swatch, document.createTextNode(mark.label));
  return chip;
}

function aggregation(cell: Cell): Node[] {
  const how = cell.companions["_aggregation"];
  if (typeof how !== "string" || how === "") return [];
  const chip = document.createElement("span");
  chip.className = "gw-chip gw-chip-aggregation";
  chip.textContent = how;
  chip.title = `This month was composed as ${how}, not observed at this level.`;
  return [chip];
}

function granularityOf(row: Row): string | null {
  const value = row.cells["/granularity"]?.value;
  return typeof value === "string" ? value : null;
}

function nullCell(cell: Cell): Node {
  const state = cell.companions["_null_semantics"];
  return typeof state === "string" ? stateChip(state) : missing(NO_SEMANTICS);
}

function missing(title: string): HTMLElement {
  const element = document.createElement("span");
  element.className = "gw-value-absent";
  element.setAttribute("data-no-glossary", "");
  element.textContent = "—";
  element.title = title;
  return element;
}

/** SB-05 §5.3's exclusion: no glossary underline inside `qr_01…`, which closes P2-12 here. */
function identifier(value: string): HTMLElement {
  const element = document.createElement("code");
  element.className = "gw-value-id";
  element.setAttribute("data-no-glossary", "");
  element.textContent = value;
  return element;
}

function enumCell(column: Column, cell: Cell): Node[] {
  const text = String(cell.value);
  if (!column.termId) {
    const plain = document.createElement("span");
    plain.className = "gw-value-enum";
    plain.textContent = text;
    return [plain];
  }
  const term = document.createElement("gw-term");
  term.setAttribute("term-id", column.termId);
  term.className = "gw-value-enum";
  term.textContent = text;
  return [term];
}

function timestamp(value: string): Node[] {
  const match = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})/.exec(value);
  if (!match) {
    const plain = document.createElement("time");
    plain.className = "gw-value-time";
    plain.setAttribute("datetime", value);
    plain.textContent = value;
    return [plain];
  }
  const element = document.createElement("time");
  element.className = "gw-value-time";
  element.setAttribute("datetime", value);
  element.textContent = match[1] as string;
  const clock = document.createElement("span");
  clock.className = "gw-value-clock";
  clock.textContent = match[2] as string;
  return [element, clock];
}

/** §3.2: a coordinate in a cell teaches the wrong thing, and the map is where geometry reads. */
function geometry(): HTMLElement {
  const element = document.createElement("span");
  element.className = "gw-value-geometry";
  element.textContent = "on the map";
  element.title =
    "Geometry renders on the map, never as coordinates in a cell. The crossing from a row to" +
    " its shape lands with the map bridge.";
  return element;
}

/** F1: prose is the one kind that ellipsizes, so it is the one kind that must say what from. */
function prose(value: unknown): HTMLElement {
  const element = document.createElement("span");
  element.className = "gw-value-prose";
  element.textContent = Array.isArray(value)
    ? value.map(String).join(" · ")
    : typeof value === "number"
      ? formatValue(String(value))
      : String(value);
  element.title = element.textContent;
  return element;
}
