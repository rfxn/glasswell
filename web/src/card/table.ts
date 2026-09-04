/**
 * The chart as a table, which is the accessibility requirement §9 makes a shipping one: a plot
 * a screen reader cannot read is a plot that answers nobody, and "the readout says the month"
 * answers one month at a time.
 *
 * Every column the plot draws is a column here, and every cell carries what the point carries:
 * the figure, its unit, the null-semantics class that says which absence an empty cell is, and
 * the point's own derivation handle. Nothing is computed here -- the running total is the
 * chart's and stays there, because a total in a table with a handle column beside it would
 * read as a figure with provenance.
 */
import { explainHandle } from "../chrome/handle.ts";
import { labelElement } from "../glossary/gw-term.ts";
import { formatMonth, nullSemantics } from "./format.ts";
import type { ChartSeries } from "../chart/series.ts";

export interface TableCallbacks {
  onExplain(handle: string): void;
  labelTermFor(pointer: string): string | null;
}

/** The months as rows, the streams as column groups. Returns the whole table element. */
export function seriesTable(chart: ChartSeries, callbacks: TableCallbacks): HTMLElement {
  const frame = document.createElement("div");
  frame.className = "gw-series-table";
  const table = document.createElement("table");

  const caption = document.createElement("caption");
  caption.textContent =
    `Production by month, ${chart.months.length} month${chart.months.length === 1 ? "" : "s"}` +
    ` shown, one row per month and one column group per stream.`;
  table.appendChild(caption);

  const head = document.createElement("thead");
  const first = document.createElement("tr");
  const month = document.createElement("th");
  month.scope = "col";
  month.rowSpan = 2;
  month.appendChild(labelElement("Month", callbacks.labelTermFor("/series/pm")));
  first.appendChild(month);
  const second = document.createElement("tr");
  for (const column of chart.columns) {
    const group = document.createElement("th");
    group.scope = "colgroup";
    group.colSpan = 3;
    group.appendChild(
      labelElement(
        `${column.label} (${column.unit})`,
        callbacks.labelTermFor(`/series/${column.key}`),
      ),
    );
    first.appendChild(group);
    for (const label of ["Value", "How it was filed", "Lineage"]) {
      const cell = document.createElement("th");
      cell.scope = "col";
      cell.textContent = label;
      second.appendChild(cell);
    }
  }
  head.append(first, second);
  table.appendChild(head);

  const body = document.createElement("tbody");
  chart.months.forEach((label, index) => {
    const row = document.createElement("tr");
    const when = document.createElement("th");
    when.scope = "row";
    when.setAttribute("data-no-glossary", "");
    when.textContent = formatMonth(label);
    row.appendChild(when);
    for (const column of chart.columns) {
      const value = document.createElement("td");
      value.className = "gw-table-value";
      value.setAttribute("data-no-glossary", "");
      const raw = column.raw[index];
      // The unit rides every cell rather than the header alone: a copied row keeps it, and a
      // row read one at a time by a screen reader never loses it.
      value.textContent = raw === null || raw === undefined ? "" : `${raw} ${column.unit}`;
      const state = document.createElement("td");
      const described = nullSemantics(column.nullSemantics[index] ?? "");
      state.className = "gw-table-state";
      state.textContent = described.label;
      state.title = described.title;
      const lineage = document.createElement("td");
      lineage.className = "gw-table-handle";
      const handle = column.handles[index] ?? column.handle;
      if (handle) {
        lineage.appendChild(
          explainHandle({
            handle,
            label: `${column.label} for ${formatMonth(label)}`,
            activate: (id) => callbacks.onExplain(id),
          }),
        );
      }
      row.append(value, state, lineage);
    }
    body.appendChild(row);
  });
  table.appendChild(body);
  frame.appendChild(table);
  return frame;
}
