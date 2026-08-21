import type { CatalogueDataset } from "../catalogue.ts";
import { unwrapNullable } from "../facets/schema.ts";
import type { JsonSchema, Parameter } from "../facets/schema.ts";
import type { Namespace } from "./rows.ts";

export const GLOSSARY_KEY = "x-glasswell-glossary";
/** A-2's extension. C4 lands the reasons; where it has not, a count says so rather than lying. */
export const NOT_A_FIGURE_KEY = "x-glasswell-not-a-figure";

export interface Operation {
  operationId?: string;
  parameters?: Parameter[];
  responses?: Record<string, { content?: Record<string, { schema?: JsonSchema }> }>;
  [key: string]: unknown;
}

export interface DatasetSchemas {
  root: JsonSchema;
  element: JsonSchema;
  series: JsonSchema | null;
}

interface Document {
  paths?: Record<string, Record<string, Operation>>;
  components?: { schemas?: Record<string, JsonSchema> };
}

function asDocument(document: unknown): Document {
  return (typeof document === "object" && document !== null ? document : {}) as Document;
}

export function operationFor(document: unknown, operationId: string): Operation | null {
  for (const item of Object.values(asDocument(document).paths ?? {})) {
    for (const operation of Object.values(item)) {
      if (operation.operationId === operationId) return operation;
    }
  }
  return null;
}

export function pathFor(document: unknown, operationId: string): string | null {
  for (const [path, item] of Object.entries(asDocument(document).paths ?? {})) {
    for (const operation of Object.values(item)) {
      if (operation.operationId === operationId) return path;
    }
  }
  return null;
}

/** `$ref` chains are shallow here, but a cycle in a hand-edited document must not hang a page. */
export function resolve(document: unknown, node: JsonSchema | undefined): JsonSchema {
  const schemas = asDocument(document).components?.schemas ?? {};
  let current = node ?? {};
  for (let hops = 0; current.$ref !== undefined && hops < 10; hops += 1) {
    current = schemas[current.$ref.split("/").pop() ?? ""] ?? {};
  }
  return current;
}

function propertyOf(document: unknown, schema: JsonSchema, name: string): JsonSchema | null {
  const found = schema.properties?.[name];
  return found ? resolve(document, found) : null;
}

/** The three namespaces a column pointer can resolve in, as schemas rather than as values. */
export function schemasFor(document: unknown, dataset: CatalogueDataset): DatasetSchemas | null {
  const operation = operationFor(document, dataset.operationId);
  const envelope = resolve(
    document,
    operation?.responses?.["200"]?.content?.["application/json"]?.schema,
  );
  const root = resolve(document, envelope.properties?.["data"]);
  if (root.properties === undefined && root.type !== "array") return null;

  let element = root;
  for (const token of dataset.collection_pointer.split("/").filter(Boolean)) {
    element = propertyOf(document, element, token) ?? {};
  }
  if (element.type === "array") element = resolve(document, element.items);

  let series: JsonSchema | null = null;
  if (dataset.series_pointer) {
    let node = element;
    for (const token of dataset.series_pointer.split("/").filter(Boolean)) {
      node = propertyOf(document, node, token) ?? {};
    }
    series = node;
  }
  return { root: root.type === "array" ? resolve(document, root.items) : root, element, series };
}

export function columnSchema(
  document: unknown,
  schemas: DatasetSchemas | null,
  namespace: Namespace,
  column: string,
): JsonSchema | null {
  if (!schemas) return null;
  const source =
    namespace === "series" ? schemas.series : namespace === "root" ? schemas.root : schemas.element;
  const found = source ? propertyOf(document, source, column.replace(/^\//, "")) : null;
  return found ? unwrapNullable(found) : null;
}

export function glossaryOf(schema: JsonSchema | null): string | null {
  const bound = schema?.[GLOSSARY_KEY];
  return typeof bound === "string" ? bound : null;
}

export function notAFigureReason(schema: JsonSchema | null): string | null {
  const reason = schema?.[NOT_A_FIGURE_KEY];
  return typeof reason === "string" && reason !== "" ? reason : null;
}

/** An enum a parameter declares is the same closed vocabulary as one a property declares. */
export function parameterEnum(operation: Operation | null, name: string): string[] | null {
  const parameter = (operation?.parameters ?? []).find((candidate) => candidate.name === name);
  if (!parameter) return null;
  const schema = unwrapNullable(parameter.schema);
  const items = schema.items ? unwrapNullable(schema.items) : null;
  return schema.enum ?? items?.enum ?? null;
}
