/**
 * The seam between the map module and everything else: intent travels one way, committed
 * state the other, so neither side imports the other and a map click cannot echo back into
 * the map. `selectWell` is a request; `wellSelected` is the answer the app committed to.
 */

export type SelectSource = "map" | "search" | "url";

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
}
