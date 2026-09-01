/**
 * The declarative layer registry. The layer panel, the pill strip, the legend, the reset
 * and the persisted capability set all read this table — adding a layer is one entry, and
 * nothing downstream keeps a second list to drift against it.
 */
import { LAND_SNAPSHOT, ND_SNAPSHOT, landCellCount, ndCoverage, ndWellCount } from "./coverage.ts";
import { DISPOSAL_COLOUR } from "./disposal.ts";
import { LAYER_FAMILIES, LAYER_GROUPS } from "./groups.ts";
import type { LayerFamily, LayerFamilyId, LayerGroup, LayerGroupId } from "./groups.ts";
import { statusColour } from "./status.ts";
import { BOUNDARY_MIN_ZOOM, GEOLOGY_FRAME_COLOUR, LAND_GRID_COLOUR, TRACE_COLOUR } from "./style.ts";
import { LIQUID_RAMP } from "./thematics.ts";

export type ProvenanceKind = "official" | "derived" | "basemap";

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
  /** Required, so a layer added to the table cannot arrive with no place in the reader's list. */
  group: LayerGroupId;
  /**
   * The nested set this row is a member of, if any. Declared with `familyLabel`, never without:
   * a row inside a family reads by the axis it divides on, because the parent above it already
   * carries the noun.
   */
  family?: LayerFamilyId;
  /** How the row reads under its parent. The state alone, where the family divides by state. */
  familyLabel?: string;
  /** The standalone name, for every surface that meets the row without its parent above it. */
  label: string;
  subtitle: string;
  swatch: LayerSwatch;
  defaultOn: boolean;
  minZoom: number;
  zoomHint?: string;
  opacity: number;
  /**
   * The refresh the counts stated in this row's subtitle were read at, as a handle the
   * panel resolves through the same explain drawer every other figure in the app uses.
   * Omitted where a row's numbers are literals with no snapshot behind them.
   */
  snapshot?: string;
  /** One entry per source the row draws, in draw order. Never empty. */
  provenance: readonly LayerProvenance[];
  /** MapLibre layer ids this row shows and hides. Never empty. */
  styleLayers: string[];
  /** Ascending = drawn first = underneath. The panel lists rows in this order. */
  drawOrder: number;
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
    // EIA and not USGS, for migration 063's reason: EIA publishes the basin/play distinction
    // this repository has to keep, and USGS assessment units slice the same rock for
    // assessment arithmetic. The USGS row this table used to carry is gone rather than
    // shipped disabled — nothing serves an assessment-unit tile to switch on.
    id: "basins",
    group: "geology",
    label: "Basins",
    subtitle:
      "EIA lower-48 basin boundaries · the published outline with the publisher's own area," +
      " rounded and never recomputed (cr_eia_area_provenance_1) · a basin and a play are" +
      " different objects and are drawn from different tiles (cr_eia_boundary_taxonomy_1)",
    swatch: { kind: "outline", colours: [GEOLOGY_FRAME_COLOUR] },
    // The land grid's reasoning at basin scale: a frame drawn unasked over four states reads
    // as structure in the data, and this one covers every well on the canvas.
    defaultOn: false,
    minZoom: BOUNDARY_MIN_ZOOM,
    zoomHint: "Visible at zoom 3 and above; names to zoom 9",
    opacity: 1,
    provenance: [{ kind: "official", source: "marts.basin_boundaries_tile" }],
    styleLayers: ["basins-fill", "basins-line", "basins-label"],
    drawOrder: 1,
    // No served collection lists a boundary: /v1/wells is the spine, and a basin is not on it.
    collection: null,
  },
  {
    id: "plays",
    group: "geology",
    label: "Plays",
    subtitle:
      "EIA lower-48 shale-play outlines · a play sits inside a basin and is never a second" +
      " one (cr_eia_boundary_taxonomy_1) · two rings arrived invalid and were repaired at" +
      " promotion rather than dropped (cr_eia_geometry_repair_1)",
    // The basin's colour, one register down: nested frames of one kind are told apart by
    // weight and dash, and a second hue would claim a difference the taxonomy does not make.
    swatch: { kind: "line", colours: [GEOLOGY_FRAME_COLOUR] },
    defaultOn: false,
    minZoom: BOUNDARY_MIN_ZOOM,
    zoomHint: "Visible at zoom 3 and above",
    opacity: 1,
    provenance: [{ kind: "official", source: "marts.basin_boundaries_tile" }],
    styleLayers: ["plays-line"],
    drawOrder: 2,
    collection: null,
  },
  {
    // M2-3: the Grid Map done honestly — observed rollups binned on the land grid, every
    // cell carrying its support, bins frozen at refresh with a resolvable handle. Which
    // wells belong to a section is cr_land_agg_membership_1, chosen with measured evidence
    // (57.3% of ND liquid volume sits on wells whose lateral midpoint and surface hole are
    // in different sections), never this file's claim.
    id: "land-metrics",
    group: "derived",
    label: "Liquid on the land grid (North Dakota)",
    subtitle:
      "Observed cumulative liquid (oil plus condensate as ND files it) summed per PLSS" +
      ` unit · ${landCellCount()} binned cells · wells assigned by lateral midpoint, else` +
      " surface hole (cr_land_agg_membership_1) · unpainted = nothing observed",
    // Three ramp steps, because the row paints from a binned expression and one amber would
    // promise a canvas the support-modulated wash does not deliver.
    swatch: { kind: "fill", colours: [LIQUID_RAMP[1], LIQUID_RAMP[3], LIQUID_RAMP[5]] },
    // An aggregate wash drawn unasked would read as geology under every dot on the map.
    defaultOn: false,
    minZoom: 5,
    zoomHint: "Townships from zoom 5; sections take over at zoom 10",
    opacity: 1,
    snapshot: LAND_SNAPSHOT.refresh,
    provenance: [{ kind: "derived", source: "marts.land_metrics_tile" }],
    styleLayers: ["land-township-metrics-fill", "land-section-metrics-fill"],
    drawOrder: 5,
    collection: null,
  },
  {
    // Real PLSS geometry, vector and queryable — not a raster picture of a grid. ND slice of
    // the BLM national CadNSDI; the publisher choice and the measured cross-publisher grid
    // divergence are conformance rows (cr_blm_plss_publisher_1), not this file's claim.
    id: "land-grid",
    group: "land",
    label: "PLSS land grid (North Dakota)",
    // Counts as published by BLM (F2): the promoted rows run 10-to-31 lower per the
    // quarantine's duplicate ledger, and the register quotes the publisher it names rather
    // than a number that moves with every re-poll.
    subtitle:
      "BLM CadNSDI townships and sections, clickable geometry · 2,067 townships · " +
      "71,486 sections as published by BLM · ND only",
    swatch: { kind: "line", colours: [LAND_GRID_COLOUR] },
    // Basin-wide reference linework drawn unasked would read as structure in the data.
    defaultOn: false,
    minZoom: 8,
    zoomHint: "Townships at zoom 8 and above; sections from zoom 10",
    opacity: 1,
    provenance: [{ kind: "official", source: "marts.land_units_tile" }],
    styleLayers: ["land-townships-line", "land-sections-line"],
    drawOrder: 6,
    collection: null,
  },
  {
    // Geometry and labels split: the linework at one zoom band, the text two bands finer.
    id: "land-grid-labels",
    group: "land",
    label: "PLSS grid labels (North Dakota)",
    subtitle: "Township-range and section numbers carried on the land grid itself",
    swatch: { kind: "line", colours: [LAND_GRID_COLOUR] },
    defaultOn: false,
    minZoom: 9,
    zoomHint: "Township labels at zoom 9 and above; section numbers from zoom 12",
    opacity: 1,
    provenance: [{ kind: "official", source: "marts.land_units_tile" }],
    styleLayers: ["land-townships-label", "land-sections-label"],
    drawOrder: 8,
    collection: null,
  },
  {
    id: "spacing-units",
    group: "land",
    label: "Spacing units (North Dakota)",
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
    group: "land",
    label: "Spacing-unit labels (North Dakota)",
    subtitle:
      "Township-range description carried on the spacing unit · the surveyed grid itself is" +
      " the PLSS land grid row",
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
    group: "spine",
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
    group: "spine",
    label: "Survey traces (North Dakota)",
    subtitle:
      `The bore path ND filed as MD/INC/AZI/TVD stations · ${ndCoverage(ND_SNAPSHOT.traced)} · ` +
      "confidential wells excluded at source",
    swatch: { kind: "line", colours: [TRACE_COLOUR] },
    // 1.2% coverage drawn by default over 43.8k wells reads as "almost no wells drilled out".
    defaultOn: false,
    // The tiles publish from z4; the map holds the layer to the laterals' gate so the two
    // line layers a reader will compare are never on the canvas at different scales.
    minZoom: 8,
    zoomHint: "Visible at zoom 8 and above",
    opacity: 1,
    snapshot: ND_SNAPSHOT.refresh,
    provenance: [{ kind: "official", source: "marts.nd_survey_traces_tile" }],
    styleLayers: ["survey-traces"],
    drawOrder: 35,
    // Drawn from tiles only; station attributes stay queryable server-side, unserved here.
    collection: null,
  },
  {
    // Deliberately not folded into the laterals row. MBOGC files one path layer covering
    // laterals, sidetracks and vertical wellbores alike, so a row promising horizontal bore
    // geometry would misdescribe 378 of the 4,173 lines — and the geometry is a cartographic
    // centreline in either case, which is the fact the subtitle leads with.
    id: "mt-paths",
    group: "spine",
    label: "Well paths (Montana)",
    subtitle:
      "MBOGC well paths: laterals, sidetracks and wellbores as filed · cartographic" +
      " centrelines averaging 2.8 vertices, never a survey (cr_mt_paths_geometry_class_1) ·" +
      " 2,836 carry one, of the 20,021 Montana wells that ever produced" +
      " (cr_mt_paths_coverage_1) · no length is served for a Montana bore" +
      " (cr_mt_paths_length_scope_1)",
    swatch: { kind: "line", colours: STATUS_KEYED_LINE },
    // 4,173 lines over a state whose wells are mostly plugged is not a first-paint question.
    defaultOn: false,
    // The laterals' own gate, so the two bore-line layers a reader compares are never on the
    // canvas at different scales — the reason survey-traces sits at 8 rather than its tile floor.
    minZoom: 8,
    zoomHint: "Visible at zoom 8 and above",
    opacity: 1,
    provenance: [{ kind: "official", source: "marts.mt_paths_tile" }],
    styleLayers: ["mt-paths"],
    drawOrder: 36,
    // Drawn from tiles only. /v1/wells counts a well's geometry classes, it does not list lines.
    collection: null,
  },
  {
    id: "wells",
    group: "spine",
    family: "wells",
    familyLabel: "North Dakota",
    label: "Wells (North Dakota)",
    subtitle: `ND DMR GIS surface locations · ${ndWellCount()} points · culled by status below zoom 9`,
    swatch: { kind: "dot", colours: ["#3FA55E"] },
    defaultOn: true,
    minZoom: 4,
    zoomHint: "Visible at zoom 4 and above",
    opacity: 1,
    snapshot: ND_SNAPSHOT.refresh,
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
    group: "spine",
    label: "Disposal & injection (North Dakota)",
    subtitle:
      `Wells NDIC types SWD, WI, CO2I, AI, GI, SFI, MWUI or INJP · ${ndCoverage(ND_SNAPSHOT.disposal)} ` +
      "· the well_type code as filed, drawn as a ring over the status dot",
    swatch: { kind: "ring", colours: [DISPOSAL_COLOUR] },
    // 4.5% of the basin drawn unasked would read as emphasis; the class is one panel row away.
    defaultOn: false,
    // The wells tile below z8 keeps one feature per half CSS pixel with no regard for type,
    // so a ring layer down there is a random sample of the class presented as its geography.
    minZoom: 8,
    zoomHint: "Visible at zoom 8 and above",
    opacity: 1,
    snapshot: ND_SNAPSHOT.refresh,
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
    group: "spine",
    family: "wells",
    familyLabel: "Texas",
    label: "Wells (Texas)",
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
    id: "nm-wells",
    group: "spine",
    family: "wells",
    familyLabel: "New Mexico",
    label: "Wells (New Mexico)",
    subtitle:
      "NM OCD well-header surface locations · 141,778 points, ten of the fourteen OCD status " +
      "codes mapped and four documented without an equivalent " +
      "(cr_nm_wellhistory_status_vocab_2)",
    // Active green, narrowly: the mart measures 54,325 active against 50,935 plugged, so the
    // plurality is the only single ink the canvas supports. A dot carries one.
    swatch: { kind: "dot", colours: [statusColour("active")] },
    defaultOn: true,
    minZoom: 4,
    zoomHint: "Visible at zoom 4 and above",
    opacity: 1,
    provenance: [{ kind: "official", source: "marts.nm_wells_tile" }],
    styleLayers: ["nm-wells", "nm-wells-struck"],
    drawOrder: 43,
    // One spine, three tile marts: /v1/wells is state-agnostic, so every row lands on it.
    collection: { dataset: "wells", bbox: "bbox" },
  },
  {
    id: "mt-wells",
    group: "spine",
    family: "wells",
    familyLabel: "Montana",
    label: "Wells (Montana)",
    subtitle:
      "MBOGC surface locations · 42,026 points, 13 of the 19 filed status values mapped and" +
      " the other 6 quarantined rather than defaulted (cr_mt_gis_status_vocab_1) · no basin" +
      " tag: Bakken is 4.6% of Montana (cr_mt_basin_scope_1) · completion year, never a spud",
    // Plugged grey, for Texas's reason rather than by imitation: 63% of Montana's mapped
    // wells are plugged and 3% carry no class, so a green dot would promise a canvas that
    // does not arrive.
    swatch: { kind: "dot", colours: [statusColour("plugged")] },
    defaultOn: true,
    minZoom: 4,
    zoomHint: "Visible at zoom 4 and above",
    opacity: 1,
    provenance: [{ kind: "official", source: "marts.mt_wells_tile" }],
    styleLayers: ["mt-wells", "mt-wells-struck"],
    drawOrder: 44,
    // One spine, four tile marts: /v1/wells is state-agnostic, so every row lands on it.
    collection: { dataset: "wells", bbox: "bbox" },
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

export interface GroupedLayers {
  group: LayerGroup;
  layers: LayerDef[];
}

/** Groups in reading order, each holding its rows in draw order. Empty groups are dropped. */
export function groupedLayers(): GroupedLayers[] {
  return LAYER_GROUPS.map((group) => ({
    group,
    layers: LAYERS.filter((layer) => layer.group === group.id),
  })).filter((entry) => entry.layers.length > 0);
}

/** Tri-state: `null` means this build has no such layer, which is not an error. */
export function layerRowState(id: string, on: ReadonlySet<string>): boolean | null {
  if (!BY_ID.has(id)) return null;
  return on.has(id);
}

export function familyMembers(id: LayerFamilyId): LayerDef[] {
  return LAYERS.filter((layer) => layer.family === id);
}

/**
 * The reader's order inside a group: a family stands where its first member would have, holding
 * its members, and the rows it took are not listed twice. `disposal-wells` therefore moves from
 * between two well rows to below the family — the ring is drawn over the dots and now reads
 * that way, and nothing about the map's own draw order moved.
 */
export type GroupEntry =
  | { kind: "layer"; layer: LayerDef }
  | { kind: "family"; family: LayerFamily; layers: LayerDef[] };

export interface GroupRows {
  group: LayerGroup;
  entries: GroupEntry[];
}

export function groupEntries(): GroupRows[] {
  return groupedLayers().map(({ group, layers }) => {
    const entries: GroupEntry[] = [];
    const placed = new Set<LayerFamilyId>();
    for (const layer of layers) {
      if (!layer.family) {
        entries.push({ kind: "layer", layer });
        continue;
      }
      if (placed.has(layer.family)) continue;
      placed.add(layer.family);
      const family = LAYER_FAMILIES.find((candidate) => candidate.id === layer.family);
      // A member naming a family the taxonomy does not declare stays a row of its own rather
      // than vanishing into a parent that does not exist.
      if (family) entries.push({ kind: "family", family, layers: familyMembers(family.id) });
      else entries.push({ kind: "layer", layer });
    }
    return { group, entries };
  });
}

/**
 * What the parent switch reports: `true` all on, `false` all off, `"mixed"` some. Derived from
 * the members on every render and stored nowhere, which is what lets a set saved before the
 * family existed restore untouched — see persist.ts.
 */
export function familyState(id: LayerFamilyId, on: ReadonlySet<string>): boolean | "mixed" {
  const members = familyMembers(id);
  const drawn = members.filter((layer) => on.has(layer.id)).length;
  if (drawn === 0) return false;
  return drawn === members.length ? true : "mixed";
}
