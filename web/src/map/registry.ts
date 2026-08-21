/**
 * The declarative layer registry. The layer panel, the pill strip, the legend, the reset
 * and the persisted capability set all read this table — adding a layer is one entry, and
 * nothing downstream keeps a second list to drift against it.
 */
export type LayerGroup = "reference" | "wells" | "model";

export type ProvenanceKind = "official" | "derived" | "basemap" | "pending";

export interface LayerSwatch {
  kind: "dot" | "line" | "fill" | "outline";
  colour: string;
}

export interface LayerProvenance {
  kind: ProvenanceKind;
  /** Filled from the tile's own `derivation_id` property once a feature has been seen. */
  derivationId?: string | null;
  source: string;
}

export interface LayerDef {
  id: string;
  group: LayerGroup;
  label: string;
  subtitle: string;
  swatch: LayerSwatch;
  defaultOn: boolean;
  minZoom: number;
  zoomHint?: string;
  opacity: number;
  provenance: LayerProvenance;
  /** MapLibre layer ids this row shows and hides. Empty for a stub. */
  styleLayers: string[];
  /** Ascending = drawn first = underneath. The panel lists rows in this order. */
  drawOrder: number;
  /** True when the source is not ingested yet: the row renders, disabled, and says why. */
  pendingSource?: boolean;
}

export const LAYERS: readonly LayerDef[] = [
  {
    id: "spacing-units",
    group: "reference",
    label: "Spacing units",
    subtitle: "ND DMR drilling-unit polygons · 10,571 units · the unit an operator thinks in",
    swatch: { kind: "outline", colour: "#4B6472" },
    defaultOn: false,
    minZoom: 8,
    zoomHint: "Visible at zoom 8 and above",
    opacity: 0.75,
    provenance: { kind: "official", source: "marts.nd_spacing_units_tile" },
    styleLayers: ["spacing-units-fill", "spacing-units-line"],
    drawOrder: 10,
  },
  {
    id: "plss-labels",
    group: "reference",
    label: "Spacing-unit labels",
    subtitle: "Township-range description carried on the spacing unit · not a PLSS survey grid",
    swatch: { kind: "line", colour: "#9FB0BC" },
    defaultOn: false,
    minZoom: 11,
    zoomHint: "Visible at zoom 11 and above",
    opacity: 1,
    provenance: { kind: "official", source: "marts.nd_spacing_units_tile" },
    styleLayers: ["spacing-units-label"],
    drawOrder: 20,
  },
  {
    id: "laterals",
    group: "wells",
    label: "Laterals",
    subtitle: "ND DMR GIS horizontal bore geometry · 23,228 lines · not a directional survey trace",
    swatch: { kind: "line", colour: "#3FA55E" },
    defaultOn: true,
    minZoom: 0,
    opacity: 1,
    provenance: { kind: "official", source: "marts.nd_laterals_tile" },
    styleLayers: ["laterals"],
    drawOrder: 30,
  },
  {
    id: "tx-laterals",
    group: "wells",
    label: "Laterals (TX)",
    subtitle: "TX RRC well arcs · 69,897 lines · bore geometry, not a directional survey",
    // Not ND's green. Both basins share one status vocabulary and one set of status colours,
    // but a swatch is a prediction about what the canvas will look like, and Texas draws
    // mostly plugged grey: 29% of its wells are plugged and 18% carry no status at all, so a
    // green dot promises a green map and delivers a grey one.
    swatch: { kind: "line", colour: "#7C8B96" },
    defaultOn: true,
    minZoom: 0,
    opacity: 1,
    provenance: { kind: "official", source: "marts.tx_laterals_tile" },
    styleLayers: ["tx-laterals"],
    drawOrder: 32,
  },
  {
    id: "wells",
    group: "wells",
    label: "Wells",
    subtitle: "ND DMR GIS surface locations · 43,817 points · culled by status below zoom 9",
    swatch: { kind: "dot", colour: "#3FA55E" },
    defaultOn: true,
    minZoom: 4,
    zoomHint: "Visible at zoom 4 and above",
    opacity: 1,
    provenance: { kind: "official", source: "marts.nd_wells_tile" },
    styleLayers: ["wells", "wells-struck"],
    drawOrder: 40,
  },
  {
    id: "tx-wells",
    group: "wells",
    label: "Wells (TX)",
    subtitle: "TX RRC GIS surface locations, 55 Permian-district counties · 355,463 points",
    swatch: { kind: "dot", colour: "#7C8B96" },
    defaultOn: true,
    minZoom: 4,
    zoomHint: "Visible at zoom 4 and above",
    opacity: 1,
    provenance: { kind: "official", source: "marts.tx_wells_tile" },
    styleLayers: ["tx-wells", "tx-wells-struck"],
    drawOrder: 42,
  },
  {
    id: "play-outline",
    group: "reference",
    label: "Play outlines",
    subtitle: "EIA shale-play boundaries · no ingest recipe yet, so nothing is drawn",
    swatch: { kind: "outline", colour: "#7C8B96" },
    defaultOn: false,
    minZoom: 0,
    opacity: 1,
    provenance: { kind: "pending", source: "EIA Shale Play Maps — not ingested" },
    styleLayers: [],
    drawOrder: 50,
    pendingSource: true,
  },
  {
    id: "geology-au",
    group: "model",
    label: "Assessment units",
    subtitle: "USGS Williston assessment-unit boundaries · no ingest recipe yet",
    swatch: { kind: "outline", colour: "#7C8B96" },
    defaultOn: false,
    minZoom: 0,
    opacity: 1,
    provenance: { kind: "pending", source: "USGS NOGA assessment units — not ingested" },
    styleLayers: [],
    drawOrder: 60,
    pendingSource: true,
  },
];

const BY_ID = new Map(LAYERS.map((layer) => [layer.id, layer]));

export function layerIds(): string[] {
  return LAYERS.map((layer) => layer.id);
}

export function layerDef(id: string): LayerDef | undefined {
  return BY_ID.get(id);
}

export function defaultLayerSet(): string[] {
  return LAYERS.filter((layer) => layer.defaultOn).map((layer) => layer.id);
}

/** Tri-state: `null` means this build has no such layer, which is not an error. */
export function layerRowState(id: string, on: ReadonlySet<string>): boolean | null {
  if (!BY_ID.has(id)) return null;
  return on.has(id);
}
