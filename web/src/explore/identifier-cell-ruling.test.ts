// @vitest-environment happy-dom
import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { buildCatalogue } from "./catalogue.ts";
import { isJoinField } from "./detail/chips.ts";
import { renderCell } from "./grid/cells.ts";
import { columnsFor } from "./grid/columns.ts";
import { extractRows } from "./grid/rows.ts";
import { quarantineEnvelope } from "./fixtures.ts";

/**
 * C8's D1, ruled by C10.
 *
 * §3.3 reads "every id-typed cell is a chip". C8 built them in the record panel only and asked
 * C10 to rule on the grid, on the premise that C10's map affordance would land in the same
 * cell. **The premise does not hold**: `cells.ts` hands the map crossing to the *geometry*
 * kind, not the identifier kind, so the two never share a cell and the question stands alone.
 *
 * Ruled: the grid's identifier cells carry no chip. The record panel is where a reader asks
 * "what is this row", and that is where the hops are. Three reasons, each asserted below so
 * the ruling is a test rather than a paragraph:
 *
 *   1. A chip is an `<a>`, and `grid.ts`'s `interactive()` yields the row's own click to any
 *      anchor. Chipping every identifier cell turns most of a quarantine row into dead zones
 *      for the affordance that opens it.
 *   2. An identifier track is `max-content`, so it would widen to the target dataset's title
 *      rather than to the id — pushing real columns off the right edge the grid already has
 *      to apologise for.
 *   3. `joinsFor` is per value: a 60-row window over four id columns is 240 resolutions for
 *      hops a reader can only take one of.
 *
 * The geometry cell is the exception that proves it, and is ruled the other way in
 * `detail.test.ts`: it has no value to compete with, because a coordinate is never printed.
 */

const SNAPSHOT = JSON.parse(readFileSync("../tests/contract/openapi_snapshot.json", "utf8"));
const CATALOGUE = buildCatalogue(SNAPSHOT);

function quarantineCells() {
  const dataset = CATALOGUE.datasets.find((candidate) => candidate.id === "quarantine");
  if (!dataset) throw new Error("no quarantine dataset");
  const envelope = quarantineEnvelope as { data: unknown; meta: { labels: Record<string, string> } };
  const columns = columnsFor(dataset, SNAPSHOT, envelope);
  const rows = extractRows(dataset, envelope.data, columns.map((column) => column.pointer));
  return { dataset, columns, rows, data: envelope.data };
}

describe("the grid's identifier cells carry no hop — C8 D1, ruled here", () => {
  it("has identifier columns that would resolve hops, so the ruling is not vacuous", () => {
    const { columns } = quarantineCells();
    const identifiers = columns.filter((column) => column.kind === "identifier");

    expect(identifiers.map((column) => column.name)).toContain("rule_id");
    expect(identifiers.filter((column) => isJoinField(column.pointer, CATALOGUE.datasets)).length)
      .toBeGreaterThan(1);
  });

  it("renders the id and nothing else in the cell", () => {
    const { columns, rows, data } = quarantineCells();
    const row = rows[0];
    if (!row) throw new Error("no quarantine row");

    for (const column of columns.filter((candidate) => candidate.kind === "identifier")) {
      const cell = renderCell(column, { data, row });
      expect(cell.querySelectorAll("a"), column.name).toHaveLength(0);
      expect(cell.querySelectorAll(".gw-join-chip"), column.name).toHaveLength(0);
    }
  });

  it("leaves the whole row clickable, which is the affordance a chip would have taken", () => {
    const { columns, rows, data } = quarantineCells();
    const row = rows[0];
    if (!row) throw new Error("no quarantine row");
    const identifier = columns.find((column) => column.kind === "identifier");
    if (!identifier) throw new Error("no identifier column");

    // `grid.ts:interactive()` yields the row's click to `a, button, gw-term, gw-figure,
    // gw-count`. The rendered cell matching none of them is what keeps the row expandable.
    const cell = renderCell(identifier, { data, row });
    expect(cell.querySelector("a, button, gw-term, gw-figure, gw-count")).toBeNull();
  });

  it("keeps the geometry kind as the one cell a crossing does land in", () => {
    const point = { lon: -102.8, lat: 47.8 };
    const row = {
      id: "one",
      index: 0,
      elementIndex: 0,
      elementPointer: "/0",
      cells: {
        "/surface_point": {
          pointer: "/surface_point",
          dataPointer: "/0/surface_point",
          namespace: "element" as const,
          value: point,
          companions: {},
        },
      },
    };
    const geometry = renderCell(
      {
        pointer: "/surface_point",
        name: "surface_point",
        labelPointer: "/surface_point",
        namespace: "element",
        kind: "geometry",
        binding: "unbound",
        termId: null,
        reason: null,
        hidden: false,
      },
      { data: {}, row },
    );

    // The value is a point and the cell still refuses to print it: the crossing in the record
    // panel is what reads it, which is why that cell is ruled the other way.
    expect(geometry.textContent).toContain("on the map");
    expect(geometry.textContent).not.toContain("-102.8");
  });
});
