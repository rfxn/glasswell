import { valueAt } from "../../api/envelope.ts";
import type { CatalogueDataset } from "../catalogue.ts";

/** Where a declared column pointer resolves: SB-08 rev 3 §2.3, C2 MUST-KNOW P2. */
export type Namespace = "series" | "element" | "root";

export interface Cell {
  /** The declared, element-relative pointer — what `columns.default` says. */
  pointer: string;
  /** The pointer into `data` this cell's value actually sits at, indexed all the way down. */
  dataPointer: string;
  namespace: Namespace;
  value: unknown;
  /** Suffix companions of a series value: `_null_semantics`, `_report_vintage`, `_aggregation`. */
  companions: Record<string, unknown>;
}

export interface Row {
  id: string;
  index: number;
  elementIndex: number;
  elementPointer: string;
  cells: Record<string, Cell>;
}

export function namespaceFor(dataset: CatalogueDataset, column: string): Namespace {
  const projection = dataset.row_projection;
  if (projection && (column === projection.axis || projection.columns.includes(column))) {
    return "series";
  }
  return dataset.anchors.includes(column) ? "root" : "element";
}

/**
 * B5a's fix: one function composes the pointer `meta.labels` is looked up with, and the client
 * and the C5 floor test both call it, so the numerator and the rendering cannot disagree.
 *
 * The index appears only for a nested collection. A top-level collection's labels are keyed per
 * column (`/reason_code` on quarantine, `/series/oil_bbl` on production — both measured); the
 * pooled form carries one (C2 MUST-KNOW P3), and every one of those is null until C5.
 */
export function responsePointerFor(
  dataset: CatalogueDataset,
  column: string,
  elementIndex = 0,
): string {
  const prefix =
    dataset.collection_pointer === ""
      ? ""
      : `${dataset.collection_pointer}/${elementIndex}`;
  switch (namespaceFor(dataset, column)) {
    case "series":
      return `${prefix}${dataset.series_pointer ?? ""}${column}`;
    case "element":
      return `${prefix}${column}`;
    case "root":
      return column;
  }
}

export function extractRows(
  dataset: CatalogueDataset,
  data: unknown,
  columns: readonly string[],
): Row[] {
  const collection =
    dataset.collection_pointer === "" ? data : valueAt(data, dataset.collection_pointer);
  const projection = dataset.row_projection;
  const elements = projection
    ? asElements(collection)
    : Array.isArray(collection)
      ? collection
      : [];

  const rows: Row[] = [];
  for (const [elementIndex, element] of elements.entries()) {
    const elementPointer = pointerToElement(dataset, elementIndex);
    if (!projection) {
      rows.push(rowFrom(dataset, data, element, columns, rows.length, elementIndex, elementPointer));
      continue;
    }
    const series = valueAt(element, dataset.series_pointer ?? "");
    const axis = valueAt(series, projection.axis);
    if (!Array.isArray(axis)) continue;
    for (let index = 0; index < axis.length; index += 1) {
      rows.push(
        rowFrom(dataset, data, element, columns, rows.length, elementIndex, elementPointer, index),
      );
    }
  }
  return rows;
}

/** A pivot's element set: an array where the collection is nested, the object itself where not. */
function asElements(collection: unknown): unknown[] {
  if (Array.isArray(collection)) return collection;
  return typeof collection === "object" && collection !== null ? [collection] : [];
}

function pointerToElement(dataset: CatalogueDataset, elementIndex: number): string {
  if (dataset.collection_pointer !== "") return `${dataset.collection_pointer}/${elementIndex}`;
  // With `data` as the element there is nothing to index; with `data` as the array there is.
  return dataset.row_projection ? "" : `/${elementIndex}`;
}

function rowFrom(
  dataset: CatalogueDataset,
  data: unknown,
  element: unknown,
  columns: readonly string[],
  index: number,
  elementIndex: number,
  elementPointer: string,
  seriesIndex?: number,
): Row {
  const cells: Record<string, Cell> = {};
  for (const column of new Set([...columns, ...dataset.row_id])) {
    const cell = cellFor(dataset, data, element, elementPointer, column, seriesIndex);
    if (cell) cells[column] = cell;
  }
  const id = dataset.row_id.map((pointer) => String(cells[pointer]?.value ?? "")).join("|");
  return { id, index, elementIndex, elementPointer, cells };
}

/** The three namespaces, probed in P2's order: series (pivots only), then element, then root. */
function cellFor(
  dataset: CatalogueDataset,
  data: unknown,
  element: unknown,
  elementPointer: string,
  column: string,
  seriesIndex?: number,
): Cell | null {
  const projection = dataset.row_projection;
  // An anchor is declared root-relative on both pivots (C2 MUST-KNOW P8), and with
  // `collection_pointer: ""` the element *is* `data` — so without this arm the probe would
  // resolve `/granularity` on the element and disagree with `namespaceFor` about a pointer
  // whose two answers happen to be the same node.
  if (!dataset.anchors.includes(column)) {
    if (projection && seriesIndex !== undefined) {
      const seriesPointer = `${elementPointer}${dataset.series_pointer ?? ""}`;
      const series = valueAt(data, seriesPointer);
      const values = valueAt(series, column);
      if (Array.isArray(values)) {
        return {
          pointer: column,
          dataPointer: `${seriesPointer}${column}/${seriesIndex}`,
          namespace: "series",
          value: values[seriesIndex],
          companions:
            column === projection.axis
              ? {}
              : companionsOf(series, column, projection.suffixes, seriesIndex),
        };
      }
    }
    const own = valueAt(element, column);
    if (own !== undefined) {
      return {
        pointer: column,
        dataPointer: `${elementPointer}${column}`,
        namespace: "element",
        value: own,
        companions: {},
      };
    }
  }
  const root = valueAt(data, column);
  if (root === undefined) return null;
  return { pointer: column, dataPointer: column, namespace: "root", value: root, companions: {} };
}

function companionsOf(
  series: unknown,
  column: string,
  suffixes: readonly string[],
  seriesIndex: number,
): Record<string, unknown> {
  const found: Record<string, unknown> = {};
  for (const suffix of suffixes) {
    const values = valueAt(series, `${column}${suffix}`);
    if (Array.isArray(values)) found[suffix] = values[seriesIndex];
  }
  return found;
}
