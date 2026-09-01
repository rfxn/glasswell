import type { MapGeoJSONFeature, MapMouseEvent, Map as MapLibreMap, PointLike } from "maplibre-gl";

/**
 * One map-level click handler with a priority sort, rather than one handler per layer.
 * Per-layer handlers hit-test the exact pixel, so a 1.8 px lateral stroke is effectively
 * unclickable, and a click near a wellhead fires twice — once for the point and once for
 * the line under it.
 */
export const PICK_RADIUS_PX = 6;

const PRIORITY: Readonly<Record<string, number>> = {
  // Above the wellhead it rings: the ink on top, and the pickable mark when the wells row
  // is off. Both hits carry the same api10, so the rank never changes what is selected.
  "disposal-wells": 41,
  // Texas at North Dakota's rank, for the laterals' reason: the two basins never overlap,
  // and TX dots absent from this map were genuinely unpickable — topHit returned null over
  // 355,463 points (gate-m17 R-5, pre-existing on every build since the TX layers landed).
  wells: 40,
  "wells-struck": 40,
  "tx-wells": 40,
  "tx-wells-struck": 40,
  // New Mexico at the same rank and for the same reason, struck sibling included: its class
  // is resolved from the registry at read time, so the strike now has a class to match.
  "nm-wells": 40,
  "nm-wells-struck": 40,
  // Montana at the same rank, and it does have a struck sibling: it has a status codebook.
  "mt-wells": 40,
  "mt-wells-struck": 40,
  // Both of the laterals row's style layers, at one rank: the two never overlap — they are
  // different basins — and one row that selected in North Dakota and did nothing in the
  // Permian would be the toggle contradicting itself.
  // Above the lateral it overlies — the trace is drawn on top, so the click follows the ink —
  // and below the wellhead, which stays the most specific thing under a cursor.
  "survey-traces": 35,
  laterals: 30,
  "tx-laterals": 30,
  // At the lateral rank and not the trace's: a map stick is filed bore geometry, not a
  // survey, and ranking it above the laterals would say the opposite (cr_mt_paths_geometry_class_1).
  "mt-paths": 30,
  "spacing-units-line": 20,
  "spacing-units-fill": 10,
  // Under the spacing unit that overlies them: an aggregate is the context a reader falls
  // through to, never what intercepts a mark. Hover-only in practice — a cell carries no
  // api10, so a click resolves nothing, exactly like the spacing fill (M2-3).
  "land-section-metrics-fill": 8,
  "land-township-metrics-fill": 6,
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
