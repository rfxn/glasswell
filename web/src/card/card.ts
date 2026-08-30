import "./gw-figure.ts";

import { ApiError, getEnvelope } from "../api/client.ts";
import { derivationFor, labelFor, unwrap } from "../api/envelope.ts";
import type { Envelope, Figure } from "../api/envelope.ts";
import { readState } from "../app/state.ts";
import { toChartSeries } from "../chart/series.ts";
import type { ProductionData } from "../chart/series.ts";
import { EXPLAIN_EVENT, explainHandle } from "../chrome/handle.ts";
import { focusPanel } from "../chrome/overlays.ts";
import { crossingLink, openThisSeries, rowsForThisWell } from "../explore/bridge.ts";
import { labelElement } from "../glossary/gw-term.ts";
import { highlight } from "../glossary/index.ts";
import { termIndex } from "../glossary/store.ts";
import { formatVintage } from "./format.ts";

export interface WellDetail {
  api10: string;
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

export interface CompletionContext {
  api10: string;
  design_availability: "not_promoted";
  events: CompletionEvent[];
  pools: CompletionPool[];
}

export interface CardCallbacks {
  onExplain(handle: string): void;
  onClose(): void;
  onSignIn?(): void;
  onLocated?(point: { lon: number; lat: number }): void;
  onVintage?(resolved: string | null): void;
}

const HEADER_FIELDS: [keyof WellDetail, string, string][] = [
  ["operator_name_reported", "Operator", "/operator_name_reported"],
  ["status_canonical", "Status", "/status_canonical"],
  ["county_code_at_permit", "County code", "/county_code_at_permit"],
  ["land_unit_label", "Land unit", "/land_unit_label"],
  ["spud_date", "Spud date", "/spud_date"],
  ["basin", "Basin", "/basin"],
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
  header.appendChild(api);

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

  const facts = document.createElement("dl");
  facts.className = "gw-facts";
  for (const [field, label, pointer] of HEADER_FIELDS) {
    const value = detail[field];
    if (value === null || value === undefined || value === "") continue;
    facts.appendChild(term(label, labelFor(well, pointer)));
    const definition = document.createElement("dd");
    definition.textContent = String(value);
    facts.appendChild(definition);
  }
  if (detail.confidential_flag) {
    facts.appendChild(term("Confidential", labelFor(well, "/confidential_flag")));
    const definition = document.createElement("dd");
    definition.textContent = "withheld by the regulator";
    facts.appendChild(definition);
  }
  facts.appendChild(term("Laterals", null));
  const laterals = document.createElement("dd");
  laterals.textContent = String(detail.lateral_count);
  facts.appendChild(laterals);

  if (detail.lateral_length_ft) {
    facts.appendChild(term("Lateral length", labelFor(well, "/lateral_length_ft")));
    const definition = document.createElement("dd");
    definition.appendChild(
      figureElement(detail.lateral_length_ft, "lateral length", derivationFor(detail, "/lateral_length_ft")),
    );
    facts.appendChild(definition);
  }

  if (detail.total_depth_ft) {
    facts.appendChild(term("Total depth", labelFor(well, "/total_depth_ft")));
    const definition = document.createElement("dd");
    definition.appendChild(
      figureElement(detail.total_depth_ft, "total depth", derivationFor(detail, "/total_depth_ft")),
    );
    facts.appendChild(definition);
  }

  if (detail.completion_date) {
    facts.appendChild(term("Completed", null));
    const definition = document.createElement("dd");
    definition.setAttribute("data-no-glossary", "");
    definition.textContent = formatVintage(detail.completion_date);
    facts.appendChild(definition);
  }

  facts.appendChild(term("As of", null));
  const asOfValue = document.createElement("dd");
  asOfValue.textContent = `${formatVintage(well.meta.as_of.resolved)} (requested ${well.meta.as_of.requested})`;
  facts.appendChild(asOfValue);
  callbacks.onVintage?.(well.meta.as_of.resolved);
  if (detail.surface_point) callbacks.onLocated?.(detail.surface_point);

  if (detail.compute_crs) {
    facts.appendChild(term("Compute CRS", labelFor(well, "/compute_crs")));
    const definition = document.createElement("dd");
    definition.setAttribute("data-no-glossary", "");
    definition.textContent = `${detail.compute_crs} · stored ${detail.storage_crs}`;
    facts.appendChild(definition);
  }
  body.appendChild(facts);

  // Everything except the codes a dedicated panel already renders, or the card shows the raw
  // internal warning line immediately above the polished version of the same sentence.
  const panelled = new Set([PENDING_ALLOCATION]);
  const generic = well.meta.warnings.filter((warning) => !panelled.has(warning.code));
  for (const panel of warningPanels(generic)) body.appendChild(panel);

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
  contextHost.appendChild(placeholder("Loading completion and formation context…"));
  contextFrame.append(contextTitle, contextHost);
  body.appendChild(contextFrame);

  const contextRequest = loadCompletionContext(
    contextHost,
    well.links?.["completions"] ?? `/v1/wells/${api10}/completions`,
    api10,
    asOfQuery,
  );

  let neighborRequest: Promise<void> = Promise.resolve();
  const neighborPath = well.links?.["neighbors"];
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
    neighborHost.appendChild(placeholder("Loading physical neighbours…"));
    neighborFrame.append(neighborTitle, neighborHost);
    body.appendChild(neighborFrame);
    neighborRequest = import("./neighbors.ts").then(({ loadNeighborContext }) =>
      loadNeighborContext(neighborHost, neighborPath, api10, { ...asOfQuery, limit: "5" }),
    );
  }

  // A lease-reporting jurisdiction has no observed well-level series, so the card says that
  // instead of drawing an empty chart: "no production has been reported" would be false about
  // a Texas well whose lease reports every month (DIR-3, cr_tx_allocation_scope_1).
  const pending = well.meta.warnings.find((warning) => warning.code === PENDING_ALLOCATION);
  if (pending) {
    container.replaceChildren(card);
    card.appendChild(pendingProductionPanel(pending, well.links?.["reporting_rule"] ?? undefined));
    highlight(card, termIndex());
    focusPanel(container);
    await Promise.all([contextRequest, neighborRequest]);
    return;
  }

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
  chartNotes.className = "gw-chart-notes";
  chartFrame.append(chartTitle, chartHost, chartNotes);
  body.appendChild(chartFrame);

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
        chartHost.replaceChildren(placeholder("No production has been reported for this well."));
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
      for (const panel of warningPanels(production.meta.warnings)) chartNotes.appendChild(panel);
      highlight(chartFrame, termIndex());
    } catch (error) {
      chartHost.replaceChildren(errorPanel(error, callbacks));
    }
  })();

  await Promise.all([contextRequest, neighborRequest, productionRequest]);
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
      context.design_availability !== "not_promoted" ||
      !Array.isArray(context.events) ||
      !Array.isArray(context.pools)
    ) {
      throw new TypeError("Completion context did not match the required well and collections");
    }
    host.replaceChildren(completionContextBody(context, envelope));
    for (const panel of warningPanels(envelope.meta.warnings)) host.appendChild(panel);
    host.dataset["state"] =
      context.events.length === 0 && context.pools.length === 0
        ? "empty"
        : "populated";
    highlight(host, termIndex());
  } catch {
    host.replaceChildren(
      placeholder(
        "Completion and formation context is unavailable because the API response could not be used.",
      ),
    );
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
  if (context.events.length === 0 && context.pools.length === 0) {
    fragment.appendChild(
      placeholder(
        "No source-reported completion events or completion-pool mappings are available for this well.",
      ),
    );
  } else {
    fragment.append(
      contextGroup(
        "Completion events",
        labelFor(envelope, "/events/0/event_kind"),
        context.events.map(completionEventItem),
        "No source-reported completion event is available for this well.",
      ),
      contextGroup(
        "Reported pools",
        labelFor(envelope, "/pools/0/pool_reported"),
        context.pools.map(completionPoolItem),
        "No source-reported completion-pool mapping is available for this well.",
      ),
    );
  }

  const scope = document.createElement("p");
  scope.className = "gw-context-scope";
  scope.textContent =
    "Completion design is not promoted; no design measurements or formation tops are served here.";
  fragment.appendChild(scope);
  return fragment;
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
    group.appendChild(placeholder(emptyText));
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
    definition.textContent = "unavailable";
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

function unavailableReason(
  value: string | null,
  semantics: CompletionPool["formation_null_semantics"],
): string {
  if (value !== null && value !== "") return value;
  if (semantics === "pool_not_reported") return "unavailable: pool not reported";
  if (semantics === "alias_unavailable") return "unavailable: alias unavailable";
  return "unavailable: no group assigned";
}

function lineageButton(handle: string, label: string): HTMLButtonElement {
  return explainHandle({ handle, label: label.toLowerCase() });
}

/** The <dt> beside it is the label, so the chip carries it for assistive tech only. */
export function figureElement(figure: Figure, label: string, handle: string | null): HTMLElement {
  const element = document.createElement("gw-figure");
  element.setAttribute("value", figure.value);
  element.setAttribute("unit", figure.unit);
  element.setAttribute("handle", handle ?? figure.d ?? "");
  element.setAttribute("label", label);
  element.setAttribute("label-hidden", "");
  if (figure.granularity) element.setAttribute("granularity", figure.granularity);
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

/** One panel per code with its count: three identical warnings used to stack as a wall. */
export function warningPanels(warnings: ApiWarning[]): HTMLElement[] {
  const grouped = new Map<string, ApiWarning[]>();
  for (const warning of warnings) {
    grouped.set(warning.code, [...(grouped.get(warning.code) ?? []), warning]);
  }
  return [...grouped.entries()].map(([code, group]) => {
    const element = document.createElement("p");
    element.className = "gw-warning";
    const count = group.length > 1 ? ` ×${group.length}` : "";
    const pointers = group
      .map((warning) => warning.pointer)
      .filter((pointer): pointer is string => Boolean(pointer))
      .join(", ");
    element.textContent =
      `${code}${count}: ${group[0]?.detail ?? ""}` + (pointers ? ` (${pointers})` : "");
    return element;
  });
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
