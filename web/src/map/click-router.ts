import type { MapGeoJSONFeature, MapMouseEvent, Map as MapLibreMap, PointLike } from "maplibre-gl";

/**
 * One map-level click handler with a priority sort, rather than one handler per layer.
 * Per-layer handlers hit-test the exact pixel, so a 1.8 px lateral stroke is effectively
 * unclickable, and a click near a wellhead fires twice — once for the point and once for
 * the line under it.
 */
export const PICK_RADIUS_PX = 6;

const PRIORITY: Readonly<Record<string, number>> = {
  wells: 40,
  "wells-struck": 40,
  // Both of the laterals row's style layers, at one rank: the two never overlap — they are
  // different basins — and one row that selected in North Dakota and did nothing in the
  // Permian would be the toggle contradicting itself.
  // Above the lateral it overlies — the trace is drawn on top, so the click follows the ink —
  // and below the wellhead, which stays the most specific thing under a cursor.
  "survey-traces": 35,
  laterals: 30,
  "tx-laterals": 30,
  "spacing-units-line": 20,
  "spacing-units-fill": 10,
};

export const PICKABLE_LAYERS: string[] = Object.keys(PRIORITY);

export interface Hit {
  layer: { id: string };
  properties: Record<string, unknown>;
}

export function pickBox(point: { x: number; y: number }, radius = PICK_RADIUS_PX): [PointLike, PointLike] {
  return [
    [point.x - radius, point.y - radius],
    [point.x + radius, point.y + radius],
  ];
}

export function topHit<T extends Hit>(hits: readonly T[]): T | null {
  let best: T | null = null;
  let bestRank = -1;
  for (const candidate of hits) {
    const rank = PRIORITY[candidate.layer.id];
    if (rank === undefined || rank <= bestRank) continue;
    best = candidate;
    bestRank = rank;
  }
  return best;
}

export function api10Of(hit: Hit | null): string | null {
  const value = hit?.properties["api10"];
  return typeof value === "string" && value !== "" ? value : null;
}

export interface RouterCallbacks {
  onClick(api10: string, hit: MapGeoJSONFeature): void;
  onHover(hit: MapGeoJSONFeature | null, event: MapMouseEvent): void;
}

/** Returns the layers actually present in the style, so a missing one is not a query error. */
function presentLayers(map: MapLibreMap): string[] {
  return PICKABLE_LAYERS.filter((id) => map.getLayer(id));
}

export function installClickRouter(map: MapLibreMap, callbacks: RouterCallbacks): void {
  const query = (event: MapMouseEvent): MapGeoJSONFeature | null => {
    const layers = presentLayers(map);
    if (layers.length === 0) return null;
    return topHit(map.queryRenderedFeatures(pickBox(event.point), { layers }) as unknown as Hit[]) as
      | MapGeoJSONFeature
      | null;
  };

  map.on("click", (event) => {
    const hit = query(event);
    const api10 = api10Of(hit);
    if (hit && api10) callbacks.onClick(api10, hit);
  });

  map.on("mousemove", (event) => {
    const hit = query(event);
    map.getCanvas().style.cursor = hit ? "pointer" : "";
    callbacks.onHover(hit, event);
  });

  map.on("mouseout", () => {
    map.getCanvas().style.cursor = "";
  });
}
