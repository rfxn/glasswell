export interface Viewport {
  zoom: number;
  lat: number;
  lon: number;
}

export type ViewMode = "map" | "explore" | "status";
export type ExploreTab = "datasets" | "query" | "learn";

export interface AppState {
  map: Viewport;
  well: string | null;
  explain: string | null;
  view: ViewMode;
  tab: ExploreTab;
  ds: string | null;
  row: string | null;
  slug: string | null;
  extra: Record<string, string[]>;
}

// Williston basin, the only basin this slice ingests.
export const DEFAULT_STATE: AppState = {
  map: { zoom: 7, lat: 47.8, lon: -102.8 },
  well: null,
  explain: null,
  view: "map",
  tab: "datasets",
  ds: null,
  row: null,
  slug: null,
  extra: {},
};

const KNOWN = new Set(["map", "well", "explain", "view", "tab", "ds", "row", "slug"]);
const VIEWS: ViewMode[] = ["map", "explore", "status"];
const TABS: ExploreTab[] = ["datasets", "query", "learn"];

/** A stale or hostile link must render the default, never a surface with no centre column. */
function oneOf<T extends string>(raw: string | null, allowed: T[], fallback: T): T {
  return allowed.find((candidate) => candidate === raw) ?? fallback;
}

export function parseState(search: string): AppState {
  const params = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  const extra: Record<string, string[]> = {};
  for (const [key, value] of params) {
    if (!KNOWN.has(key)) (extra[key] ??= []).push(value);
  }
  return {
    map: parseViewport(params.get("map")) ?? DEFAULT_STATE.map,
    well: params.get("well"),
    explain: params.get("explain"),
    view: oneOf(params.get("view"), VIEWS, DEFAULT_STATE.view),
    tab: oneOf(params.get("tab"), TABS, DEFAULT_STATE.tab),
    ds: params.get("ds"),
    row: params.get("row"),
    slug: params.get("slug"),
    extra,
  };
}

export function serializeState(state: AppState): string {
  const params = new URLSearchParams();
  // The viewport rides an explorer link only when the reader moved it: without that arm the
  // crossing is one-way, because popstate rebuilds state from the URL and not from memory.
  const movedViewport =
    state.map.zoom !== DEFAULT_STATE.map.zoom ||
    state.map.lat !== DEFAULT_STATE.map.lat ||
    state.map.lon !== DEFAULT_STATE.map.lon;
  if (state.view === "map" || movedViewport) params.set("map", formatViewport(state.map));
  if (state.well) params.set("well", state.well);
  if (state.explain) params.set("explain", state.explain);
  if (state.view !== DEFAULT_STATE.view) params.set("view", state.view);
  if (state.tab !== DEFAULT_STATE.tab) params.set("tab", state.tab);
  if (state.ds) params.set("ds", state.ds);
  if (state.row) params.set("row", state.row);
  if (state.slug) params.set("slug", state.slug);
  for (const [key, values] of Object.entries(state.extra)) {
    for (const value of values) params.append(key, value);
  }
  return `?${params.toString()}`;
}

export function formatViewport(viewport: Viewport): string {
  return [viewport.zoom.toFixed(2), viewport.lat.toFixed(5), viewport.lon.toFixed(5)].join("/");
}

export function parseViewport(raw: string | null): Viewport | null {
  if (!raw) return null;
  const parts = raw.split("/");
  if (parts.length < 3) return null;
  const [zoom, lat, lon] = parts.map(Number);
  if (zoom === undefined || lat === undefined || lon === undefined) return null;
  if (!Number.isFinite(zoom) || !Number.isFinite(lat) || !Number.isFinite(lon)) return null;
  return { zoom, lat, lon };
}

export function readState(): AppState {
  return parseState(window.location.search);
}

/** Viewport churn uses replaceState so the back button is not forty pan events (SB-05 §6.1). */
export function writeState(state: AppState, mode: "push" | "replace" = "push"): void {
  const url = serializeState(state);
  if (mode === "push") window.history.pushState(state, "", url);
  else window.history.replaceState(state, "", url);
}
