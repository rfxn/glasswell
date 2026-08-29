export interface SearchResult {
  /** Null for a well the issuing authority is not the API: absent says absent (§5.3). */
  api10: string | null;
  name: string;
  operator: string | null;
  status: string | null;
}

export interface SearchRequest {
  path: string;
  query: Record<string, string>;
}

const API10 = /^\d{10}$/;
const API14 = /^\d{14}$/;
const PAGE = "20";

/**
 * The general key is `(authority, native_id)` and the API-10 is its US instantiation, so a row
 * is a well when it carries any of these — ordered, because the first one present is also the
 * label a nameless well falls back to. `authority` is not among them: it names who assigns the
 * identifier, not which well.
 */
const IDENTIFIERS = ["api10", "well_id", "native_id", "uwi"] as const;

interface WellRow {
  api10?: string;
  well_id?: string;
  native_id?: string;
  uwi?: string;
  well_name?: string | null;
  operator_name_reported?: string | null;
  status_canonical?: string | null;
}

export function searchRequest(term: string): SearchRequest | null {
  const trimmed = term.trim();
  if (trimmed === "") return null;
  if (API10.test(trimmed)) return { path: `/v1/wells/${trimmed}`, query: {} };
  // The path takes ten digits only, and `q` would read an API-14 as a name and answer nothing.
  if (API14.test(trimmed)) return { path: "/v1/wells", query: { api10: trimmed, limit: PAGE } };
  return { path: "/v1/wells", query: { q: trimmed, limit: PAGE } };
}

/** Both routes answer the same question, so the dropdown reads one shape. */
export function toResults(envelope: { data: unknown }): SearchResult[] {
  const data = envelope.data;
  const rows: unknown[] = Array.isArray(data) ? data : data ? [data] : [];
  return rows.filter(isWellRow).map((row) => ({
    api10: given(row.api10),
    // A well with neither a name nor an API-10 rendered as `undefined` before the chain ended
    // at the identifier the guard already proved is there (N-6).
    name: row.well_name ?? identifierOf(row),
    operator: row.operator_name_reported ?? null,
    status: row.status_canonical ?? null,
  }));
}

/**
 * An identifier the row actually carries, or null. `?? ` alone let `""` through, so a row kept
 * alive by a second identifier served an empty api10 against this field's own contract, and
 * `selectWell` reads null as deselect and `""` as neither (gate-udmw1 F-3).
 */
function given(value: string | undefined): string | null {
  return typeof value === "string" && value !== "" ? value : null;
}

/** The first identifier the row answers to, or `""` when it answers to none. */
function identifierOf(row: WellRow): string {
  for (const field of IDENTIFIERS) {
    const value = given(row[field]);
    if (value !== null) return value;
  }
  return "";
}

function isWellRow(row: unknown): row is WellRow {
  return typeof row === "object" && row !== null && identifierOf(row as WellRow) !== "";
}
