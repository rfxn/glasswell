import "./grid.css";

import { getEnvelope } from "../../api/client.ts";
import type { Envelope } from "../../api/envelope.ts";
import type { AppState } from "../../app/state.ts";
import type { CatalogueDataset } from "../catalogue.ts";
import { renderFacets } from "../facets/facets.ts";
import { filtersOf, requestFor, withFilter } from "../router.ts";
import { renderCell, vintagesIn } from "./cells.ts";
import { columnsFor, coverageOf, renderHeader } from "./columns.ts";
import type { Column } from "./columns.ts";
import { paginationOf, renderPagination, summaryTotalFor } from "./paging.ts";
import { extractRows } from "./rows.ts";
import type { Row } from "./rows.ts";
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
  signal: AbortSignal;
}

interface Loaded {
  envelope: Envelope<unknown>;
  columns: Column[];
  rows: Row[];
  total: number | null;
  vintages: Set<string>;
}

export async function mountGrid(host: HTMLElement, options: GridOptions): Promise<void> {
  const request = requestFor(options.dataset, options.state);
  renderFacetBar(options);

  if (request.missing.length > 0) {
    host.replaceChildren(anchorPrompt(request.missing, options));
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

  try {
    const envelope = await getEnvelope<unknown>(request.path, request.query, options.signal);
    if (options.signal.aborted) return;
    const columns = columnsFor(options.dataset, options.document, envelope);
    const rows = extractRows(
      options.dataset,
      envelope.data,
      columns.map((column) => column.pointer),
    );
    const total = await summaryTotalFor(
      options.dataset,
      options.document,
      summaryFilters(options),
      options.signal,
    );
    if (options.signal.aborted) return;
    render(host, options, { envelope, columns, rows, total, vintages: vintagesIn(rows) });
  } catch (error) {
    if (options.signal.aborted) return;
    host.replaceChildren(failure(error));
  }
}

function render(host: HTMLElement, options: GridOptions, loaded: Loaded): void {
  const { columns, rows } = loaded;
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

  const extend = (): void => {
    const next = Math.min(shown + WINDOW, rows.length);
    for (const row of rows.slice(shown, next)) body.append(bodyRow(row, columns, loaded));
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
  host.replaceChildren(strap(columns, loaded), table, more, pagination);

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
      ? "1 more column is off the right edge of this panel — scroll the grid sideways to read it. Nothing is hidden; the panel is narrower than the row."
      : `${cut} more columns are off the right edge of this panel — scroll the grid sideways to read them. Nothing is hidden; the panel is narrower than the row.`,
    "gw-grid-offscreen",
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

function bodyRow(row: Row, columns: readonly Column[], loaded: Loaded): HTMLElement {
  const element = document.createElement("div");
  element.className = "gw-grid-tr";
  element.setAttribute("role", "row");
  element.dataset["rowId"] = row.id;
  for (const column of columns) {
    const cell = document.createElement("div");
    cell.className = `gw-grid-td gw-grid-td-${column.kind}`;
    cell.setAttribute("role", "cell");
    cell.append(
      renderCell(column, {
        data: loaded.envelope.data,
        row,
        uniformVintage: loaded.vintages.size === 1,
      }),
    );
    element.append(cell);
  }
  return element;
}

/** One line above the grid: what every value here reports at, and how much of it is bound. */
function strap(columns: readonly Column[], loaded: Loaded): HTMLElement {
  const wrapper = document.createElement("div");
  wrapper.className = "gw-grid-strap";
  const [only] = [...loaded.vintages];
  if (loaded.vintages.size === 1 && only !== undefined) {
    const vintage = document.createElement("p");
    vintage.className = "gw-grid-vintage";
    vintage.textContent = `every value here reports at vintage ${only}`;
    wrapper.append(vintage);
  }
  wrapper.append(coverageLine(columns));
  return wrapper;
}

/** §3.2's counted-unbound treatment is a percentage, so the percentage is on the surface. */
function coverageLine(columns: readonly Column[]): HTMLElement {
  const coverage = coverageOf(columns);
  const line = document.createElement("p");
  line.className = "gw-grid-coverage";
  line.textContent =
    coverage.bound === coverage.total
      ? `every column here is bound to a glossary term`
      : `${coverage.bound} of ${coverage.total} column headers are bound to a glossary term (${coverage.percent}%); the rest carry ? and are counted, not hidden`;
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
