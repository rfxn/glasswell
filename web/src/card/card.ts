import "./gw-figure.ts";

import { ApiError, getEnvelope } from "../api/client.ts";
import { derivationFor, labelFor, unwrap } from "../api/envelope.ts";
import type { Envelope, Figure } from "../api/envelope.ts";
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
import { absentValue, formatMonth, formatVintage, nullSemantics } from "./format.ts";

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

export interface WellCumulatives {
  api10: string;
  granularity: string;
  snapshot_vintage: string;
  coverage_outcome: string;
  cumulative: { oil_bbl: Figure | null; gas_mcf: Figure | null; water_bbl: Figure | null } | null;
  coverage: Record<string, StreamCoverage> & { _lineage: Record<string, string> };
  months_withheld: Figure;
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
      ["basin", "Basin", "/basin"],
      ["county_code_at_permit", "County", "/county_code_at_permit"],
      ["land_unit_label", "Land unit", "/land_unit_label"],
    ],
  },
  {
    title: "Drilling",
    fields: [
      ["spud_date", "Spud", "/spud_date"],
      ["well_type_reported", "Well type", "/well_type_reported"],
    ],
  },
  { title: "Record", fields: [] },
];

export async function renderWellCard(
  container: HTMLElement,
  api10: string,
  callbacks: CardCallbacks,
): Promise<void> {
  container.replaceChildren(placeholder(`Loading well ${api10}…`));
  container.hidden = false;
  const state = readState();
  const pinnedAsOf = state.extra["as_of"]?.[0];
  const asOfQuery: Record<string, string> = pinnedAsOf ? { as_of: pinnedAsOf } : {};

  let well: Envelope<WellDetail>;
  try {
    well = await getEnvelope<WellDetail>(`/v1/wells/${api10}`, asOfQuery);
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

  // The reading order the card is built in, and the change that matters most about it:
  // production is what a reader opened the card for, and it used to sit at 49% of a 1,600px
  // scroll behind two sections that are empty for most wells. Slots are placed first and
  // filled by their own requests, so the order cannot drift with which response lands first.
  const cumulativeSlot = document.createElement("div");
  const factsSlot = document.createElement("div");
  factsSlot.className = "gw-card-facts";
  const contextSlot = document.createElement("div");
  const neighborSlot = document.createElement("div");
  const notesSlot = document.createElement("div");
  notesSlot.className = "gw-notes gw-card-notes";

  // Title outside the swappable body: the placeholder, the plot and an error all land in
  // .gw-frame-body, so none of them can take the frame's label down with them.
  const chartFrame = document.createElement("section");
  chartFrame.className = "gw-card-chart gw-production-chart";
  const chartTitle = document.createElement("h3");
  chartTitle.className = "gw-frame-title";
  chartTitle.textContent = "Monthly production";
  const chartHost = document.createElement("div");
  chartHost.className = "gw-frame-body";
  chartHost.appendChild(placeholder("Loading production…"));
  // The chart owns .gw-frame-body and replaces it on every span change and theme repaint, so
  // the series' warnings — R8's disclosure of the derivations behind a column — sit beside it.
  const chartNotes = document.createElement("div");
  chartNotes.className = "gw-chart-notes gw-notes";
  chartFrame.append(chartTitle, chartHost, chartNotes);

  // Directly under the chart: the total belongs beside the series it is a total of, and a
  // reader who came for production should not have to scroll past the fact bands to find it.
  body.append(chartFrame, cumulativeSlot, factsSlot, contextSlot, neighborSlot, notesSlot);

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
  const contextTitle = document.createElement("h3");
  contextTitle.className = "gw-frame-title";
  contextTitle.textContent = "Completions & formations";
  const contextHost = document.createElement("div");
  contextHost.className = "gw-frame-body";
  contextHost.dataset["state"] = "loading";
  contextHost.setAttribute("aria-busy", "true");
  contextHost.setAttribute("aria-live", "polite");
  contextHost.appendChild(placeholder("Loading completions…"));
  contextFrame.append(contextTitle, contextHost);
  contextSlot.appendChild(contextFrame);

  const contextRequest = loadCompletionContext(
    contextHost,
    well.links?.["completions"] ?? `/v1/wells/${api10}/completions`,
    api10,
    asOfQuery,
  );

  // Absent outside the mart's states: the API declines to offer a link it would 404, and a
  // section headed "no cumulative" would say the well produced nothing rather than that this
  // jurisdiction is not summed here.
  let cumulativeRequest: Promise<void> = Promise.resolve();
  const cumulativePath = well.links?.["cumulatives"];
  if (cumulativePath) {
    const cumulativeFrame = document.createElement("section");
    cumulativeFrame.className = "gw-card-chart gw-well-cumulatives";
    const cumulativeTitle = document.createElement("h3");
    cumulativeTitle.className = "gw-frame-title";
    cumulativeTitle.textContent = "Cumulative";
    const cumulativeHost = document.createElement("div");
    cumulativeHost.className = "gw-frame-body";
    cumulativeHost.dataset["state"] = "loading";
    cumulativeHost.setAttribute("aria-busy", "true");
    cumulativeHost.setAttribute("aria-live", "polite");
    cumulativeHost.appendChild(placeholder("Loading cumulative…"));
    cumulativeFrame.append(cumulativeTitle, cumulativeHost);
    cumulativeSlot.appendChild(cumulativeFrame);
    cumulativeRequest = loadWellCumulatives(cumulativeHost, cumulativePath, api10, asOfQuery);
  }

  let neighborRequest: Promise<void> = Promise.resolve();
  const neighborPath = well.links?.["neighbors"];
  // A third case beside served and absent: the jurisdiction registers laterals and the mart's
  // measured domain does not reach it. Rendering nothing at all reads as "this well has no
  // neighbours", which is a different claim from "nobody measured here".
  if (!neighborPath && detail.neighbors_reason) {
    const refusalFrame = document.createElement("section");
    refusalFrame.className = "gw-card-chart gw-neighbor-context";
    const refusalTitle = document.createElement("h3");
    refusalTitle.className = "gw-frame-title";
    refusalTitle.textContent = "Physical neighbours";
    const refusalHost = document.createElement("div");
    refusalHost.className = "gw-frame-body";
    refusalHost.dataset["state"] = "not_covered";
    refusalFrame.append(refusalTitle, refusalHost);
    neighborSlot.appendChild(refusalFrame);
    neighborRequest = import("./neighbors.ts").then(({ renderNeighborRefusal }) => {
      refusalHost.replaceChildren(renderNeighborRefusal(detail.neighbors_reason as string));
    });
  }
  if (neighborPath) {
    const neighborFrame = document.createElement("section");
    neighborFrame.className = "gw-card-chart gw-neighbor-context";
    const neighborTitle = document.createElement("h3");
    neighborTitle.className = "gw-frame-title";
    neighborTitle.textContent = "Physical neighbours";
    const neighborHost = document.createElement("div");
    neighborHost.className = "gw-frame-body";
    neighborHost.dataset["state"] = "loading";
    neighborHost.setAttribute("aria-busy", "true");
    neighborHost.setAttribute("aria-live", "polite");
    neighborHost.appendChild(placeholder("Loading neighbours…"));
    neighborFrame.append(neighborTitle, neighborHost);
    neighborSlot.appendChild(neighborFrame);
    neighborRequest = import("./neighbors.ts").then(({ loadNeighborContext }) =>
      loadNeighborContext(neighborHost, neighborPath, api10, { ...asOfQuery, limit: "5" }),
    );
  }

  // A lease-reporting jurisdiction has no observed well-level series, so the card says that
  // instead of drawing an empty chart: "no production has been reported" would be false about
  // a Texas well whose lease reports every month (DIR-3, cr_tx_allocation_scope_1).
  const pending = well.meta.warnings.find((warning) => warning.code === PENDING_ALLOCATION);
  if (pending) {
    chartFrame.replaceWith(
      pendingProductionPanel(pending, well.links?.["reporting_rule"] ?? undefined),
    );
    container.replaceChildren(card);
    highlight(card, termIndex());
    focusPanel(container);
    await Promise.all([statusRequest, contextRequest, cumulativeRequest, neighborRequest]);
    return;
  }

  container.replaceChildren(card);
  highlight(card, termIndex());
  focusPanel(container);

  const productionRequest = (async () => {
    try {
      const production = await getEnvelope<ProductionData>(
        `/v1/wells/${api10}/production`,
        asOfQuery,
      );
      const data = unwrap(production);
      if (data.streams.length === 0) {
        chartHost.replaceChildren(emptyState("No production reported."));
        return;
      }
      chartTitle.replaceChildren(
        labelElement("Monthly production", labelFor(production, "/series")),
      );
      // SB-08 §2.6 row 2, in the chart's own header and after that replaceChildren rather
      // than before it: the title is rebuilt when the series lands, so an earlier append
      // goes with the placeholder. The vintage pinned is the series' own, not the card's.
      const series = openThisSeries(detail.api10, {
        state,
        resolved: production.meta.as_of.resolved,
      });
      if (series) chartTitle.appendChild(crossingLink(series));
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
    } catch (error) {
      chartHost.replaceChildren(errorPanel(error, callbacks));
    }
  })();

  await Promise.all([
    statusRequest,
    contextRequest,
    cumulativeRequest,
    neighborRequest,
    productionRequest,
  ]);
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
      host.replaceChildren(emptyState("No cumulative: not in the snapshot."));
      host.dataset["state"] = "empty";
      return;
    }
    host.replaceChildren(emptyState("Unavailable: the response could not be read."));
    host.dataset["state"] = "unavailable";
  } finally {
    host.setAttribute("aria-busy", "false");
  }
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
    const record = coverageTitle(data.coverage[key]);
    if (record) cell.title = record;
    cell.append(term_, value);
    row.appendChild(cell);
  }
  fragment.appendChild(row);
  fragment.appendChild(scopeLine(cumulativeScope(data)));
  return fragment;
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
  const low = Math.min(...admitted);
  const high = Math.max(...admitted);
  const count = low === high ? `${low}` : `${low}–${high}`;
  return [
    window,
    span > 0 && `${count} of ${span} months admitted`,
    unbreakable(`snapshot ${formatVintage(data.snapshot_vintage)}`),
  ];
}

async function loadCompletionContext(
  host: HTMLElement,
  path: string,
  expectedApi10: string,
  query: Record<string, string>,
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
    for (const note of warningNotes(envelope.meta.warnings)) host.appendChild(note);
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
  lateral_length_unavailable: "unavailable \u2014 no lateral geometry",
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
export function pendingProductionPanel(warning: ApiWarning, ruleLink?: string): HTMLElement {
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
  const link = document.createElement("a");
  link.className = "gw-pending-rule";
  // The rule itself, not the collection: the well header already carries the link, and a
  // reader sent to a list of thirty-three rules has to find this one again.
  link.href = ruleLink ?? "/v1/conformance";
  link.textContent = "See the conformance rule that decided this.";
  body.append(detail, link);
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
