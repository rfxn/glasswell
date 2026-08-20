import { ApiError, getEnvelope } from "../api/client.ts";
import { derivationFor, labelFor, unwrap } from "../api/envelope.ts";
import type { Envelope, Figure } from "../api/envelope.ts";
import { renderChart } from "../chart/chart.ts";
import { toChartSeries } from "../chart/series.ts";
import type { ProductionData } from "../chart/series.ts";
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
  const heading = document.createElement("h2");
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

  if (detail.compute_crs) {
    facts.appendChild(term("Compute CRS", labelFor(well, "/compute_crs")));
    const definition = document.createElement("dd");
    definition.setAttribute("data-no-glossary", "");
    definition.textContent = `${detail.compute_crs} · stored ${detail.storage_crs}`;
    facts.appendChild(definition);
  }
  card.appendChild(facts);

  for (const warning of well.meta.warnings) card.appendChild(warningPanel(warning));

  const chartHost = document.createElement("section");
  chartHost.className = "gw-card-chart";
  chartHost.appendChild(placeholder("Loading production…"));
  card.appendChild(chartHost);

  container.replaceChildren(card);
  highlight(card, termIndex());

  try {
    const production = await getEnvelope<ProductionData>(`/v1/wells/${api10}/production`);
    const data = unwrap(production);
    if (data.streams.length === 0) {
      chartHost.replaceChildren(placeholder("No production has been reported for this well."));
      return;
    }
    renderChart(chartHost, toChartSeries(data), {
      onExplain: callbacks.onExplain,
      labelTermFor: (pointer) => labelFor(production, pointer),
    });
    for (const warning of production.meta.warnings) chartHost.appendChild(warningPanel(warning));
    highlight(chartHost, termIndex());
  } catch (error) {
    chartHost.replaceChildren(errorPanel(error, callbacks));
  }
}

function figureElement(figure: Figure, label: string, handle: string | null): HTMLElement {
  const element = document.createElement("gw-figure");
  element.setAttribute("value", figure.value);
  element.setAttribute("unit", figure.unit);
  element.setAttribute("handle", handle ?? figure.d ?? "");
  element.setAttribute("label", label);
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

function warningPanel(warning: { code: string; detail?: string; pointer?: string }): HTMLElement {
  const element = document.createElement("p");
  element.className = "gw-warning";
  element.textContent = `${warning.code}: ${warning.detail ?? ""}${
    warning.pointer ? ` (${warning.pointer})` : ""
  }`;
  return element;
}

export function errorPanel(error: unknown, callbacks: { onClose(): void }): HTMLElement {
  const element = document.createElement("div");
  element.className = "gw-error";
  const heading = document.createElement("h3");
  const body = document.createElement("p");
  if (error instanceof ApiError) {
    heading.textContent = `${error.problem.title} (${error.code})`;
    body.textContent = error.problem.detail ?? "";
    if (error.problem.status === 403) {
      body.textContent =
        "The API needs the owner key. Open this page with ?key=<GLASSWELL_OWNER_KEY> once and it is remembered.";
    }
    const link = document.createElement("a");
    link.href = error.problem.type;
    link.textContent = error.problem.type;
    element.append(heading, body, link);
  } else {
    heading.textContent = "Request failed";
    body.textContent = String(error);
    element.append(heading, body);
  }
  const close = document.createElement("button");
  close.type = "button";
  close.className = "gw-close";
  close.textContent = "×";
  close.addEventListener("click", callbacks.onClose);
  element.appendChild(close);
  return element;
}
