import "./card.css";
import "./gw-figure.ts";

import { ApiError, getEnvelope } from "../api/client.ts";
import { derivationFor, labelFor, unwrap } from "../api/envelope.ts";
import type { Envelope, Figure, Links } from "../api/envelope.ts";
import { readState } from "../app/state.ts";
import { toChartSeries } from "../chart/series.ts";
import type { ProductionData } from "../chart/series.ts";
import { EXPLAIN_EVENT, explainHandle } from "../chrome/handle.ts";
import { emptyState, scopeLine, unbreakable, warningNotes } from "../chrome/notes.ts";
import { focusPanel } from "../chrome/overlays.ts";
import { crossingLink, openThisSeries, rowsForThisWell } from "../explore/bridge.ts";
import { labelElement } from "../glossary/gw-term.ts";
import { highlight } from "../glossary/index.ts";
import { termIndex } from "../glossary/store.ts";
import {
  absentValue,
  formatMonth,
  formatValue,
  formatVintage,
  nullSemantics,
  roundTo,
} from "./format.ts";
import { cardQuery } from "./requests.ts";
import { renderBasin } from "./basin.ts";
import type { WellBasin } from "./basin.ts";
import { renderIdentity } from "./identity.ts";
import type { WellIdentity } from "./identity.ts";
import {
  SECTION_OPEN_EVENT,
  applySection,
  mountSections,
  sectionLink,
  sectionsSettled,
} from "./sections.ts";
import type { SectionSpec } from "./sections.ts";

export interface WellDetail {
  api10: string;
  api14: string | null;
  well_name: string | null;
  operator_name_reported: string | null;
  status_canonical: string | null;
  status_reported: string | null;
  county_code_at_permit: string | null;
  land_unit_label: string | null;
  spud_date: string | null;
  confidential_flag: boolean;
  basin: string | null;
  lateral_count: number;
  lateral_length_ft: Figure | null;
  total_depth_ft: Figure | null;
  completion_date: string | null;
  compute_crs: string | null;
  storage_crs: string;
  effective_from: string;
  surface_point: { lon: number; lat: number } | null;
  ndic_file_no: string | null;
  well_type_reported: string | null;
  length_method: string | null;
  /** Why no neighbour context is offered, where the jurisdiction registers laterals but the
   *  neighbour mart's measured domain does not reach it. Null where neighbours are served. */
  neighbors_reason: string | null;
}

export interface CompletionEvent {
  event_id: string;
  event_kind: string;
  job_start_date: string | null;
  completion_date: string;
  source_id: string;
  report_vintage: string;
  _lineage: Record<string, string>;
}

export interface CompletionPool {
  completion_key: string;
  well_completion_pool: string;
  pool_reported: string | null;
  formation: string | null;
  formation_group: string | null;
  formation_null_semantics: "mapped" | "pool_not_reported" | "alias_unavailable";
  source_id: string;
  first_production_month: string | null;
  last_production_month: string | null;
  effective_from: string | null;
  latest_report_vintage: string;
  _lineage: Record<string, string>;
}

export interface CompletionDesign {
  disclosure_id: string;
  base_water_volume: Figure | null;
  base_water_null_semantics: string;
  lateral_length_ft: Figure | null;
  fluid_intensity: Figure | null;
  intensity_null_semantics: string;
  source_id: string;
  report_vintage: string;
}

export interface CompletionContext {
  api10: string;
  /** A statement about the release, not about this well; per-well absence is `design`. */
  design_availability: string;
  design: CompletionDesign | null;
  design_null_semantics: string;
  events: CompletionEvent[];
  pools: CompletionPool[];
}

export interface StreamCoverage {
  months_reported: number;
  months_reported_zero: number;
  months_no_report: number;
  months_withheld: number;
  span_months: number;
  first_month: string | null;
  last_month: string | null;
  coverage_complete: boolean;
}

export interface CumulativeAllocation {
  basis: string;
  model_id: string | null;
  rule_id: string;
  months: Record<string, Figure>;
  share: Record<string, Figure>;
  shares_counted: Figure | null;
}

export interface WellCumulatives {
  api10: string;
  granularity: string;
  snapshot_vintage: string;
  coverage_outcome: string;
  cumulative: { oil_bbl: Figure | null; gas_mcf: Figure | null; water_bbl: Figure | null } | null;
  coverage: Record<string, StreamCoverage> & { _lineage: Record<string, string> };
  months_withheld: Figure;
  /** Present only where allocated months contribute to the totals beside it. */
  allocation?: CumulativeAllocation | null;
}

export interface CardCallbacks {
  onExplain(handle: string): void;
  onClose(): void;
  onSignIn?(): void;
  onLocated?(point: { lon: number; lat: number }): void;
  onVintage?(resolved: string | null): void;
}

/**
 * Three bands below the identity block, in the order an engineer reads a well: where it is,
 * what was drilled, and which reading of the record this is. The operator used to be a fourth
 * band — a heading and a rule for one datum — and now rides in the header beside the name.
 */
const FACT_GROUPS: { title: string; fields: [keyof WellDetail, string, string][] }[] = [
  {
    title: "Location",
    fields: [
      ["county_code_at_permit", "County", "/county_code_at_permit"],
    ],
  },
  {
    // No `well_type_reported` here: the Identity section renders it as `<code> · as <regulator>
    // filed it`, and §2.3 replaces the bare code rather than printing both five rows apart.
    title: "Drilling",
    fields: [["spud_date", "Spud", "/spud_date"]],
  },
  { title: "Record", fields: [] },
];

// The newest card's own re-count, and the one listener that calls it.
let recountLineage: (() => void) | null = null;
let recounting = false;

export async function renderWellCard(
  container: HTMLElement,
  api10: string,
  callbacks: CardCallbacks,
): Promise<void> {
  container.replaceChildren(placeholder(`Loading well ${api10}…`));
  container.hidden = false;
  const state = readState();
  // Every request this card makes carries the same bag, built in one place. It used to pick
  // `as_of` out by name and forward nothing else, so a brushed window and a normalisation
  // basis had no route from the URL into the request that would have to answer for them.
  const query = cardQuery(state);

  let well: Envelope<WellDetail>;
  try {
    well = await getEnvelope<WellDetail>(`/v1/wells/${api10}`, query);
  } catch (error) {
    container.replaceChildren(errorPanel(error, callbacks));
    return;
  }

  const detail = unwrap(well);
  const card = document.createElement("article");
  card.className = "gw-card";
  card.addEventListener(EXPLAIN_EVENT, (event) => {
    event.stopPropagation();
    callbacks.onExplain((event as CustomEvent<{ handle: string }>).detail.handle);
  });

  const header = document.createElement("header");
  header.className = "gw-panel-head";
  const heading = document.createElement("h2");
  heading.tabIndex = -1;
  heading.textContent = detail.well_name ?? detail.api10;
  header.appendChild(heading);

  const api = document.createElement("p");
  api.className = "gw-card-api";
  api.appendChild(labelElement("API-10", labelFor(well, "/api10")));
  const apiValue = document.createElement("span");
  apiValue.setAttribute("data-no-glossary", "");
  apiValue.textContent = ` ${detail.api10}`;
  api.appendChild(apiValue);
  // The 14 is the join key a reader pastes elsewhere, and it was served but never shown. It
  // rides the same line at half emphasis rather than taking a fact row of its own.
  if (detail.api14 && detail.api14 !== detail.api10) {
    const api14 = document.createElement("span");
    api14.className = "gw-card-api14";
    api14.setAttribute("data-no-glossary", "");
    api14.title = "API-14";
    api14.textContent = detail.api14;
    api.append(" ", api14);
  }
  header.appendChild(api);

  // The same glyph grammar the map paints the well with, so the dot a reader clicked and the
  // chip they land on are one mark. The reported code rides beside the canonical class: the
  // card showed only the class, which hid the mapping rather than making it readable. The slot
  // is placed now and filled after the import, so the chip cannot land out of order.
  const statusSlot = document.createElement("p");
  statusSlot.className = "gw-card-status";
  statusSlot.hidden = true;
  header.appendChild(statusSlot);
  const statusTerm = labelFor(well, "/status_canonical");
  const statusRequest = detail.status_canonical
    ? import("./status-chip.ts").then(({ fillStatusChip }) =>
        fillStatusChip(statusSlot, detail, statusTerm),
      )
    : Promise.resolve();

  // Who holds the well is identity, not a fact row: a band heading and a hairline for one
  // datum cost more vertical room than the datum, and it was the first thing a reader looked
  // for. Confidential rides beside it because it qualifies who is allowed to have reported.
  if (detail.operator_name_reported || detail.confidential_flag) {
    const operatorLine = document.createElement("p");
    operatorLine.className = "gw-card-operator";
    if (detail.operator_name_reported) {
      operatorLine.appendChild(
        labelElement(detail.operator_name_reported, labelFor(well, "/operator_name_reported")),
      );
    }
    if (detail.confidential_flag) {
      const chip = document.createElement("span");
      chip.className = "gw-card-confidential";
      chip.title = "Withheld by the regulator";
      chip.appendChild(labelElement("confidential", labelFor(well, "/confidential_flag")));
      operatorLine.append(" ", chip);
    }
    header.appendChild(operatorLine);
  }

  // SB-08 §2.6 row 1, after the api10 line and ahead of the close button: the crossing
  // reads as part of the identity block rather than as one more control in the corner.
  const rows = rowsForThisWell(detail.api10, {
    state,
    resolved: well.meta.as_of.resolved,
  });
  if (rows) header.appendChild(crossingLink(rows));

  const close = document.createElement("button");
  close.type = "button";
  close.className = "gw-close";
  close.setAttribute("aria-label", "Close the well card");
  close.textContent = "×";
  close.addEventListener("click", callbacks.onClose);
  header.appendChild(close);
  card.appendChild(header);

  // Head fixed, body scrolling: the shell is capped in CSS and only this child overflows.
  const body = document.createElement("div");
  body.className = "gw-panel-body";
  card.appendChild(body);

  const bands = new Map<string, HTMLDListElement>();
  for (const { title, fields } of FACT_GROUPS) {
    const facts = document.createElement("dl");
    facts.className = "gw-facts";
    for (const [field, label, pointer] of fields) {
      const value = detail[field];
      if (value === null || value === undefined || value === "") continue;
      facts.appendChild(term(label, labelFor(well, pointer)));
      const definition = document.createElement("dd");
      definition.textContent = String(value);
      facts.appendChild(definition);
    }
    bands.set(title, facts);
  }
  const location = bands.get("Location")!;
  const drilling = bands.get("Drilling")!;
  const record = bands.get("Record")!;

  // Served since the spine landed and never drawn. The surface hole is the coordinate a
  // reader copies into anything else they own, so it belongs beside the land unit.
  if (detail.surface_point) {
    location.appendChild(term("Surface", labelFor(well, "/surface_point")));
    const definition = document.createElement("dd");
    definition.setAttribute("data-no-glossary", "");
    definition.className = "gw-fact-mono";
    definition.textContent = `${detail.surface_point.lat.toFixed(5)}, ${detail.surface_point.lon.toFixed(5)}`;
    location.appendChild(definition);
  }

  if (detail.completion_date) {
    drilling.appendChild(term("Completed", null));
    const definition = document.createElement("dd");
    definition.setAttribute("data-no-glossary", "");
    definition.textContent = formatVintage(detail.completion_date);
    drilling.appendChild(definition);
  }
  drilling.appendChild(term("Laterals", null));
  const laterals = document.createElement("dd");
  laterals.textContent = String(detail.lateral_count);
  drilling.appendChild(laterals);

  if (detail.lateral_length_ft) {
    drilling.appendChild(term("Lateral length", labelFor(well, "/lateral_length_ft")));
    const definition = document.createElement("dd");
    definition.appendChild(
      figureElement(detail.lateral_length_ft, "lateral length", derivationFor(detail, "/lateral_length_ft")),
    );
    // How the length was measured qualifies the figure; it is not a row of its own.
    if (detail.length_method) {
      const method = document.createElement("span");
      method.className = "gw-fact-qualifier";
      method.appendChild(labelElement(detail.length_method, labelFor(well, "/length_method")));
      definition.append(" ", method);
    }
    drilling.appendChild(definition);
  }

  if (detail.total_depth_ft) {
    drilling.appendChild(term("Total depth", labelFor(well, "/total_depth_ft")));
    const definition = document.createElement("dd");
    definition.appendChild(
      figureElement(detail.total_depth_ft, "total depth", derivationFor(detail, "/total_depth_ft")),
    );
    drilling.appendChild(definition);
  }

  record.appendChild(term("As of", null));
  const asOfValue = document.createElement("dd");
  asOfValue.setAttribute("data-no-glossary", "");
  asOfValue.textContent = `${formatVintage(well.meta.as_of.resolved)} · asked ${well.meta.as_of.requested}`;
  record.appendChild(asOfValue);
  callbacks.onVintage?.(well.meta.as_of.resolved);
  if (detail.surface_point) callbacks.onLocated?.(detail.surface_point);

  // The regulator's own file number: the identifier an operator quotes back on the phone,
  // and the one a reader needs to reach the source filing.
  if (detail.ndic_file_no) {
    record.appendChild(term("NDIC file", labelFor(well, "/ndic_file_no")));
    const definition = document.createElement("dd");
    definition.setAttribute("data-no-glossary", "");
    definition.className = "gw-fact-mono";
    definition.textContent = detail.ndic_file_no;
    record.appendChild(definition);
  }

  if (detail.compute_crs) {
    record.appendChild(term("CRS", labelFor(well, "/compute_crs")));
    const definition = document.createElement("dd");
    definition.setAttribute("data-no-glossary", "");
    definition.className = "gw-fact-mono";
    definition.textContent = `${detail.compute_crs} · stored ${detail.storage_crs}`;
    record.appendChild(definition);
  }

  // Ten named sections in one order, three of them expanded. The order is the order an
  // engineer reads a well; the split is that a section is expanded when its content is why a
  // reader opens a well, and collapsed when it is why they open this particular one. The
  // frames are built first and handed to their sections, so the order cannot drift with which
  // response lands first.
  const cumulativeSlot = document.createElement("div");
  const factsSlot = document.createElement("div");
  factsSlot.className = "gw-card-facts";
  const contextSlot = document.createElement("div");
  const neighborSlot = document.createElement("div");
  const notesSlot = document.createElement("div");
  notesSlot.className = "gw-notes gw-card-notes";

  const chartFrame = document.createElement("section");
  chartFrame.className = "gw-card-chart gw-production-chart";
  const chartHost = document.createElement("div");
  chartHost.className = "gw-frame-body";
  chartHost.appendChild(placeholder("Loading production…"));
  // The chart owns .gw-frame-body and replaces it on every span change and theme repaint, so
  // the series' warnings — R8's disclosure of the derivations behind a column — sit beside it.
  const chartNotes = document.createElement("div");
  chartNotes.className = "gw-chart-notes gw-notes";
  chartFrame.append(chartHost, chartNotes);

  // A band whose every field was absent is a heading over nothing: dropped, not left standing.
  for (const { title } of FACT_GROUPS) {
    const facts = bands.get(title)!;
    if (facts.childElementCount === 0) continue;
    const band = document.createElement("section");
    band.className = "gw-facts-band";
    const heading = document.createElement("h3");
    heading.className = "gw-frame-title";
    heading.textContent = title;
    band.append(heading, facts);
    factsSlot.appendChild(band);
  }

  // Everything except the codes a dedicated panel already renders, or the card shows the raw
  // internal warning line immediately above the polished version of the same sentence.
  const panelled = new Set([PENDING_ALLOCATION]);
  const generic = well.meta.warnings.filter((warning) => !panelled.has(warning.code));
  for (const note of warningNotes(generic)) notesSlot.appendChild(note);

  const contextFrame = document.createElement("section");
  contextFrame.className = "gw-card-chart gw-completion-context";
  const contextHost = document.createElement("div");
  contextHost.className = "gw-frame-body";
  contextHost.dataset["state"] = "loading";
  contextHost.setAttribute("aria-busy", "true");
  contextHost.setAttribute("aria-live", "polite");
  contextHost.appendChild(placeholder("Loading completions…"));
  contextFrame.append(contextHost);
  contextSlot.appendChild(contextFrame);

  const loadContext = (): Promise<void> => loadCompletionContext(
    contextHost,
    well.links?.["completions"] ?? `/v1/wells/${api10}/completions`,
    api10,
    query,
    // Said once per card, and only for the two codes that say it twice. The header and the
    // completion design are two surfaces and both rightly disclose a withheld length, but on
    // one screen the reader gets the sentence under two headings and reads the second as a
    // second problem. Narrow on purpose: keyed on `code` alone this swallowed any warning the
    // two envelopes happened to share, whatever it said. The intensity consequence is not
    // lost with it — the design panel prints it beside the null figure, from
    // `intensity_null_semantics`, which is a better place for it than a note.
    new Set(
      well.meta.warnings
        .map((warning) => warning.code)
        .filter((code) => SAID_ONCE_PER_CARD.has(code)),
    ),
  );

  // Absent outside the mart's states: the API declines to offer a link it would 404, and a
  // section headed "no cumulative" would say the well produced nothing rather than that this
  // jurisdiction is not summed here.
  let loadCumulative: (() => Promise<void>) | undefined;
  const cumulativePath = well.links?.["cumulatives"];
  if (cumulativePath) {
    const cumulativeFrame = document.createElement("section");
    cumulativeFrame.className = "gw-card-chart gw-well-cumulatives";
    const cumulativeHost = document.createElement("div");
    cumulativeHost.className = "gw-frame-body";
    cumulativeHost.dataset["state"] = "loading";
    cumulativeHost.setAttribute("aria-busy", "true");
    cumulativeHost.setAttribute("aria-live", "polite");
    cumulativeHost.appendChild(placeholder("Loading cumulative…"));
    cumulativeFrame.append(cumulativeHost);
    cumulativeSlot.appendChild(cumulativeFrame);
    loadCumulative = (): Promise<void> =>
      loadWellCumulatives(cumulativeHost, cumulativePath, api10, query);
  }

  let loadNeighbours: (() => Promise<void>) | undefined;
  const neighborPath = well.links?.["neighbors"];
  // A third case beside served and absent: the jurisdiction registers laterals and the mart's
  // measured domain does not reach it. Rendering nothing at all reads as "this well has no
  // neighbours", which is a different claim from "nobody measured here".
  if (!neighborPath && detail.neighbors_reason) {
    const refusalFrame = document.createElement("section");
    refusalFrame.className = "gw-card-chart gw-neighbor-context";
    const refusalHost = document.createElement("div");
    refusalHost.className = "gw-frame-body";
    refusalHost.dataset["state"] = "not_covered";
    refusalFrame.append(refusalHost);
    neighborSlot.appendChild(refusalFrame);
    loadNeighbours = (): Promise<void> =>
      import("./neighbors.ts").then(({ renderNeighborRefusal }) => {
        refusalHost.replaceChildren(renderNeighborRefusal(detail.neighbors_reason as string));
      });
  }
  if (neighborPath) {
    const neighborFrame = document.createElement("section");
    neighborFrame.className = "gw-card-chart gw-neighbor-context";
    const neighborHost = document.createElement("div");
    neighborHost.className = "gw-frame-body";
    neighborHost.dataset["state"] = "loading";
    neighborHost.setAttribute("aria-busy", "true");
    neighborHost.setAttribute("aria-live", "polite");
    neighborHost.appendChild(placeholder("Loading neighbours…"));
    neighborFrame.append(neighborHost);
    neighborSlot.appendChild(neighborFrame);
    loadNeighbours = (): Promise<void> =>
      import("./neighbors.ts").then(({ loadNeighborContext }) =>
        loadNeighborContext(neighborHost, neighborPath, api10, { ...query, limit: "5" }),
      );
  }

  // Land and basin leave the Location band for sections of their own: the land unit becomes a
  // link in v0.81 and basin becomes a served polygon answer with a handle at P4, and neither
  // is a fact row once it has a rule behind it.
  const landBody = document.createElement("dl");
  landBody.className = "gw-facts";
  if (detail.land_unit_label) {
    landBody.appendChild(term("Land unit", labelFor(well, "/land_unit_label")));
    const value = document.createElement("dd");
    value.textContent = detail.land_unit_label;
    landBody.appendChild(value);
  }

  // The served polygon answer, its plays, the ingest label beside it and their agreement.
  // Rendered on expansion rather than at mount because the section is collapsed by default and
  // its content is the reason a reader opens this particular well.
  const basinBody = document.createElement("div");

  const lineageBody = document.createElement("div");
  const identityHost = document.createElement("div");

  // Ten ids in one fixed order. A section absent for this well is not rendered at all, but it
  // stays in the list so a link that named it is answered with its own name and rule rather
  // than with silence. Only three are expanded, and the rule behind that split is that a
  // section is expanded when its content is why a reader opens a well, and collapsed when it
  // is why they open this particular one.
  const specs: SectionSpec[] = [
    { id: "production", title: "Production", expanded: true, body: chartFrame },
    {
      id: "cumulative",
      title: "Cumulative",
      expanded: true,
      body: cumulativeSlot,
      present: loadCumulative !== undefined,
      ...(loadCumulative ? { load: loadCumulative } : {}),
    },
    {
      id: "identity",
      title: "Identity and status",
      expanded: true,
      body: identityHost,
      // Whose well it is, plus the status history where the jurisdiction's clock has one.
      // The request rides the section rather than the card, so it is inside the same bound.
      load: () =>
        renderIdentity(
          identityHost,
          well as unknown as Envelope<WellIdentity>,
          factsSlot,
          query,
        ),
    },
    {
      id: "completions",
      title: "Completions and fluids",
      expanded: false,
      body: contextSlot,
      load: loadContext,
    },
    {
      id: "neighbours",
      title: "Neighbours and spacing",
      expanded: false,
      body: neighborSlot,
      present: loadNeighbours !== undefined,
      ...(loadNeighbours ? { load: loadNeighbours } : {}),
      ...(well.links?.["neighbors_rule"] ? { absentRule: well.links["neighbors_rule"] } : {}),
    },
    { id: "land", title: "Land and lease", expanded: false, body: landBody },
    {
      id: "basin",
      title: "Basin and geology",
      expanded: false,
      body: basinBody,
      load: () => {
        renderBasin(basinBody, well as unknown as Envelope<WellBasin>);
        return Promise.resolve();
      },
    },
    {
      id: "pools",
      title: "Production by pool",
      expanded: false,
      present: well.links?.["pools"] !== undefined,
    },
    {
      id: "peer",
      title: "Peer control",
      expanded: false,
      present: well.links?.["type_curve"] !== undefined,
    },
    {
      id: "lineage",
      title: "Lineage",
      expanded: false,
      body: lineageBody,
      load: () => fillLineage(),
    },
  ];

  const sections = mountSections(body, api10, specs);
  body.appendChild(notesSlot);

  // The index is a count of what is rendered, so it has to be taken again when more renders:
  // opened by deep link before Production had drawn, it listed Identity alone and read as a
  // card carrying two handles (gate N7). One document listener, re-pointed at the newest card.
  recountLineage = () => {
    const host = sections.get("lineage");
    if (!host || host.toggle.getAttribute("aria-expanded") !== "true") return;
    // After the queue drains, not at the moment of expansion: a section's handles are drawn
    // by its own load, so counting on the click counts the body it has not rendered yet.
    void sectionsSettled().then(() => fillLineage());
  };
  if (!recounting) {
    recounting = true;
    document.addEventListener(SECTION_OPEN_EVENT, () => recountLineage?.());
  }

  // "What can I check here", and it costs a request of zero. The counts are read off what is
  // rendered at the moment the reader looks, so they are not served figures and carry no
  // handle of their own; the sentence says so, in the shape the running total will use.
  async function fillLineage(): Promise<void> {
    const list = document.createElement("dl");
    list.className = "gw-facts gw-lineage-index";
    for (const spec of specs) {
      const host = sections.get(spec.id);
      if (!host || spec.id === "lineage") continue;
      const count = host.body.querySelectorAll("gw-figure[handle], .gw-handle").length;
      if (count === 0) continue;
      const name = document.createElement("dt");
      name.appendChild(sectionLink(spec.id, spec.title));
      const value = document.createElement("dd");
      value.setAttribute("data-no-glossary", "");
      value.textContent = `${count} handle${count === 1 ? "" : "s"}`;
      list.append(name, value);
    }
    const note = document.createElement("p");
    note.className = "gw-note";
    note.textContent = list.childElementCount
      ? "Counted on this page from what is rendered now, so these counts are not served figures and carry no handle of their own. Each handle's own is beside it."
      : "This card is carrying no derivation handles yet.";
    lineageBody.replaceChildren(list, note);
  }

  // A lease-reporting jurisdiction has no observed well-level series, so the card says that
  // instead of drawing an empty chart: "no production has been reported" would be false about
  // a Texas well whose lease reports every month (DIR-3, cr_tx_allocation_scope_1).
  const pending = well.meta.warnings.find((warning) => warning.code === PENDING_ALLOCATION);
  if (pending) {
    // Texas's two rule links, landed through P2's section machinery: the panel names the grain
    // decision and the model rule, and the card is still mounted by `land` so the reader's
    // deep-linked section is the one that opens.
    chartFrame.replaceWith(pendingProductionPanel(pending, ruleLinks(well.links)));
    land(container, card, state.section);
    await Promise.all([statusRequest, sectionsSettled()]);
    return;
  }

  land(container, card, state.section);

  const productionRequest = (async () => {
    try {
      const production = await getEnvelope<ProductionData>(
        `/v1/wells/${api10}/production`,
        query,
      );
      const data = unwrap(production);
      // The disclosure the API serves while the allocated mart is empty. It arrives on THIS
      // envelope, not on the well's -- the well's warning was retired when the grain rule
      // superseded the disclosure rule -- and without reading it here the card printed "No
      // production reported." over a lease that has filed every month (gate-tx H-10-W).
      const pendingSeries = production.meta.warnings.find(
        (warning) => warning.code === PENDING_ALLOCATION,
      );
      if (pendingSeries) {
        chartFrame.replaceWith(
          pendingProductionPanel(pendingSeries, ruleLinks(production.links)),
        );
        return;
      }
      if (data.streams.length === 0) {
        chartHost.replaceChildren(emptyState("No production reported."));
        return;
      }
      const head = sections.get("production");
      head?.title.replaceChildren(labelElement("Production", labelFor(production, "/series")));
      // SB-08 §2.6 row 2, in the section's own head and after that replaceChildren rather
      // than before it: the title is rebuilt when the series lands, so an earlier append
      // goes with the placeholder. The vintage pinned is the series' own, not the card's.
      const series = openThisSeries(detail.api10, {
        state,
        resolved: production.meta.as_of.resolved,
      });
      if (series) head?.aside.appendChild(crossingLink(series));
      // Loaded here rather than at module scope: the plot is drawn only once a series has
      // arrived, and the entry chunk carries every reader who never opens a card. The budget
      // test in explore/bundle-budget.test.ts is what holds this to it.
      const { renderChart } = await import("../chart/chart.ts");
      renderChart(chartHost, toChartSeries(data), {
        onExplain: callbacks.onExplain,
        labelTermFor: (pointer) => labelFor(production, pointer),
      });
      for (const note of warningNotes(production.meta.warnings)) chartNotes.appendChild(note);
      highlight(chartFrame, termIndex());
      // The chart's own handles arrive here, outside the section queue: the production request
      // runs beside it and `sectionsSettled()` is long resolved by the time the plot draws, so
      // an index counted on the queue alone still missed the section with the most handles
      // on the card (gate N7's other half).
      recountLineage?.();
    } catch (error) {
      chartHost.replaceChildren(errorPanel(error, callbacks));
    }
  })();

  await Promise.all([statusRequest, productionRequest, sectionsSettled()]);
}

/**
 * Mount, highlight, and land focus. With `?section=` present the landing target is that
 * section's disclosure rather than the card heading, so a deep-linked reader lands on the
 * thing the link named; `applySection` carries the same quiet-focus rule `focusPanel` does.
 */
function land(container: HTMLElement, card: HTMLElement, section: string | null): void {
  container.replaceChildren(card);
  highlight(card, termIndex());
  if (section) applySection(section);
  else focusPanel(container);
}

const CUMULATIVE_STREAMS: [keyof NonNullable<WellCumulatives["cumulative"]>, string, string][] = [
  ["oil_bbl", "Oil", "/cumulative/oil_bbl"],
  ["gas_mcf", "Gas", "/cumulative/gas_mcf"],
  ["water_bbl", "Water", "/cumulative/water_bbl"],
];

async function loadWellCumulatives(
  host: HTMLElement,
  path: string,
  expectedApi10: string,
  query: Record<string, string>,
): Promise<void> {
  try {
    const envelope = await getEnvelope<WellCumulatives>(path, query);
    const data = unwrap(envelope);
    if (data.api10 !== expectedApi10 || data.cumulative === undefined || !data.coverage) {
      throw new TypeError("Cumulatives did not match the required well");
    }
    host.replaceChildren(cumulativesBody(data, envelope));
    for (const note of warningNotes(envelope.meta.warnings)) host.appendChild(note);
    host.dataset["state"] = data.cumulative === null ? "empty" : "populated";
    highlight(host, termIndex());
  } catch (error) {
    // An ND well the snapshot has not absorbed yet. Distinct from "produced nothing", which
    // is the null cumulative above, and from a read failure, which is the line below.
    if (error instanceof ApiError && error.code === "not_found") {
      // The API's own sentence, where it served one: only the API knows whether this well is
      // outside the mart's scope or inside a jurisdiction whose mart the last refresh skipped,
      // and "not in the snapshot" said the first about the second (gate-tx H-10-W, H-10-C).
      host.replaceChildren(
        emptyState(asProse(error.problem.detail ?? "No cumulative: not in the snapshot.")),
      );
      host.dataset["state"] = "empty";
      return;
    }
    host.replaceChildren(emptyState("Unavailable: the response could not be read."));
    host.dataset["state"] = "unavailable";
  } finally {
    host.setAttribute("aria-busy", "false");
  }
}

// A `problem` detail is written for a machine-readable field and opens lowercase. This is the
// one place one is reused as a section's prose, and it is already a whole sentence.
function asProse(detail: string): string {
  return detail.charAt(0).toUpperCase() + detail.slice(1);
}


function cumulativesBody(
  data: WellCumulatives,
  envelope: Envelope<WellCumulatives>,
): DocumentFragment {
  const fragment = document.createDocumentFragment();
  if (data.cumulative === null) {
    fragment.appendChild(emptyState("No cumulative: nothing ever filed."));
    fragment.appendChild(scopeLine([unbreakable(`snapshot ${formatVintage(data.snapshot_vintage)}`)]));
    return fragment;
  }

  const row = document.createElement("dl");
  row.className = "gw-cumulative-row";
  for (const [key, label, pointer] of CUMULATIVE_STREAMS) {
    const cell = document.createElement("div");
    cell.className = "gw-cumulative-cell";
    const term_ = document.createElement("dt");
    term_.appendChild(labelElement(label, labelFor(envelope, pointer)));
    const value = document.createElement("dd");
    const figure = data.cumulative[key];
    if (figure) {
      // Whole units: a cumulative is no more measured to a thousandth of a barrel than a
      // monthly volume is, and the three-decimal tail crowded the row at 390.
      value.appendChild(figureElement(figure, label, figure.d ?? null, 0));
    } else {
      value.appendChild(absentValue(absentStreamReason(data.coverage[key])));
    }
    // R8 / CLAUDE.md: state the policy wherever the number appears. The chart frame states its
    // basis beside each series and this row did not, so the oil total was the one liquids
    // number on the card shown without saying that oil means oil plus condensate. It goes
    // beside the value rather than in the dt, which stays the stream's name and nothing else.
    if (figure?.basis) {
      const basis = document.createElement("span");
      basis.className = "gw-chip gw-cumulative-basis";
      basis.textContent = figure.basis;
      value.appendChild(basis);
    }
    // The allocated share, beside the total and never after it. A total that sums allocated
    // months without saying so is the naked number this whole surface exists against, and the
    // share is the one number that says how much of it is an estimate.
    const share = data.allocation?.share[streamOf(key)];
    // A stream with no allocated month is not partly allocated, and "0% allocated" beside a
    // total is noise that trains a reader to stop reading the chip.
    if (figure && share && Number(share.value) > 0) {
      const chip = document.createElement("span");
      chip.className = "gw-chip gw-alloc-share";
      chip.textContent = `${percent(share.value)} allocated`;
      chip.title =
        `${percent(share.value)} of this total is an allocated estimate rather than a` +
        ` reported figure (${data.allocation?.rule_id ?? ""}).`;
      value.appendChild(chip);
    }
    const record = coverageTitle(data.coverage[key]);
    if (record) cell.title = record;
    cell.append(term_, value);
    row.appendChild(cell);
  }
  fragment.appendChild(row);
  const chip = allocationChip(data);
  if (chip) fragment.appendChild(chip);
  fragment.appendChild(scopeLine(cumulativeScope(data)));
  return fragment;
}

const MART_STREAM_OF: Record<string, string> = {
  oil_bbl: "liquid",
  gas_mcf: "gas",
  water_bbl: "water",
};

function streamOf(key: string): string {
  return MART_STREAM_OF[key] ?? key;
}

/** A decimal share as a whole-number percent, without ever parsing it as a float. */
function percent(value: string): string {
  return `${roundTo(String(Number(value) * 100), 0)}%`;
}

/**
 * `observed_with_allocated` as a labelled chip rather than a footnote.
 *
 * A reader who does not notice a footnote has read the total as an observation, which is the
 * one reading this coverage class exists to prevent.
 */
function allocationChip(data: WellCumulatives): HTMLElement | null {
  if (data.coverage_outcome !== "observed_with_allocated" || !data.allocation) return null;
  const chip = document.createElement("p");
  chip.className = "gw-chip gw-alloc-coverage";
  chip.dataset["basis"] = data.allocation.basis;
  const model = data.allocation.model_id ?? "";
  chip.append(`${coverageSentence(data.allocation)}${model ? ` · ${model}` : ""}`);
  // The share count is served with a handle and had nowhere on screen to be: the brief asks
  // this row to state the basis, the model and how many shares are behind it.
  const counted = data.allocation.shares_counted;
  if (counted) {
    const shares = document.createElement("span");
    shares.className = "gw-alloc-shares";
    shares.textContent = ` · ${formatValue(counted.value)} ${counted.unit}`;
    if (counted.d) shares.dataset["handle"] = counted.d;
    chip.appendChild(shares);
  }
  chip.title =
    "Part of this total is an estimate: the jurisdiction files production by lease and the" +
    ` per-well share is computed under ${data.allocation.rule_id}. The share of each total` +
    " it accounts for is stated beside that total.";
  return chip;
}

/**
 * How much of the total is a share, in words. "Some" on a well where every month is one is a
 * hedge the data does not support, and it sits beside a chip reading `100% allocated`.
 */
function coverageSentence(allocation: CumulativeAllocation): string {
  const shares = Object.values(allocation.share).map((figure) => Number(figure.value));
  if (shares.length > 0 && shares.every((share) => share >= 1)) return "All months are allocated";
  const months = Object.values(allocation.months).map((figure) => Number(figure.value));
  if (months.length > 0) return `${range(months)} months are allocated`;
  return "Some months are allocated";
}

/**
 * A null total means no month was admitted, so the reason is which class the months fell in.
 * Withheld outranks no-report when both are present: the regulator holding a month back is a
 * stronger statement than a missing filing, and `title` carries the full count either way.
 */
function absentStreamReason(coverage: StreamCoverage | undefined): string {
  if (!coverage || coverage.span_months === 0) return "nothing filed";
  if (coverage.months_withheld > 0) return nullSemantics("withheld").label;
  if (coverage.months_no_report > 0) return nullSemantics("no_report").label;
  return "nothing filed";
}

/** The four counts behind one total, never collapsed: they are four different facts. */
function coverageTitle(coverage: StreamCoverage | undefined): string {
  if (!coverage) return "";
  return (
    `${coverage.months_reported} reported · ${coverage.months_reported_zero} reported zero` +
    ` · ${coverage.months_no_report} no report · ${coverage.months_withheld} withheld` +
    ` of ${coverage.span_months} months`
  );
}

function cumulativeScope(data: WellCumulatives): (string | Node | false)[] {
  const blocks = CUMULATIVE_STREAMS.map(([key]) => data.coverage[key]).filter(
    (block): block is StreamCoverage => Boolean(block),
  );
  const first = blocks.map((block) => block.first_month).filter((month) => month !== null);
  const last = blocks.map((block) => block.last_month).filter((month) => month !== null);
  const window =
    first.length && last.length
      ? `${formatMonth(first.reduce((a, b) => (a < b ? a : b)))} – ` +
        `${formatMonth(last.reduce((a, b) => (a > b ? a : b)))}`
      : "";
  // Admitted counts can differ per stream — one stream's month can be withheld while
  // another's is filed — so a single number would be wrong for two of the three.
  const admitted = blocks.map((block) => block.months_reported + block.months_reported_zero);
  const span = Math.max(...blocks.map((block) => block.span_months), 0);
  const count = range(admitted);
  return [
    window,
    span > 0 && (allocatedScope(data, span, count) ?? `${count} of ${span} months admitted`),
    // The span is the months this source has filed for this well, not the well's life, and
    // the two are far apart where a regulator publishes a rolling window rather than a
    // history. Said generically because it is true of every jurisdiction: a total over what
    // was filed is the only total there is, and a reader who takes it for a life-of-well
    // figure has been told something false by omission.
    span > 0 && "over the months filed, not the well's life",
    unbreakable(`snapshot ${formatVintage(data.snapshot_vintage)}`),
  ];
}

/** One number where every stream agrees, and the range where they do not. */
function range(counts: number[]): string {
  const low = Math.min(...counts);
  const high = Math.max(...counts);
  return low === high ? `${low}` : `${low}–${high}`;
}

/**
 * The scope line for a total built from shares, or null where the total is observed.
 *
 * `months_reported` counts well-grain canonical months and a lease-grain jurisdiction has
 * none of them, so "0 of 24 months admitted" printed under a 7,200 bbl total: the card
 * contradicting its own number one line down (M3). Both counts are stated instead, and the
 * allocated one is the served figure rather than a recount of it.
 */
function allocatedScope(
  data: WellCumulatives,
  span: number,
  observed: string,
): HTMLElement | null {
  const months = Object.values(data.allocation?.months ?? {});
  if (months.length === 0) return null;
  const line = document.createElement("span");
  line.className = "gw-scope-allocated";
  line.textContent =
    `${range(months.map((figure) => Number(figure.value)))} of ${span} months allocated` +
    ` · ${observed} observed`;
  const handle = months.find((figure) => figure.d)?.d;
  if (handle) line.dataset["handle"] = handle;
  line.title =
    "An allocated month is a computed share of the lease's filing; an observed month is a" +
    ` report about this well. This jurisdiction files at the lease (${
      data.allocation?.rule_id ?? ""
    }).`;
  return line;
}

/** The disclosures both the header and the completion design carry, worded for their own
 *  panel. Everything else a shared code might mean is left alone. */
const SAID_ONCE_PER_CARD = new Set(["length_not_served", "length_scope_unregistered"]);

async function loadCompletionContext(
  host: HTMLElement,
  path: string,
  expectedApi10: string,
  query: Record<string, string>,
  alreadySaid: ReadonlySet<string> = new Set(),
): Promise<void> {
  try {
    const envelope = await getEnvelope<CompletionContext>(path, query);
    const context = unwrap(envelope);
    if (
      context.api10 !== expectedApi10 ||
      typeof context.design_availability !== "string" ||
      context.design === undefined ||
      !Array.isArray(context.events) ||
      !Array.isArray(context.pools)
    ) {
      throw new TypeError("Completion context did not match the required well and collections");
    }
    host.replaceChildren(completionContextBody(context, envelope));
    const unsaid = envelope.meta.warnings.filter((warning) => !alreadySaid.has(warning.code));
    for (const note of warningNotes(unsaid)) host.appendChild(note);
    host.dataset["state"] =
      context.events.length === 0 && context.pools.length === 0 && context.design === null
        ? "empty"
        : "populated";
    highlight(host, termIndex());
  } catch {
    host.replaceChildren(emptyState("Unavailable: the response could not be read."));
    host.dataset["state"] = "unavailable";
  } finally {
    host.setAttribute("aria-busy", "false");
  }
}

function completionContextBody(
  context: CompletionContext,
  envelope: Envelope<CompletionContext>,
): DocumentFragment {
  const fragment = document.createDocumentFragment();
  if (context.events.length === 0 && context.pools.length === 0 && context.design === null) {
    fragment.appendChild(emptyState("No events, pools or design reported."));
  } else {
    fragment.append(
      contextGroup(
        "Completion events",
        labelFor(envelope, "/events/0/event_kind"),
        context.events.map(completionEventItem),
        "None reported",
      ),
      contextGroup(
        "Reported pools",
        labelFor(envelope, "/pools/0/pool_reported"),
        context.pools.map(completionPoolItem),
        "None reported",
      ),
      contextGroup(
        "Completion design",
        labelFor(envelope, "/design/fluid_intensity"),
        completionDesignItems(context),
        "None disclosed",
      ),
    );
  }

  // The absence is a served fact, not a load failure, so it stays on the card — as a scope
  // line under the section it scopes rather than as the sentence it used to be.
  fragment.appendChild(
    scopeLine([
      context.design === null
        ? "No design disclosed: FracFocus is voluntary"
        : "Design as disclosed, measured against computed geometry",
      "Formation tops not served",
    ]),
  );
  return fragment;
}

/** cr_ff_design_promote_1's vocabulary, for the disclosed volume. */
const VOLUME_REASONS: Record<string, string> = {
  no_report: "unavailable \u2014 no disclosed volume",
  withheld: "unavailable \u2014 withheld by the regulator",
};

/** cr_ff_fluid_intensity_1's vocabulary, for the quotient. A different set of facts. */
const INTENSITY_REASONS: Record<string, string> = {
  no_report: "unavailable \u2014 no disclosed volume",
  withheld: "unavailable \u2014 withheld by the regulator",
  // Not "no lateral geometry": a Montana well has geometry and a withheld length, and an
  // unregistered basin has geometry and no rule to measure it under. What is missing in all
  // three cases is the divisor, so that is what the row says.
  lateral_length_unavailable: "unavailable \u2014 no lateral length to divide by",
  lateral_length_implausible: "unavailable \u2014 lateral too short to divide by",
  intensity_out_of_range: "unavailable \u2014 result outside the rule's range",
  intensity_rule_unregistered: "unavailable \u2014 the intensity rule is not registered",
};

function completionDesignItems(context: CompletionContext): HTMLElement[] {
  const design = context.design;
  if (design === null) return [];
  const item = document.createElement("li");
  const facts = document.createElement("dl");
  facts.className = "gw-context-facts";
  appendContextFact(facts, "Disclosure", design.disclosure_id, true);
  appendFigureFact(
    facts,
    "Base fluid",
    design.base_water_volume,
    VOLUME_REASONS[design.base_water_null_semantics] ?? "unavailable",
  );
  appendFigureFact(facts, "Lateral", design.lateral_length_ft, "unavailable \u2014 no geometry");
  appendFigureFact(
    facts,
    "Fluid intensity",
    design.fluid_intensity,
    INTENSITY_REASONS[design.intensity_null_semantics] ?? "unavailable",
  );
  appendContextFact(
    facts,
    "Source",
    sourceLabel(design.source_id, design.report_vintage),
    true,
  );
  item.appendChild(facts);
  return [item];
}

/** A figure renders as a chip with its handle; an absence renders as its stated reason. */
function appendFigureFact(
  facts: HTMLDListElement,
  label: string,
  value: Figure | null,
  reason: string,
): void {
  if (value === null) {
    appendContextFact(facts, label, reason);
    return;
  }
  appendContextFact(facts, label, figureElement(value, label, value.d ?? null));
}

export function contextGroup(
  heading: string,
  termId: string | null,
  items: HTMLElement[],
  emptyText: string,
): HTMLElement {
  const group = document.createElement("section");
  group.className = "gw-context-group";
  const title = document.createElement("h4");
  title.appendChild(labelElement(heading, termId));
  group.appendChild(title);
  if (items.length === 0) {
    group.appendChild(emptyState(emptyText));
    return group;
  }
  const list = document.createElement("ul");
  list.className = "gw-context-list";
  list.append(...items);
  group.appendChild(list);
  return group;
}

function completionEventItem(event: CompletionEvent): HTMLElement {
  const item = document.createElement("li");
  const facts = document.createElement("dl");
  facts.className = "gw-context-facts";
  appendContextFact(facts, "Event", eventLabel(event.event_kind));
  appendContextDate(facts, "Job start", event.job_start_date, event._lineage["job_start_date"]);
  appendContextDate(
    facts,
    "Job end",
    event.completion_date,
    event._lineage["completion_date"],
  );
  appendContextFact(facts, "Source", sourceLabel(event.source_id, event.report_vintage), true);
  item.appendChild(facts);
  return item;
}

function completionPoolItem(pool: CompletionPool): HTMLElement {
  const item = document.createElement("li");
  const facts = document.createElement("dl");
  facts.className = "gw-context-facts";
  appendContextFact(facts, "Pool entity", pool.completion_key, true);
  appendContextFact(
    facts,
    "Reported pool",
    unavailableReason(pool.pool_reported, pool.formation_null_semantics),
    false,
    pool._lineage["pool_reported"],
  );
  appendContextFact(
    facts,
    "Canonical formation",
    unavailableReason(pool.formation, pool.formation_null_semantics),
  );
  appendContextFact(
    facts,
    "Formation group",
    unavailableReason(pool.formation_group, pool.formation_null_semantics),
  );
  appendContextDate(
    facts,
    "First observed month",
    pool.first_production_month,
    pool._lineage["first_production_month"],
  );
  appendContextDate(
    facts,
    "Last observed month",
    pool.last_production_month,
    pool._lineage["last_production_month"],
  );
  if (pool.effective_from !== null) {
    appendContextDate(
      facts,
      "Effective from",
      pool.effective_from,
      pool._lineage["effective_from"],
    );
  }
  appendContextFact(
    facts,
    "Source",
    sourceLabel(pool.source_id, pool.latest_report_vintage),
    true,
  );
  item.appendChild(facts);
  return item;
}

export function appendContextFact(
  facts: HTMLDListElement,
  label: string,
  value: string | Node,
  literal = false,
  handle?: string,
): void {
  const term = document.createElement("dt");
  term.textContent = label;
  const definition = document.createElement("dd");
  if (literal) definition.setAttribute("data-no-glossary", "");
  definition.append(value);
  if (handle) definition.append(" ", lineageButton(handle, label));
  facts.append(term, definition);
}

export function appendContextDate(
  facts: HTMLDListElement,
  label: string,
  value: string | null,
  handle?: string,
): void {
  const term = document.createElement("dt");
  term.textContent = label;
  const definition = document.createElement("dd");
  definition.setAttribute("data-no-glossary", "");
  if (value === null) {
    definition.appendChild(absentValue(null));
  } else {
    const time = document.createElement("time");
    time.dateTime = value;
    time.textContent = formatVintage(value);
    definition.appendChild(time);
    if (handle) definition.append(" ", lineageButton(handle, label));
  }
  facts.append(term, definition);
}

function eventLabel(kind: string): string {
  return kind === "hydraulic_frac_job_end" ? "Hydraulic frac job end" : kind;
}

function sourceLabel(sourceId: string, reportVintage: string): string {
  return `${sourceId} · report ${formatVintage(reportVintage)}`;
}

/** cr_nd_formation_alias_1's vocabulary. One state, one string, wherever the state appears. */
const POOL_ABSENCE: Record<CompletionPool["formation_null_semantics"], string> = {
  pool_not_reported: "pool not reported",
  alias_unavailable: "no registered alias",
  mapped: "no group assigned",
};

function unavailableReason(
  value: string | null,
  semantics: CompletionPool["formation_null_semantics"],
): string | HTMLElement {
  if (value !== null && value !== "") return value;
  return absentValue(POOL_ABSENCE[semantics] ?? null);
}

function lineageButton(handle: string, label: string): HTMLButtonElement {
  return explainHandle({ handle, label: label.toLowerCase() });
}

/** The <dt> beside it is the label, so the chip carries it for assistive tech only. */
export function figureElement(
  figure: Figure,
  label: string,
  handle: string | null,
  digits?: number,
): HTMLElement {
  const element = document.createElement("gw-figure");
  element.setAttribute("value", figure.value);
  element.setAttribute("unit", figure.unit);
  element.setAttribute("handle", handle ?? figure.d ?? "");
  element.setAttribute("label", label);
  element.setAttribute("label-hidden", "");
  if (figure.granularity) element.setAttribute("granularity", figure.granularity);
  if (digits !== undefined) element.setAttribute("digits", String(digits));
  return element;
}


function term(label: string, termId: string | null): HTMLElement {
  const element = document.createElement("dt");
  element.appendChild(labelElement(label, termId));
  return element;
}

export function placeholder(text: string): HTMLElement {
  const element = document.createElement("p");
  element.className = "gw-placeholder";
  element.textContent = text;
  return element;
}

type ApiWarning = { code: string; detail?: string; pointer?: string };

/** The one warning code the card renders as its own panel rather than as a warning line. */
export const PENDING_ALLOCATION = "production_pending_allocation";

/**
 * The production slot for a well whose regulator reports at the lease. It is a state, not an
 * absence: the section is titled for what is pending and links to the rule that says so.
 */
/** A rule the panel sends the reader to, named by its own id so the link says which. */
export interface PendingRuleLink {
  href: string;
  label: string;
}

/** `/v1/conformance/cr_tx_allocation_v0_1` -> `cr_tx_allocation_v0_1`. */
function ruleIdOf(href: string): string {
  return href.split("/").filter(Boolean).pop() ?? href;
}

export function ruleLinks(links: Links | undefined): PendingRuleLink[] {
  // Two rules, and they answer two questions: the decision that admits a well-level figure
  // for this jurisdiction at all, and the rule that will compute the share once the mart is
  // built. A panel that names neither is the empty envelope with a heading on it.
  const wanted: [string, string][] = [
    ["allocation_rule", "The registered grain decision"],
    ["allocation_model_rule", "The rule that computes the share"],
    ["reporting_rule", "The conformance rule that decided this"],
  ];
  return wanted.flatMap(([key, sentence]) => {
    const href = links?.[key];
    return href ? [{ href, label: `${sentence}: ${ruleIdOf(href)}.` }] : [];
  });
}

export function pendingProductionPanel(
  warning: ApiWarning,
  links: PendingRuleLink[] = [],
): HTMLElement {
  const frame = document.createElement("section");
  frame.className = "gw-card-chart gw-pending";
  frame.dataset["state"] = "production_pending_allocation";
  const title = document.createElement("h3");
  title.className = "gw-frame-title";
  title.textContent = "Production pending allocation";
  const body = document.createElement("div");
  body.className = "gw-frame-body";
  const detail = document.createElement("p");
  detail.textContent =
    warning.detail ??
    "This well's regulator reports production at the lease, so no well-level series has" +
      " been observed.";
  body.append(detail);
  // The rules themselves, not the collection: the reader sent to a list of thirty-three has
  // to find these again.
  const named = links.length
    ? links
    : [{ href: "/v1/conformance", label: "See the conformance rule that decided this." }];
  for (const rule of named) {
    const link = document.createElement("a");
    link.className = "gw-pending-rule";
    link.href = rule.href;
    link.textContent = rule.label;
    body.appendChild(link);
  }
  frame.append(title, body);
  return frame;
}

export function errorPanel(
  error: unknown,
  callbacks: { onClose(): void; onSignIn?(): void },
): HTMLElement {
  const element = document.createElement("div");
  element.className = "gw-error";
  const heading = document.createElement("h3");
  const body = document.createElement("p");
  if (error instanceof ApiError) {
    heading.textContent = `${error.problem.title} (${error.code})`;
    body.textContent = error.problem.detail ?? "";
    if (error.problem.status === 403) {
      body.textContent = "This browser has no live session, so the API served nothing.";
      if (callbacks.onSignIn) {
        const fix = document.createElement("button");
        fix.type = "button";
        fix.className = "gw-error-key";
        fix.textContent = "Sign in";
        fix.addEventListener("click", () => callbacks.onSignIn?.());
        element.append(heading, body, fix);
      } else {
        element.append(heading, body);
      }
    } else {
      element.append(heading, body);
    }
    element.appendChild(errorLink(error.code));
  } else {
    heading.textContent = "Request failed";
    body.textContent = String(error);
    element.append(heading, body);
  }
  const close = document.createElement("button");
  close.type = "button";
  close.className = "gw-close";
  close.setAttribute("aria-label", "Dismiss this error");
  close.textContent = "×";
  close.addEventListener("click", callbacks.onClose);
  element.appendChild(close);
  return element;
}

/**
 * `problem.type` is absolute at a host that does not resolve, and the same document is
 * served here. The relative path is the only link in an error panel that works (UX P1-7).
 */
function errorLink(code: string): HTMLElement {
  const link = document.createElement("a");
  link.href = `/v1/errors/${code}`;
  link.textContent = `What does ${code} mean?`;
  link.setAttribute("data-no-glossary", "");
  return link;
}
