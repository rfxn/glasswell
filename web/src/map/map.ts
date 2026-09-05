import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import "../map.css";
import { getEnvelope, isAuthRefusal } from "../api/client.ts";
import { connectMap, onSessionBegan, selectWell, setUrlParam } from "../bus.ts";
import type { FlyTarget } from "../bus.ts";
import type { Viewport } from "../app/state.ts";
import { toast } from "../chrome/status.ts";
import type { BasemapDef } from "./basemap.ts";
import {
  BASEMAP_SOURCE,
  GLYPHS_URL,
  PMTILES_PATH,
  applyBasemapVariant,
  basemapDef,
  chooseBasemap,
  fallbackStyle,
  firstLabelLayerId,
  graticuleStyle,
  rasterStyle,
  rememberBasemap,
  sourceLabel,
  tileOrigin,
  tileProbeUrl,
  vectorStyle,
} from "./basemap.ts";
import { installClickRouter } from "./click-router.ts";
import {
  STATUS_SUMMARY_PATH,
  bboxParam,
  censusOfDrawn,
  createCountSource,
  retainVintage,
  rowDerivations,
} from "./counts.ts";
import type { Bbox, CountsState, WellStatusSummary } from "./counts.ts";
import { WELLS_BY_PREFIX } from "../explore/facets/wells-by.ts";
import type { FacetBucket } from "../explore/facets/wells-by.ts";
import { EXTENT_PARAM, countedBbox, extentFilterOn } from "./extent.ts";
import { createFacetPill } from "./facet-pill.ts";
import { PICK_PARAM, facetFromSearch, wellsByTerms } from "./facet-pick.ts";
import { createHoverCard } from "./hover-card.ts";
import { createLayerPanel } from "./layer-panel.ts";
import { createLegend, legendEnabled } from "./legend.ts";
import {
  LAYER_STORAGE_KEY,
  STATUS_STORAGE_KEY,
  readCapabilitySet,
  restoreCapabilitySet,
  writeCapabilitySet,
} from "./persist.ts";
import { createPillStrip } from "./pills.ts";
import { LAYERS, defaultLayerSet, layerDef, layerIds } from "./registry.ts";
import { createSelection } from "./selection.ts";
import { filterableStatusIds } from "./status.ts";
import {
  FACET_FILTERED_LAYERS,
  OPACITY_OVERRIDE,
  WELL_POINT_LAYERS,
  dataLayers,
  sourceSpecs,
  strikeGlyph,
  wellFilter,
} from "./style.ts";
import { METRIC_FILL_LAYERS } from "./thematics.ts";
import { createThematicsKey } from "./thematics-key.ts";
import { createTileBanner } from "./tile-banner.ts";
import { tileRequest } from "./tile-request.ts";
import { applyVariantStyling } from "./variant-style.ts";
import { createWellsBySheet } from "./wells-by-sheet.ts";

// Exported for the archive-failure test: the degradation path is the one part of the map
// module that only runs when something is broken, so it is the part most likely to rot.
export { resolveStyle as resolveBasemapStyle };

export interface MapCallbacks {
  onViewport(viewport: Viewport): void;
}

export interface MapHandle {
  select(api10: string | null): void;
  flyTo(target: FlyTarget): void;
}

interface BasemapManifest {
  archive: string;
  labels: boolean;
  vintage?: string;
  sha256?: string;
}

const MANIFEST_PATH = "/basemap/manifest.json";

/**
 * The deepest zoom the imagery was measured to carry over the regions this deploys against.
 * Above it the service answers 200 with a grey placeholder rather than a 404, which nothing
 * in the client can tell from imagery — so this tracks `BasemapDef.maxzoom` and is re-probed,
 * never raised on the 24 levels the service advertises (`infra/basemap/README.md`).
 */
export const MAP_MAX_ZOOM = 19;

/**
 * The shallowest zoom worth serving. Below it the whole basin fits in a fraction of the
 * canvas and the rest is ocean, and every tile source is fetching a pyramid nothing on it
 * can be read at. z3 holds the contiguous states plus a Canadian margin in one frame.
 */
export const MAP_MIN_ZOOM = 3;

/**
 * `[[west, south], [east, north]]`, which is the order MapLibre's LngLatBoundsLike takes.
 *
 * Generous on purpose: this build serves four states, the next ones are American and Canada
 * is the stated direction, so the box holds the contiguous forty-eight, mainland Alaska, the
 * Canadian provinces to Newfoundland, and Mexico. A pan floor and not a data extent — it
 * claims no coverage of what it contains, only that outside it there is nothing to look at.
 *
 * A rectangle holding both Utqiagvik and Key West holds a corner of open Pacific with them;
 * the western Aleutians are the one populated place deliberately outside, because a box drawn
 * across the antimeridian to reach them would take the whole ocean.
 */
export const MAP_MAX_BOUNDS: [[number, number], [number, number]] = [
  [-170, 18],
  [-52, 75],
];

/** Built once: the style is rebuilt on every basemap swap and this set is a property of neither
 *  the style nor the viewport. */
const facetLayers = new Set(FACET_FILTERED_LAYERS.map((layer) => layer.id));

const OPACITY_PROPERTY: Readonly<Record<string, string>> = {
  circle: "circle-opacity",
  line: "line-opacity",
  fill: "fill-opacity",
  symbol: "icon-opacity",
};

/** The type's default slot, unless the layer names its own — the disposal ring's stroke. */
function opacityProperty(layer: { type: string; metadata?: unknown }): string | undefined {
  const override = (layer.metadata as Record<string, unknown> | undefined)?.[OPACITY_OVERRIDE];
  return typeof override === "string" ? override : OPACITY_PROPERTY[layer.type];
}

let protocolRegistered = false;

async function registerPmtilesProtocol(): Promise<void> {
  if (protocolRegistered) return;
  const { Protocol } = await import("pmtiles");
  maplibregl.addProtocol("pmtiles", new Protocol().tile);
  protocolRegistered = true;
}

/**
 * PMTiles is read with HTTP range requests; a server that answers a ranged GET with a whole
 * 200 would make every tile read pull the entire archive. Requiring the 206 is how the
 * serving mechanism is verified at runtime rather than assumed from the deploy notes.
 */
async function archiveServesRanges(path: string): Promise<boolean> {
  try {
    const response = await fetch(path, { headers: { Range: "bytes=0-15" } });
    return response.status === 206;
  } catch {
    return false; // A network failure and a missing archive lead to the same fallback.
  }
}

/**
 * Imagery is somebody else's origin, so "can it be reached" is a question with an answer
 * before anything is drawn — and the answer decides whether the reader is shown a basemap or
 * a fallback, rather than an empty canvas with an attribution over it.
 */
async function tilesReachable(base: BasemapDef): Promise<boolean> {
  const probe = tileProbeUrl(base);
  if (!probe) return false;
  try {
    return (await fetch(probe)).ok;
  } catch {
    return false; // A refused origin and an unreachable one are one failure to the reader.
  }
}

async function readManifest(): Promise<BasemapManifest | null> {
  try {
    const response = await fetch(MANIFEST_PATH, { headers: { Accept: "application/json" } });
    if (!response.ok) return null;
    const parsed = (await response.json()) as Partial<BasemapManifest>;
    if (typeof parsed.archive !== "string") return null;
    return { archive: parsed.archive, labels: parsed.labels === true, ...parsed };
  } catch {
    return null; // No manifest is a normal state before the basemap is deployed.
  }
}

interface ResolvedStyle {
  style: maplibregl.StyleSpecification | string;
  /** No `fallback` where nothing replaced what failed: the banner then states only the loss. */
  failure?: { source: string; fallback?: string };
  vintage?: string;
}

async function resolveStyle(id: string): Promise<ResolvedStyle> {
  const base = basemapDef(id) ?? basemapDef("none")!;
  if (base.kind !== "vector") {
    const assets = await readManifest();
    // Glyphs are served from this origin whatever the basemap is, and without the url every
    // symbol layer is dropped — which is why the spacing-unit label did not exist at all on
    // satellite or on none, the two variants VF-5 calls hardest to read.
    const labelled = (style: maplibregl.StyleSpecification): maplibregl.StyleSpecification => {
      if (assets?.labels === true) style.glyphs = GLYPHS_URL;
      return style;
    };
    if (base.kind !== "raster") return { style: labelled(graticuleStyle()) };
    const declared = fallbackStyle(base);
    if (declared && !(await tilesReachable(base))) {
      return { style: labelled(declared.style), failure: declared.failure };
    }
    return { style: labelled(rasterStyle(base)) };
  }

  const manifest = await readManifest();
  const archive = manifest?.archive ?? PMTILES_PATH;
  if (await archiveServesRanges(archive)) {
    await registerPmtilesProtocol();
    // A hybrid draws a second substrate that can fail on its own. Dropping the source is what
    // keeps its credit from outliving it, and it is also what silences MapLibre — an absent
    // source requests no tile and raises no `error` — so this is the only place left to say so.
    const imagery = base.tiles?.length ? await tilesReachable(base) : true;
    const style = vectorStyle(base, { labels: manifest?.labels === true, imagery });
    const source = style.sources[BASEMAP_SOURCE];
    if (source && "url" in source) source.url = `pmtiles://${archive}`;
    const result: ResolvedStyle = { style };
    if (manifest?.vintage) result.vintage = manifest.vintage;
    if (!imagery) result.failure = { source: tileOrigin(base) };
    return result;
  }

  // The same declared fallback the imagery path runs, named for the archive that failed.
  const declared = fallbackStyle(base);
  if (declared) return { style: declared.style, failure: { ...declared.failure, source: archive } };
  return { style: graticuleStyle() };
}

export function createMap(
  container: HTMLElement,
  viewport: Viewport,
  callbacks: MapCallbacks,
): MapHandle {
  const map = new maplibregl.Map({
    container,
    style: graticuleStyle(),
    center: [viewport.lon, viewport.lat],
    zoom: viewport.zoom,
    attributionControl: false,
    minZoom: MAP_MIN_ZOOM,
    maxZoom: MAP_MAX_ZOOM,
    maxBounds: MAP_MAX_BOUNDS,
    transformRequest: (url) => tileRequest(url),
  });

  // An analytic map has an up. Rotation costs orientation and buys nothing here.
  map.dragRotate.disable();
  map.touchZoomRotate.disableRotation();
  map.keyboard.disableRotation();

  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  map.addControl(new maplibregl.ScaleControl({ maxWidth: 120, unit: "imperial" }), "bottom-left");
  map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");

  const chrome = document.createElement("div");
  chrome.className = "gw-map-chrome";
  container.appendChild(chrome);

  const banner = createTileBanner();
  const thematics = createThematicsKey();
  const hover = createHoverCard({
    // The key's box in the chrome's own coordinates, so the card can dodge it (m23 V-1).
    avoid: () => {
      if (thematics.element.hidden || !thematics.element.isConnected) return null;
      const key = thematics.element.getBoundingClientRect();
      const origin = chrome.getBoundingClientRect();
      return {
        left: key.left - origin.left,
        top: key.top - origin.top,
        right: key.right - origin.left,
        bottom: key.bottom - origin.top,
      };
    },
  });
  chrome.append(banner.element, hover.element);

  let basemap = chooseBasemap();
  let variant = applyBasemapVariant(basemap, container);
  let on = restoreCapabilitySet(readCapabilitySet(LAYER_STORAGE_KEY), layerIds(), defaultLayerSet());
  // Every class on by default; the same {on,known} shape, so a class added to the vocabulary
  // later arrives visible rather than hidden by a stored set that predates it.
  let statuses = restoreCapabilitySet(
    readCapabilitySet(STATUS_STORAGE_KEY),
    filterableStatusIds(),
    filterableStatusIds(),
  );
  const opacities = new Map(LAYERS.map((layer) => [layer.id, layer.opacity]));
  // The URL is the extent predicate's only home (M1-2): a shared link reconstructs the
  // population, and no session state can disagree with what the link says.
  let extentOn = extentFilterOn(window.location.search);
  // The Wells-By press, from the URL for the reason the extent node is: a shared link has to
  // reproduce the canvas, and no session state may disagree with what the link says.
  let facet = facetFromSearch(window.location.search);

  const legend = createLegend({
    on: statuses,
    // The counts do not move: a class the reader stopped drawing is still in the area. What
    // moves is the canvas, and the census of it has to wait for the repaint.
    onFilter: (next) => {
      statuses = next;
      writeCapabilitySet(STATUS_STORAGE_KEY, statuses, filterableStatusIds());
      applyWellFilter();
      invalidateDrawn();
    },
    extentOn,
    // The canvas does not move — it is the viewport either way. What moves is the question
    // the counts ask, so only the counts are re-asked.
    onExtent: (next) => {
      extentOn = next;
      setUrlParam(EXTENT_PARAM, next ? null : "0");
      refreshCounts();
    },
  });

  const panel = createLayerPanel({
    on,
    basemap,
    onToggle: (id, next) => setLayer(id, next),
    onOpacity: (id, value) => setOpacity(id, value),
    onBasemap: (id) => setBasemap(id),
    // The other half of the one-sheet-at-a-time rule the Wells-By hook states below. Declared
    // one way it was not a rule: opening this one second left both on the column, each trigger
    // announcing itself expanded (visual-map-wells-by D3).
    onOpen: () => wellsBy.close(),
    onReset: (next) => {
      on = next;
      applyVisibility();
      persist();
    },
  });

  const pills = createPillStrip({
    onRemove: (id) => setLayer(id, !on.has(id)),
    onOpen: () => panel.open(),
  });

  // On the canvas rather than only inside the sheet: at 768 the sheet covers the map, so a
  // reader who pressed a bucket and shut it would have no way to see or release the filter.
  const facetPill = createFacetPill({
    onClear: () => setPick(null, null),
    onOpen: () => wellsBy.open(),
  });

  const wellsBy = createWellsBySheet({
    setPanel: (values, mode) => {
      for (const [key, value] of Object.entries(values)) {
        setUrlParam(`${WELLS_BY_PREFIX}${key}`, value, mode);
      }
      panelTerms = wellsByTerms(window.location.search);
      // A press belongs to the dimension and the state it was made in: carried across either, it
      // would narrow the canvas by a value the new ranking never listed.
      if ("by" in values || "state" in values) setPick(null, null);
      else wellsBy.refresh();
    },
    onPick: (value, bucket) => setPick(value, bucket),
    // One sheet at a time: the two share a column and a geometry, and two open sheets are one
    // sheet with the other's rows behind it.
    onOpen: () => panel.close(),
  });

  /** What the URL said about the panel when the map last acted on it. */
  let panelTerms = wellsByTerms(window.location.search);

  /**
   * A press, committed. `push` and not `replace`: narrowing the map to one operator is a
   * decision the back button should undo, unlike a pan (`?extent`, `?layers`), which is churn.
   */
  function setPick(value: string | null, bucket: FacetBucket | null): void {
    setUrlParam(PICK_PARAM, value, "push");
    panelTerms = wellsByTerms(window.location.search);
    facet = facetFromSearch(window.location.search);
    applyWellFilter();
    invalidateDrawn();
    facetPill.set(
      facet ? { dimension: facet.dimension, value: facet.value, wells: bucket?.wells ?? null } : null,
    );
    facetPill.setZoom(map.getZoom());
    wellsBy.refresh();
  }

  /**
   * The other end of that push. Without this the URL moved on a back press and nothing else did,
   * so the pill still named a press the link no longer carried and a reader who copied it sent a
   * map they were not looking at — the invariant stated above `facet` (visual-map-wells-by D2).
   */
  window.addEventListener("popstate", () => {
    const next = wellsByTerms(window.location.search);
    if (next === panelTerms) return;
    panelTerms = next;
    facet = facetFromSearch(window.location.search);
    applyWellFilter();
    invalidateDrawn();
    // No figure: the panel has not answered for this bucket, and a census of the canvas would
    // move when the reader pans. The same rule a press restored from a link follows.
    facetPill.set(facet ? { dimension: facet.dimension, value: facet.value, wells: null } : null);
    facetPill.setZoom(map.getZoom());
    wellsBy.refresh();
  });

  // The handle stays live either way: refreshCounts() writes to a detached legend without
  // knowing it is off-canvas, so nothing has to test for the suppressed case at every call.
  const showLegend = legendEnabled(window.location.search);
  // `?legend=0` suppresses the thematic key with the status key: both are legends, and an
  // embed that asked for a clean canvas asked for both to go.
  // One band, stacked: the layer pills and the applied-bucket pill both state what is applied
  // and both want the top left, so they share a column rather than overlaying each other. The
  // facet pill is not behind `?legend=0` — an embed that asked for a clean canvas did not ask
  // for a filter it cannot see, and the pill is applied state rather than a key.
  const topLeft = document.createElement("div");
  topLeft.className = "gw-map-topleft";
  topLeft.append(pills.element, facetPill.element);
  chrome.append(
    ...(showLegend ? [topLeft, legend.element, thematics.element] : [topLeft]),
    panel.element,
    wellsBy.element,
  );
  map.addControl(new SheetButton("Layers", "gw-layers-button", () => panel.toggle()), "top-right");
  map.addControl(
    new SheetButton("Wells by", "gw-wells-by-button", () => wellsBy.toggle()),
    "top-right",
  );

  function persist(): void {
    writeCapabilitySet(LAYER_STORAGE_KEY, on, layerIds());
    const extras = layerIds().filter((id) => on.has(id) !== Boolean(layerDef(id)?.defaultOn));
    setUrlParam("layers", extras.length > 0 ? extras.join(",") : null);
  }

  function setLayer(id: string, next: boolean): void {
    if (next) on.add(id);
    else on.delete(id);
    applyVisibility();
    persist();
  }

  function setOpacity(id: string, value: number): void {
    opacities.set(id, value);
    applyOpacity(id);
  }

  function applyVisibility(): void {
    for (const layer of LAYERS) {
      for (const styleLayer of layer.styleLayers) {
        if (map.getLayer(styleLayer)) {
          map.setLayoutProperty(styleLayer, "visibility", on.has(layer.id) ? "visible" : "none");
        }
      }
    }
    panel.setOn(on);
    pills.setOn(on);
    refreshThematics();
    invalidateDrawn();
  }

  function applyOpacity(id: string): void {
    const layer = layerDef(id);
    if (!layer) return;
    for (const styleLayer of layer.styleLayers) {
      const spec = map.getLayer(styleLayer);
      const property = spec && opacityProperty(spec);
      if (property) map.setPaintProperty(styleLayer, property, opacities.get(id) ?? 1);
    }
  }

  /**
   * One writer for one slot. `setFilter` replaces a layer's filter whole and this runs on every
   * `zoom` event, so the status gate and the facet press have to be composed here rather than
   * written separately — a press written on its own is clobbered on the next frame of a pinch.
   * Every well layer, not only the status-gated seven: the strikes, the disposal ring and the
   * survey traces carry their own predicate and would otherwise keep drawing what was filtered
   * away.
   */
  function applyWellFilter(): void {
    for (const { id } of FACET_FILTERED_LAYERS) {
      if (!map.getLayer(id)) continue;
      const filter = wellFilter(map.getZoom(), statuses, facet, id);
      map.setFilter(id, filter as maplibregl.FilterSpecification | undefined);
    }
  }

  let countTimer: ReturnType<typeof setTimeout> | undefined;
  let countsFailing = false;
  // The map's only reading of the served vintage: the rail's chip is main.ts's, and a crossing
  // off this surface has to pin something the reader was actually looking at (SB-08 M6).
  let resolvedVintage: string | null = null;

  const countSource = createCountSource({
    load: (bbox, signal) =>
      getEnvelope<WellStatusSummary>(STATUS_SUMMARY_PATH, { bbox: bboxParam(bbox) }, signal),
    onState: (state) => paintCounts(state),
  });

  function scheduleCounts(): void {
    clearTimeout(countTimer);
    countTimer = setTimeout(() => {
      // A debounce can outlive its map; a detached container has no window to read.
      if (container.isConnected) refreshCounts();
    }, 250);
  }

  function viewportBbox(): Bbox {
    const bounds = map.getBounds();
    return [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()];
  }

  /**
   * Two questions with two answers. What is in the area is asked of the data, at any zoom;
   * what is on the canvas is a census of the canvas, and is only ever reported as that.
   */
  function refreshCounts(): void {
    panel.setZoom(map.getZoom());
    // The counted population, not always the viewport: with the extent node off the counts
    // cover everything ingested, and the crossing has to name that same population.
    const bbox = countedBbox(extentOn, viewportBbox());
    // The crossing narrows by the box, so it is rebuilt with the box and not with the answer:
    // a reader who pans and clicks before the counts settle must not get the last viewport.
    panel.setCrossing(bbox, resolvedVintage, !extentOn);
    countSource.request(bbox);
    refreshDrawn();
  }

  /** The canvas has changed but not yet repainted, so there is no census to report yet. */
  function invalidateDrawn(): void {
    legend.setDrawn(null);
    scheduleCounts();
  }

  /**
   * Which switched-on rows painted nothing here. Only on `idle`, because a layer whose tiles
   * are still streaming queries empty and would be reported as absent mid-load.
   */
  function refreshCoverage(): void {
    const zoom = map.getZoom();
    const drawable = LAYERS.filter((layer) => on.has(layer.id) && zoom >= layer.minZoom);
    const queried = drawable.flatMap((layer) => layer.styleLayers).filter((id) => map.getLayer(id));
    if (queried.length === 0) {
      panel.setCoverage(new Set());
      return;
    }
    const features = map.queryRenderedFeatures({ layers: queried });
    const painted = new Set(features.map((feature) => feature.layer.id));
    // R3: every drawn row resolves its own ⌾ off the tile that drew it, not just the four
    // wells rows and the thematic wash. A row with nothing on the canvas keeps its last
    // handle rather than being blanked — the tile it named is still the tile it draws from.
    for (const [id, handle] of rowDerivations(drawable, features)) panel.setProvenance(id, handle);
    panel.setCoverage(
      new Set(
        drawable
          .filter((layer) => !layer.styleLayers.some((id) => painted.has(id)))
          .map((layer) => layer.id),
      ),
    );
  }

  /** The pixel census, demoted to the one thing it can honestly answer. */
  function refreshDrawn(): void {
    refreshThematics();
    const layers = WELL_POINT_LAYERS.filter((id) => map.getLayer(id) && on.has(id));
    if (layers.length === 0) {
      // Not a partial plot: the reader switched the layer off, and the panel already says so.
      legend.setDrawn(null);
      return;
    }
    const features = map.queryRenderedFeatures({ layers: [...layers] });
    legend.setDrawn(censusOfDrawn(features).wells);
    // Each state's row takes the handle of its own tile. WELL_POINT_LAYERS names ids that are
    // both a style layer and a registry row, which is what lets one call key both.
    for (const [id, handle] of rowDerivations(
      layers.map((id) => ({ id, styleLayers: [id] })),
      features,
    )) {
      panel.setProvenance(id, handle);
    }
  }

  /**
   * The thematic key restates the frame the rendered cells carry — bins are cut at refresh
   * and ride the tile, so the key reads them off the canvas rather than recomputing, and an
   * empty canvas (or the row off) is a hidden key, never a stale one.
   */
  function refreshThematics(): void {
    if (!on.has("land-metrics")) {
      thematics.clear();
      return;
    }
    const layers = METRIC_FILL_LAYERS.filter((id) => map.getLayer(id));
    if (layers.length === 0) {
      thematics.clear();
      return;
    }
    const rendered = map.queryRenderedFeatures({ layers: [...layers] });
    thematics.set(rendered.map((feature) => feature.properties as Record<string, unknown>));
    const derivation = rendered
      .map((feature) => feature.properties?.["derivation_id"])
      .find((handle): handle is string => typeof handle === "string" && handle !== "");
    if (derivation) panel.setProvenance("land-metrics", derivation);
  }

  function paintCounts(state: CountsState): void {
    const zoom = map.getZoom();
    // Ahead of the two early returns, so a failing or in-flight answer cannot leave the panel
    // offering a crossing that names no vintage for the rest of the session (SB-08 M6).
    resolvedVintage = retainVintage(resolvedVintage, state);
    if (state.kind === "loading") {
      legend.setPending(zoom);
      return;
    }
    if (state.kind === "error") {
      // A refusal for want of a session is pending, not unavailable: signing in re-asks it.
      if (state.auth) {
        legend.setPending(zoom);
        return;
      }
      legend.setUnavailable(zoom);
      // One toast per failing episode: a pan over a degraded API is a dozen settles, and a
      // dozen toasts would bury the one line that says what happened.
      if (!countsFailing) toast(`Well counts unavailable: ${state.message}`);
      countsFailing = true;
      return;
    }
    countsFailing = false;
    panel.setCrossing(state.bbox, resolvedVintage, !extentOn);
    legend.setCounts(state.counts, zoom, state.handles, {
      wells: state.total,
      handle: state.totalHandle,
    });
    legend.setVocabulary(state.vocabulary);
    legend.setProducing(state.producing);
    legend.setWellTypes(state.wellTypes);
    legend.setProvenance(state.provenance);
    refreshDrawn();
  }

  /**
   * The well layers are folded into the incoming style rather than added after it loads.
   * Adding them on a style event is a race — `isStyleLoaded()` stays false while a vector
   * source is still streaming tiles — and `transformStyle` is the one point where the new
   * style exists and nothing has been rendered from it yet.
   */
  function withDataLayers(next: maplibregl.StyleSpecification): maplibregl.StyleSpecification {
    const background = next.layers.find((layer) => layer.type === "background");
    const hollowFill =
      (background && "paint" in background && background.paint?.["background-color"]) || undefined;
    const built = dataLayers({
      labels: Boolean(next.glyphs),
      variant,
      ...(typeof hollowFill === "string" ? { hollowFill } : {}),
    });
    const styled = built.map((layer) => {
      const owner = LAYERS.find((candidate) => candidate.styleLayers.includes(layer.id));
      if (owner && !on.has(owner.id)) {
        layer.layout = { ...layer.layout, visibility: "none" } as typeof layer.layout;
      }
      if (owner) {
        const property = opacityProperty(layer);
        const opacity = opacities.get(owner.id);
        if (property && opacity !== undefined) {
          layer.paint = { ...layer.paint, [property]: opacity } as typeof layer.paint;
        }
      }
      if (facetLayers.has(layer.id)) {
        // The style is rebuilt wholesale on a basemap swap (`setStyle` runs with diff:false), so
        // a press held only in a live filter slot vanishes when the reader picks satellite.
        // Circle and line layers, which the spec allows a filter on; the union type includes
        // `background`, which does not, so the narrowing has to be written out.
        const slot = layer as { filter?: maplibregl.FilterSpecification };
        const filter = wellFilter(map.getZoom(), statuses, facet, layer.id);
        // Deleted rather than set to undefined: MapLibre validates a property that is present,
        // so `filter: undefined` fails validation and the style never loads at all.
        if (filter) slot.filter = filter as maplibregl.FilterSpecification;
        else delete slot.filter;
      }
      return layer;
    });

    // Under the basemap's own labels, so town and county names stay readable over wells.
    const layers = [...next.layers];
    const labelIndex = layers.findIndex((layer) => layer.id === firstLabelLayerId(next));
    layers.splice(labelIndex < 0 ? layers.length : labelIndex, 0, ...styled);
    const data = sourceSpecs();
    // The variant pass runs over the merged list — the basemap's labels and lines as well as
    // this app's — so nothing text-bearing reaches the canvas unkeyed to the substrate.
    return {
      ...next,
      sources: { ...next.sources, ...data },
      layers: applyVariantStyling(layers, variant, new Set(Object.keys(data))),
    };
  }

  function installStrikeGlyph(): void {
    if (map.hasImage("gw-strike")) return;
    const image = strikeGlyph();
    if (image) map.addImage("gw-strike", image);
  }

  function featureRefs(api10: string): { source: string; sourceLayer: string; id: string }[] {
    return Object.keys(sourceSpecs()).map((source) => ({ source, sourceLayer: source, id: api10 }));
  }

  const selection = createSelection(featureRefs, {
    hasSource: (source) => Boolean(map.getSource(source)),
    set: (reference) => map.setFeatureState(reference, { selected: true }),
    remove: (reference) => map.removeFeatureState(reference, "selected"),
  });

  async function setBasemap(id: string): Promise<void> {
    basemap = id;
    variant = applyBasemapVariant(id, container);
    rememberBasemap(id);
    setUrlParam("base", id === "dark" ? null : id);
    panel.setBasemap(id);
    const resolved = await resolveStyle(id);
    if (resolved.failure) banner.report(resolved.failure.source, resolved.failure.fallback);
    map.setStyle(resolved.style as maplibregl.StyleSpecification, {
      diff: false,
      transformStyle: (_previous, next) => withDataLayers(next),
    });
    // The new style's sources do not exist yet, here or at boot; `styledata` is where they do.
    selection.forget();
    installStrikeGlyph();
    applyVisibility();
  }

  map.on("load", () => {
    void setBasemap(basemap);
    installClickRouter(map, {
      onClick: (api10) => selectWell(api10, "map"),
      onHover: (hit, event) => {
        if (hit) hover.show(hit.properties, event.point);
        else hover.hide();
      },
    });
    // `idle` alone misses the case where the last tile of a pan lands after it fired, which
    // leaves the legend showing an em dash over a map full of wells.
    map.on("idle", scheduleCounts);
    map.on("idle", refreshCoverage);
    map.on("moveend", scheduleCounts);
    map.on("remove", () => clearTimeout(countTimer));
    map.on("sourcedata", (event) => {
      if (event.isSourceLoaded) scheduleCounts();
    });
    map.on("zoom", () => {
      applyWellFilter();
      // The thinning sentence is a fact about the zoom, and the pill is where it is stated.
      facetPill.setZoom(map.getZoom());
    });
    map.on("styleimagemissing", (event) => {
      if (event.id === "gw-strike") installStrikeGlyph();
    });
    panel.setZoom(map.getZoom());
    pills.setOn(on);
    facetPill.set(facet ? { dimension: facet.dimension, value: facet.value, wells: null } : null);
    facetPill.setZoom(map.getZoom());
  });

  map.on("moveend", () => {
    const centre = map.getCenter();
    callbacks.onViewport({ zoom: map.getZoom(), lat: centre.lat, lon: centre.lng });
  });

  map.on("error", (event) => {
    // Nobody has signed in yet, or the session lapsed. `sessionBegan` re-requests these tiles,
    // so the refusal is a state this map passes through rather than one it reports (DR-H20).
    if (isAuthRefusal((event as unknown as { error?: unknown }).error)) return;
    const source = (event as unknown as { sourceId?: string }).sourceId;
    if (source) banner.report(sourceLabel(source));
    // MapLibre logs errors itself only when nothing is listening. Having a listener and
    // dropping the ones it cannot attribute to a source is how a style-validation failure
    // becomes an empty map over a clean console.
    else console.error("map error", event.error ?? event);
  });

  map.on("styledata", () => selection.resync());

  /**
   * The signed-out arrival refused every data tile and every count. MapLibre does not retry a
   * source on its own — an errored tile stays errored until the source is told to load again —
   * so handing each one its own tile list back is what puts the wells on the canvas.
   */
  onSessionBegan(() => {
    for (const [id, spec] of Object.entries(sourceSpecs())) {
      banner.forget(sourceLabel(id));
      const source = map.getSource(id);
      if (source && "setTiles" in source && "tiles" in spec && spec.tiles) {
        (source as maplibregl.VectorTileSource).setTiles([...spec.tiles]);
      }
    }
    countsFailing = false;
    refreshCounts();
  });

  const handle: MapHandle = {
    select(api10) {
      selection.select(api10);
    },
    flyTo(point) {
      // Nothing reserved on the right any more: the card is a column beside the map, not a
      // panel over it, so holding back half the canvas would land the well in the left third
      // of the column it should sit in the middle of.
      const padding = { top: 0, bottom: 0, left: 0, right: 0 };
      // The caller's zoom is a floor: a search from the basin pulls in, a search at z14 stays.
      const zoom = Math.max(map.getZoom(), point.zoom ?? 11);
      const target = { center: [point.lon, point.lat] as [number, number], zoom, padding };
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) map.jumpTo(target);
      else map.easeTo({ ...target, duration: 600 });
    },
  };
  connectMap(handle);
  return handle;
}

/**
 * Opens one of the map's sheets from its own control cluster, not from the app header. One
 * class for both: they are the same control over the same frame, and the sheet each opens
 * announces its own state back onto this button's `aria-expanded` off the class name.
 */
class SheetButton implements maplibregl.IControl {
  private readonly label: string;
  private readonly className: string;
  private readonly onClick: () => void;
  private container: HTMLElement | undefined;

  constructor(label: string, className: string, onClick: () => void) {
    this.label = label;
    this.className = className;
    this.onClick = onClick;
  }

  onAdd(): HTMLElement {
    const container = document.createElement("div");
    container.className = "maplibregl-ctrl maplibregl-ctrl-group";
    const button = document.createElement("button");
    button.type = "button";
    button.className = this.className;
    button.textContent = this.label;
    button.setAttribute("aria-label", this.label);
    button.addEventListener("click", this.onClick);
    container.appendChild(button);
    this.container = container;
    return container;
  }

  onRemove(): void {
    this.container?.remove();
  }
}
