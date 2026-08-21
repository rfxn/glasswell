import { layers, namedFlavor } from "@protomaps/basemaps";
import type { Flavor } from "@protomaps/basemaps";
import type { LayerSpecification, StyleSpecification } from "maplibre-gl";

import { BASE_STORAGE_KEY, readGuarded, writeGuarded } from "./persist.ts";

/**
 * Basemap options, all keyless and all attributable. The vector flavours read a PMTiles
 * archive from this app's own origin, so the map does not depend on anyone else's uptime, and
 * every option degrades to the graticule locally rather than to a hosted substitute that
 * `connect-src 'self'` would refuse. Satellite imagery is the one external origin, and the
 * policy names it (`glasswell.api.security`, `infra/basemap/README.md`).
 */
export type BasemapKind = "vector" | "raster" | "graticule";

export interface BasemapDef {
  id: string;
  label: string;
  kind: BasemapKind;
  /** `@protomaps/basemaps` flavour name for the vector options. */
  flavor?: "dark" | "light" | "grayscale" | "white" | "black";
  tiles?: string[];
  maxzoom?: number;
  attribution: string;
  /** What the map degrades to when this option's tiles cannot be had. `fallbackStyle` runs it. */
  fallback: "graticule" | null;
  /** Overrides applied on top of the named flavour, from BRAND.md's palette. */
  palette?: Record<string, string>;
}

export const PMTILES_PATH = "/basemap/basemap.pmtiles";
export const BASEMAP_SOURCE = "protomaps";
export const GLYPHS_URL = "/basemap/fonts/{fontstack}/{range}.pbf";

const OSM_CREDIT =
  '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors · basemap <a href="https://protomaps.com">Protomaps</a>';

/** Ink, Panel, Slate and the deep-cyan ramp from BRAND.md, so the substrate is on-brand. */
const DARK_PALETTE: Record<string, string> = {
  background: "#0B1014",
  earth: "#0E151B",
  water: "#122530",
  boundaries: "#46606E",
  buildings: "#141C23",
  park_a: "#101A1C",
  park_b: "#101A1C",
  wood_a: "#101A1C",
  wood_b: "#101A1C",
  scrub_a: "#111A20",
  scrub_b: "#111A20",
  sand: "#151D22",
  glacier: "#16202A",
  major: "#2C3A44",
  minor_a: "#212C34",
  minor_b: "#1B242B",
  minor_service: "#1B242B",
  other: "#1B242B",
  link: "#2C3A44",
  highway: "#3A4C57",
  railway: "#26333B",
  major_casing_early: "#0E151B",
  highway_casing_early: "#0E151B",
  pier: "#1B242B",
};

/** The grayscale flavour is Protomaps' own data-visualization flavour; this only cools it. */
const LIGHT_PALETTE: Record<string, string> = {
  background: "#E9EEF2",
  earth: "#F2F5F8",
  water: "#D3E0E8",
  boundaries: "#8FA3AF",
  buildings: "#DFE6EB",
  major: "#FFFFFF",
  minor_a: "#FFFFFF",
  minor_b: "#F7F9FA",
  highway: "#FFFFFF",
};

export const BASEMAPS: readonly BasemapDef[] = [
  {
    id: "dark",
    label: "Dark",
    kind: "vector",
    flavor: "dark",
    attribution: OSM_CREDIT,
    fallback: "graticule",
    palette: DARK_PALETTE,
  },
  {
    id: "light",
    label: "Light",
    kind: "vector",
    flavor: "grayscale",
    attribution: OSM_CREDIT,
    fallback: "graticule",
    palette: LIGHT_PALETTE,
  },
  {
    id: "satellite",
    label: "Satellite",
    kind: "raster",
    // ArcGIS MapServer writes y before x. Written any other way, every tile 404s.
    tiles: [
      "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}",
    ],
    maxzoom: 16,
    attribution: "USGS National Map — imagery, public domain",
    fallback: "graticule",
  },
  {
    id: "none",
    label: "None",
    kind: "graticule",
    attribution: "Geometry: ND DMR GIS · one-degree graticule, no basemap",
    fallback: null,
  },
];

export const DEFAULT_BASEMAP = "dark";

/** The four substrates a label, a line or a chrome surface has to stay legible against. */
export const BASEMAP_VARIANTS = ["dark", "light", "satellite", "none"] as const;

export type BasemapVariant = (typeof BASEMAP_VARIANTS)[number];

export function basemapVariant(id: string | undefined): BasemapVariant {
  return BASEMAP_VARIANTS.find((variant) => variant === id) ?? DEFAULT_BASEMAP;
}

/**
 * The seam the rest of the styling hangs off: the active variant is published as
 * `data-basemap` on the document element, so a stylesheet that owns no map code can key on
 * it. Mirrored onto the map container because map.css scopes to the container, not the root.
 */
export function applyBasemapVariant(id: string, container?: HTMLElement): BasemapVariant {
  const variant = basemapVariant(id);
  if (typeof document !== "undefined") document.documentElement.dataset["basemap"] = variant;
  if (container) container.dataset["basemap"] = variant;
  return variant;
}

const BY_ID = new Map(BASEMAPS.map((base) => [base.id, base]));

export function basemapIds(): string[] {
  return BASEMAPS.map((base) => base.id);
}

export function basemapDef(id: string): BasemapDef | undefined {
  return BY_ID.get(id);
}

export function chooseBasemap(search: string = window.location.search): string {
  const requested = new URLSearchParams(search).get("base");
  if (requested && BY_ID.has(requested)) return requested;
  return readGuarded(BASE_STORAGE_KEY, basemapIds()) ?? DEFAULT_BASEMAP;
}

export function rememberBasemap(id: string): void {
  writeGuarded(BASE_STORAGE_KEY, id, basemapIds());
}

export function pmtilesUrl(path: string = PMTILES_PATH): string {
  return `pmtiles://${path}`;
}

export interface StyleOptions {
  /** Font and sprite assets are a separate deploy artifact; without them, no symbol layers. */
  labels: boolean;
  /** MapLibre rejects a relative sprite url outright, so the origin has to be written in. */
  origin?: string;
}

export function vectorStyle(base: BasemapDef, options: StyleOptions): StyleSpecification {
  const flavor = { ...namedFlavor(base.flavor ?? "dark"), ...(base.palette ?? {}) } as Flavor;
  const built = layers(BASEMAP_SOURCE, flavor, { lang: "en" }) as LayerSpecification[];
  const styled = splitBoundaries(
    options.labels ? built : built.filter((layer) => layer.type !== "symbol"),
    flavor,
  );
  const style: StyleSpecification = {
    version: 8,
    sources: {
      [BASEMAP_SOURCE]: { type: "vector", url: pmtilesUrl(), attribution: base.attribution },
    },
    layers: styled,
  };
  // Assigned rather than declared: MapLibre validates a property that is present, so an
  // undefined `glyphs` fails validation and the whole style — every layer — never loads.
  if (options.labels) {
    const origin = options.origin ?? (typeof window === "undefined" ? "" : window.location.origin);
    style.glyphs = GLYPHS_URL;
    style.sprite = `${origin}/basemap/sprites/${base.flavor ?? "dark"}`;
  }
  return style;
}

/**
 * Protomaps draws states and counties as one line at one weight. Upstream readers navigate
 * by county name, so the two get separate weights and the county line becomes a real layer.
 */
function splitBoundaries(built: LayerSpecification[], flavor: Flavor): LayerSpecification[] {
  const colour = String(flavor.boundaries);
  const out: LayerSpecification[] = [];
  for (const layer of built) {
    if (layer.id !== "boundaries") {
      out.push(layer);
      continue;
    }
    out.push({
      id: "gw-boundaries-county",
      type: "line",
      source: BASEMAP_SOURCE,
      "source-layer": "boundaries",
      filter: [">", ["get", "kind_detail"], 4],
      minzoom: 7,
      paint: { "line-color": colour, "line-width": 0.5, "line-opacity": 0.7 },
    });
    out.push({
      id: "gw-boundaries-state",
      type: "line",
      source: BASEMAP_SOURCE,
      "source-layer": "boundaries",
      filter: ["==", ["get", "kind_detail"], 4],
      paint: { "line-color": colour, "line-width": 1.2 },
    });
  }
  return out;
}

export function rasterStyle(base: BasemapDef): StyleSpecification {
  return {
    version: 8,
    sources: {
      // Its own id, not the vector one: a tile error carries `sourceId`, and reusing
      // `protomaps` here made a USGS outage report itself as a Protomaps one (R3.2).
      [base.id]: {
        type: "raster",
        tiles: base.tiles ?? [],
        tileSize: 256,
        maxzoom: base.maxzoom ?? 16,
        attribution: base.attribution,
      },
    },
    layers: [
      { id: "canvas", type: "background", paint: { "background-color": "#0B1014" } },
      { id: base.id, type: "raster", source: base.id },
    ],
  };
}

/** The locator a reader could act on: the host imagery comes from, the path an archive is at. */
export function tileOrigin(base: BasemapDef): string {
  const template = base.tiles?.[0];
  if (!template) return PMTILES_PATH;
  try {
    return new URL(template).host;
  } catch {
    return template; // A template that is not a URL is still the truest name we have for it.
  }
}

/** One tile, fetched to find out whether the origin will serve any at all. */
export function tileProbeUrl(base: BasemapDef): string | null {
  const template = base.tiles?.[0];
  return template ? template.replace(/\{[zxy]\}/g, "0") : null;
}

/** What a MapLibre `sourceId` means to a reader; a data source is already named for one. */
export function sourceLabel(sourceId: string): string {
  if (sourceId === BASEMAP_SOURCE) return PMTILES_PATH;
  const base = basemapDef(sourceId);
  return base ? tileOrigin(base) : sourceId;
}

export interface BasemapFallback {
  style: StyleSpecification;
  failure: { source: string; fallback: string };
}

/**
 * Runs the option's declared fallback, or returns null where none is declared. The graticule
 * is local — no request leaves this origin — so it works under the same policy that refuses
 * a hosted substitute.
 */
export function fallbackStyle(base: BasemapDef): BasemapFallback | null {
  if (base.fallback !== "graticule") return null;
  return { style: graticuleStyle(), failure: { source: tileOrigin(base), fallback: "the graticule" } };
}

/** The no-basemap view is a shipped choice, not the only state: SB-05 §2.1's `?base=none`. */
export function graticuleStyle(): StyleSpecification {
  return {
    version: 8,
    sources: { graticule: { type: "geojson", data: graticule() } },
    layers: [
      { id: "canvas", type: "background", paint: { "background-color": "#0B1014" } },
      {
        id: "graticule",
        type: "line",
        source: "graticule",
        paint: { "line-color": "#1d2a33", "line-width": 1 },
      },
    ],
  };
}

function graticule(): GeoJSON.FeatureCollection {
  const lines: GeoJSON.Feature[] = [];
  for (let lon = -112; lon <= -92; lon += 1) lines.push(line([[lon, 40], [lon, 52]]));
  for (let lat = 40; lat <= 52; lat += 1) lines.push(line([[-112, lat], [-92, lat]]));
  return { type: "FeatureCollection", features: lines };
}

function line(coordinates: [number, number][]): GeoJSON.Feature {
  return { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates } };
}

/**
 * The label layers sit on top of the basemap, so data inserted before the first of them
 * keeps town and county names readable over dense wells (MapLibre `beforeId`).
 */
export function firstLabelLayerId(style: StyleSpecification): string | undefined {
  return style.layers.find((layer) => layer.type === "symbol")?.id;
}
