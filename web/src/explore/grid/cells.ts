import { derivationFor, isFigure, sidecarFor } from "../../api/envelope.ts";
import { formatValue, nullSemantics } from "../../card/format.ts";
import "../../card/gw-figure.ts";
import "../gw-count.ts";
import type { Column } from "./columns.ts";
import type { Cell, Row } from "./rows.ts";

const ABSENT =
  "This field was absent from the response. That is not the same as a zero and not the same" +
  " as a value the source withheld.";
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
  const handle = source?.d ?? derivationFor(context.data, cell.dataPointer) ?? "";
  const unit = source?.unit ?? sidecarFor(context.data, cell.dataPointer, "_units") ?? "";
  const figure = document.createElement("gw-figure");
  figure.setAttribute("value", String(source?.value ?? cell.value));
  figure.setAttribute("unit", unit);
  figure.setAttribute("handle", handle);
  figure.setAttribute("label", column.name);
  figure.setAttribute("label-hidden", "");

  const granularity = granularityOf(context.row) ?? source?.granularity ?? null;
  if (granularity) figure.setAttribute("granularity", granularity);
  const vintage = cell.companions["_report_vintage"] ?? source?.report_vintage ?? null;
  if (typeof vintage === "string" && context.uniformVintage !== true) {
    figure.setAttribute("vintage", vintage);
  }

  return [figure, ...stateStrip(cell), ...aggregation(cell)];
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

/** §3.2: `reported_zero`, `no_report`, `withheld` and `multi_pool_pending` are different facts. */
function stateStrip(cell: Cell): Node[] {
  const state = cell.companions["_null_semantics"];
  if (typeof state !== "string" || state === "reported") return [];
  return [stateChip(state)];
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
function stateChip(state: string): HTMLElement {
  const mark = nullSemantics(state);
  const chip = document.createElement("span");
  chip.className = "gw-state";
  chip.dataset["state"] = state;
  chip.title = mark.title;
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
  element.className = "gw-cell-absent";
  element.setAttribute("data-no-glossary", "");
  element.textContent = "—";
  element.title = title;
  return element;
}

/** SB-05 §5.3's exclusion: no glossary underline inside `qr_01…`, which closes P2-12 here. */
function identifier(value: string): HTMLElement {
  const element = document.createElement("code");
  element.className = "gw-cell-id";
  element.setAttribute("data-no-glossary", "");
  element.textContent = value;
  return element;
}

function enumCell(column: Column, cell: Cell): Node[] {
  const text = String(cell.value);
  if (!column.termId) {
    const plain = document.createElement("span");
    plain.className = "gw-cell-enum";
    plain.textContent = text;
    return [plain];
  }
  const term = document.createElement("gw-term");
  term.setAttribute("term-id", column.termId);
  term.className = "gw-cell-enum";
  term.textContent = text;
  return [term];
}

function timestamp(value: string): Node[] {
  const match = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})/.exec(value);
  if (!match) {
    const plain = document.createElement("time");
    plain.className = "gw-cell-time";
    plain.setAttribute("datetime", value);
    plain.textContent = value;
    return [plain];
  }
  const element = document.createElement("time");
  element.className = "gw-cell-time";
  element.setAttribute("datetime", value);
  element.textContent = match[1] as string;
  const clock = document.createElement("span");
  clock.className = "gw-cell-clock";
  clock.textContent = match[2] as string;
  return [element, clock];
}

/** §3.2: a coordinate in a cell teaches the wrong thing, and the map is where geometry reads. */
function geometry(): HTMLElement {
  const element = document.createElement("span");
  element.className = "gw-cell-geometry";
  element.textContent = "on the map";
  element.title =
    "Geometry renders on the map, never as coordinates in a cell. The crossing from a row to" +
    " its shape lands with the map bridge.";
  return element;
}

function prose(value: unknown): HTMLElement {
  const element = document.createElement("span");
  element.className = "gw-cell-prose";
  element.textContent = Array.isArray(value)
    ? value.map(String).join(" · ")
    : typeof value === "number"
      ? formatValue(String(value))
      : String(value);
  return element;
}
