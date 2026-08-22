import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import "../map.css";
import { getEnvelope } from "../api/client.ts";
import { connectMap, selectWell, setUrlParam } from "../bus.ts";
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
} from "./counts.ts";
import type { Bbox, CountsState, WellStatusSummary } from "./counts.ts";
import { EXTENT_PARAM, countedBbox, extentFilterOn } from "./extent.ts";
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
  WELL_POINT_LAYERS,
  dataLayers,
  sourceSpecs,
  statusFilter,
  statusStyledLayerIds,
  strikeGlyph,
} from "./style.ts";
import { createTileBanner } from "./tile-banner.ts";
import { tileRequest } from "./tile-request.ts";
import { applyVariantStyling } from "./variant-style.ts";

export { absoluteTileUrl } from "./style.ts";
export { graticuleStyle as baseStyle } from "./basemap.ts";
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
const OPACITY_PROPERTY: Readonly<Record<string, string>> = {
  circle: "circle-opacity",
  line: "line-opacity",
  fill: "fill-opacity",
  symbol: "icon-opacity",
};

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
  failure?: { source: string; fallback: string };
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
    const style = vectorStyle(base, { labels: manifest?.labels === true });
    const source = style.sources[BASEMAP_SOURCE];
    if (source && "url" in source) source.url = `pmtiles://${archive}`;
    const result: ResolvedStyle = { style };
    if (manifest?.vintage) result.vintage = manifest.vintage;
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
    maxZoom: 18,
    transformRequest: (url, resourceType) => tileRequest(url, resourceType),
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
  const hover = createHoverCard();
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
  // Built once: `zoom` fires on every animation frame of a pinch, and the gated set is a
  // property of the style, not of the viewport.
  const statusGated = statusStyledLayerIds();

  const legend = createLegend({
    on: statuses,
    // The counts do not move: a class the reader stopped drawing is still in the area. What
    // moves is the canvas, and the census of it has to wait for the repaint.
    onFilter: (next) => {
      statuses = next;
      writeCapabilitySet(STATUS_STORAGE_KEY, statuses, filterableStatusIds());
      applyStatusFilter();
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

  // The handle stays live either way: refreshCounts() writes to a detached legend without
  // knowing it is off-canvas, so nothing has to test for the suppressed case at every call.
  const showLegend = legendEnabled(window.location.search);
  chrome.append(...(showLegend ? [pills.element, legend.element] : [pills.element]), panel.element);
  map.addControl(new LayerButton(() => panel.toggle()), "top-right");

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
    invalidateDrawn();
  }

  function applyOpacity(id: string): void {
    const layer = layerDef(id);
    if (!layer) return;
    for (const styleLayer of layer.styleLayers) {
      const spec = map.getLayer(styleLayer);
      const property = spec && OPACITY_PROPERTY[spec.type];
      if (property) map.setPaintProperty(styleLayer, property, opacities.get(id) ?? 1);
    }
  }

  function applyStatusFilter(): void {
    const filter = statusFilter(map.getZoom(), statuses);
    for (const id of statusGated) {
      if (map.getLayer(id)) map.setFilter(id, filter as maplibregl.FilterSpecification);
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
    countTimer = setTimeout(refreshCounts, 250);
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

  /** The pixel census, demoted to the one thing it can honestly answer. */
  function refreshDrawn(): void {
    const layers = WELL_POINT_LAYERS.filter((id) => map.getLayer(id) && on.has(id));
    if (layers.length === 0) {
      // Not a partial plot: the reader switched the layer off, and the panel already says so.
      legend.setDrawn(null);
      return;
    }
    const census = censusOfDrawn(map.queryRenderedFeatures({ layers: [...layers] }));
    legend.setDrawn(census.wells);
    if (census.derivation) for (const id of layers) panel.setProvenance(id, census.derivation);
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
    const gated = new Set(statusStyledLayerIds(built));
    const styled = built.map((layer) => {
      const owner = LAYERS.find((candidate) => candidate.styleLayers.includes(layer.id));
      if (owner && !on.has(owner.id)) {
        layer.layout = { ...layer.layout, visibility: "none" } as typeof layer.layout;
      }
      if (owner) {
        const property = OPACITY_PROPERTY[layer.type];
        const opacity = opacities.get(owner.id);
        if (property && opacity !== undefined) {
          layer.paint = { ...layer.paint, [property]: opacity } as typeof layer.paint;
        }
      }
      if (gated.has(layer.id)) {
        // Circle and line layers, which the spec allows a filter on; the union type includes
        // `background`, which does not, so the narrowing has to be written out.
        (layer as { filter?: maplibregl.FilterSpecification }).filter = statusFilter(
          map.getZoom(),
          statuses,
        ) as maplibregl.FilterSpecification;
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
    map.on("moveend", scheduleCounts);
    map.on("sourcedata", (event) => {
      if (event.isSourceLoaded) scheduleCounts();
    });
    map.on("zoom", applyStatusFilter);
    map.on("styleimagemissing", (event) => {
      if (event.id === "gw-strike") installStrikeGlyph();
    });
    panel.setZoom(map.getZoom());
    pills.setOn(on);
  });

  map.on("moveend", () => {
    const centre = map.getCenter();
    callbacks.onViewport({ zoom: map.getZoom(), lat: centre.lat, lon: centre.lng });
  });

  map.on("error", (event) => {
    const source = (event as unknown as { sourceId?: string }).sourceId;
    if (source) banner.report(sourceLabel(source));
    // MapLibre logs errors itself only when nothing is listening. Having a listener and
    // dropping the ones it cannot attribute to a source is how a style-validation failure
    // becomes an empty map over a clean console.
    else console.error("map error", event.error ?? event);
  });

  map.on("styledata", () => selection.resync());

  const handle: MapHandle = {
    select(api10) {
      selection.select(api10);
    },
    flyTo(point) {
      // Land the well in the strip the card does not cover, not under it.
      const padding = { top: 0, bottom: 0, left: 0, right: Math.min(520, container.clientWidth / 2) };
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

/** Opens the layer panel from the map's own control cluster, not from the app header. */
class LayerButton implements maplibregl.IControl {
  private readonly onClick: () => void;
  private container: HTMLElement | undefined;

  constructor(onClick: () => void) {
    this.onClick = onClick;
  }

  onAdd(): HTMLElement {
    const container = document.createElement("div");
    container.className = "maplibregl-ctrl maplibregl-ctrl-group";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "gw-layers-button";
    button.textContent = "Layers";
    button.setAttribute("aria-label", "Layers");
    button.addEventListener("click", this.onClick);
    container.appendChild(button);
    this.container = container;
    return container;
  }

  onRemove(): void {
    this.container?.remove();
  }
}
