// @vitest-environment happy-dom
import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { buildCatalogue } from "../catalogue.ts";
import type { CatalogueDataset } from "../catalogue.ts";
import { productionEnvelope, quarantineEnvelope, vintagesEnvelope } from "../fixtures.ts";
import { renderCell } from "./cells.ts";
import { columnsFor } from "./columns.ts";
import { extractRows } from "./rows.ts";

const SNAPSHOT = JSON.parse(readFileSync("../tests/contract/openapi_snapshot.json", "utf8"));
const CATALOGUE = buildCatalogue(SNAPSHOT);

function dataset(id: string): CatalogueDataset {
  const found = CATALOGUE.datasets.find((candidate) => candidate.id === id);
  if (!found) throw new Error(`no dataset ${id}`);
  return found;
}

function cellsOf(id: string, envelope: { data: unknown; meta: { labels: Record<string, string> } }) {
  const columns = columnsFor(dataset(id), SNAPSHOT, envelope);
  const rows = extractRows(dataset(id), envelope.data, columns.map((column) => column.pointer));
  return (rowIndex: number, pointer: string): HTMLElement => {
    const column = columns.find((candidate) => candidate.pointer === pointer);
    const row = rows[rowIndex];
    if (!column || !row) throw new Error(`no cell ${pointer} at row ${rowIndex}`);
    return renderCell(column, { data: envelope.data, row });
  };
}

describe("a cell renders the fact the API stated, never a tidier one (§3.2)", () => {
  it("renders a projected volume as a figure carrying the handle its sidecar supplies", () => {
    const cell = cellsOf("production", productionEnvelope)(3, "/oil_bbl");
    const figure = cell.querySelector("gw-figure") as HTMLElement;

    expect(figure.getAttribute("value")).toBe(productionEnvelope.data.series.oil_bbl[3]);
    expect(figure.getAttribute("unit")).toBe("bbl");
    expect(figure.getAttribute("handle")).toBe(
      productionEnvelope.data._lineage["series.oil_bbl.3"],
    );
    // The report vintage is the column's own companion, not a separate column.
    expect(figure.getAttribute("vintage")).toBe(
      productionEnvelope.data.series.oil_bbl_report_vintage[3],
    );
    expect(figure.getAttribute("granularity")).toBe("well_observed");
  });

  it("renders an exempt number as a count carrying the value the response served", () => {
    const cell = cellsOf("quarantine", quarantineEnvelope)(0, "/occurrence_count");
    const count = cell.querySelector("gw-count") as HTMLElement;

    expect(count.getAttribute("value")).toBe(String(quarantineEnvelope.data[0]?.occurrence_count));
    // One or the other, always: an unreasoned count that also lacks the marker throws.
    expect(count.hasAttribute("reason") !== count.hasAttribute("no-reason")).toBe(true);
  });

  it("quotes the reason where the document serves one and states the gap where it does not", () => {
    const reason = "how many fetches re-presented the row; bookkeeping, not a measurement";
    const served = JSON.parse(JSON.stringify(SNAPSHOT));
    const bare = JSON.parse(JSON.stringify(SNAPSHOT));
    const property = "occurrence_count";
    served.components.schemas.QuarantineRow.properties[property]["x-glasswell-not-a-figure"] =
      reason;
    delete bare.components.schemas.QuarantineRow.properties[property]["x-glasswell-not-a-figure"];

    const render = (document_: unknown): HTMLElement => {
      const columns = columnsFor(dataset("quarantine"), document_, quarantineEnvelope);
      const rows = extractRows(dataset("quarantine"), quarantineEnvelope.data, [`/${property}`]);
      const column = columns.find((candidate) => candidate.pointer === `/${property}`);
      return renderCell(column as never, {
        data: quarantineEnvelope.data,
        row: rows[0] as never,
      });
    };

    expect(render(served).querySelector("gw-count")?.getAttribute("reason")).toBe(reason);
    expect(render(bare).querySelector("gw-count")?.hasAttribute("no-reason")).toBe(true);
    // The unreasoned wording is gw-count's own and is asserted there; the element renders on
    // connection, so a detached cell has attributes and no children to read it off.
    expect(render(bare).querySelector("gw-count")?.getAttribute("reason")).toBeNull();
  });

  it("promotes a counted column to a handled figure the moment its sidecars arrive (T1)", () => {
    // The shape C3 lands on /v1/vintages: a `_lineage` handle for the promotion, and the unit
    // R6 needs beside it. No client change is required for the cell to become a figure, and
    // this is the arm that proves it rather than the note that promises it.
    const promoted = JSON.parse(JSON.stringify(vintagesEnvelope));
    promoted.data = promoted.data.map((row: Record<string, unknown>) => ({
      ...row,
      _lineage: { rows_appended: "drv_promotion_handle#vintage=1" },
      _units: { rows_appended: "rows" },
    }));

    const before = cellsOf("vintages", vintagesEnvelope)(0, "/rows_appended");
    const after = cellsOf("vintages", promoted)(0, "/rows_appended");

    expect(before.querySelector("gw-count")).not.toBeNull();
    expect(after.querySelector("gw-count")).toBeNull();
    expect(after.querySelector("gw-figure")?.getAttribute("handle")).toBe(
      "drv_promotion_handle#vintage=1",
    );
  });

  it("keeps a handle that arrives without a unit rather than dropping it on the floor (O-1)", () => {
    const handled = JSON.parse(JSON.stringify(vintagesEnvelope));
    handled.data = handled.data.map((row: Record<string, unknown>) => ({
      ...row,
      _lineage: { rows_appended: "drv_promotion_handle#vintage=1" },
    }));

    const cell = cellsOf("vintages", handled)(0, "/rows_appended");

    // `formatFigure` refuses a unit-less figure, so this cannot become one until O-1 lands.
    expect(cell.querySelector("gw-figure")).toBeNull();
    expect(cell.querySelector("gw-count")?.getAttribute("data-handle")).toBe(
      "drv_promotion_handle#vintage=1",
    );
  });

  it("distinguishes an absent field from a null one, because they are different facts", () => {
    const columns = columnsFor(dataset("quarantine"), SNAPSHOT, quarantineEnvelope);
    const notes = columns.find((column) => column.pointer === "/rule_id");
    const rows = extractRows(dataset("quarantine"), quarantineEnvelope.data, ["/rule_id"]);
    const base = rows[0] as NonNullable<(typeof rows)[0]>;
    const cell = base.cells["/rule_id"] as NonNullable<(typeof base.cells)[string]>;
    const nulled = { ...base, cells: { "/rule_id": { ...cell, value: null, companions: {} } } };

    const absent = renderCell(notes as never, {
      data: quarantineEnvelope.data,
      row: { ...base, cells: {} },
    });
    const isNull = renderCell(notes as never, { data: quarantineEnvelope.data, row: nulled });

    expect(absent.querySelector(".gw-cell-absent")?.getAttribute("title")).toMatch(/absent from/);
    expect(isNull.querySelector(".gw-cell-absent")?.getAttribute("title")).toMatch(
      /stated no null semantics/,
    );
  });

  it("renders each null semantics as its own fact, never as a shared blank", () => {
    const withheld = JSON.parse(JSON.stringify(productionEnvelope));
    const states = ["reported_zero", "no_report", "withheld", "multi_pool_pending"];
    withheld.data.series.oil_bbl_null_semantics = [...states, "reported", "reported"];

    const cell = cellsOf("production", withheld);
    const rendered = states.map((_, index) => {
      const strip = cell(index, "/oil_bbl").querySelector(".gw-state") as HTMLElement;
      const swatch = strip.querySelector(".gw-state-mark") as HTMLElement;
      // Only what a reader can perceive: the swatch, the word and the explanation. A `data-`
      // attribute that differs while all three agree is four facts nobody can tell apart, and
      // a mutation that collapses the mark survived this assertion until it was written this way.
      return `${swatch.className}|${strip.textContent}|${strip.title}`;
    });

    expect(new Set(rendered).size).toBe(states.length);
    // `reported` is the unremarkable case and earns no chip; the other four each earn their own.
    expect(cell(4, "/oil_bbl").querySelector(".gw-state")).toBeNull();
  });

  it("renders an identifier as monospace the glossary highlighter will not scan", () => {
    const cell = cellsOf("quarantine", quarantineEnvelope)(0, "/quarantine_id");

    expect(cell.querySelector("code")?.hasAttribute("data-no-glossary")).toBe(true);
    expect(cell.querySelector("code")?.textContent).toBe(quarantineEnvelope.data[0]?.quarantine_id);
  });

  it("binds an enum value to the column's own term where the column is bound", () => {
    const cell = cellsOf("quarantine", quarantineEnvelope)(0, "/state");

    expect(cell.querySelector("gw-term")?.getAttribute("term-id")).toBe("gt_quarantine");
    expect(cell.querySelector("gw-term")?.textContent).toBe(quarantineEnvelope.data[0]?.state);
  });

  it("splits a timestamp so the date reads first and the clock stays subordinate", () => {
    const cell = cellsOf("quarantine", quarantineEnvelope)(0, "/last_seen_at");

    expect(cell.querySelector("time")?.textContent).toBe("2026-08-01");
    expect(cell.querySelector(".gw-cell-clock")?.textContent).toBe("05:02");
    expect(cell.querySelector("time")?.getAttribute("datetime")).toBe(
      quarantineEnvelope.data[0]?.last_seen_at,
    );
  });
});
