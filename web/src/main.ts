import "./style.css";

import { ApiError } from "./api/client.ts";
import { DEFAULT_STATE, readState, serializeState, writeState } from "./app/state.ts";
import type { AppState } from "./app/state.ts";
import { renderWellCard } from "./card/card.ts";
import { EXPLAIN_EVENT } from "./card/gw-figure.ts";
import { highlight } from "./glossary/index.ts";
import { loadGlossary, termIndex } from "./glossary/store.ts";
import "./glossary/gw-term.ts";
import { renderLineageDrawer } from "./lineage/drawer.ts";
import { createMap, layerLegend } from "./map/map.ts";
import type { MapHandle } from "./map/map.ts";

const mapHost = required("gw-map");
const cardHost = required("gw-card");
const drawerHost = required("gw-drawer");
const statusLine = required("gw-status");

let state: AppState = readState();
let map: MapHandle | null = null;

function required(id: string): HTMLElement {
  const element = document.getElementById(id);
  if (!element) throw new Error(`missing #${id} in index.html`);
  return element;
}

function commit(next: Partial<AppState>, mode: "push" | "replace" = "push"): void {
  state = { ...state, ...next };
  writeState(state, mode);
}

function selectWell(api10: string | null, mode: "push" | "replace" = "push"): void {
  commit({ well: api10 }, mode);
  map?.select(api10);
  if (!api10) {
    cardHost.hidden = true;
    cardHost.replaceChildren();
    return;
  }
  void renderWellCard(cardHost, api10, {
    onExplain: (handle) => openExplain(handle),
    onClose: () => selectWell(null),
  });
}

function openExplain(handle: string | null, mode: "push" | "replace" = "push"): void {
  commit({ explain: handle }, mode);
  if (!handle) {
    drawerHost.hidden = true;
    drawerHost.replaceChildren();
    return;
  }
  void renderLineageDrawer(drawerHost, handle, { onClose: () => openExplain(null) });
}

document.addEventListener(EXPLAIN_EVENT, (event) => {
  const handle = (event as CustomEvent<{ handle: string }>).detail.handle;
  if (handle) openExplain(handle);
});

window.addEventListener("popstate", () => {
  const next = readState();
  state = next;
  map?.select(next.well);
  if (next.well) selectWell(next.well, "replace");
  else selectWell(null, "replace");
  openExplain(next.explain, "replace");
});

async function boot(): Promise<void> {
  mapHost.appendChild(layerLegend());
  map = createMap(mapHost, state.map, {
    onSelect: (api10) => selectWell(api10),
    onViewport: (viewport) => commit({ map: viewport }, "replace"),
  });
  map.select(state.well);

  try {
    await loadGlossary();
    statusLine.textContent = `Glossary loaded: ${termIndex().surfaces.length} highlightable surface forms.`;
    highlight(document.querySelector("header") ?? document.body, termIndex());
  } catch (error) {
    statusLine.textContent =
      error instanceof ApiError && error.problem.status === 403
        ? "The API needs the owner key: open this page once with #key=<GLASSWELL_OWNER_KEY>."
        : `Glossary unavailable: ${String(error)}`;
  }

  if (state.well) selectWell(state.well, "replace");
  if (state.explain) openExplain(state.explain, "replace");
  if (window.location.search === "") {
    window.history.replaceState(state, "", serializeState({ ...DEFAULT_STATE, ...state }));
  }
}

void boot();
