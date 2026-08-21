import { readFileSync } from "node:fs";

import { afterEach, describe, expect, it, vi } from "vitest";

import { DATASET_GROUPS, DATASET_KEY, buildCatalogue } from "./catalogue.ts";

// vitest roots at web/, so this is the committed contract artifact, not a fixture of it.
// SB-08 §2.3: the document is the catalogue, so the assertions below derive from whatever
// the snapshot carries — five datasets today, eleven once C2 lands, and green through both.
const SNAPSHOT_PATH = "../tests/contract/openapi_snapshot.json";

interface Operation {
  operationId?: string;
  [key: string]: unknown;
}
interface Document {
  paths: Record<string, Record<string, Operation>>;
}

function snapshot(): Document {
  return JSON.parse(readFileSync(SNAPSHOT_PATH, "utf8")) as Document;
}

interface Declared {
  path: string;
  operationId: string;
  raw: Record<string, unknown>;
}

function declaredDatasets(document: Document): Declared[] {
  const found: Declared[] = [];
  for (const [path, item] of Object.entries(document.paths)) {
    const operation = item["get"];
    const raw = operation?.[DATASET_KEY];
    if (!operation || typeof raw !== "object" || raw === null) continue;
    found.push({
      path,
      operationId: operation.operationId ?? "",
      raw: raw as Record<string, unknown>,
    });
  }
  return found;
}

function byOrder(a: Declared, b: Declared): number {
  return (a.raw["order"] as number) - (b.raw["order"] as number);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("the catalogue is the document (SB-08 §2.3)", () => {
  it("lists exactly the operations the committed snapshot declares browsable, in order", () => {
    const declared = declaredDatasets(snapshot()).sort(byOrder);
    // Vacuity floor, not a count: an empty document would satisfy the equality below.
    expect(declared.length).toBeGreaterThan(0);

    const catalogue = buildCatalogue(snapshot());

    expect(catalogue.datasets.map((dataset) => dataset.id)).toEqual(
      declared.map((entry) => entry.raw["id"]),
    );
  });

  it("sorts on order alone, because the lint makes order unique document-wide", () => {
    const orders = buildCatalogue(snapshot()).datasets.map((dataset) => dataset.order);

    expect(orders).toEqual([...orders].sort((a, b) => a - b));
    expect(new Set(orders).size).toBe(orders.length);
  });

  it("carries the operation each dataset came from, so nothing needs a second lookup", () => {
    const declared = new Map(
      declaredDatasets(snapshot()).map((entry) => [entry.raw["id"] as string, entry]),
    );

    for (const dataset of buildCatalogue(snapshot()).datasets) {
      expect(dataset.operationId).toBe(declared.get(dataset.id)?.operationId);
      expect(dataset.path).toBe(declared.get(dataset.id)?.path);
    }
  });

  it("reads path parameters off the template, which is what a pivot anchors on", () => {
    for (const dataset of buildCatalogue(snapshot()).datasets) {
      const templated = [...dataset.path.matchAll(/\{([^}]+)\}/g)].map((match) => match[1]);
      expect(dataset.pathParameters).toEqual(templated);
    }
  });

  it("groups in the fixed order, and renders no group the document does not populate", () => {
    const catalogue = buildCatalogue(snapshot());
    const populated = DATASET_GROUPS.filter((group) =>
      catalogue.datasets.some((dataset) => dataset.group === group),
    );

    expect(catalogue.groups.map((group) => group.id)).toEqual(populated);
    for (const group of catalogue.groups) {
      expect(group.datasets.length).toBeGreaterThan(0);
      expect(group.datasets.map((dataset) => dataset.id)).toEqual(
        catalogue.datasets.filter((d) => d.group === group.id).map((d) => d.id),
      );
    }
  });
});

describe("the six optional members are a property of the served document, not a guess", () => {
  // C1 MUST-KNOW K1: `dataset()` dumps with exclude_none, so these ten are always emitted and
  // exactly these six are not. A member the API adds and the client does not know about fails
  // here, in CI, rather than in a reader's rail.
  const ALWAYS = [
    "id",
    "title",
    "group",
    "collection_pointer",
    "anchors",
    "row_id",
    "facets",
    "columns",
    "intro",
    "order",
  ];
  const OPTIONAL = ["series_pointer", "row_projection", "detail_operation", "summary_operation"];
  const COLUMNS_ALWAYS = ["hidden", "hidden_reason"];
  const COLUMNS_OPTIONAL = ["default", "sort"];

  it("emits every always-present member on every declared dataset", () => {
    const declared = declaredDatasets(snapshot());
    expect(declared.length).toBeGreaterThan(0);

    for (const entry of declared) {
      for (const member of ALWAYS) expect(Object.keys(entry.raw), entry.operationId).toContain(member);
      const columns = entry.raw["columns"] as Record<string, unknown>;
      for (const member of COLUMNS_ALWAYS) expect(Object.keys(columns)).toContain(member);
    }
  });

  it("emits nothing outside the ten plus six the client type declares", () => {
    for (const entry of declaredDatasets(snapshot())) {
      for (const member of Object.keys(entry.raw)) {
        expect([...ALWAYS, ...OPTIONAL], `${entry.operationId}.${member}`).toContain(member);
      }
      const columns = entry.raw["columns"] as Record<string, unknown>;
      for (const member of Object.keys(columns)) {
        expect([...COLUMNS_ALWAYS, ...COLUMNS_OPTIONAL]).toContain(member);
      }
    }
  });

  it("never needs a ?? [] for anchors or hidden columns", () => {
    for (const dataset of buildCatalogue(snapshot()).datasets) {
      expect(Array.isArray(dataset.anchors)).toBe(true);
      expect(Array.isArray(dataset.columns.hidden)).toBe(true);
    }
  });
});

describe("a document the explorer cannot read degrades, and says so (SB-08 rev 2 §9)", () => {
  function corrupt(mutate: (raw: Record<string, unknown>) => void): Document {
    const document = snapshot();
    const first = declaredDatasets(document)[0];
    if (!first) throw new Error("the snapshot declares no dataset to corrupt");
    const operation = document.paths[first.path]?.["get"];
    mutate(operation?.[DATASET_KEY] as Record<string, unknown>);
    return document;
  }

  it("omits a malformed declaration and does not throw", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const before = buildCatalogue(snapshot()).datasets.length;

    const catalogue = buildCatalogue(corrupt((raw) => delete raw["row_id"]));

    expect(catalogue.datasets).toHaveLength(before - 1);
    expect(warn).toHaveBeenCalled();
  });

  it("omits a declaration whose group is not one of the four", () => {
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const before = buildCatalogue(snapshot()).datasets.length;

    const catalogue = buildCatalogue(corrupt((raw) => (raw["group"] = "geology")));

    expect(catalogue.datasets).toHaveLength(before - 1);
  });

  it("omits a declaration taking a shell route's id, so no dataset can shadow the shell", () => {
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const before = buildCatalogue(snapshot()).datasets.length;

    const catalogue = buildCatalogue(corrupt((raw) => (raw["id"] = "learn")));

    expect(catalogue.datasets).toHaveLength(before - 1);
  });

  it("omits a dataset whose detail_operation is not in the document, never renders it dead", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const withDetail = declaredDatasets(snapshot()).find((entry) => entry.raw["detail_operation"]);
    if (!withDetail) throw new Error("no dataset declares a detail_operation");
    const document = snapshot();
    const raw = document.paths[withDetail.path]?.["get"]?.[DATASET_KEY] as Record<string, unknown>;
    raw["detail_operation"] = "get_a_thing_that_was_deleted";

    const catalogue = buildCatalogue(document);

    expect(catalogue.datasets.map((dataset) => dataset.id)).not.toContain(withDetail.raw["id"]);
    expect(warn.mock.calls.flat().join(" ")).toContain("get_a_thing_that_was_deleted");
  });

  it("survives a document with no paths at all rather than throwing on the rail's behalf", () => {
    expect(buildCatalogue({}).datasets).toEqual([]);
    expect(buildCatalogue(null).groups).toEqual([]);
  });
});
