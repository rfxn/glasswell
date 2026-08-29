/**
 * SB-08 §2.6, both directions. Two invariants hold across every row of that table: `as_of`
 * survives the crossing, and the crossing is a single `pushState`, so one back press returns
 * the reader to what they were looking at.
 *
 * The explorer end of a crossing is built by `stateFor` (C8 N4) and never by assembling a URL
 * here. The map end is reached through `bus.ts` alone, so this module imports no map code and
 * the canvas stays out of the explorer's chunk.
 */
import "./bridge.css";

import { serializeState, writeState } from "../app/state.ts";
import type { AppState, Viewport } from "../app/state.ts";
import { flyTo } from "../bus.ts";
import type { FlyTarget } from "../bus.ts";
import { stateFor } from "./detail/chips.ts";
import type { Hop, HopKind, HopTarget } from "./detail/chips.ts";

export type CrossingId =
  | "rows-for-this-well"
  | "open-this-series"
  | "whats-behind-this-layer"
  | "vintages"
  | "show-on-map";

export interface Crossing {
  id: CrossingId;
  label: string;
  title: string;
  next: AppState;
  href: string;
  /**
   * The vintage this crossing's own `href` carries, read back off `next` rather than taken
   * from the context, so the flag and the link cannot disagree. Null means the link would
   * answer differently after the next vintage lands, and M6 says that is not a link to hand a
   * reader — see `applyCrossing` and `cross`.
   */
  pinned: string | null;
  /** Set only where the crossing also asks the camera to move (§2.6's explorer row). */
  camera?: FlyTarget;
}

export interface BridgeContext {
  state: AppState;
  /**
   * The vintage the source surface resolved, read off the envelope it already holds. M6: a
   * shared link that names no vintage answers differently tomorrow, so a crossing pins this
   * one unless the reader has pinned their own.
   */
  resolved?: string | null;
}

/**
 * §2.6's destinations, as the little `stateFor` reads: an id, the path shape, and the
 * parameter each one narrows by. Declared rather than looked up in the catalogue because four
 * of these five crossings are built on the map, which never fetches the document — and
 * `bridge.test.ts` checks every member of this table against the committed one, so a renamed
 * dataset or parameter reddens a test instead of shipping a dead link.
 */
interface CrossingTarget extends HopTarget {
  filter: string | null;
}

export const TARGETS: Record<string, CrossingTarget> = {
  // A row hop narrows by the destination's identity; `q` is a name search and matches no API-10.
  wells: { id: "wells", pathParameters: [], filter: "api10" },
  production: { id: "production", pathParameters: ["api10"], filter: "api10" },
  vintages: { id: "vintages", pathParameters: [], filter: null },
};

export interface LayerCollectionRef {
  dataset: string;
  bbox: string | null;
}

/** `[minLon, minLat, maxLon, maxLat]`, the order `?bbox=` takes. */
export type Bbox = readonly [number, number, number, number];

/**
 * `wells.py:43` rejects a box wider than this on either side with `bbox_cap`, and the served
 * parameter description states it. A crossing that sent one would hand the reader a 422 they
 * did not ask for, so it drops the filter and says the view is too wide instead.
 */
export const BBOX_DEGREE_CAP = 4;

/** Close enough to read a pad; `flyTo` treats it as a floor, so a zoomed-in reader stays put. */
const WELL_ZOOM = 12;

/**
 * SB-04 §4.8's multi-select crossing needs an operation nobody serves. Named as data so the
 * refusal here and the rail's own class B register cannot drift apart (§2.6, 10.2).
 */
export const DEFERRED_WELLSET = {
  title: "Well sets",
  path: "/v1/wellsets",
  section: "SB-04 §4.8",
} as const;

const ASOF = "as_of";

/** The layer crossing's target is the registry's declaration, checked by the same test. */
function layerTarget(collection: LayerCollectionRef): CrossingTarget {
  return { id: collection.dataset, pathParameters: [], filter: collection.bbox };
}

/** The `as_of` a state carries. An empty one is nobody's pin: it serialises to a bare `as_of=`. */
function asOfIn(state: AppState): string | null {
  const value = state.extra[ASOF]?.[0];
  return value && value.length > 0 ? value : null;
}

/**
 * M6, applied before the hop rather than inside it: `stateFor` carries whatever `as_of` the
 * source state holds, so pinning is a transformation of the source and the router stays the
 * one place a crossing's URL is decided.
 */
export function pinnedState(context: BridgeContext): AppState {
  if (asOfIn(context.state)) return context.state;
  const resolved = context.resolved;
  if (!resolved) return context.state;
  return { ...context.state, extra: { ...context.state.extra, [ASOF]: [resolved] } };
}

function crossing(
  id: CrossingId,
  label: string,
  title: string,
  hop: Hop,
  context: BridgeContext,
): Crossing {
  const next = stateFor(hop, pinnedState(context));
  return { id, label, title, next, href: serializeState(next), pinned: asOfIn(next) };
}

/**
 * The destination's own declaration decides what it narrows by. Passing the parameter in at
 * the call site instead would leave `TARGETS.filter` as data nothing reads, and a table the
 * code ignores is a table that drifts from it silently.
 */
function hopTo(target: CrossingTarget, value: string, kind: HopKind, narrows = true): Hop {
  return {
    target: { id: target.id, pathParameters: target.pathParameters },
    value,
    kind,
    filter: narrows ? target.filter : null,
  };
}

export function rowsForThisWell(api10: string, context: BridgeContext): Crossing | null {
  if (api10 === "") return null;
  return crossing(
    "rows-for-this-well",
    "Rows for this well",
    "Open this well as a row in the wells collection, at the same as-of.",
    hopTo(TARGETS["wells"] as CrossingTarget, api10, "row"),
    context,
  );
}

export function openThisSeries(api10: string, context: BridgeContext): Crossing | null {
  if (api10 === "") return null;
  return crossing(
    "open-this-series",
    "Open this series",
    "Open the months behind this chart, one row each, at the same as-of.",
    hopTo(TARGETS["production"] as CrossingTarget, api10, "filtered"),
    context,
  );
}

/** Both sides of the box, because the server caps each independently (`wells.py:378`). */
function withinCap(box: Bbox): boolean {
  return box[2] - box[0] <= BBOX_DEGREE_CAP && box[3] - box[1] <= BBOX_DEGREE_CAP;
}

function bboxParam(box: Bbox): string {
  return box.map((value) => String(value)).join(",");
}

export function whatsBehindThisLayer(
  collection: LayerCollectionRef | null,
  box: Bbox,
  context: BridgeContext,
  extentOff = false,
): Crossing | null {
  if (!collection) return null;
  const target = layerTarget(collection);
  const narrows = collection.bbox !== null && withinCap(box);
  // Two causes, two sentences (gate-m12 F1): an unticked Map view node widens the box itself,
  // so blaming the view's width there would name the wrong cause.
  const title = narrows
    ? "Open the collection this layer draws from, narrowed to the current view."
    : extentOff
      ? "Open the collection this layer draws from. Map view is unticked — the counts cover everything ingested — so the whole collection is listed."
      : `Open the collection this layer draws from. The view is too wide to narrow by — the box is capped at ${BBOX_DEGREE_CAP} degrees a side — so the whole collection is listed.`;

  return crossing(
    "whats-behind-this-layer",
    "What is behind this layer",
    title,
    hopTo(target, bboxParam(box), "filtered", narrows),
    context,
  );
}

export function vintagesCrossing(context: BridgeContext): Crossing | null {
  const target = TARGETS["vintages"] as CrossingTarget;
  return crossing(
    "vintages",
    "Vintages",
    "Every vintage this deployment has published, and what each one appended.",
    hopTo(target, "", "filtered"),
    context,
  );
}

export interface Point {
  lon: number;
  lat: number;
}

/**
 * The one crossing that runs the other way. `stateFor` is the explorer's router, so it is not
 * the builder here — the destination is the map, and what it needs is the well, the viewport
 * the link reopens at, and the `as_of` the reader was reading under.
 */
export function showOnMap(api10: string, point: Point, context: BridgeContext): Crossing | null {
  if (api10 === "" || !Number.isFinite(point.lon) || !Number.isFinite(point.lat)) return null;
  const from = pinnedState(context);
  const map: Viewport = { zoom: Math.max(from.map.zoom, WELL_ZOOM), lat: point.lat, lon: point.lon };
  const next: AppState = {
    ...from,
    view: "map",
    well: api10,
    row: null,
    map,
  };
  return {
    id: "show-on-map",
    label: "Show on map",
    title: "Open this row's geometry on the map, at the same as-of.",
    next,
    href: serializeState(next),
    pinned: asOfIn(next),
    camera: { lon: point.lon, lat: point.lat, zoom: WELL_ZOOM },
  };
}

/**
 * C6's route, verbatim (`chrome/header.ts:80-82`): push so the back button returns the reader,
 * then the one synthetic popstate main.ts dispatches every surface change through.
 *
 * The camera is asked afterwards and only reaches a map that is already mounted. On the first
 * crossing it is not, and the pushed `map=` is what positions the canvas `createMap` builds —
 * so both paths land on the same viewport and neither needs to know which one ran.
 */
export function cross(crossing: Crossing): void {
  // The one refusal, at the one route: an unpinned crossing would write its own drifting URL
  // into the address bar, which is a copy surface like any other (M6).
  if (!crossing.pinned) return;
  writeState(crossing.next, "push");
  window.dispatchEvent(new PopStateEvent("popstate"));
  if (crossing.camera) flyTo(crossing.camera);
}

export const UNPINNED_LABEL = "no vintage yet";

/** Short by obligation, not by taste: §2.3 arm 4 bars the client from authoring domain prose. */
export const UNPINNED_TITLE =
  "This view has not resolved a vintage yet, so a link from here would answer differently tomorrow.";

/**
 * M6 at the affordance rather than only in the state. A crossing whose href names no vintage is
 * written as HTML's own placeholder-for-a-link — an anchor with no `href` — so there is nothing
 * to copy, nothing to open in a new tab, and nothing announced as a link. It says why instead of
 * vanishing: a reader who cannot see the difference between a pinned link and a drifting one is
 * the reader M6 exists to protect.
 */
export function applyCrossing(link: HTMLAnchorElement, crossing: Crossing): void {
  link.dataset["crossing"] = crossing.id;
  if (crossing.pinned) {
    link.href = crossing.href;
    link.textContent = crossing.label;
    link.title = crossing.title;
    link.removeAttribute("aria-disabled");
    link.removeAttribute("data-unpinned");
    return;
  }
  link.removeAttribute("href");
  link.textContent = `${crossing.label} — ${UNPINNED_LABEL}`;
  link.title = `${crossing.title} ${UNPINNED_TITLE}`;
  link.setAttribute("aria-disabled", "true");
  link.dataset["unpinned"] = "true";
}

export interface CrossingLinkOptions {
  /**
   * Optional because the listener is on the anchor itself: a host that discards the element
   * discards the listener with it. Hosts that re-render into a live container (the record
   * panel) pass one; hosts that replace their whole subtree (the well card) need not.
   */
  signal?: AbortSignal;
  className?: string;
}

/** A chip's shape (C8 N4): a real href, a plain left click intercepted, a modified one left. */
export function crossingLink(
  crossing: Crossing,
  options: CrossingLinkOptions = {},
): HTMLAnchorElement {
  const link = document.createElement("a");
  link.className = options.className ?? "gw-crossing";
  applyCrossing(link, crossing);
  const listener: AddEventListenerOptions = {};
  if (options.signal) listener.signal = options.signal;
  link.addEventListener(
    "click",
    (event) => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
      event.preventDefault();
      cross(crossing);
    },
    listener,
  );
  return link;
}
