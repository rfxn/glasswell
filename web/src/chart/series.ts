export type NullSemanticsState = string;

export interface ProductionSeries {
  pm: string[];
  [column: string]: (string | null)[] | string[];
}

export interface ProductionData {
  api10: string;
  source_id: string | null;
  granularity: string;
  streams: string[];
  series: ProductionSeries;
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
  values: (number | null)[];
  raw: (string | null)[];
  vintages: (string | null)[];
  nullSemantics: NullSemanticsState[];
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
}

const STREAM_COLUMNS: Record<string, string> = {
  oil: "oil_bbl",
  gas: "gas_mcf",
  water: "water_bbl",
};

const STREAM_LABELS: Record<string, string> = { oil: "Oil", gas: "Gas", water: "Water" };

export function toChartSeries(production: ProductionData): ChartSeries {
  const months = production.series.pm;
  const x = months.map(monthToEpoch);
  const columns: SeriesColumn[] = [];

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
    columns.push({
      key,
      stream,
      label: STREAM_LABELS[stream] ?? stream,
      unit: production._units[`series.${key}`] ?? "",
      basis: production._basis[`series.${key}`] ?? null,
      handle: production._lineage[`series.${key}`] ?? null,
      values: raw.map((value, index) => plotted(value, states[index] ?? "")),
      raw,
      vintages,
      nullSemantics: states,
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
  };
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
