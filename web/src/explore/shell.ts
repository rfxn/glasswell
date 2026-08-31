import "./layout.css";

import { apiUrl } from "../api/client.ts";
import { readState } from "../app/state.ts";
import type { AppState, ExploreTab } from "../app/state.ts";
import { mountPane } from "./api/pane.ts";
import { buildCatalogue } from "./catalogue.ts";
import type { Catalogue, CatalogueDataset } from "./catalogue.ts";
import { mountGrid } from "./grid/grid.ts";
import { renderRail } from "./rail.ts";
import { requestFor, withFilter } from "./router.ts";
import { WELLS_BY_PREFIX, mountWellsBy } from "./facets/wells-by.ts";

export interface ExplorerHooks {
  commit(next: Partial<AppState>, mode?: "push" | "replace"): void;
}

export const GRID_HOST_ID = "gw-explore-grid";
export const FACET_HOST_ID = "gw-explore-facets";
export const WELLS_BY_HOST_ID = "gw-explore-wells-by";
export const PANE_HOST_ID = "gw-explore-pane";

/** The one dataset "Wells by ..." counts over; its filters are the dimensions it offers. */
const WELLS_BY_DATASET = "wells";

const TABS: { id: ExploreTab; title: string }[] = [
  { id: "datasets", title: "Datasets" },
  { id: "query", title: "Query" },
  { id: "learn", title: "Learn" },
];

const UNBUILT_TABS: Record<string, string> = {
  query:
    "The Query workspace lands in P-B: compose across parameters, walk the cursor deliberately, and keep a session history of what you ran. Until then the Datasets tab is the whole surface.",
  learn:
    "Walkthroughs and concept pages land in P-C, each driving the Datasets tab rather than describing it. They are prose held as data, so none of them exists yet.",
};

let pending: Promise<unknown> | null = null;
let mounted: { host: HTMLElement; abort: AbortController; hooks: ExplorerHooks } | null = null;
let state: AppState | null = null;
let catalogue: Catalogue | null = null;
// The document the catalogue was built from: C7 reads response schemas and parameters out of it
// rather than fetching it a second time (C6 MUST-KNOW K2).
let apiDocument: unknown = null;
// One render, one in-flight grid: a filter changed twice quickly must not race two responses
// into the same host, and the loser has to be cancelled rather than merely ignored.
let gridAbort: AbortController | null = null;
// Its own controller: the facet panel and the grid answer different requests, and a filter
// click re-renders both — cancelling one must not cancel the other's in-flight response.
let wellsByAbort: AbortController | null = null;

/** SB-08 §2.3's one exemption: /openapi.json is not an envelope, so `getEnvelope` cannot type it. */
async function openapiDocument(): Promise<unknown> {
  pending ??= (async () => {
    const response = await fetch(apiUrl("/openapi.json"), { credentials: "same-origin" });
    if (!response.ok) throw new Error(`/openapi.json answered ${response.status}`);
    return (await response.json()) as unknown;
  })();
  return await pending;
}

export function unmountExplorer(): void {
  if (!mounted) return;
  gridAbort?.abort();
  gridAbort = null;
  wellsByAbort?.abort();
  wellsByAbort = null;
  mounted.abort.abort();
  mounted.host.replaceChildren();
  mounted.host.removeAttribute("data-tab");
  mounted = null;
  state = null;
}

export async function mountExplorer(
  host: HTMLElement,
  next: AppState,
  hooks: ExplorerHooks,
): Promise<void> {
  unmountExplorer();
  const abort = new AbortController();
  mounted = { host, abort, hooks };
  state = next;

  try {
    apiDocument = await openapiDocument();
    catalogue = buildCatalogue(apiDocument);
  } catch (error) {
    // Never rethrow: main.ts unhides this host only after the mount resolves, so a failed
    // document would otherwise leave the reader on a surface with nothing on it at all.
    catalogue = null;
    pending = null;
    console.warn(`explorer: the catalogue is unavailable — ${String(error)}`);
  }
  if (mounted?.abort !== abort) return;

  window.addEventListener("popstate", () => render(readState()), { signal: abort.signal });
  render(next);
}

function commit(next: Partial<AppState>): void {
  if (!mounted || !state) return;
  state = { ...state, ...next };
  mounted.hooks.commit(next, "push");
  render(state);
}

/**
 * A row expansion is a `pushState` and nothing else. The grid opens its own panel in place, so
 * re-rendering here would re-issue the collection request the reader is already looking at —
 * and the back button still arrives through `popstate` and the full render.
 */
function select(row: string | null): void {
  if (!mounted || !state) return;
  state = { ...state, row };
  mounted.hooks.commit({ row }, "push");
}

/**
 * Collapsing a section is not a new question for the API. It rides the URL so a shared link
 * teaches what the sharer meant (§4.1), and it takes `select`'s route — the write without the
 * re-render — because re-rendering here would re-issue the request the reader is reading.
 */
function sections(value: string): void {
  if (!mounted || !state) return;
  const extra = { ...state.extra, api: [value] };
  state = { ...state, extra };
  mounted.hooks.commit({ extra }, "replace");
}

function render(next: AppState): void {
  if (!mounted) return;
  state = next;
  const { host, abort } = mounted;
  host.setAttribute("data-tab", next.tab);

  const root = element("div", "gw-explore");
  const rail = element("nav", "gw-explore-rail");
  rail.setAttribute("aria-label", "Dataset catalogue");
  renderRail(rail, {
    catalogue,
    selected: selected(next)?.id ?? null,
    onSelect: (id) => commit({ ds: id, row: null }),
    signal: abort.signal,
  });

  const centre = element("div", "gw-explore-centre");
  centre.append(tabs(next.tab, abort.signal), panel(next));

  const pane = element("aside", "gw-explore-pane");
  pane.id = PANE_HOST_ID;
  pane.setAttribute("aria-label", "API guide");
  mountPane(pane, {
    document: apiDocument,
    state: next,
    onSections: sections,
    signal: abort.signal,
  });

  root.append(rail, centre, pane);
  host.replaceChildren(root);
  renderWellsBy(next);
  renderGrid(next);
}

/**
 * The counted list sits above the grid it narrows, on the one dataset whose rows it counts.
 * It is deliberately not a map surface: the map's counts are bbox-scoped by design, and a
 * "top 15 operators" that reordered as the reader panned would be the same defect
 * `/v1/wells/status-summary` was written to avoid — a count of what was drawn.
 */
function renderWellsBy(next: AppState): void {
  wellsByAbort?.abort();
  wellsByAbort = null;
  const host = document.getElementById(WELLS_BY_HOST_ID);
  if (!host || next.tab !== "datasets" || selected(next)?.id !== WELLS_BY_DATASET) return;

  wellsByAbort = new AbortController();
  void mountWellsBy(host, {
    state: next,
    hooks: {
      setPanel: (values) => {
        const extra = { ...state?.extra };
        for (const [key, value] of Object.entries(values)) {
          if (value === null) delete extra[`${WELLS_BY_PREFIX}${key}`];
          else extra[`${WELLS_BY_PREFIX}${key}`] = [value];
        }
        commit({ extra });
      },
      applyFilter: (name, values) => {
        if (!state) return;
        commit({ extra: withFilter(state, name, values).extra });
      },
    },
    signal: wellsByAbort.signal,
  });
}

function renderGrid(next: AppState): void {
  gridAbort?.abort();
  gridAbort = null;
  const dataset = selected(next);
  const grid = document.getElementById(GRID_HOST_ID);
  const facets = document.getElementById(FACET_HOST_ID);
  if (!dataset || !grid || !facets || next.tab !== "datasets") return;

  gridAbort = new AbortController();
  void mountGrid(grid, {
    dataset,
    document: apiDocument,
    datasets: catalogue?.datasets ?? [],
    state: next,
    facetHost: facets,
    commit,
    select,
    signal: gridAbort.signal,
  });
}

function selected(next: AppState): CatalogueDataset | undefined {
  return catalogue?.datasets.find((dataset) => dataset.id === next.ds);
}

function tabs(current: ExploreTab, signal: AbortSignal): HTMLElement {
  const list = element("div", "gw-explore-tabs");
  list.setAttribute("role", "tablist");
  for (const tab of TABS) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "gw-explore-tab";
    button.setAttribute("role", "tab");
    button.setAttribute("aria-selected", String(tab.id === current));
    button.dataset["tab"] = tab.id;
    button.textContent = tab.title;
    button.addEventListener("click", () => commit({ tab: tab.id }), { signal });
    list.appendChild(button);
  }
  return list;
}

function panel(next: AppState): HTMLElement {
  const body = element("div", "gw-explore-panel");
  body.setAttribute("role", "tabpanel");

  const unbuilt = UNBUILT_TABS[next.tab];
  if (unbuilt !== undefined) {
    body.append(heading(TABS.find((tab) => tab.id === next.tab)?.title ?? ""), note(unbuilt));
    return body;
  }
  if (!catalogue) {
    body.append(note("The dataset catalogue is unavailable, so there is nothing to browse here."));
    return body;
  }
  const dataset = selected(next);
  if (!dataset) {
    body.append(
      heading("Pick a dataset"),
      note(
        next.ds
          ? `This link names the dataset ${next.ds}, and the served document does not declare it. It may have been renamed, or it may never have existed.`
          : "Every collection on the left is an operation that declared itself browsable. The catalogue is the document, so nothing here can drift from the API.",
      ),
    );
    return body;
  }
  body.append(datasetHeader(dataset, next), facetHost(), gridHost(dataset));
  if (dataset.id === WELLS_BY_DATASET) body.insertBefore(wellsByHost(), body.children[1] ?? null);
  return body;
}

function wellsByHost(): HTMLElement {
  const host = element("section", "gw-wells-by");
  host.id = WELLS_BY_HOST_ID;
  host.setAttribute("aria-label", "Wells by dimension");
  return host;
}

function datasetHeader(dataset: CatalogueDataset, next: AppState): HTMLElement {
  const header = document.createElement("header");
  header.className = "gw-explore-head";
  header.append(heading(dataset.title));

  const request = requestFor(dataset, next);
  const operation = element("p", "gw-explore-op");
  const method = document.createElement("code");
  method.textContent = `GET ${request.path}`;
  const id = element("span", "gw-explore-op-id");
  id.textContent = dataset.operationId;
  operation.append(method, id);
  header.append(operation);

  const identity = element("p", "gw-explore-identity");
  identity.textContent = `Row identity ${dataset.row_id.join(" + ")}`;
  header.append(identity);

  // C2: the grid's own anchor prompt says this, names the 404 and offers the input. Two
  // paraphrases of one fact 110 px apart is one more than the reader needs.
  return header;
}

function facetHost(): HTMLElement {
  const host = element("div", "gw-explore-facets");
  host.id = FACET_HOST_ID;
  return host;
}

/** C7's mount point: it replaces these children, so the empty state is never a blank rectangle. */
function gridHost(dataset: CatalogueDataset): HTMLElement {
  const wrapper = element("div", "gw-explore-grid");
  wrapper.id = GRID_HOST_ID;
  wrapper.dataset["ds"] = dataset.id;
  const columns = dataset.columns.default;
  wrapper.append(
    note(
      columns
        ? `Rows are not rendered on this surface yet. When they are, the columns will be the ones the operation declares: ${columns.join(", ")}.`
        : "Rows are not rendered on this surface yet. This operation declares no default columns, so the grid will render its response schema in order.",
    ),
  );
  return wrapper;
}

function heading(text: string): HTMLElement {
  const element_ = document.createElement("h2");
  element_.className = "gw-explore-title";
  element_.textContent = text;
  return element_;
}

function note(text: string): HTMLElement {
  const element_ = element("p", "gw-explore-note");
  element_.textContent = text;
  return element_;
}

function element(tag: string, className: string): HTMLElement {
  const created = document.createElement(tag);
  created.className = className;
  return created;
}
