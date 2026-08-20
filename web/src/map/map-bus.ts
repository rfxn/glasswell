/**
 * The narrow surface the rest of the app drives the map through: pick a well, move there.
 *
 * MERGE POINT — the parallel `ui-panels-chrome` work introduces `web/src/bus.ts` with the
 * same two calls for the header search. When that lands, `bus.ts` should re-export these
 * rather than define a second registry, or the search and the map will hold different
 * ideas of what is selected.
 */
export interface MapBus {
  selectWell(api10: string | null): void;
  flyTo(point: { lon: number; lat: number }): void;
}

const PENDING: MapBus = {
  selectWell() {},
  flyTo() {},
};

let current: MapBus = PENDING;

export function registerMapBus(bus: MapBus): void {
  current = bus;
}

export function mapBus(): MapBus {
  return current;
}

export function resetMapBus(): void {
  current = PENDING;
}

/**
 * Layer and basemap choices belong in the URL so a shared link reproduces the reader's map.
 *
 * MERGE POINT — `main.ts` reads the query string once at boot into `AppState.extra`, so a
 * later `commit()` writes back the snapshot it took then. `main.ts` mirrors these writes
 * into `state.extra`; if that wiring is dropped, the parameters survive in `localStorage`
 * but a link shared after a pan loses them.
 */
export function setUrlParam(key: string, value: string | null): void {
  const url = new URL(window.location.href);
  if (value === null) url.searchParams.delete(key);
  else url.searchParams.set(key, value);
  window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
  urlMirror?.(key, value);
}

let urlMirror: ((key: string, value: string | null) => void) | undefined;

/** Lets the app owner of `AppState.extra` keep its copy in step with what the map writes. */
export function onUrlParam(mirror: (key: string, value: string | null) => void): void {
  urlMirror = mirror;
}
