import { ApiError, getEnvelope } from "../api/client.ts";
import { derivationFor, labelFor, unwrap } from "../api/envelope.ts";
import type { Envelope, Figure } from "../api/envelope.ts";
import { renderChart } from "../chart/chart.ts";
import { toChartSeries } from "../chart/series.ts";
import type { ProductionData } from "../chart/series.ts";
import { focusPanel } from "../chrome/overlays.ts";
import { labelElement } from "../glossary/gw-term.ts";
import { highlight } from "../glossary/index.ts";
import { termIndex } from "../glossary/store.ts";
import { EXPLAIN_EVENT } from "./gw-figure.ts";
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
  compute_crs: string | null;
  storage_crs: string;
  effective_from: string;
  surface_point: { lon: number; lat: number } | null;
}

export interface CardCallbacks {
  onExplain(handle: string): void;
  onClose(): void;
  onFixKey?(): void;
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

  let well: Envelope<WellDetail>;
  try {
    well = await getEnvelope<WellDetail>(`/v1/wells/${api10}`);
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

  for (const panel of warningPanels(well.meta.warnings)) body.appendChild(panel);

  // Title outside the swappable body: the placeholder, the plot and an error all land in
  // .gw-frame-body, so none of them can take the frame's label down with them.
  const chartFrame = document.createElement("section");
  chartFrame.className = "gw-card-chart";
  const chartTitle = document.createElement("h3");
  chartTitle.className = "gw-frame-title";
  chartTitle.textContent = "Monthly production";
  const chartHost = document.createElement("div");
  chartHost.className = "gw-frame-body";
  chartHost.appendChild(placeholder("Loading production…"));
  chartFrame.append(chartTitle, chartHost);
  body.appendChild(chartFrame);

  container.replaceChildren(card);
  highlight(card, termIndex());
  focusPanel(container);

  try {
    const production = await getEnvelope<ProductionData>(`/v1/wells/${api10}/production`);
    const data = unwrap(production);
    if (data.streams.length === 0) {
      chartHost.replaceChildren(placeholder("No production has been reported for this well."));
      return;
    }
    chartTitle.replaceChildren(
      labelElement("Monthly production", labelFor(production, "/series")),
    );
    renderChart(chartHost, toChartSeries(data), {
      onExplain: callbacks.onExplain,
      labelTermFor: (pointer) => labelFor(production, pointer),
    });
    for (const panel of warningPanels(production.meta.warnings)) chartHost.appendChild(panel);
    highlight(chartHost, termIndex());
  } catch (error) {
    chartHost.replaceChildren(errorPanel(error, callbacks));
  }
}

/** The <dt> beside it is the label, so the chip carries it for assistive tech only. */
function figureElement(figure: Figure, label: string, handle: string | null): HTMLElement {
  const element = document.createElement("gw-figure");
  element.setAttribute("value", figure.value);
  element.setAttribute("unit", figure.unit);
  element.setAttribute("handle", handle ?? figure.d ?? "");
  element.setAttribute("label", label);
  element.setAttribute("label-hidden", "");
  if (figure.granularity) element.setAttribute("granularity", figure.granularity);
  if (figure.report_vintage) element.setAttribute("vintage", figure.report_vintage);
  return element;
}

function term(label: string, termId: string | null): HTMLElement {
  const element = document.createElement("dt");
  element.appendChild(labelElement(label, termId));
  return element;
}

function placeholder(text: string): HTMLElement {
  const element = document.createElement("p");
  element.className = "gw-placeholder";
  element.textContent = text;
  return element;
}

type ApiWarning = { code: string; detail?: string; pointer?: string };

/** One panel per code with its count: three identical warnings used to stack as a wall. */
function warningPanels(warnings: ApiWarning[]): HTMLElement[] {
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
  callbacks: { onClose(): void; onFixKey?(): void },
): HTMLElement {
  const element = document.createElement("div");
  element.className = "gw-error";
  const heading = document.createElement("h3");
  const body = document.createElement("p");
  if (error instanceof ApiError) {
    heading.textContent = `${error.problem.title} (${error.code})`;
    body.textContent = error.problem.detail ?? "";
    if (error.problem.status === 403) {
      body.textContent =
        "The API rejected this browser's owner key, or has never been given one.";
      if (callbacks.onFixKey) {
        const fix = document.createElement("button");
        fix.type = "button";
        fix.className = "gw-error-key";
        fix.textContent = "Enter or clear the key";
        fix.addEventListener("click", () => callbacks.onFixKey?.());
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
