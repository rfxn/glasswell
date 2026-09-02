import { getEnvelope } from "../api/client.ts";
import { unwrap } from "../api/envelope.ts";
import { buildIndex } from "./index.ts";
import type { TermIndex } from "./index.ts";

export interface TermSummary {
  term_id: string;
  term: string;
  aliases: string[];
  short_definition: string;
  domain_tags: string[];
  highlightable: boolean;
}

export interface TermDetail extends TermSummary {
  expanded_definition: string;
  related_terms: string[];
  source_refs: string[];
  appears_in: { kind: string; ref: string }[];
}

const summaries = new Map<string, TermSummary>();
const details = new Map<string, Promise<TermDetail>>();

let index: TermIndex = buildIndex({ index_version: "gix_empty", entries: [], stopwords: [] });
let loaded = false;
const listeners = new Set<() => void>();

export function termIndex(): TermIndex {
  return index;
}

/**
 * Fires when the index is in hand, and immediately if it already is. The map and the status
 * page mount before boot resolves the glossary, so a surface that only highlighted at build
 * time would teach nothing for the life of the page.
 */
export function onGlossaryReady(listener: () => void): () => void {
  listeners.add(listener);
  if (loaded) listener();
  return () => listeners.delete(listener);
}

export function termSummary(termId: string): TermSummary | null {
  return summaries.get(termId) ?? null;
}

/**
 * Hand the loaded vocabulary over. Called once, by `./load.ts`, which is where the fetch
 * lives so that the entry chunk does not carry a boot-only round trip.
 */
export function publishGlossary(built: TermIndex, terms: Map<string, TermSummary>): void {
  for (const [termId, term] of terms) summaries.set(termId, term);
  index = built;
  loaded = true;
  for (const listener of [...listeners]) listener();
}

export function termDetail(termId: string): Promise<TermDetail> {
  const cached = details.get(termId);
  if (cached) return cached;
  const pending = getEnvelope<TermDetail>(`/v1/glossary/${encodeURIComponent(termId)}`).then(
    (envelope) => unwrap(envelope),
  );
  details.set(termId, pending);
  return pending;
}
