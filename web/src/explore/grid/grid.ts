import "./grid.css";

import { getEnvelope } from "../../api/client.ts";
import type { ResponseMeta } from "../../api/client.ts";
import type { Envelope } from "../../api/envelope.ts";
import type { AppState } from "../../app/state.ts";
import { clearRecord, publishCall } from "../api/context.ts";
import type { CallState } from "../api/context.ts";
import type { CatalogueDataset } from "../catalogue.ts";
import { mountDetail } from "../detail/detail.ts";
import { renderFacets } from "../facets/facets.ts";
import { filtersOf, requestFor, withFilter } from "../router.ts";
import { renderSeriesPanel } from "../series/series.ts";
import { renderCell, vintagesIn } from "./cells.ts";
import { columnsFor, coverageOf, renderHeader } from "./columns.ts";
import type { Column } from "./columns.ts";
import { paginationOf, renderPagination, summaryTotalFor } from "./paging.ts";
import { extractRows } from "./rows.ts";
import type { Row } from "./rows.ts";
import { SORT_KEY, directionOf, ordered, renderSort, sortColumnOf } from "./sort.ts";
import { anchorPrompt, emptyState, failure, note } from "./states.ts";

/** The server caps a page at 200 or 1000; this is how many of them reach the DOM at once. */
export const WINDOW = 60;

export interface GridOptions {
  dataset: CatalogueDataset;
  document: unknown;
  datasets: readonly CatalogueDataset[];
  state: AppState;
  facetHost: HTMLElement;
  commit(next: Partial<AppState>): void;
  /**
   * Expanding a row is a `pushState` and a detail request, not a re-read of the collection —
   * the shell writes the URL and leaves the grid standing. Without it, every row click would
   * re-issue the page request the reader is already looking at.
   */
  select?(row: string | null): void;
  signal: AbortSignal;
}

interface Loaded {
  envelope: Envelope<unknown>;
  columns: Column[];
  /** Visible plus hidden, in declaration order: the detail's field list (M3). */
  all: Column[];
  rows: Row[];
  total: number | null;
  vintages: Set<string>;
}

export async function mountGrid(host: HTMLElement, options: GridOptions): Promise<void> {
  const request = requestFor(options.dataset, options.state);
  renderFacetBar(options);

  if (request.missing.length > 0) {
    host.replaceChildren(anchorPrompt(request.missing, options));
    // The pane still has an operation to teach, and stating that nothing was issued is more
    // use to a reader than an empty column beside a prompt they have not answered yet.
    publish(options, request, "unissued");
    return;
  }
  // The frame before the answer names the request and its columns rather than spinning: a
  // reader who never sees the grid still learns what was asked for (C6 MUST-KNOW K1).
  host.replaceChildren(
    note(
      `Requesting ${request.path} — ${(options.dataset.columns.default ?? []).join(", ")}`,
      "gw-grid-loading",
    ),
  );

  publish(options, request, "pending");

  const response: { out?: ResponseMeta } = {};
  try {
    const envelope = await getEnvelope<unknown>(
      request.path,
      request.query,
      options.signal,
      response,
    );
    if (options.signal.aborted) return;
    publish(options, request, "loaded", { envelope, meta: response.out ?? null });
    // M3: the detail lists the hidden columns too — `hidden` means "not a cell", never "not a
    // fact" — so one picker answers both surfaces and there is no second list to drift.
    const all = columnsFor(options.dataset, options.document, envelope, { includeHidden: true });
    const columns = all.filter((column) => !column.hidden);
    const rows = extractRows(
      options.dataset,
      envelope.data,
      all.map((column) => column.pointer),
    );
    const total = await summaryTotalFor(
      options.dataset,
      options.document,
      summaryFilters(options),
      options.signal,
    );
    if (options.signal.aborted) return;
    render(host, options, { envelope, columns, all, rows, total, vintages: vintagesIn(rows) });
  } catch (error) {
    if (options.signal.aborted) return;
    // §4.7: a failed request keeps its REQUEST block, so the pane is told about it rather than
    // left rendering the last call that worked.
    publish(options, request, "failed", { error, meta: response.out ?? null });
    host.replaceChildren(failure(error));
  }
}

function publish(
  options: GridOptions,
  request: ReturnType<typeof requestFor>,
  state: CallState,
  answer: { envelope?: Envelope<unknown>; error?: unknown; meta?: ResponseMeta | null } = {},
): void {
  publishCall({
    state,
    role: "collection",
    dataset: options.dataset,
    request: { operationId: request.operationId, path: request.path, query: request.query },
    missing: request.missing,
    envelope: answer.envelope ?? null,
    error: answer.error ?? null,
    meta: answer.meta ?? null,
  });
}

function render(host: HTMLElement, options: GridOptions, loaded: Loaded): void {
  const { columns } = loaded;
  const rows = ordered(loaded.rows, directionOf(options.state));
  if (rows.length === 0) {
    // C3: the coverage line counts headers, and there are none on screen to count.
    host.replaceChildren(emptyState(options.state));
    return;
  }

  const table = document.createElement("div");
  table.className = "gw-grid-table";
  table.setAttribute("role", "table");
  table.style.gridTemplateColumns = trackList(columns);
  table.append(headRow(columns));

  const body = document.createElement("div");
  body.className = "gw-grid-body";
  body.setAttribute("role", "rowgroup");
  table.append(body);

  let shown = 0;
  const more = document.createElement("button");
  more.type = "button";
  more.className = "gw-grid-more";
  // A `row=` deep link must reach its row even when the window would have stopped short of it.
  const expanded = rows.findIndex((row) => row.id === options.state.row);
  const open = openPanel(body, loaded, options);

  const extend = (): void => {
    const next = Math.min(Math.max(shown + WINDOW, expanded + 1), rows.length);
    for (const row of rows.slice(shown, next)) {
      const element = bodyRow(row, columns, loaded, options, open);
      body.append(element);
      // By id, not by index: `ordered` reverses the array for a descending page while
      // `row.index` stays the position the row was built at, so the two disagree there.
      if (row.id === options.state.row) open(row, row.id, element);
    }
    shown = next;
    more.hidden = shown >= rows.length;
    more.textContent = `show ${Math.min(WINDOW, rows.length - shown)} more of ${rows.length - shown} loaded`;
  };
  more.addEventListener("click", extend, { signal: options.signal });
  extend();

  // A windowed renderer over an array the server already capped: no virtualiser, no dependency.
  const scroller = host.closest(".gw-explore-panel");
  scroller?.addEventListener(
    "scroll",
    () => {
      if (more.hidden) return;
      const bottom = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight;
      if (bottom < 400) extend();
    },
    { signal: options.signal, passive: true },
  );

  const pagination = renderPagination(
    paginationOf(options.dataset, options.document, loaded.envelope, rows.length, loaded.total),
    { onNext: (href) => followNext(href, options) },
  );
  host.replaceChildren(strap(columns, loaded, options), narrowNotice());
  // The wider redraw §2.6's crossing was for, from the response the grid already has — never a
  // second request for the series the reader is looking at.
  renderSeriesPanel(host, { envelope: loaded.envelope });
  host.append(table, more, pagination);
  // A chip hop lands on a row this page need not contain, so the panel stands on its own above
  // the grid rather than the link dead-ending in "not found here".
  if (options.state.row !== null && expanded < 0) {
    table.before(detailSlot(null, options.state.row, loaded, options));
  }

  // Read after the tracks are in the document, because only layout knows whether they fit.
  const cut = offScreenColumns(table, columns);
  const note_ = overflowNote(cut);
  if (note_) table.after(note_);
}

/**
 * F1: one track per column, two for a figure — the value and the marks beside it — so a state
 * chip cannot displace a number, and only prose is allowed to give up width. Every other kind
 * stays at `max-content`, which is what stops a date being cut to `2026-0` at the panel's edge.
 */
export function trackList(columns: readonly Column[]): string {
  return columns.map(trackFor).join(" ");
}

function trackFor(column: Column): string {
  if (column.kind === "figure") return "max-content auto";
  // The one kind that can be shortened without becoming a different value, so it absorbs the
  // slack and ellipsizes — and carries its full text in a title when it does.
  if (column.kind === "prose") return "minmax(8ch, max-content)";
  return "max-content";
}

function offScreenColumns(table: HTMLElement, columns: readonly Column[]): number {
  const overflow = table.scrollWidth - table.clientWidth;
  if (overflow <= 0 || table.clientWidth <= 0) return 0;
  const heads = [...table.querySelectorAll(".gw-grid-th")];
  const edge = table.getBoundingClientRect().right;
  const cut = heads.filter((head) => head.getBoundingClientRect().right > edge + 1).length;
  return Math.min(Math.max(cut, 1), columns.length);
}

/**
 * A value cut at the panel's edge with no signal reads as a complete value — `2019-05-2` for a
 * date, `2026-0` for a vintage. The columns that do not fit are named rather than cropped.
 */
export function overflowNote(cut: number): HTMLElement | null {
  if (cut <= 0) return null;
  return note(
    cut === 1
      ? "1 more column is off the right edge of this panel. Scroll the grid sideways to read it. Nothing is hidden; the panel is narrower than the row."
      : `${cut} more columns are off the right edge of this panel. Scroll the grid sideways to read them. Nothing is hidden; the panel is narrower than the row.`,
    "gw-grid-offscreen",
  );
}

/**
 * §2.5's 390 posture, and the inversion it is: on a phone the API guide is the whole product
 * and a twelve-column grid is not. The refusal is `display: none` until the media query says
 * otherwise, so at every other width it is absent from the page rather than merely invisible.
 */
function narrowNotice(): HTMLElement {
  return note(
    "The result grid needs a wider window. The API guide below works everywhere.",
    "gw-grid-narrow",
  );
}

function headRow(columns: readonly Column[]): HTMLElement {
  const head = document.createElement("div");
  head.className = "gw-explore-grid-head";
  head.setAttribute("role", "row");
  for (const column of columns) {
    const cell = document.createElement("div");
    cell.className = `gw-grid-th gw-grid-th-${column.kind}`;
    cell.setAttribute("role", "columnheader");
    cell.append(renderHeader(column));
    head.append(cell);
    // F3: a figure's label occupies the value track alone, right-aligned to the same edge its
    // numbers are, so a plumb line from the header lands on its own data rather than on the
    // gap left of it. The marks track gets a spacer so auto-placement stays in step.
    if (column.kind === "figure") head.append(spacer());
  }
  return head;
}

function spacer(): HTMLElement {
  const element = document.createElement("div");
  element.className = "gw-grid-th gw-grid-th-spacer";
  element.setAttribute("aria-hidden", "true");
  return element;
}

/** Anything that already answers a click keeps it: a term, a handle, an exemption, a chip. */
function interactive(target: EventTarget | null): boolean {
  return target instanceof Element && target.closest("a, button, gw-term, gw-figure, gw-count") !== null;
}

type OpenPanel = (row: Row | null, rowId: string, element: HTMLElement | null) => void;

/**
 * The panel opens and closes in the DOM the grid already rendered — the URL is written beside
 * it, never instead of it, so a row click costs one detail request and no page re-read.
 */
function openPanel(body: HTMLElement, loaded: Loaded, options: GridOptions): OpenPanel {
  let slot: HTMLElement | null = null;
  let owner: HTMLElement | null = null;

  return (row, rowId, element) => {
    slot?.remove();
    owner?.setAttribute("aria-expanded", "false");
    slot = null;
    owner = null;
    if (rowId === "") return;
    slot = detailSlot(row, rowId, loaded, options);
    if (element) {
      element.setAttribute("aria-expanded", "true");
      element.after(slot);
      owner = element;
      return;
    }
    body.prepend(slot);
  };
}

function bodyRow(
  row: Row,
  columns: readonly Column[],
  loaded: Loaded,
  options: GridOptions,
  open: OpenPanel,
): HTMLElement {
  const element = document.createElement("div");
  element.className = "gw-grid-tr";
  element.setAttribute("role", "row");
  element.dataset["rowId"] = row.id;
  element.tabIndex = 0;
  element.setAttribute("aria-expanded", "false");
  const toggle = (): void => {
    const opening = element.getAttribute("aria-expanded") !== "true";
    open(opening ? row : null, opening ? row.id : "", opening ? element : null);
    select(options, opening ? row.id : null);
  };
  element.addEventListener(
    "click",
    (event) => {
      if (!interactive(event.target)) toggle();
    },
    { signal: options.signal },
  );
  element.addEventListener(
    "keydown",
    (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      if (interactive(event.target)) return;
      event.preventDefault();
      toggle();
    },
    { signal: options.signal },
  );
  for (const column of columns) {
    const cell = document.createElement("div");
    cell.className = `gw-grid-td gw-grid-td-${column.kind}`;
    cell.setAttribute("role", "cell");
    // §2.5's card list is a CSS posture, not a second renderer: below 820 the header row is
    // not painted, so each cell carries the name it would have been read under. A rendered
    // element rather than `content: attr(data-name)`, because a pseudo-element is neither
    // selectable nor reliably a label to assistive technology (D12); the attribute stays as
    // the machine-readable hook the shot pack and the probes select on.
    cell.dataset["name"] = column.name;
    const name = document.createElement("span");
    name.className = "gw-grid-td-name";
    name.textContent = column.name;
    cell.append(name);
    cell.append(
      renderCell(column, { data: loaded.envelope.data, row }),
    );
    element.append(cell);
  }
  return element;
}

function select(options: GridOptions, row: string | null): void {
  // Closing a row uncovers the collection the reader is still looking at, so the pane goes back
  // to that call rather than keeping a record open that is no longer on screen.
  if (row === null) clearRecord();
  if (options.select) options.select(row);
  else options.commit({ row });
}

/**
 * §3.4's panel, in flow inside the table so it sits with its row — and spanning every track
 * without sizing any of them, which is N1's lesson applied one element out.
 */
function detailSlot(
  row: Row | null,
  rowId: string,
  loaded: Loaded,
  options: GridOptions,
): HTMLElement {
  const slot = document.createElement("div");
  slot.className = "gw-grid-detail";
  slot.setAttribute("role", "row");
  void mountDetail(slot, {
    dataset: options.dataset,
    document: options.document,
    datasets: options.datasets,
    state: { ...options.state, row: rowId },
    row,
    rowId,
    columns: loaded.all,
    data: loaded.envelope.data,
    request: requestFor(options.dataset, options.state),
    navigate: (next) => options.commit({ ds: next.ds, row: next.row, tab: next.tab, extra: next.extra }),
    close: () => {
      const owner = slot.previousElementSibling;
      slot.remove();
      if (owner?.classList.contains("gw-grid-tr")) owner.setAttribute("aria-expanded", "false");
      select(options, null);
    },
    signal: options.signal,
  });
  return slot;
}

/** One line above the grid: what every value here reports at, and how much of it is bound. */
function strap(columns: readonly Column[], loaded: Loaded, options: GridOptions): HTMLElement {
  const wrapper = document.createElement("div");
  wrapper.className = "gw-grid-strap";
  // One line either way. A second vintage changes what the line says, not how many places it
  // is said — eighteen per-cell chips was a column of noise, and each figure's own handle
  // resolves the vintage it read at.
  const vintages = [...loaded.vintages].sort();
  const [only] = vintages;
  if (only !== undefined) {
    const vintage = document.createElement("p");
    vintage.className = "gw-grid-vintage";
    vintage.textContent =
      vintages.length === 1
        ? `every value here reports at vintage ${only}`
        : `values here report at ${vintages.length} vintages: ${vintages.join(", ")}`;
    wrapper.append(vintage);
  }
  wrapper.append(coverageLine(columns));
  const sort = sortControl(loaded, options);
  if (sort) wrapper.append(sort);
  return wrapper;
}

function sortControl(loaded: Loaded, options: GridOptions): HTMLElement | null {
  const pointer = sortColumnOf(options.dataset, loaded.envelope);
  if (pointer === null) return null;
  const named = loaded.all.find((column) => column.pointer === pointer);
  return renderSort(
    pointer,
    named?.name ?? pointer.replace(/^\//, ""),
    directionOf(options.state),
    (direction) => {
      const extra = { ...options.state.extra };
      // The server's own order is the absence of the parameter, so it is never written into a
      // link: an explicit default in every URL is a claim the reader did not make.
      if (direction === "asc") delete extra[SORT_KEY];
      else extra[SORT_KEY] = [direction];
      options.commit({ extra });
    },
  );
}

/** §3.2's counted-unbound treatment is a percentage, so the percentage is on the surface. */
function coverageLine(columns: readonly Column[]): HTMLElement {
  const coverage = coverageOf(columns);
  const line = document.createElement("p");
  line.className = "gw-grid-coverage";
  line.textContent =
    coverage.bound === coverage.total
      ? "Glossary: every column bound"
      : `Glossary: ${coverage.bound}/${coverage.total} columns (${coverage.percent}%)`;
  // The unbound columns carry ? in the header itself, so the count no longer has to say so.
  line.title = "Unbound headers carry ? — they are counted here, not hidden.";
  return line;
}

function renderFacetBar(options: GridOptions): void {
  renderFacets(options.facetHost, {
    dataset: options.dataset,
    document: options.document,
    datasets: options.datasets,
    filters: filtersOf(options.state),
    hoisted: options.state.extra,
    signal: options.signal,
    hooks: {
      setFilter: (name, values) => {
        // A filter change restarts the walk: a cursor minted under the old filters is a 422.
        const next = withFilter(options.state, name, values);
        options.commit({ extra: withoutCursor(next.extra) });
      },
      setHoisted: (name, values) => {
        const extra = { ...options.state.extra };
        if (values.length === 0) delete extra[name];
        else extra[name] = values;
        options.commit({ extra: withoutCursor(extra) });
      },
      clearFilters: () => {
        const kept: Record<string, string[]> = {};
        for (const [key, values] of Object.entries(options.state.extra)) {
          if (!key.startsWith("f.")) kept[key] = values;
        }
        options.commit({ extra: withoutCursor(kept) });
      },
    },
  });
}

/**
 * The server built the next URL, so its cursor is read out of it rather than assembled here —
 * and it rides the app's own URL so a walk mid-collection is a link somebody else can open.
 */
function followNext(href: string, options: GridOptions): void {
  const cursor = new URLSearchParams(href.split("?")[1] ?? "").get("cursor");
  const extra = { ...options.state.extra };
  if (cursor) extra["cursor"] = [cursor];
  else delete extra["cursor"];
  options.commit({ extra });
}

function withoutCursor(extra: Record<string, string[]>): Record<string, string[]> {
  const next = { ...extra };
  delete next["cursor"];
  return next;
}


function summaryFilters(options: GridOptions): Record<string, string[]> {
  const query = { ...requestFor(options.dataset, options.state).query };
  // The total is over the filtered population, not over this page: the page controls go.
  delete query["cursor"];
  delete query["limit"];
  return query;
}
