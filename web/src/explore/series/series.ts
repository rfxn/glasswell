/**
 * SB-08 §2.6's "Open this series", answered with the series. The crossing already landed the
 * reader on the months as rows; what the wider surface adds is the plot the card cannot fit,
 * drawn from the response the grid already fetched rather than from a second request.
 */
import "./series.css";

import { labelFor } from "../../api/envelope.ts";
import type { Envelope } from "../../api/envelope.ts";
import { EXPLAIN_EVENT } from "../../chrome/handle.ts";
import { renderChart } from "../../chart/chart.ts";
import { toChartSeries } from "../../chart/series.ts";
import type { ProductionData } from "../../chart/series.ts";

export interface SeriesPanelOptions {
  envelope: Envelope<unknown>;
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

/**
 * The one shape `toChartSeries` reads. A pooled response carries its series under `pools`, and
 * feeding it here would draw an empty axis rather than refuse — so this is a check, not a cast.
 */
export function productionSeries(data: unknown): ProductionData | null {
  if (typeof data !== "object" || data === null || Array.isArray(data)) return null;
  const record = data as Record<string, unknown>;
  const series = record["series"];
  if (typeof series !== "object" || series === null || Array.isArray(series)) return null;
  if (!isStringArray((series as Record<string, unknown>)["pm"])) return null;
  if (!isStringArray(record["streams"])) return null;
  for (const sidecar of ["_lineage", "_units", "_basis"]) {
    const value = record[sidecar];
    if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  }
  return record as unknown as ProductionData;
}

/**
 * §2.5's 390 posture, which the grid already takes: below 520 the panel's band is 38% of the
 * viewport and the API guide is the product, so a 260 px plot would be a scrollport inside a
 * scrollport. It says where the same chart is readable instead of shrinking into unusable.
 */
function narrowNotice(): HTMLElement {
  const element = document.createElement("p");
  element.className = "gw-explore-series-narrow";
  element.textContent =
    "This plot needs a wider window. The well card draws the same series, with the same" +
    " month readout, at every width.";
  return element;
}

export function renderSeriesPanel(host: HTMLElement, options: SeriesPanelOptions): boolean {
  const series = productionSeries(options.envelope.data);
  if (!series) return false;

  const panel = document.createElement("section");
  panel.className = "gw-explore-series";
  const title = document.createElement("h3");
  title.className = "gw-frame-title";
  title.textContent = "Monthly production";
  const body = document.createElement("div");
  body.className = "gw-frame-body";
  const note = document.createElement("p");
  note.className = "gw-explore-series-note";
  // The facets are the window here, and they ride the URL — so the chart says which controls
  // move it rather than growing a second, unshareable one of its own.
  note.textContent =
    "Narrow this plot with the stream, from and to filters above; they travel in the link.";
  panel.append(title, note, narrowNotice(), body);
  host.appendChild(panel);

  renderChart(
    body,
    toChartSeries(series),
    {
      onExplain: (handle) => {
        document.dispatchEvent(
          new CustomEvent(EXPLAIN_EVENT, { detail: { handle }, bubbles: true }),
        );
      },
      labelTermFor: (pointer) => labelFor(options.envelope, pointer),
    },
    { span: "served" },
  );
  return true;
}
