/**
 * The declarative layer registry. The layer panel, the pill strip, the legend, the reset
 * and the persisted capability set all read this table — adding a layer is one entry, and
 * nothing downstream keeps a second list to drift against it.
 */
import { ND_SNAPSHOT, ndCoverage, ndWellCount } from "./coverage.ts";
import { DISPOSAL_COLOUR } from "./disposal.ts";
import { statusColour } from "./status.ts";
import { TRACE_COLOUR } from "./style.ts";

export type LayerGroup = "reference" | "wells" | "model";

export type ProvenanceKind = "official" | "derived" | "basemap" | "pending";

export interface LayerSwatch {
  kind: "dot" | "line" | "fill" | "outline" | "ring";
  /** More than one only where the row paints from an expression instead of a fixed colour. */
  colours: readonly [string, ...string[]];
}

export interface LayerProvenance {
  kind: ProvenanceKind;
  /** Filled from the tile's own `derivation_id` property once a feature has been seen. */
  derivationId?: string | null;
  source: string;
  /** The regulator file behind this source. Required where one row draws more than one. */
  label?: string;
}

/**
 * Where §2.6's "what's behind this layer" lands. `bridge.test.ts` checks both members against
 * the committed document, so a renamed dataset or facet reddens rather than drifting into a
 * dead link. A tile mart with no browsable collection declares `null` and says so on the row.
 */
export interface LayerCollection {
  dataset: string;
  /** The query parameter that narrows it to a viewport, where the operation takes one. */
  bbox: string | null;
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
  /** One entry per source the row draws, in draw order. Never empty. */
  provenance: readonly LayerProvenance[];
  /** MapLibre layer ids this row shows and hides. Empty for a stub. */
  styleLayers: string[];
  /** Ascending = drawn first = underneath. The panel lists rows in this order. */
  drawOrder: number;
  /** True when the source is not ingested yet: the row renders, disabled, and says why. */
  pendingSource?: boolean;
  collection: LayerCollection | null;
}

/**
 * Both lateral layers paint from `statusColourExpression()`, so this row has no colour of its
 * own — and the two it replaced each predicted a canvas the other contradicted, ND's green
 * against Texas's grey. What this build measures is the *well* status mix, not the lateral
 * one, so a single colour would be a frequency claim nothing here supports. Two is the claim
 * that holds: the row is keyed to status, and the key beside it names every class.
 */
const STATUS_KEYED_LINE: readonly [string, ...string[]] = [
  statusColour("active"),
  statusColour("plugged"),
];

export const LAYERS: readonly LayerDef[] = [
  {
    id: "spacing-units",
    group: "reference",
    label: "Spacing units",
    subtitle: "ND DMR drilling-unit polygons · 10,571 units · the unit an operator thinks in",
    swatch: { kind: "outline", colours: ["#4B6472"] },
    defaultOn: false,
    minZoom: 8,
    zoomHint: "Visible at zoom 8 and above",
    opacity: 0.75,
    provenance: [{ kind: "official", source: "marts.nd_spacing_units_tile" }],
    styleLayers: ["spacing-units-fill", "spacing-units-line"],
    drawOrder: 10,
    // SB-04 §4.7's /v1/spacingunits is class B — the rail already lists it as not served.
    collection: null,
  },
  {
    id: "plss-labels",
    group: "reference",
    label: "Spacing-unit labels",
    subtitle: "Township-range description carried on the spacing unit · not a PLSS survey grid",
    swatch: { kind: "line", colours: ["#9FB0BC"] },
    defaultOn: false,
    minZoom: 11,
    zoomHint: "Visible at zoom 11 and above",
    opacity: 1,
    provenance: [{ kind: "official", source: "marts.nd_spacing_units_tile" }],
    styleLayers: ["spacing-units-label"],
    drawOrder: 20,
    collection: null,
  },
  {
    // A different capability under a different id, which is the whole migration: a stored set
    // written against `laterals` or `tx-laterals` never knew this row, so it arrives at the
    // default below rather than inheriting a bit about a layer that drew one state at z0.
    id: "lateral-bores",
    group: "wells",
    label: "Laterals",
    subtitle: "Horizontal bore geometry as each regulator filed it · not a directional survey trace",
    swatch: { kind: "line", colours: STATUS_KEYED_LINE },
    // 93,125 lines is the largest thing the map can draw and the reader never asked for it.
    defaultOn: false,
    // marts/tiles.py holds THIN_MAX_ZOOM at 7: at and below it a lateral tile keeps one feature
    // per half CSS pixel, so the layer down there is a sample of itself. z8 is the lowest zoom
    // that serves every lateral in view, and the lowest at which one is longer than the 6 px
    // the click router picks with. The z7 tile it stops fetching measured 2,037,023 B.
    minZoom: 8,
    zoomHint: "Visible at zoom 8 and above",
    opacity: 1,
    provenance: [
      { kind: "official", source: "marts.nd_laterals_tile", label: "ND DMR GIS · 23,228 lines" },
      { kind: "official", source: "marts.tx_laterals_tile", label: "TX RRC arcs · 69,897 lines" },
    ],
    styleLayers: ["laterals", "tx-laterals"],
    drawOrder: 30,
    // The bore geometry is drawn from two tile marts and is carried by no served collection:
    // /v1/wells counts a well's laterals, it does not list the lines.
    collection: null,
  },
  {
    // The other half of the laterals row's "not a directional survey trace": this is the one
    // that is. Coverage is stated on the row because a trace is absent 98.8% of the time,
    // absence here is not "no lateral", and the hole has a reason the subtitle names.
    id: "survey-traces",
    group: "wells",
    label: "Survey traces (ND)",
    subtitle:
      `The bore path ND filed as MD/INC/AZI/TVD stations · ${ndCoverage(ND_SNAPSHOT.traced)} — ` +
      "confidential wells excluded at source",
    swatch: { kind: "line", colours: [TRACE_COLOUR] },
    // 1.2% coverage drawn by default over 43.8k wells reads as "almost no wells drilled out".
    defaultOn: false,
    // The tiles publish from z4; the map holds the layer to the laterals' gate so the two
    // line layers a reader will compare are never on the canvas at different scales.
    minZoom: 8,
    zoomHint: "Visible at zoom 8 and above",
    opacity: 1,
    provenance: [{ kind: "official", source: "marts.nd_survey_traces_tile" }],
    styleLayers: ["survey-traces"],
    drawOrder: 35,
    // Drawn from tiles only; station attributes stay queryable server-side, unserved here.
    collection: null,
  },
  {
    id: "wells",
    group: "wells",
    label: "Wells",
    subtitle: `ND DMR GIS surface locations · ${ndWellCount()} points · culled by status below zoom 9`,
    swatch: { kind: "dot", colours: ["#3FA55E"] },
    defaultOn: true,
    minZoom: 4,
    zoomHint: "Visible at zoom 4 and above",
    opacity: 1,
    provenance: [{ kind: "official", source: "marts.nd_wells_tile" }],
    styleLayers: ["wells", "wells-struck"],
    drawOrder: 40,
    collection: { dataset: "wells", bbox: "bbox" },
  },
  {
    // A well_type fact from the regulator, not an interpretation: the ring marks the wells
    // NDIC itself types as injection class, over the status dot the wells row still draws.
    // The membership is a conformance row, not this file's — see disposal.ts.
    id: "disposal-wells",
    group: "wells",
    label: "Disposal & injection (ND)",
    subtitle:
      `Wells NDIC types SWD, WI, CO2I, AI, GI, SFI, MWUI or INJP · ${ndCoverage(ND_SNAPSHOT.disposal)} ` +
      "— the well_type code as filed, drawn as a ring over the status dot",
    swatch: { kind: "ring", colours: [DISPOSAL_COLOUR] },
    // 4.5% of the basin drawn unasked would read as emphasis; the class is one panel row away.
    defaultOn: false,
    // The wells tile below z8 keeps one feature per half CSS pixel with no regard for type,
    // so a ring layer down there is a random sample of the class presented as its geography.
    minZoom: 8,
    zoomHint: "Visible at zoom 8 and above",
    opacity: 1,
    provenance: [{ kind: "official", source: "marts.nd_wells_tile" }],
    styleLayers: ["disposal-wells"],
    drawOrder: 41,
    // The same spine the wells rows land on. /v1/wells takes no well-type predicate yet, so
    // the crossing narrows by the box alone, exactly as it does for the status filter — the
    // missing predicate is a recorded seam (work-output/m17-status.md), not a silent claim.
    collection: { dataset: "wells", bbox: "bbox" },
  },
  {
    id: "tx-wells",
    group: "wells",
    label: "Wells (TX)",
    subtitle: "TX RRC GIS surface locations, 55 Permian-district counties · 355,463 points",
    // Not ND's green. Both basins share one status vocabulary and one set of status colours,
    // but a swatch is a prediction about what the canvas will look like, and Texas draws
    // mostly plugged grey: 29% of its wells are plugged and 18% carry no status at all, so a
    // green dot promises a green map and delivers a grey one.
    swatch: { kind: "dot", colours: ["#7C8B96"] },
    defaultOn: true,
    minZoom: 4,
    zoomHint: "Visible at zoom 4 and above",
    opacity: 1,
    provenance: [{ kind: "official", source: "marts.tx_wells_tile" }],
    styleLayers: ["tx-wells", "tx-wells-struck"],
    drawOrder: 42,
    // One spine, two tile marts: /v1/wells is state-agnostic, so both rows land on it.
    collection: { dataset: "wells", bbox: "bbox" },
  },
  {
    id: "play-outline",
    group: "reference",
    label: "Play outlines",
    subtitle: "EIA shale-play boundaries · no ingest recipe yet, so nothing is drawn",
    swatch: { kind: "outline", colours: ["#7C8B96"] },
    defaultOn: false,
    minZoom: 0,
    opacity: 1,
    provenance: [{ kind: "pending", source: "EIA Shale Play Maps — not ingested" }],
    styleLayers: [],
    drawOrder: 50,
    pendingSource: true,
    collection: null,
  },
  {
    id: "geology-au",
    group: "model",
    label: "Assessment units",
    subtitle: "USGS Williston assessment-unit boundaries · no ingest recipe yet",
    swatch: { kind: "outline", colours: ["#7C8B96"] },
    defaultOn: false,
    minZoom: 0,
    opacity: 1,
    provenance: [{ kind: "pending", source: "USGS NOGA assessment units — not ingested" }],
    styleLayers: [],
    drawOrder: 60,
    pendingSource: true,
    collection: null,
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
