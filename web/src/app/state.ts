export interface Viewport {
  zoom: number;
  lat: number;
  lon: number;
}

export interface AppState {
  map: Viewport;
  well: string | null;
  explain: string | null;
  extra: Record<string, string>;
}

// Williston basin, the only basin this slice ingests.
export const DEFAULT_STATE: AppState = {
  map: { zoom: 7, lat: 47.8, lon: -102.8 },
  well: null,
  explain: null,
  extra: {},
};

const KNOWN = new Set(["map", "well", "explain"]);

export function parseState(search: string): AppState {
  const params = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  const extra: Record<string, string> = {};
  for (const [key, value] of params) {
    if (!KNOWN.has(key)) extra[key] = value;
  }
  return {
    map: parseViewport(params.get("map")) ?? DEFAULT_STATE.map,
    well: params.get("well"),
    explain: params.get("explain"),
    extra,
  };
}

export function serializeState(state: AppState): string {
  const params = new URLSearchParams();
  params.set("map", formatViewport(state.map));
  if (state.well) params.set("well", state.well);
  if (state.explain) params.set("explain", state.explain);
  for (const [key, value] of Object.entries(state.extra)) params.set(key, value);
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
