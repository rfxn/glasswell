export interface SearchResult {
  api10: string;
  name: string;
  operator: string | null;
  status: string | null;
}

export interface SearchRequest {
  path: string;
  query: Record<string, string>;
}

const API10 = /^\d{10}$/;
const PAGE = "20";

interface WellRow {
  api10?: string;
  well_name?: string | null;
  operator_name_reported?: string | null;
  status_canonical?: string | null;
}

export function searchRequest(term: string): SearchRequest | null {
  const trimmed = term.trim();
  if (trimmed === "") return null;
  if (API10.test(trimmed)) return { path: `/v1/wells/${trimmed}`, query: {} };
  return { path: "/v1/wells", query: { q: trimmed, limit: PAGE } };
}

/** Both routes answer the same question, so the dropdown reads one shape. */
export function toResults(envelope: { data: unknown }): SearchResult[] {
  const data = envelope.data;
  const rows: unknown[] = Array.isArray(data) ? data : data ? [data] : [];
  return rows.filter(isWellRow).map((row) => ({
    api10: row.api10,
    name: row.well_name ?? row.api10,
    operator: row.operator_name_reported ?? null,
    status: row.status_canonical ?? null,
  }));
}

function isWellRow(row: unknown): row is WellRow & { api10: string } {
  return typeof row === "object" && row !== null && typeof (row as WellRow).api10 === "string";
}
