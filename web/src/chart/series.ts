export type NullSemanticsState = string;

export interface ProductionSeries {
  pm: string[];
  [column: string]: (string | null)[] | string[];
}

export interface ErrorBounds {
  outcome: string;
  measured_by_rule?: string | null;
  bed?: string | null;
  error_lo?: string | null;
  error_hi?: string | null;
}

export interface AllocationBlock {
  model_id: string | null;
  rule_id: string;
  leases: string[];
  membership_vintage: string | null;
  incomplete_from?: string | null;
  error_bounds: ErrorBounds;
}

export interface ProductionData {
  api10: string;
  source_id: string | null;
  granularity: string;
  streams: string[];
  series: ProductionSeries;
  /** Present only where the series is an allocation; absent on every observed jurisdiction. */
  allocation?: AllocationBlock | null;
  _lineage: Record<string, string>;
  _units: Record<string, string>;
  _basis: Record<string, string>;
}

export interface SeriesColumn {
  key: string;
  stream: string;
  label: string;
  unit: string;
  basis: string | null;
  handle: string | null;
  handles: (string | null)[];
  values: (number | null)[];
  raw: (string | null)[];
  vintages: (string | null)[];
  nullSemantics: NullSemanticsState[];
  /**
   * Per month, because the scalar cannot describe a series that is partly observed and partly
   * allocated: a lease that crossed one to two eligible wells produces exactly that. Empty on
   * an observed jurisdiction, which is what keeps the second band off North Dakota's chart.
   */
  allocationClasses: string[];
  granularities: (string | null)[];
  eligibleWells: (number | null)[];
  /** Months inside the regulator's own completeness lag, shaded rather than read as decline. */
  incomplete: boolean[];
  vintage: string | null;
  mixedVintages: boolean;
}

export interface ChartSeries {
  api10: string;
  granularity: string;
  months: string[];
  x: number[];
  data: (number | null)[][];
  columns: SeriesColumn[];
  scales: string[];
  /** The allocation this series is, where it is one. Null on every observed jurisdiction. */
  allocation: AllocationBlock | null;
  /** Whether any column carries an allocation class, which is what draws the second band. */
  allocated: boolean;
}

const STREAM_COLUMNS: Record<string, string> = {
  oil: "oil_bbl",
  gas: "gas_mcf",
  water: "water_bbl",
};

const STREAM_LABELS: Record<string, string> = { oil: "Oil", gas: "Gas", water: "Water" };

export function toChartSeries(
  production: ProductionData,
  options: { incompleteFromMonth?: string | null } = {},
): ChartSeries {
  const months = production.series.pm;
  const x = months.map(monthToEpoch);
  const columns: SeriesColumn[] = [];
  const incompleteFrom = firstIncomplete(
    months,
    options.incompleteFromMonth ?? production.allocation?.incomplete_from ?? null,
  );

  for (const stream of production.streams) {
    const key = STREAM_COLUMNS[stream];
    if (!key) continue;
    const raw = column(production.series, key);
    if (!raw) continue;
    const vintages = column(production.series, `${key}_report_vintage`) ?? months.map(() => null);
    const semantics = column(production.series, `${key}_null_semantics`) ?? months.map(() => "");
    const present = vintages.filter((vintage): vintage is string => vintage !== null);
    const distinct = new Set(present);
    const states = semantics.map((state) => state ?? "");
    const handles = pointHandles(production._lineage, key, months.length);
    const classes = column(production.series, `${key}_allocation_class_by_month`) ?? [];
    const grains = column(production.series, `${key}_granularity_by_month`) ?? [];
    const divisors = column(production.series, `${key}_eligible_wells_by_month`) ?? [];
    columns.push({
      key,
      stream,
      label: STREAM_LABELS[stream] ?? stream,
      unit: production._units[`series.${key}`] ?? "",
      basis: production._basis[`series.${key}`] ?? null,
      handle: handles.find((handle) => handle !== null) ?? null,
      handles,
      values: raw.map((value, index) => plotted(value, states[index] ?? "")),
      raw,
      vintages,
      nullSemantics: states,
      allocationClasses: months.map((_, index) => classes[index] ?? ""),
      granularities: months.map((_, index) => grains[index] ?? null),
      eligibleWells: months.map((_, index) => {
        const value = divisors[index];
        return value === null || value === undefined || value === "" ? null : Number(value);
      }),
      incomplete: months.map((_, index) => incompleteFrom !== null && index >= incompleteFrom),
      vintage: distinct.size === 1 ? (present[0] ?? null) : null,
      mixedVintages: distinct.size > 1,
    });
  }

  return {
    api10: production.api10,
    granularity: production.granularity,
    months,
    x,
    data: [x, ...columns.map((entry) => entry.values)],
    columns,
    scales: [...new Set(columns.map((entry) => entry.unit))],
    allocation: production.allocation ?? null,
    allocated: columns.some((entry) => entry.allocationClasses.some((state) => state !== "")),
  };
}

/** The index the completeness lag starts at, or null where the wire named no month. */
function firstIncomplete(months: string[], from: string | null): number | null {
  if (from === null) return null;
  const at = months.indexOf(from);
  return at === -1 ? null : at;
}

/**
 * SB-07 §9.3: a column whose months were promoted by different derivations carries one
 * `series.<col>.<index>` entry per point and no column entry, so reading the column key
 * alone leaves every handle on the chart null.
 */
function pointHandles(
  lineage: Record<string, string>,
  key: string,
  length: number,
): (string | null)[] {
  const shared = lineage[`series.${key}`] ?? null;
  return Array.from({ length }, (_, index) => lineage[`series.${key}.${index}`] ?? shared);
}

/**
 * A withheld or unreported month is not a measurement, so it is a gap in the line whatever
 * number the wire carries for it. The state strip still renders which of the four it was;
 * a gap is never left ambiguous (SB-05 §3.2).
 */
const NOT_MEASURED = new Set(["withheld", "no_report"]);

function plotted(value: string | null, state: string): number | null {
  if (value === null || NOT_MEASURED.has(state)) return null;
  return Number(value);
}

/** The handle that explains one plotted point: the point's own if the wire carried one. */
export function handleAt(column: SeriesColumn, index: number, month: string): string | null {
  const handle = column.handles[index] ?? column.handle;
  return handle === null ? null : pointHandle(handle, month);
}

/** SB-05 §3.9.6: one handle on the wire, point-level explain built from the key columns. */
export function pointHandle(handle: string, month: string): string {
  const [derivation, selector] = splitHandle(handle);
  if (selector === null) return `${derivation}#pm=${month}`;
  if (/(^|&)pm=/.test(selector)) return handle;
  return `${derivation}#${selector}&pm=${month}`;
}

function splitHandle(handle: string): [string, string | null] {
  const at = handle.indexOf("#");
  return at === -1 ? [handle, null] : [handle.slice(0, at), handle.slice(at + 1)];
}

function column(series: ProductionSeries, key: string): (string | null)[] | null {
  const found = series[key];
  return Array.isArray(found) ? (found as (string | null)[]) : null;
}

export function monthToEpoch(month: string): number {
  const [year, index] = month.split("-");
  return Date.UTC(Number(year), Number(index) - 1, 1) / 1000;
}

export function epochToMonth(seconds: number): string {
  const when = new Date(seconds * 1000);
  return `${when.getUTCFullYear()}-${String(when.getUTCMonth() + 1).padStart(2, "0")}`;
}
