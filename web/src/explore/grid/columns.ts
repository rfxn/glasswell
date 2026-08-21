import { labelElement } from "../../glossary/gw-term.ts";
import type { CatalogueDataset } from "../catalogue.ts";
import type { JsonSchema } from "../facets/schema.ts";
import { namespaceFor, responsePointerFor } from "./rows.ts";
import type { Namespace } from "./rows.ts";
import {
  columnSchema,
  glossaryOf,
  notAFigureReason,
  operationFor,
  parameterEnum,
  schemasFor,
} from "./schema.ts";

/** SB-08 §3.2's table, as a closed set the tests can assert nothing escapes. */
export const COLUMN_KINDS = [
  "figure",
  "count",
  "identifier",
  "enum",
  "prose",
  "timestamp",
  "geometry",
] as const;

export type ColumnKind = (typeof COLUMN_KINDS)[number];
export type Binding = "labels" | "schema" | "unbound";

export interface Column {
  pointer: string;
  name: string;
  /** The pointer `meta.labels` is looked up with — `responsePointerFor`, never a second guess. */
  labelPointer: string;
  namespace: Namespace;
  kind: ColumnKind;
  binding: Binding;
  termId: string | null;
  /** A-2's `x-glasswell-not-a-figure`, verbatim. Null until C4 serves it. */
  reason: string | null;
  hidden: boolean;
  hiddenReason?: string;
}

export interface Coverage {
  bound: number;
  total: number;
  percent: number;
}

export interface HeaderTreatment {
  className: string;
  marker: string | null;
  underlined: boolean;
  title: string;
}

const IDENTIFIER_NAMES = new Set(["api10", "api14", "sha256", "row_fingerprint", "value_hash"]);
const GEOMETRY_NAMES = new Set(["geometry", "surface_point", "links", "bbox"]);

interface LabelSource {
  meta: { labels: Record<string, string> };
}

export function columnsFor(
  dataset: CatalogueDataset,
  document: unknown,
  envelope: LabelSource,
  options: { includeHidden?: boolean } = {},
): Column[] {
  const schemas = schemasFor(document, dataset);
  const operation = operationFor(document, dataset.operationId);
  const declared = dataset.columns.default ?? fallbackColumns(dataset, schemas);
  const hidden = new Set(dataset.columns.hidden);
  const pointers = options.includeHidden ? [...declared, ...dataset.columns.hidden] : declared;

  return pointers.map((pointer) => {
    const namespace = namespaceFor(dataset, pointer);
    const schema = columnSchema(document, schemas, namespace, pointer);
    const labelPointer = responsePointerFor(dataset, pointer);
    const name = pointer.replace(/^\//, "");
    const fromResponse = envelope.meta.labels[labelPointer] ?? null;
    const fromSchema = glossaryOf(schema);
    const column: Column = {
      pointer,
      name,
      labelPointer,
      namespace,
      kind: classify(dataset, operation, namespace, pointer, name, schema),
      // §3.2: `meta.labels` wins, being per-response and therefore more specific.
      binding: fromResponse ? "labels" : fromSchema ? "schema" : "unbound",
      termId: fromResponse ?? fromSchema,
      reason: notAFigureReason(schema),
      hidden: hidden.has(pointer),
    };
    const reason = dataset.columns.hidden_reason[pointer];
    if (column.hidden && reason !== undefined) column.hiddenReason = reason;
    return column;
  });
}

/** §2.3's stated fallback: no `columns.default` renders every property in schema order. */
function fallbackColumns(
  dataset: CatalogueDataset,
  schemas: ReturnType<typeof schemasFor>,
): string[] {
  const series = Object.keys(schemas?.series?.properties ?? {}).map((name) => `/${name}`);
  const element = Object.keys(schemas?.element.properties ?? {}).map((name) => `/${name}`);
  const suffixes = dataset.row_projection?.suffixes ?? [];
  return [...series, ...element].filter(
    (pointer) => !suffixes.some((suffix) => pointer.endsWith(suffix)),
  );
}

function classify(
  dataset: CatalogueDataset,
  operation: ReturnType<typeof operationFor>,
  namespace: Namespace,
  pointer: string,
  name: string,
  schema: JsonSchema | null,
): ColumnKind {
  if (GEOMETRY_NAMES.has(name) || isGeometry(schema)) return "geometry";
  // The axis is the row key, so it renders as one (C2 MUST-KNOW P6) — and it takes no suffixes.
  if (pointer === dataset.row_projection?.axis) return "identifier";
  // A pivot's value columns are figures by declaration: they carry `_lineage`, `_units` and
  // `_basis`, and `isFigure` is false for every one of them because the wire form is a string.
  if (namespace === "series") return "figure";
  if (isFigureShaped(schema)) return "figure";
  if (dataset.row_id.includes(pointer) || name.endsWith("_id") || IDENTIFIER_NAMES.has(name)) {
    return "identifier";
  }
  if (schema?.type === "integer" || schema?.type === "number") return "count";
  if (schema?.enum || schema?.type === "boolean" || parameterEnum(operation, name)) return "enum";
  if (schema?.format === "date" || schema?.format === "date-time") return "timestamp";
  return "prose";
}

function isGeometry(schema: JsonSchema | null): boolean {
  const properties = schema?.properties;
  if (!properties) return false;
  return ("lat" in properties && "lon" in properties) || "geom_type" in properties;
}

function isFigureShaped(schema: JsonSchema | null): boolean {
  const properties = schema?.properties;
  return properties !== undefined && "value" in properties && "unit" in properties && "d" in properties;
}

export function coverageOf(columns: readonly Column[]): Coverage {
  const bound = columns.filter((column) => column.binding !== "unbound").length;
  const total = columns.length;
  return { bound, total, percent: total === 0 ? 0 : Math.round((bound / total) * 100) };
}

/**
 * §3.2's counted-unbound treatment. A reader is never misled into thinking a term was checked
 * and found absent, so the two states differ in every field that carries meaning.
 */
export function headerTreatment(binding: Binding): HeaderTreatment {
  if (binding === "unbound") {
    return {
      className: "gw-col-unbound-head",
      marker: "?",
      underlined: false,
      title: "This column has no glossary entry yet.",
    };
  }
  return {
    className: "gw-col-bound",
    marker: null,
    underlined: true,
    title: "Hover for the definition this column is bound to.",
  };
}

export function renderHeader(column: Column): HTMLElement {
  const treatment = headerTreatment(column.binding);
  const header = document.createElement("div");
  header.className = `gw-col-head ${treatment.className}`;
  header.dataset["kind"] = column.kind;
  header.append(labelElement(column.name, column.termId));

  if (treatment.marker) {
    const marker = document.createElement("span");
    marker.className = "gw-col-unbound";
    marker.textContent = treatment.marker;
    marker.title = `${column.name}: this column has no glossary entry yet.`;
    marker.setAttribute("aria-label", `${column.name} has no glossary entry yet`);
    header.append(marker);
  }
  if (column.hiddenReason) {
    const note = document.createElement("span");
    note.className = "gw-col-hidden";
    note.textContent = "hidden";
    note.title = column.hiddenReason;
    header.append(note);
  }
  return header;
}
