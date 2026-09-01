import "./style.css";

import {
  ApiError,
  getEnvelope,
  hasSignedInBefore,
  logout,
  purgeLegacyKey,
  whoami,
} from "./api/client.ts";
import { DEFAULT_STATE, readState, serializeState, writeState } from "./app/state.ts";
import type { AppState } from "./app/state.ts";
import { loginPanel } from "./auth/login.ts";
import { flyTo, onSelectWell, onUrlParam, selectWell, sessionBegan, wellSelected } from "./bus.ts";
import type { SelectSource } from "./bus.ts";
import { renderWellCard } from "./card/card.ts";
import { EXPLAIN_EVENT } from "./chrome/handle.ts";
import { setSignedIn, wireHeader } from "./chrome/header.ts";
import { registerOverlay } from "./chrome/overlays.ts";
import { setSessionState, setStatus, setVintage, toast } from "./chrome/status.ts";
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
const statusHost = required("gw-status-page");
const shell = required("gw-main");

let state: AppState = readState();
let mapHandle: MapHandle | undefined;
let pendingSource: SelectSource = "url";
let historySource: SelectSource | null = null;
let historyGeneration = 0;
let renderGeneration = 0;
let unmountExplorer: (() => void) | undefined;
let unmountStatusPage: (() => void) | undefined;
let hadSession = false;

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
    onSignIn: () => showLoginPanel(),
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

/**
 * The server refuses every auth failure identically, so "expired" is inferred from what this
 * page has already seen rather than from anything the server said.
 */
function showLoginPanel(): void {
  const reason = hadSession ? "expired" : "required";
  setSessionState(reason);
  setSignedIn(null);
  keyHost.replaceChildren(
    loginPanel({
      reason,
      // The panel hands back the session it just got, so nothing here re-asks who the reader is:
      // `sessionResolved` latched on the probe that failed, and boot() would skip resolveSession.
      onSignedIn: (session) => {
        keyHost.hidden = true;
        hadSession = session.kind === "user";
        setSignedIn(session.username);
        setSessionState("ok");
        sessionBegan();
        void boot();
        if (state.view === "status") void renderView();
      },
    }),
  );
  keyHost.hidden = false;
}

async function endSession(): Promise<void> {
  try {
    await logout();
  } catch (error) {
    // A refused logout is already a dead session; the panel is the same answer either way.
    if (!(error instanceof ApiError)) toast(`Sign out failed: ${String(error)}`);
  }
  hideMapOverlays();
  showLoginPanel();
}

/** Every 403 lands here, so an ended session can never brick the app in silence. */
function handleApiError(error: unknown, context: string): void {
  if (error instanceof ApiError && error.problem.status === 403) {
    showLoginPanel();
    return;
  }
  toast(`${context} failed: ${error instanceof ApiError ? error.problem.title : String(error)}`);
}

onSelectWell(({ api10, source }) => {
  if (source === "search" && api10 && state.view !== "map") {
    historySource = source;
    writeState({ ...state, view: "map", well: api10, explain: null }, "push");
    window.dispatchEvent(new PopStateEvent("popstate"));
    return;
  }
  pendingSource = source;
  showWell(api10);
});

document.addEventListener(EXPLAIN_EVENT, (event) => {
  const handle = (event as CustomEvent<{ handle: string }>).detail.handle;
  if (handle) openExplain(handle);
});

// The rail's popouts and the glossary popover sit above the panels on the z ladder and each
// owns its own dismissal, so this handler has to see them still open to yield to them —
// which is why it reads at capture, ahead of the listeners that close them.
const ABOVE_PANELS = [
  ".gw-popover:not([hidden])",
  ".gw-help-panel:not([hidden])",
  ".gw-search-panel:not([hidden])",
].join(", ");

/** SB-05 §7: Escape closes the topmost layer, and one place decides what that is. */
document.addEventListener(
  "keydown",
  (event) => {
    if (event.key !== "Escape") return;
    if (document.querySelector(ABOVE_PANELS)) return;
    if (!keyHost.hidden) {
      keyHost.hidden = true;
      return;
    }
    if (!drawerHost.hidden) {
      openExplain(null);
      return;
    }
    if (!cardHost.hidden) {
      selectWell(null, "url");
      return;
    }
    // Map chrome, so it is under the panels on the ladder and last here. The element rather
    // than a handle: the sheets are built inside createMap and never reach this module, and
    // each announces its own state off this attribute. One selector for both, because only one
    // of them is ever open.
    const sheet = document.querySelector<HTMLElement>(".gw-sheet:not([hidden])");
    if (!sheet) return;
    sheet.hidden = true;
    // Back to the control that opened it, found through the pair it already announces: focus
    // otherwise fell to the brand mark and a keyboard reader lost the control cluster.
    document.querySelector<HTMLElement>(`[aria-controls="${sheet.id}"]`)?.focus();
  },
  true,
);

window.addEventListener("popstate", () => void followHistory());

async function followHistory(): Promise<void> {
  const generation = ++historyGeneration;
  // Captured before the assignment: comparing next.view with state.view after it would be
  // comparing next with itself, and a back button across the mode switch would render nothing.
  const previousView = state.view;
  const next = readState();
  state = next;
  pendingSource = historySource ?? "url";
  historySource = null;
  if (next.view !== previousView) await renderView();
  if (generation !== historyGeneration) return;
  if (next.view === "map") {
    showWell(next.well, "replace");
    openExplain(next.explain, "replace");
  } else {
    hideMapOverlays();
  }
}

function hideMapOverlays(): void {
  cardHost.hidden = true;
  cardHost.replaceChildren();
  drawerHost.hidden = true;
  drawerHost.replaceChildren();
  shell.setAttribute("data-drawer", "closed");
}

async function renderView(): Promise<void> {
  const generation = ++renderGeneration;
  const view = state.view;
  hideMapOverlays();

  if (view === "explore") {
    const explorer = await import("./explore/shell.ts");
    if (generation !== renderGeneration || state.view !== view) return;
    unmountExplorer = explorer.unmountExplorer;
    unmountStatusPage?.();
    statusHost.hidden = true;
    mapHost.hidden = true;
    exploreHost.hidden = false;
    await explorer.mountExplorer(exploreHost, state, { commit });
    if (generation !== renderGeneration || state.view !== view) return;
    return;
  }
  if (view === "status") {
    const statusPage = await import("./status-page/surface.ts");
    if (generation !== renderGeneration || state.view !== view) return;
    unmountStatusPage = statusPage.unmountStatusPage;
    unmountExplorer?.();
    mapHost.hidden = true;
    exploreHost.hidden = true;
    statusHost.hidden = false;
    await statusPage.mountStatusPage(statusHost, {
      onForbidden: (error) => handleApiError(error, "Status"),
    });
    if (generation !== renderGeneration || state.view !== view) return;
    return;
  }

  // Arriving here from Status, the probe boot() skipped is now worth making: this surface
  // renders per-principal state and the header has to be right.
  if (!sessionResolved) void resolveSession();

  unmountExplorer?.();
  unmountStatusPage?.();
  exploreHost.hidden = true;
  statusHost.hidden = true;
  mapHost.hidden = false;
  const { createMap } = await import("./map/map.ts");
  if (generation !== renderGeneration || state.view !== view) return;
  // createMap is not idempotent and connectMap's disposer is discarded inside it, so a second
  // mount is a second canvas and a second bus handler. Mount once; the map lives behind the
  // explorer after that.
  mapHandle ??= createMap(mapHost, state.map, {
    onViewport: (viewport) => commit({ map: viewport }, "replace"),
  });
}

/** Whether asking "who am I" can tell this page anything it does not already know.
 *
 * Status is a public surface: arriving there directly does not require knowing who you are,
 * and a browser that has never signed in has no session for the answer to describe. Probing
 * anyway makes the ordinary first visit a request whose only possible answer is "nobody".
 * Every other surface asks, because the header has to render the right state.
 */
function shouldResolveSession(): boolean {
  return state.view !== "status" || hasSignedInBefore();
}

let sessionResolved = false;

async function resolveSession(): Promise<boolean> {
  sessionResolved = true;
  try {
    const session = await whoami();
    hadSession = session.kind === "user";
    setSignedIn(session.username);
    setSessionState("ok");
    return true;
  } catch (error) {
    handleApiError(error, "Session");
    // Nothing further in boot can succeed without a principal; signing in runs it again.
    if (error instanceof ApiError && error.problem.status === 403) return false;
    return true;
  }
}

async function boot(): Promise<void> {
  if (shouldResolveSession() && !sessionResolved && !(await resolveSession())) return;

  try {
    const index = await getEnvelope<{ published_vintages: { vintage_date: string }[] }>("/v1");
    const pinned = state.extra["as_of"]?.[0];
    setVintage(pinned && pinned.length > 0 ? pinned : index.data.published_vintages[0]?.vintage_date ?? null);
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
  purgeLegacyKey();

  registerOverlay(cardHost);
  registerOverlay(drawerHost);
  registerOverlay(keyHost, { modal: true });

  wireHeader({
    search: createSearch({
      onPick: (result) => selectWell(result.api10, "search"),
      onError: (error) => handleApiError(error, "Search"),
    }),
    onSignIn: () => showLoginPanel(),
    onLogout: () => void endSession(),
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

  if (state.view === "map" && state.well) showWell(state.well, "replace");
  if (state.view === "map" && state.explain) openExplain(state.explain, "replace");
  if (window.location.search === "") {
    window.history.replaceState(state, "", serializeState({ ...DEFAULT_STATE, ...state }));
  }
  void boot();
}

void start();
