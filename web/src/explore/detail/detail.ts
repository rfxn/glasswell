import "./detail.css";

import { getEnvelope } from "../../api/client.ts";
import type { ResponseMeta } from "../../api/client.ts";
import { isFigure, valueAt } from "../../api/envelope.ts";
import type { AppState } from "../../app/state.ts";
import { labelElement } from "../../glossary/gw-term.ts";
import { publishCall } from "../api/context.ts";
import type { CatalogueDataset } from "../catalogue.ts";
import { renderCell } from "../grid/cells.ts";
import { columnsFor } from "../grid/columns.ts";
import type { Column } from "../grid/columns.ts";
import type { Cell, Row } from "../grid/rows.ts";
import { operationFor, pathFor } from "../grid/schema.ts";
import { inertChip, isJoinField, joinsFor, recordStep, renderChip, renderTrail } from "./chips.ts";

const PATH_PARAMETER = /\{([^}]+)\}/g;
/** Sidecars are how a figure carries its handle, not fields of the record. */
const SIDECAR = /^\/_/;
/** The envelope's own navigation. §4.4's RESPONSE section is where links read. */
const NAVIGATION = "/links";

const PAYLOAD_CAPTION =
  "this is the source row as it arrived, not a number the system stands behind";

export interface DetailOptions {
  dataset: CatalogueDataset;
  document: unknown;
  datasets: readonly CatalogueDataset[];
  state: AppState;
  /** The grid row, when this id is on the page the grid loaded. A chip hop arrives without one. */
  row: Row | null;
  rowId: string;
  columns: readonly Column[];
  /** The grid envelope's `data`, because a row's sidecars are rooted there. */
  data: unknown;
  request: { path: string; query: Record<string, string[]> };
  navigate(next: AppState): void;
  close(): void;
  signal: AbortSignal;
}

// §3.4's own default, and not in the URL: it changes nothing a shared link teaches (§2.1).
let pointersOn = false;

export function pointerLabels(): boolean {
  return pointersOn;
}

export function setPointerLabels(on: boolean): void {
  pointersOn = on;
}

export async function mountDetail(host: HTMLElement, options: DetailOptions): Promise<void> {
  const root = document.createElement("div");
  root.className = "gw-detail";
  root.dataset["rowId"] = options.rowId;
  root.dataset["pointers"] = pointersOn ? "on" : "off";
  root.setAttribute("role", "region");
  root.setAttribute("aria-label", `Row ${options.rowId}`);
  host.replaceChildren(root);

  const body = document.createElement("div");
  body.className = "gw-detail-body";
  root.append(header(root, options), body);

  const detail = detailDatasetFor(options.dataset, options.document);
  if (options.row) {
    renderRecord(body, options, {
      columns: [...options.columns],
      row: options.row,
      data: options.data,
      source: detail
        ? `the row as the collection served it — fetching the fuller record from ${detail.operationId}`
        : `${options.dataset.operationId} declares no detail operation, so these are the row's own fields as the collection served them`,
    });
  }

  if (!detail) {
    if (!options.row) body.append(missingRow(options));
    step(options, options.dataset.operationId, options.request);
    root.append(...trailNodes(options));
    return;
  }

  const request = detailRequest(detail, options);
  if (!request) {
    body.append(
      note(
        `${detail.operationId} is read by ${detail.pathParameters.join(" and ")}, and this row supplies no value for it.`,
      ),
    );
    return;
  }

  const response: { out?: ResponseMeta } = {};
  try {
    const envelope = await getEnvelope<unknown>(
      request.path,
      request.query,
      options.signal,
      response,
    );
    if (options.signal.aborted) return;
    // C8 N1: while a row is open the record is the call in view, so the pane renders it over
    // the collection's rather than teaching a request the reader has moved on from.
    publishRecord(detail, request, "loaded", { envelope, meta: response.out ?? null });
    const columns = columnsFor(detail, options.document, envelope).filter(listed);
    renderRecord(body, options, {
      columns,
      row: recordRow(columns, envelope.data),
      data: envelope.data,
      source: `${detail.operationId} — the fuller record, ${columns.length} fields`,
      omitted: omittedFrom(envelope.data, columns),
    });
    step(options, detail.operationId, request);
    root.append(...trailNodes(options));
  } catch (error) {
    if (options.signal.aborted) return;
    publishRecord(detail, request, "failed", { error, meta: response.out ?? null });
    body.append(
      note(`${detail.operationId} did not answer: ${String(error)}. The fields above are the collection's.`),
    );
  }
}

function publishRecord(
  detail: CatalogueDataset,
  request: { path: string; query: Record<string, string[]> },
  state: "loaded" | "failed",
  answer: { envelope?: unknown; error?: unknown; meta?: ResponseMeta | null },
): void {
  publishCall({
    state,
    role: "record",
    dataset: detail,
    request: { operationId: detail.operationId, path: request.path, query: request.query },
    envelope: (answer.envelope as never) ?? null,
    error: answer.error ?? null,
    meta: answer.meta ?? null,
  });
}

interface RecordView {
  columns: readonly Column[];
  row: Row;
  data: unknown;
  source: string;
  omitted?: string[];
}

function renderRecord(body: HTMLElement, options: DetailOptions, view: RecordView): void {
  const source = document.createElement("p");
  source.className = "gw-detail-source";
  source.textContent = view.source;

  const list = document.createElement("dl");
  list.className = "gw-detail-fields";
  for (const column of view.columns) list.append(field(column, view, options));

  const nodes: Node[] = [source, list];
  if (view.omitted && view.omitted.length > 0) {
    nodes.push(
      note(
        `${view.omitted.join(", ")} ${view.omitted.length === 1 ? "is" : "are"} not listed here: the API guide renders the envelope's navigation.`,
      ),
    );
  }
  body.replaceChildren(...nodes);
}

function field(column: Column, view: RecordView, options: DetailOptions): HTMLElement {
  const wrapper = document.createElement("div");
  wrapper.className = "gw-detail-field";
  wrapper.dataset["kind"] = column.kind;

  const key = document.createElement("dt");
  key.className = "gw-detail-key";
  key.append(labelElement(column.name, column.termId));
  if (column.binding === "unbound") key.append(unbound(column));
  const pointer = document.createElement("code");
  pointer.className = "gw-detail-pointer";
  pointer.textContent = column.labelPointer;
  key.append(pointer);

  const value = document.createElement("dd");
  value.className = "gw-detail-value";
  const cell = view.row.cells[column.pointer];
  value.append(...valueNodes(column, cell, view, options));
  if (column.hiddenReason) value.append(hiddenNote(column.hiddenReason));

  wrapper.append(key, value);
  return wrapper;
}

function valueNodes(
  column: Column,
  cell: Cell | undefined,
  view: RecordView,
  options: DetailOptions,
): Node[] {
  const raw = cell?.value;
  // A coordinate is never printed (§3.2), so geometry keeps the grid's treatment even though
  // its value is an object; everything else structural reads as the JSON it is.
  if (column.kind !== "geometry" && isStructural(raw)) {
    return [jsonView(column, raw, view.row)];
  }
  // m12: kind is decided per response, not per schema. A `FigureModel` reaches the detail
  // behind an `anyOf` nullable, which the schema walk cannot see through — but the value
  // carries its own unit and handle, and that is the classification.
  const shape = isFigure(raw) && column.kind !== "figure" ? { ...column, kind: "figure" as const } : column;
  const rendered = renderCell(shape, { data: view.data, row: view.row });
  // The row's own identity is not a hop and not a missing endpoint: it is where the reader is.
  if (options.dataset.row_id.includes(column.pointer)) return [rendered];
  if (!isJoinField(column.pointer, options.datasets)) return [rendered];

  const values = Array.isArray(raw) ? raw : [raw];
  const chips = document.createElement("span");
  chips.className = "gw-join-chips";
  for (const one of values) {
    if (typeof one !== "string" || one === "") continue;
    const joins = joinsFor(column.pointer, one, {
      from: options.dataset,
      datasets: options.datasets,
      document: options.document,
      state: options.state,
    });
    if (joins.length === 0) {
      chips.append(inertChip(column.pointer));
      continue;
    }
    for (const join of joins) {
      chips.append(renderChip(join, options.state, { navigate: options.navigate, signal: options.signal }));
    }
  }
  return chips.childElementCount > 0 ? [rendered, chips] : [rendered];
}

function isStructural(value: unknown): boolean {
  if (isFigure(value)) return false;
  if (Array.isArray(value)) return value.some((item) => typeof item === "object" && item !== null);
  return typeof value === "object" && value !== null;
}

/**
 * §3.7's quarantine treatment. A key is highlighted only when the record itself names it —
 * `applies_to_fields` does, a reason code does not — because inventing which field offended is
 * exactly the confident nonsense the caption exists to refuse.
 */
function jsonView(column: Column, value: unknown, row: Row): HTMLElement {
  const wrapper = document.createElement("div");
  wrapper.className = "gw-json";
  const named = namedElsewhere(row, column.pointer);
  const block = document.createElement("pre");
  block.className = "gw-json-block";
  let highlighted = 0;

  for (const line of JSON.stringify(value, null, 2).split("\n")) {
    const rendered = document.createElement("span");
    rendered.className = "gw-json-line";
    const key = /^\s*"([^"]+)":/.exec(line)?.[1];
    if (key !== undefined && named.has(key)) {
      rendered.classList.add("gw-json-offender");
      highlighted += 1;
    }
    rendered.textContent = line;
    // No newline beside it: the span is a block, and `white-space: pre` would break twice.
    block.append(rendered);
  }
  wrapper.append(block);

  if (/payload/.test(column.name)) {
    const caption = document.createElement("p");
    caption.className = "gw-json-caption";
    caption.textContent = PAYLOAD_CAPTION;
    wrapper.append(caption);
    if (highlighted === 0) {
      wrapper.append(
        note("the response does not name which field was refused, so nothing here is highlighted"),
      );
    }
  }
  return wrapper;
}

function namedElsewhere(row: Row, exclude: string): Set<string> {
  const named = new Set<string>();
  for (const [pointer, cell] of Object.entries(row.cells)) {
    if (pointer === exclude) continue;
    if (typeof cell.value === "string") named.add(cell.value);
    else if (Array.isArray(cell.value)) {
      for (const item of cell.value) if (typeof item === "string") named.add(item);
    }
  }
  return named;
}

function header(root: HTMLElement, options: DetailOptions): HTMLElement {
  const head = document.createElement("header");
  head.className = "gw-detail-head";

  const title = document.createElement("p");
  title.className = "gw-detail-title";
  title.textContent = `${options.dataset.title} · ${options.rowId}`;

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "gw-detail-pointers";
  toggle.textContent = "pointers";
  toggle.setAttribute("aria-pressed", String(pointersOn));
  toggle.title =
    "Show each field's JSON Pointer, which is the key meta.labels, _lineage and the walker all speak.";
  toggle.addEventListener(
    "click",
    () => {
      setPointerLabels(!pointersOn);
      root.dataset["pointers"] = pointersOn ? "on" : "off";
      toggle.setAttribute("aria-pressed", String(pointersOn));
    },
    { signal: options.signal },
  );

  const close = document.createElement("button");
  close.type = "button";
  close.className = "gw-detail-close";
  close.textContent = "close";
  close.setAttribute("aria-label", "Close this row");
  close.addEventListener("click", () => options.close(), { signal: options.signal });

  head.append(title, toggle, close);
  return head;
}

function missingRow(options: DetailOptions): HTMLElement {
  return note(
    `${options.rowId} is not on the page this collection loaded, and ${options.dataset.operationId} declares no detail operation, so there is no second request that could fetch it alone.`,
  );
}

function unbound(column: Column): HTMLElement {
  const marker = document.createElement("span");
  marker.className = "gw-col-unbound";
  marker.textContent = "?";
  marker.title = `${column.name}: this field has no glossary entry yet.`;
  marker.setAttribute("aria-label", `${column.name} has no glossary entry yet`);
  return marker;
}

function hiddenNote(reason: string): HTMLElement {
  const note_ = document.createElement("span");
  note_.className = "gw-detail-hidden";
  note_.textContent = "hidden in the grid";
  note_.title = reason;
  return note_;
}

function note(text: string): HTMLElement {
  const element = document.createElement("p");
  element.className = "gw-detail-note";
  element.textContent = text;
  return element;
}

function listed(column: Column): boolean {
  return !SIDECAR.test(column.pointer) && column.pointer !== NAVIGATION;
}

function omittedFrom(data: unknown, columns: readonly Column[]): string[] {
  const shown = new Set(columns.map((column) => column.pointer));
  if (typeof data !== "object" || data === null) return [];
  return Object.keys(data).filter((name) => `/${name}` === NAVIGATION && !shown.has(NAVIGATION));
}

/**
 * The detail operation read as a dataset of one: the same column kinds, the same binding
 * precedence and the same figure treatment as the grid, off the detail response's own schema.
 */
export function detailDatasetFor(
  dataset: CatalogueDataset,
  document: unknown,
): CatalogueDataset | null {
  const operationId = dataset.detail_operation;
  if (operationId === undefined) return null;
  const path = pathFor(document, operationId);
  if (path === null) return null;

  const flattened: CatalogueDataset = {
    ...dataset,
    operationId,
    path,
    pathParameters: [...path.matchAll(PATH_PARAMETER)].map((match) => match[1] as string),
    collection_pointer: "",
    anchors: [],
    columns: { hidden: [], hidden_reason: {} },
  };
  // A detail response is one record, so the pivot that turned a series into rows is gone with it.
  delete flattened.row_projection;
  delete flattened.series_pointer;
  delete flattened.columns.default;
  return flattened;
}

function recordRow(columns: readonly Column[], data: unknown): Row {
  const cells: Record<string, Cell> = {};
  for (const column of columns) {
    cells[column.pointer] = {
      pointer: column.pointer,
      dataPointer: column.pointer,
      namespace: "element",
      value: valueAt(data, column.pointer),
      companions: {},
    };
  }
  return { id: "", index: 0, elementIndex: 0, elementPointer: "", cells };
}

/** Every detail operation is read by exactly one path parameter; a second one is not addressable. */
function detailRequest(
  detail: CatalogueDataset,
  options: DetailOptions,
): { path: string; query: Record<string, string[]> } | null {
  const [name, ...rest] = detail.pathParameters;
  if (name === undefined || rest.length > 0) return null;
  const identity = identityValue(options);
  if (identity === null) return null;

  const query: Record<string, string[]> = {};
  const asOf = options.state.extra["as_of"];
  if (asOf && asOf.length > 0 && declaresAsOf(options.document, detail)) query["as_of"] = [...asOf];
  return { path: detail.path.replace(`{${name}}`, encodeURIComponent(identity)), query };
}

function identityValue(options: DetailOptions): string | null {
  if (options.dataset.row_id.length !== 1) return null;
  const pointer = options.dataset.row_id[0] as string;
  const own = options.row?.cells[pointer]?.value;
  if (typeof own === "string" || typeof own === "number") return String(own);
  return options.rowId === "" ? null : options.rowId;
}

/** Only what the operation declares reaches the wire: an undeclared as_of teaches a filter it has not got. */
function declaresAsOf(document: unknown, detail: CatalogueDataset): boolean {
  const operation = operationFor(document, detail.operationId);
  return (operation?.parameters ?? []).some((parameter) => parameter.name === "as_of");
}

function step(
  options: DetailOptions,
  operationId: string,
  request: { path: string; query: Record<string, string[]> },
): void {
  recordStep({
    operationId,
    request,
    url: window.location.search,
    title: `${options.dataset.title} · ${options.rowId}`,
  });
}

function trailNodes(options: DetailOptions): Node[] {
  const nav = renderTrail({ signal: options.signal });
  return nav ? [nav] : [];
}
