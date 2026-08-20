import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import { authHeaders, tileUrl } from "../api/client.ts";
import type { Viewport } from "../app/state.ts";

// martin publishes one source id per table and the MVT layer inside carries that id. The
// running service auto-publishes, so the ids are overridable without a rebuild.
const LATERALS = new URLSearchParams(window.location.search).get("laterals") ?? "nd_laterals";
const WELLS = new URLSearchParams(window.location.search).get("wells") ?? "nd_wells";

const STATUS_COLOURS: [string, string][] = [
  ["active", "#3FA55E"],
  ["producing", "#3FA55E"],
  ["inactive", "#E4A33C"],
  ["plugged", "#D9534F"],
  ["permitted", "#5FD3E8"],
  ["drilling", "#5FD3E8"],
  ["confidential", "#9FB0BC"],
];

const STATUS_EXPRESSION = [
  "match",
  ["downcase", ["coalesce", ["get", "status_canonical"], "unknown"]],
  ...STATUS_COLOURS.flat(),
  "#7C8B96",
];

export interface MapCallbacks {
  onSelect(api10: string): void;
  onViewport(viewport: Viewport): void;
}

export interface MapHandle {
  select(api10: string | null): void;
  flyTo(point: { lon: number; lat: number }): void;
}

export function createMap(
  container: HTMLElement,
  viewport: Viewport,
  callbacks: MapCallbacks,
): MapHandle {
  const map = new maplibregl.Map({
    container,
    style: baseStyle(),
    center: [viewport.lon, viewport.lat],
    zoom: viewport.zoom,
    attributionControl: false,
    transformRequest: (url, resourceType) => {
      if (resourceType === "Tile" && url.includes("/v1/tiles/")) {
        return { url, headers: authHeaders() };
      }
      return { url };
    },
  });

  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  map.addControl(
    new maplibregl.AttributionControl({
      customAttribution: "Geometry: ND DMR GIS · no basemap (SB-05 §2.1 graticule view)",
    }),
    "bottom-right",
  );

  map.on("load", () => {
    map.addSource("nd_laterals", {
      type: "vector",
      tiles: [absolute(tileUrl(LATERALS))],
      minzoom: 0,
      maxzoom: 14,
    });
    map.addSource("nd_wells", {
      type: "vector",
      tiles: [absolute(tileUrl(WELLS))],
      minzoom: 0,
      maxzoom: 14,
    });

    map.addLayer({
      id: "laterals",
      type: "line",
      source: "nd_laterals",
      "source-layer": LATERALS,
      paint: {
        "line-color": STATUS_EXPRESSION as maplibregl.DataDrivenPropertyValueSpecification<string>,
        "line-width": ["interpolate", ["linear"], ["zoom"], 6, 0.6, 10, 1.8, 14, 3],
      },
    });
    map.addLayer({
      id: "laterals-selected",
      type: "line",
      source: "nd_laterals",
      "source-layer": LATERALS,
      filter: ["==", ["get", "api10"], ""],
      paint: { "line-color": "#5FD3E8", "line-width": 4, "line-opacity": 0.9 },
    });
    map.addLayer({
      id: "wells",
      type: "circle",
      source: "nd_wells",
      "source-layer": WELLS,
      minzoom: 9,
      paint: {
        "circle-color": STATUS_EXPRESSION as maplibregl.DataDrivenPropertyValueSpecification<string>,
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, 2, 14, 6],
        "circle-stroke-color": "#0B1014",
        "circle-stroke-width": 0.5,
      },
    });
    map.addLayer({
      id: "wells-selected",
      type: "circle",
      source: "nd_wells",
      "source-layer": WELLS,
      minzoom: 9,
      filter: ["==", ["get", "api10"], ""],
      paint: {
        "circle-color": "#5FD3E8",
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, 4, 14, 9],
      },
    });

    for (const layer of ["laterals", "wells"]) {
      map.on("click", layer, (event) => {
        const api10 = event.features?.[0]?.properties?.["api10"];
        if (typeof api10 === "string" && api10 !== "") callbacks.onSelect(api10);
      });
      map.on("mouseenter", layer, () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", layer, () => {
        map.getCanvas().style.cursor = "";
      });
    }
  });

  map.on("moveend", () => {
    const centre = map.getCenter();
    callbacks.onViewport({ zoom: map.getZoom(), lat: centre.lat, lon: centre.lng });
  });

  return {
    select(api10: string | null) {
      const filter: maplibregl.FilterSpecification = ["==", ["get", "api10"], api10 ?? ""];
      for (const layer of ["laterals-selected", "wells-selected"]) {
        if (map.getLayer(layer)) map.setFilter(layer, filter);
      }
    },
    flyTo(point) {
      map.flyTo({ center: [point.lon, point.lat], zoom: Math.max(map.getZoom(), 11) });
    },
  };
}

/** M12: no third-party basemap. A graticule and the well geometry are the whole reference. */
function baseStyle(): maplibregl.StyleSpecification {
  return {
    version: 8,
    glyphs: undefined,
    sources: {
      graticule: { type: "geojson", data: graticule() },
    },
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
  for (let lon = -112; lon <= -92; lon += 1) {
    lines.push(line([[lon, 40], [lon, 52]]));
  }
  for (let lat = 40; lat <= 52; lat += 1) {
    lines.push(line([[-112, lat], [-92, lat]]));
  }
  return { type: "FeatureCollection", features: lines };
}

function line(coordinates: [number, number][]): GeoJSON.Feature {
  return {
    type: "Feature",
    properties: {},
    geometry: { type: "LineString", coordinates },
  };
}

function absolute(path: string): string {
  return new URL(path, window.location.origin).toString();
}

export function layerLegend(): HTMLElement {
  const element = document.createElement("div");
  element.className = "gw-legend";
  const heading = document.createElement("h4");
  heading.textContent = "Status";
  element.appendChild(heading);
  for (const [status, colour] of STATUS_COLOURS) {
    const row = document.createElement("p");
    const swatch = document.createElement("span");
    swatch.className = "gw-swatch";
    swatch.style.background = colour;
    row.appendChild(swatch);
    row.appendChild(document.createTextNode(status));
    element.appendChild(row);
  }
  const note = document.createElement("p");
  note.className = "gw-legend-note";
  note.textContent = "No basemap: the graticule and the well geometry are the reference.";
  element.appendChild(note);
  return element;
}
