// @vitest-environment happy-dom
import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { buildCatalogue } from "../catalogue.ts";
import type { CatalogueDataset } from "../catalogue.ts";
import {
  healthEnvelope,
  manifestsEnvelope,
  productionEnvelope,
  quarantineEnvelope,
  serviceIndexEnvelope,
  vintagesEnvelope,
  wellsEnvelope,
} from "../fixtures.ts";
import { COLUMN_KINDS, columnsFor, coverageOf, headerTreatment, renderHeader } from "./columns.ts";

const SNAPSHOT = JSON.parse(readFileSync("../tests/contract/openapi_snapshot.json", "utf8"));
const CATALOGUE = buildCatalogue(SNAPSHOT);

function dataset(id: string): CatalogueDataset {
  const found = CATALOGUE.datasets.find((candidate) => candidate.id === id);
  if (!found) throw new Error(`the committed document declares no dataset ${id}`);
  return found;
}

function kinds(id: string, envelope: { meta: { labels: Record<string, string> } }) {
  const found: Record<string, string> = {};
  for (const column of columnsFor(dataset(id), SNAPSHOT, envelope)) found[column.pointer] = column.kind;
  return found;
}

describe("the grid's column kinds come from the document, not from the values (§3.2)", () => {
  it("classifies every kind the specification names, on a real column of a real dataset", () => {
    const quarantine = kinds("quarantine", quarantineEnvelope);
    const wells = kinds("wells", wellsEnvelope);
    const production = kinds("production", productionEnvelope);
    const problems = kinds("problems", serviceIndexEnvelope);

    expect(quarantine["/quarantine_id"]).toBe("identifier");
    expect(quarantine["/state"]).toBe("enum");
    expect(quarantine["/stage"]).toBe("enum");
    expect(quarantine["/occurrence_count"]).toBe("count");
    expect(quarantine["/last_seen_at"]).toBe("timestamp");
    expect(wells["/well_name"]).toBe("prose");
    expect(wells["/api10"]).toBe("identifier");
    expect(wells["/spud_date"]).toBe("timestamp");
    // A pivot's value columns carry `_lineage`, `_units` and `_basis`: they are figures by
    // declaration, even though the wire form is an array of strings.
    expect(production["/oil_bbl"]).toBe("figure");
    // P6: the axis is the row key, not a value, and it renders as one.
    expect(production["/pm"]).toBe("identifier");
    expect(problems["/status"]).toBe("count");
  });

  it("renders geometry as an affordance and never as coordinates in a cell", () => {
    const wells = dataset("wells");
    const withGeometry = columnsFor({ ...wells, columns: { ...wells.columns, default: undefined } },
      SNAPSHOT, wellsEnvelope);
    const geometry = withGeometry.filter((column) => column.kind === "geometry");

    // The full-schema fallback is where geometry columns actually surface; the default six
    // do not include one, and a test that asserted over them would assert nothing.
    expect(withGeometry.length).toBeGreaterThan(6);
    expect(geometry.map((column) => column.pointer)).toContain("/links");
  });

  it("covers exactly the kinds it declares, so a new kind cannot arrive unnamed", () => {
    const seen = new Set<string>();
    for (const [id, envelope] of [
      ["quarantine", quarantineEnvelope],
      ["wells", wellsEnvelope],
      ["production", productionEnvelope],
      ["problems", serviceIndexEnvelope],
      ["manifests", manifestsEnvelope],
      ["sources", healthEnvelope],
    ] as const) {
      for (const column of columnsFor(dataset(id), SNAPSHOT, envelope)) seen.add(column.kind);
    }

    for (const kind of seen) expect(COLUMN_KINDS).toContain(kind);
    expect(seen.size).toBeGreaterThanOrEqual(5);
  });
});

describe("a column header binds where a binding exists and says so where it does not (B4)", () => {
  it("prefers meta.labels over the schema binding, being per-response and more specific", () => {
    const labelled = {
      meta: { labels: { "/reason_code": "gt_per_response_wins" } },
    };
    const [reason] = columnsFor(dataset("quarantine"), SNAPSHOT, labelled).filter(
      (column) => column.pointer === "/reason_code",
    );

    expect(reason?.termId).toBe("gt_per_response_wins");
    expect(reason?.binding).toBe("labels");
    // Same column, no per-response label: the schema's own binding is the fallback, not nothing.
    const [fromSchema] = columnsFor(dataset("quarantine"), SNAPSHOT, { meta: { labels: {} } }).filter(
      (column) => column.pointer === "/reason_code",
    );
    expect(fromSchema?.termId).toBe("gt_quarantine");
    expect(fromSchema?.binding).toBe("schema");
  });

  it("marks a column with neither binding unbound rather than guessing at a term", () => {
    const [staging] = columnsFor(dataset("quarantine"), SNAPSHOT, quarantineEnvelope).filter(
      (column) => column.pointer === "/rule_id",
    );

    expect(staging?.binding).toBe("unbound");
    expect(staging?.termId).toBeNull();
  });

  it("gives a bound and an unbound header treatments that are not identical (§3.9.4 applied)", () => {
    const bound = headerTreatment("labels");
    const schema = headerTreatment("schema");
    const unbound = headerTreatment("unbound");

    expect(unbound.marker).toBe("?");
    expect(unbound.underlined).toBe(false);
    expect(bound.underlined).toBe(true);
    // Two treatments that render the same are a reader who cannot tell the two facts apart.
    for (const field of ["className", "marker", "underlined"] as const) {
      expect(bound[field], field).not.toBe(unbound[field]);
    }
    expect(schema.className).toBe(bound.className);
  });

  it("renders an unbound header with no dotted underline and no hover affordance", () => {
    const columns = columnsFor(dataset("vintages"), SNAPSHOT, vintagesEnvelope);
    const unbound = columns.find((column) => column.binding === "unbound");
    const header = renderHeader(unbound as never);

    expect(header.querySelector("gw-term")).toBeNull();
    expect(header.querySelector(".gw-col-unbound")?.textContent).toBe("?");
    expect(header.querySelector(".gw-col-unbound")?.getAttribute("title")).toMatch(
      /no glossary entry yet/,
    );
    expect(header.className).not.toContain("gw-col-bound");
  });

  it("carries the whole column name in a title, because a narrow track ellipsizes it", () => {
    const columns = columnsFor(dataset("wells"), SNAPSHOT, wellsEnvelope);
    const long = columns.find((column) => column.name === "operator_name_reported");
    const header = renderHeader(long as never);

    // At 1366 six columns share 762 px and this name does not fit; without the title it read
    // as `operator_name_reportedtatus_canonical`, overrunning into the next column.
    expect(header.querySelector(".gw-label")?.getAttribute("title")).toBe(
      "operator_name_reported",
    );
  });

  it("renders a bound header as a term, which is the affordance the unbound one withholds", () => {
    const [reasonCode] = columnsFor(dataset("quarantine"), SNAPSHOT, quarantineEnvelope).filter(
      (column) => column.binding !== "unbound",
    );
    const header = renderHeader(reasonCode as never);

    expect(header.querySelector("gw-term")).not.toBeNull();
    expect(header.querySelector(".gw-col-unbound")).toBeNull();
    expect(header.className).toContain("gw-col-bound");
  });

  it("counts the gap per dataset, because a percentage is what makes the debt a surface", () => {
    const quarantine = coverageOf(columnsFor(dataset("quarantine"), SNAPSHOT, quarantineEnvelope));
    const vintages = coverageOf(columnsFor(dataset("vintages"), SNAPSHOT, vintagesEnvelope));

    expect(quarantine.total).toBe((dataset("quarantine").columns.default ?? []).length);
    expect(quarantine.bound).toBeGreaterThan(0);
    expect(quarantine.bound).toBeLessThan(quarantine.total);
    // C5 authored vintage bindings; the grid reports real partial coverage.
    expect(vintages.bound).toBeGreaterThan(0);
    expect(vintages.bound).toBeLessThan(vintages.total);
  });

  it("names a column by the field the API itself uses, which is what a reader would curl", () => {
    const columns = columnsFor(dataset("quarantine"), SNAPSHOT, quarantineEnvelope);

    expect(columns.map((column) => column.name)).toContain("occurrence_count");
    expect(columns.map((column) => column.pointer)).toEqual(dataset("quarantine").columns.default);
  });

  it("falls back to the response schema in order where a dataset declares no defaults", () => {
    const bare = { ...dataset("vintages") };
    bare.columns = { ...bare.columns, default: undefined };

    const columns = columnsFor(bare, SNAPSHOT, vintagesEnvelope);

    expect(columns.length).toBeGreaterThan((dataset("vintages").columns.default ?? []).length);
    expect(columns.some((column) => column.pointer === "/vintage_id")).toBe(true);
  });

  it("carries the exemption reason where the document serves one, and says so where it does not", () => {
    // Written against both states on purpose: C4 lands `x-glasswell-not-a-figure` on a schedule
    // this chunk does not control, so pinning today's answer would redden on somebody else's
    // merge. What is asserted is the mechanism — the reason is read, never invented.
    const reason = "a count of fetches, not a measured quantity";
    const served = JSON.parse(JSON.stringify(SNAPSHOT));
    const bare = JSON.parse(JSON.stringify(SNAPSHOT));
    served.components.schemas.QuarantineRow.properties.occurrence_count[
      "x-glasswell-not-a-figure"
    ] = reason;
    delete bare.components.schemas.QuarantineRow.properties.occurrence_count[
      "x-glasswell-not-a-figure"
    ];

    const withReason = columnsFor(dataset("quarantine"), served, quarantineEnvelope).find(
      (column) => column.pointer === "/occurrence_count",
    );
    const without = columnsFor(dataset("quarantine"), bare, quarantineEnvelope).find(
      (column) => column.pointer === "/occurrence_count",
    );

    expect(withReason?.reason).toBe(reason);
    expect(without?.reason).toBeNull();
  });

  it("marks hidden columns hidden and carries the reason the lint made them declare", () => {
    const columns = columnsFor(dataset("quarantine"), SNAPSHOT, quarantineEnvelope, {
      includeHidden: true,
    });
    const fingerprint = columns.find((column) => column.pointer === "/row_fingerprint");

    expect(fingerprint?.hidden).toBe(true);
    expect(fingerprint?.hiddenReason).toMatch(/content address/i);
    expect(columnsFor(dataset("quarantine"), SNAPSHOT, quarantineEnvelope).map((c) => c.pointer))
      .not.toContain("/row_fingerprint");
  });
});
