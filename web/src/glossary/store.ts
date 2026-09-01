import { getEnvelope } from "../api/client.ts";
import { unwrap } from "../api/envelope.ts";
import { buildIndex } from "./index.ts";
import type { GlossaryIndexPayload, TermIndex } from "./index.ts";

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

/** DIR-8: one boot fetch of the index and the definitions, so a hover never costs a request. */
export async function loadGlossary(): Promise<TermIndex> {
  const [indexEnvelope, termsEnvelope] = await Promise.all([
    getEnvelope<GlossaryIndexPayload>("/v1/glossary/index"),
    getEnvelope<TermSummary[]>("/v1/glossary", { limit: "200" }),
  ]);
  for (const term of unwrap(termsEnvelope)) summaries.set(term.term_id, term);
  index = buildIndex(unwrap(indexEnvelope));
  loaded = true;
  for (const listener of [...listeners]) listener();
  return index;
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
