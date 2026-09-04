/**
 * Export, with the rule that governs every format: an export carries the handles or it is not
 * shipped.
 *
 * A CSV without the handle column is the artifact that ends up in a model with its provenance
 * stripped, which is the thing this product exists to prevent. So each row carries the value,
 * the unit, the null-semantics class, the report vintage and the derivation handle, and the
 * header block carries the api10, the basis and grain in force, the normalisation arm, the
 * `as_of` resolved and the URL that reproduces the view.
 *
 * The running total is not a column. It is a number the client computed over the points on
 * screen; putting it in a file beside a handle column would give it provenance it does not
 * have, which is the same ruling the chart applies by refusing it a ring.
 */
import type { Envelope } from "../api/envelope.ts";
import type { ChartSeries } from "../chart/series.ts";

export interface ExportContext {
  api10: string;
  /** What the reader is looking at, so the file can be re-fetched into the same view. */
  url: string;
  asOfResolved: string | null;
  normalization: string | null;
  grain: string;
}

const HEADER_PREFIX = "# ";

function comment(line: string): string {
  return `${HEADER_PREFIX}${line}`;
}

function escape(value: string): string {
  return /[",\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

/** One row per month per stream: long, because a wide file loses the per-cell handle. */
export function toCsv(chart: ChartSeries, context: ExportContext): string {
  const head = [
    comment(`api10=${context.api10}`),
    comment(`grain=${context.grain}`),
    comment(`normalization=${context.normalization ?? "none"}`),
    comment(`as_of_resolved=${context.asOfResolved ?? "latest"}`),
    comment(`reproduce=${context.url}`),
    comment(
      "every row carries the derivation handle of the point it reports; the running total on" +
        " the page is computed in the browser and is deliberately not a column here",
    ),
    ["month", "stream", "value", "unit", "null_semantics", "report_vintage", "handle"].join(","),
  ];
  const rows: string[] = [];
  chart.months.forEach((month, index) => {
    for (const column of chart.columns) {
      rows.push(
        [
          month,
          column.stream,
          column.raw[index] ?? "",
          column.unit,
          column.nullSemantics[index] ?? "",
          column.vintages[index] ?? "",
          column.handles[index] ?? column.handle ?? "",
        ]
          .map((cell) => escape(String(cell)))
          .join(","),
      );
    }
  });
  return [...head, ...rows].join("\n") + "\n";
}

/** The served envelope for the window, unmodified: the cheapest format to be correct. */
export function toJson(envelope: Envelope<unknown>): string {
  return `${JSON.stringify(envelope, null, 2)}\n`;
}

function download(name: string, body: string, type: string): void {
  const blob = new Blob([body], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

export interface ExportCallbacks {
  series(): ChartSeries | null;
  envelope(): Envelope<unknown> | null;
  context(): ExportContext;
}

/** Two controls, one rule: what leaves the page carries what the page carries. */
export function exportControls(callbacks: ExportCallbacks): HTMLElement {
  const group = document.createElement("div");
  group.className = "gw-export";
  group.setAttribute("role", "group");
  group.setAttribute("aria-label", "Export the months on screen");

  const csv = document.createElement("button");
  csv.type = "button";
  csv.className = "gw-export-csv";
  csv.textContent = "CSV";
  csv.title = "One row per month per stream, each with its unit, its class and its handle.";
  csv.addEventListener("click", () => {
    const chart = callbacks.series();
    if (!chart) return;
    const context = callbacks.context();
    download(`${context.api10}-production.csv`, toCsv(chart, context), "text/csv");
  });

  const json = document.createElement("button");
  json.type = "button";
  json.className = "gw-export-json";
  json.textContent = "JSON";
  json.title = "The served envelope for this window, unmodified: meta, _lineage, _units, _basis.";
  json.addEventListener("click", () => {
    const envelope = callbacks.envelope();
    if (!envelope) return;
    download(
      `${callbacks.context().api10}-production.json`,
      toJson(envelope),
      "application/json",
    );
  });

  const note = document.createElement("p");
  note.className = "gw-note gw-export-note";
  note.textContent =
    "Both carry the derivation handle of every point and the URL that reproduces this view." +
    " The running total on the page is not a column: it is computed here from the points" +
    " shown, and a file cannot carry provenance it never had.";

  group.append(csv, json, note);
  return group;
}
