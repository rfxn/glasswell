import "./style.css";

import { ApiError, apiKey, getEnvelope } from "./api/client.ts";
import { DEFAULT_STATE, readState, serializeState, writeState } from "./app/state.ts";
import type { AppState } from "./app/state.ts";
import { keyPanel } from "./auth/key-panel.ts";
import { flyTo, onSelectWell, onUrlParam, selectWell, wellSelected } from "./bus.ts";
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
// Type-only, so it emits no import edge and the map stays out of the entry chunk.
import type { MapHandle } from "./map/map.ts";
import { createSearch } from "./search/search.ts";

const mapHost = required("gw-map");
const cardHost = required("gw-card");
const drawerHost = required("gw-drawer");
const keyHost = required("gw-key-host");
const exploreHost = required("gw-explore");
const shell = required("gw-main");

let state: AppState = readState();
let mapHandle: MapHandle | undefined;
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
  // Captured before the assignment: comparing next.view with state.view after it would be
  // comparing next with itself, and a back button across the mode switch would render nothing.
  const previousView = state.view;
  const next = readState();
  state = next;
  pendingSource = "url";
  if (next.view !== previousView) void renderView();
  showWell(next.well, "replace");
  openExplain(next.explain, "replace");
});

async function renderView(): Promise<void> {
  if (state.view === "explore") {
    const { mountExplorer } = await import("./explore/shell.ts");
    await mountExplorer(exploreHost, state, { commit });
    mapHost.hidden = true;
    exploreHost.hidden = false;
    return;
  }
  const { createMap } = await import("./map/map.ts");
  exploreHost.hidden = true;
  mapHost.hidden = false;
  // createMap is not idempotent and connectMap's disposer is discarded inside it, so a second
  // mount is a second canvas and a second bus handler. Mount once; the map lives behind the
  // explorer after that.
  mapHandle ??= createMap(mapHost, state.map, {
    onViewport: (viewport) => commit({ map: viewport }, "replace"),
  });
}

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

async function start(): Promise<void> {
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

  // The map writes its own share parameters; mirror them so a later viewport commit,
  // which serialises the snapshot taken at boot, does not drop them.
  onUrlParam((key, value) => {
    const extra = { ...state.extra };
    if (value === null) delete extra[key];
    // The map only ever writes single-valued parameters, so replacing the array is exact.
    else extra[key] = [value];
    state = { ...state, extra };
  });

  // Awaited: the map subscribes itself to the bus inside createMap, and a selection restored
  // before that would fire into a bus the map has not joined.
  await renderView();

  if (state.well) showWell(state.well, "replace");
  if (state.explain) openExplain(state.explain, "replace");
  if (window.location.search === "") {
    window.history.replaceState(state, "", serializeState({ ...DEFAULT_STATE, ...state }));
  }
  void boot();
}

void start();
