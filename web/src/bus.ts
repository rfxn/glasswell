/**
 * The seam between the map module and everything else: intent travels one way, committed
 * state the other, so neither side imports the other and a map click cannot echo back into
 * the map. `selectWell` is a request; `wellSelected` is the answer the app committed to.
 */

export type SelectSource = "card" | "map" | "search" | "url";

export interface SelectRequest {
  api10: string | null;
  source: SelectSource;
}

export interface FlyTarget {
  lon: number;
  lat: number;
  /** Zoom floor, not a set: a caller asking for 11 must not pull a reader back from 14. */
  zoom?: number;
}

type Handler<T> = (payload: T) => void;

interface Channel<T> {
  emit(payload: T): void;
  on(handler: Handler<T>): () => void;
  clear(): void;
}

function channel<T>(): Channel<T> {
  const handlers = new Set<Handler<T>>();
  return {
    emit(payload) {
      for (const handler of [...handlers]) handler(payload);
    },
    on(handler) {
      handlers.add(handler);
      return () => {
        handlers.delete(handler);
      };
    },
    clear() {
      handlers.clear();
    },
  };
}

const requested = channel<SelectRequest>();
const committed = channel<string | null>();
const camera = channel<FlyTarget>();
const session = channel<void>();

export function selectWell(api10: string | null, source: SelectSource): void {
  requested.emit({ api10, source });
}

export function onSelectWell(handler: Handler<SelectRequest>): () => void {
  return requested.on(handler);
}

export function wellSelected(api10: string | null): void {
  committed.emit(api10);
}

export function onWellSelected(handler: Handler<string | null>): () => void {
  return committed.on(handler);
}

/**
 * A session now exists where none did. Surfaces that mounted signed-out were refused rather
 * than broken, so this is their cue to ask again — it carries no principal, because what they
 * do about it is theirs to decide and none of them renders who the reader is.
 */
export function sessionBegan(): void {
  session.emit();
}

export function onSessionBegan(handler: () => void): () => void {
  return session.on(handler);
}

export function flyTo(target: FlyTarget): void {
  camera.emit(target);
}

export function onFlyTo(handler: Handler<FlyTarget>): () => void {
  return camera.on(handler);
}

export function resetBus(): void {
  requested.clear();
  committed.clear();
  camera.clear();
  session.clear();
  urlMirror = undefined;
}

/** What the map offers the rest of the app. Structural, so the bus imports no map code. */
export interface MapTarget {
  select(api10: string | null): void;
  flyTo(target: FlyTarget): void;
}

/** The map's end of the seam: it subscribes here instead of keeping a registry of its own. */
export function connectMap(target: MapTarget): () => void {
  const offSelection = onWellSelected((api10) => target.select(api10));
  const offCamera = onFlyTo((point) => target.flyTo(point));
  return () => {
    offSelection();
    offCamera();
  };
}

let urlMirror: ((key: string, value: string | null) => void) | undefined;

/**
 * Layer and basemap choices belong in the URL so a shared link reproduces the reader's map.
 * `replaceState` by default, because a pan is not a navigation — but a decision is: narrowing
 * the map to one operator is something the back button should undo, so the caller can ask for
 * a history entry rather than the app deciding that for every parameter alike.
 */
export function setUrlParam(
  key: string,
  value: string | null,
  mode: "push" | "replace" = "replace",
): void {
  const url = new URL(window.location.href);
  if (value === null) url.searchParams.delete(key);
  else url.searchParams.set(key, value);
  const href = `${url.pathname}${url.search}${url.hash}`;
  if (mode === "push") window.history.pushState(window.history.state, "", href);
  else window.history.replaceState(window.history.state, "", href);
  urlMirror?.(key, value);
}

/**
 * Lets the app owner of `AppState.extra` keep its copy in step with what the map writes:
 * `main.ts` reads the query string once at boot, so a later commit would serialise the
 * snapshot it took then and drop these parameters from a shared link.
 */
export function onUrlParam(mirror: (key: string, value: string | null) => void): void {
  urlMirror = mirror;
}
