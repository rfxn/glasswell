import "./layout.css";

import { apiUrl, authHeaders } from "../api/client.ts";
import { readState } from "../app/state.ts";
import type { AppState, ExploreTab } from "../app/state.ts";
import { buildCatalogue } from "./catalogue.ts";
import type { Catalogue, CatalogueDataset } from "./catalogue.ts";
import { renderRail } from "./rail.ts";
import { requestFor } from "./router.ts";

export interface ExplorerHooks {
  commit(next: Partial<AppState>, mode?: "push" | "replace"): void;
}

export const GRID_HOST_ID = "gw-explore-grid";
export const FACET_HOST_ID = "gw-explore-facets";
export const PANE_HOST_ID = "gw-explore-pane";

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

/** SB-08 §2.3's one exemption: /openapi.json is not an envelope, so `getEnvelope` cannot type it. */
async function openapiDocument(): Promise<unknown> {
  pending ??= (async () => {
    const response = await fetch(apiUrl("/openapi.json"), { headers: authHeaders() });
    if (!response.ok) throw new Error(`/openapi.json answered ${response.status}`);
    return (await response.json()) as unknown;
  })();
  return await pending;
}

export function unmountExplorer(): void {
  if (!mounted) return;
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
    catalogue = buildCatalogue(await openapiDocument());
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
  // A blank third of the window is a defect a reader has to guess at. The pane states what it
  // is for until C9 fills it, and C9 replaces these children rather than finding an empty box.
  pane.append(
    eyebrow("API"),
    note(
      "The exact call behind whatever the centre column is showing renders here — its URL, its operation, the response envelope and the problems it can return. It arrives with the result grid.",
    ),
  );

  root.append(rail, centre, pane);
  host.replaceChildren(root);
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
  return body;
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

  if (request.missing.length > 0) {
    header.append(
      note(
        `This dataset is read one anchor at a time: ${request.missing.join(", ")} has no value yet, so there is nothing to list until you supply one.`,
      ),
    );
  }
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

function eyebrow(text: string): HTMLElement {
  const element_ = element("p", "gw-explore-eyebrow");
  element_.textContent = text;
  return element_;
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
