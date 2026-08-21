export const DATASET_KEY = "x-glasswell-dataset";
export const DATASET_GROUPS = ["wells", "kitchen", "vocabulary", "service"] as const;

export type DatasetGroup = (typeof DATASET_GROUPS)[number];

const RESERVED_IDS = new Set(["map", "query", "learn", "api"]);
const ID_SHAPE = /^[a-z][a-z0-9_]*$/;
const PATH_PARAMETER = /\{([^}]+)\}/g;

export interface RowProjection {
  axis: string;
  columns: string[];
  suffixes: string[];
}

export interface DatasetColumns {
  hidden: string[];
  hidden_reason: Record<string, string>;
  default?: string[];
  sort?: string;
}

/**
 * A-1's declaration as the client sees it. Six members are optional and the rest are not,
 * because `dataset()` dumps with `exclude_none` — so `anchors` and `columns.hidden` never
 * need a `?? []` and the absence of `columns.default` is the schema-order fallback, not a bug.
 */
export interface Dataset {
  id: string;
  title: string;
  group: DatasetGroup;
  collection_pointer: string;
  anchors: string[];
  row_id: string[];
  facets: string[];
  columns: DatasetColumns;
  intro: string;
  order: number;
  series_pointer?: string;
  row_projection?: RowProjection;
  detail_operation?: string;
  summary_operation?: string;
}

export interface CatalogueDataset extends Dataset {
  operationId: string;
  path: string;
  pathParameters: string[];
}

export interface CatalogueGroup {
  id: DatasetGroup;
  datasets: CatalogueDataset[];
}

export interface Catalogue {
  datasets: CatalogueDataset[];
  groups: CatalogueGroup[];
}

interface Operation {
  operationId?: unknown;
  [key: string]: unknown;
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function strings(value: unknown): string[] | null {
  return Array.isArray(value) && value.every((item) => typeof item === "string")
    ? (value as string[])
    : null;
}

function columnsOf(value: unknown): DatasetColumns | null {
  const raw = record(value);
  if (!raw) return null;
  const hidden = strings(raw["hidden"]);
  const reasons = record(raw["hidden_reason"]);
  if (!hidden || !reasons) return null;
  const columns: DatasetColumns = { hidden, hidden_reason: reasons as Record<string, string> };
  if (raw["default"] !== undefined) {
    const declared = strings(raw["default"]);
    if (!declared) return null;
    columns.default = declared;
  }
  if (raw["sort"] !== undefined) {
    if (typeof raw["sort"] !== "string") return null;
    columns.sort = raw["sort"];
  }
  return columns;
}

function projectionOf(value: unknown): RowProjection | null {
  const raw = record(value);
  if (!raw || typeof raw["axis"] !== "string") return null;
  const columns = strings(raw["columns"]);
  const suffixes = strings(raw["suffixes"]);
  if (!columns || columns.length === 0 || !suffixes) return null;
  return { axis: raw["axis"], columns, suffixes };
}

function optionalString(raw: Record<string, unknown>, member: string): string | null | undefined {
  const value = raw[member];
  if (value === undefined) return undefined;
  return typeof value === "string" ? value : null;
}

function datasetOf(value: unknown): Dataset | null {
  const raw = record(value);
  if (!raw) return null;
  const { id, title, group, collection_pointer: collection, intro, order } = raw;
  if (typeof id !== "string" || !ID_SHAPE.test(id) || RESERVED_IDS.has(id)) return null;
  if (typeof title !== "string" || title === "") return null;
  if (typeof group !== "string" || !DATASET_GROUPS.includes(group as DatasetGroup)) return null;
  if (typeof collection !== "string" || typeof intro !== "string") return null;
  if (typeof order !== "number" || !Number.isFinite(order)) return null;

  const anchors = strings(raw["anchors"]);
  const rowId = strings(raw["row_id"]);
  const facets = strings(raw["facets"]);
  const columns = columnsOf(raw["columns"]);
  if (!anchors || !rowId || rowId.length === 0 || !facets || !columns) return null;

  const dataset: Dataset = {
    id,
    title,
    group: group as DatasetGroup,
    collection_pointer: collection,
    anchors,
    row_id: rowId,
    facets,
    columns,
    intro,
    order,
  };

  for (const member of ["series_pointer", "detail_operation", "summary_operation"] as const) {
    const value_ = optionalString(raw, member);
    if (value_ === null) return null;
    if (value_ !== undefined) dataset[member] = value_;
  }
  if (raw["row_projection"] !== undefined) {
    const projection = projectionOf(raw["row_projection"]);
    if (!projection) return null;
    dataset.row_projection = projection;
  }
  // A pivot is declared whole or not at all; half of one is a defect, not a default.
  if ((dataset.row_projection === undefined) !== (dataset.series_pointer === undefined)) return null;
  return dataset;
}

/**
 * SB-08 §2.3: the served document is the catalogue. Pure by construction — `shell.ts` does the
 * one fetch — which is what lets the contract snapshot on disk stand in for the live API.
 */
export function buildCatalogue(document: unknown): Catalogue {
  const paths = record(record(document)?.["paths"]);
  const found: CatalogueDataset[] = [];
  const seen = new Set<string>();

  for (const [path, item] of Object.entries(paths ?? {})) {
    const operation = record(item)?.["get"] as Operation | undefined;
    const declaration = operation?.[DATASET_KEY];
    if (declaration === undefined) continue;

    const operationId = typeof operation?.operationId === "string" ? operation.operationId : "";
    const dataset = datasetOf(declaration);
    if (!dataset || operationId === "") {
      console.warn(`explorer: ignoring an unreadable ${DATASET_KEY} on GET ${path}`);
      continue;
    }
    if (seen.has(dataset.id)) {
      console.warn(`explorer: ignoring a second dataset claiming the id ${dataset.id}`);
      continue;
    }
    seen.add(dataset.id);
    found.push({
      ...dataset,
      operationId,
      path,
      pathParameters: [...path.matchAll(PATH_PARAMETER)].map((match) => match[1] as string),
    });
  }

  const served = servedOperations(paths ?? {});
  const datasets = found
    .filter((dataset) => namesOnlyLiveOperations(dataset, served))
    .sort((a, b) => a.order - b.order);

  return {
    datasets,
    groups: DATASET_GROUPS.filter((group) => datasets.some((d) => d.group === group))
      .map((group) => ({ id: group, datasets: datasets.filter((d) => d.group === group) }))
      .filter((group) => group.datasets.length > 0),
  };
}

function servedOperations(paths: Record<string, unknown>): Set<string> {
  const served = new Set<string>();
  for (const item of Object.values(paths)) {
    for (const operation of Object.values(record(item) ?? {})) {
      const id = record(operation)?.["operationId"];
      if (typeof id === "string") served.add(id);
    }
  }
  return served;
}

/** Drift is a dead link the reader would only discover by clicking it, so drop the dataset. */
function namesOnlyLiveOperations(dataset: CatalogueDataset, served: Set<string>): boolean {
  for (const member of ["detail_operation", "summary_operation"] as const) {
    const named = dataset[member];
    if (named !== undefined && !served.has(named)) {
      console.warn(
        `explorer: dropping dataset ${dataset.id} — its ${member} ${named} is not in the document`,
      );
      return false;
    }
  }
  return true;
}
