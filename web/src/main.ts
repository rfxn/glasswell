import "./style.css";

import { ApiError, apiKey, getEnvelope } from "./api/client.ts";
import { DEFAULT_STATE, readState, serializeState, writeState } from "./app/state.ts";
import type { AppState } from "./app/state.ts";
import { keyPanel } from "./auth/key-panel.ts";
import { flyTo, onFlyTo, onSelectWell, onWellSelected, selectWell, wellSelected } from "./bus.ts";
import type { SelectSource } from "./bus.ts";
import { renderWellCard } from "./card/card.ts";
import { EXPLAIN_EVENT } from "./card/gw-figure.ts";
import { wireHeader } from "./chrome/header.ts";
import { registerOverlay } from "./chrome/overlays.ts";
import { setKeyState, setStatus, setVintage, toast } from "./chrome/status.ts";
import { highlight } from "./glossary/index.ts";
import { loadGlossary, termIndex } from "./glossary/store.ts";
import "./glossary/gw-term.ts";
import { renderLineageDrawer } from "./lineage/drawer.ts";
import { createMap, layerLegend } from "./map/map.ts";
import type { MapHandle } from "./map/map.ts";
import { createSearch } from "./search/search.ts";

const mapHost = required("gw-map");
const cardHost = required("gw-card");
const drawerHost = required("gw-drawer");
const keyHost = required("gw-key-host");
const shell = required("gw-main");

let state: AppState = readState();
let map: MapHandle | null = null;
let pendingSource: SelectSource = "url";

function required(id: string): HTMLElement {
  const element = document.getElementById(id);
  if (!element) throw new Error(`missing #${id} in index.html`);
  return element;
}

function commit(next: Partial<AppState>, mode: "push" | "replace" = "push"): void {
  state = { ...state, ...next };
  writeState(state, mode);
}

function showWell(api10: string | null, mode: "push" | "replace" = "push"): void {
  commit({ well: api10 }, mode);
  wellSelected(api10);
  if (!api10) {
    cardHost.hidden = true;
    cardHost.replaceChildren();
    return;
  }
  const source = pendingSource;
  void renderWellCard(cardHost, api10, {
    onExplain: (handle) => openExplain(handle),
    onClose: () => selectWell(null, source),
    onFixKey: () => showKeyPanel("rejected"),
    onVintage: (resolved) => setVintage(resolved),
    // Only a search hit moves the camera: a map click is already looking at the well, and a
    // deep link carries its own ?map= viewport that the reader chose.
    onLocated: (point) => {
      if (source === "search") flyTo({ ...point, zoom: 12 });
    },
  });
}

function openExplain(handle: string | null, mode: "push" | "replace" = "push"): void {
  commit({ explain: handle }, mode);
  shell.setAttribute("data-drawer", handle ? "open" : "closed");
  if (!handle) {
    drawerHost.hidden = true;
    drawerHost.replaceChildren();
    return;
  }
  void renderLineageDrawer(drawerHost, handle, { onClose: () => openExplain(null) });
}

function showKeyPanel(reason: "missing" | "rejected"): void {
  setKeyState(reason);
  keyHost.replaceChildren(
    keyPanel({
      reason,
      onRetry: () => {
        keyHost.hidden = true;
        void boot();
      },
    }),
  );
  keyHost.hidden = false;
}

/** Every 403 lands here, so a wrong stored key can never brick the app in silence. */
function handleApiError(error: unknown, context: string): void {
  if (error instanceof ApiError && error.problem.status === 403) {
    showKeyPanel(error.code === "key_required" ? "missing" : "rejected");
    return;
  }
  toast(`${context} failed: ${error instanceof ApiError ? error.problem.title : String(error)}`);
}

onSelectWell(({ api10, source }) => {
  pendingSource = source;
  showWell(api10);
});

onWellSelected((api10) => map?.select(api10));
onFlyTo((target) => map?.flyTo(target));

document.addEventListener(EXPLAIN_EVENT, (event) => {
  const handle = (event as CustomEvent<{ handle: string }>).detail.handle;
  if (handle) openExplain(handle);
});

/** SB-05 §7: Escape closes the topmost layer, and one place decides what that is. */
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (!keyHost.hidden) {
    keyHost.hidden = true;
    return;
  }
  if (!drawerHost.hidden) {
    openExplain(null);
    return;
  }
  if (!cardHost.hidden) selectWell(null, "url");
});

window.addEventListener("popstate", () => {
  const next = readState();
  state = next;
  pendingSource = "url";
  showWell(next.well, "replace");
  openExplain(next.explain, "replace");
});

async function boot(): Promise<void> {
  try {
    const index = await getEnvelope<{ published_vintages: { vintage_date: string }[] }>("/v1");
    setVintage(index.data.published_vintages[0]?.vintage_date ?? null);
    setKeyState("ok");
    setStatus("Click any ⌾ to see where a number came from.");
  } catch (error) {
    handleApiError(error, "Service index");
  }

  try {
    await loadGlossary();
    highlight(document.querySelector("#gw-help-panel") ?? document.body, termIndex());
  } catch (error) {
    if (error instanceof ApiError && error.problem.status === 403) handleApiError(error, "Glossary");
    else setStatus("Glossary unavailable", String(error), { degraded: true });
  }
}

function start(): void {
  // First, and before any history rewrite: serializeState() writes a search-only URL, which
  // drops the fragment the key arrived in.
  apiKey();

  registerOverlay(cardHost);
  registerOverlay(drawerHost);
  registerOverlay(keyHost, { modal: true });

  wireHeader({
    search: createSearch({
      onPick: (result) => selectWell(result.api10, "search"),
      onError: (error) => handleApiError(error, "Search"),
    }),
    onKeyPanel: () => showKeyPanel("rejected"),
  });

  shell.setAttribute("data-drawer", "closed");
  mapHost.appendChild(layerLegend());
  map = createMap(mapHost, state.map, {
    onSelect: (api10) => selectWell(api10, "map"),
    onViewport: (viewport) => commit({ map: viewport }, "replace"),
  });
  map.select(state.well);

  if (state.well) showWell(state.well, "replace");
  if (state.explain) openExplain(state.explain, "replace");
  if (window.location.search === "") {
    window.history.replaceState(state, "", serializeState({ ...DEFAULT_STATE, ...state }));
  }
  void boot();
}

start();
