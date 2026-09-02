import { getEnvelope } from "../api/client.ts";
import { unwrap } from "../api/envelope.ts";
import type { Envelope } from "../api/envelope.ts";
import { buildIndex } from "./index.ts";
import type { GlossaryIndexPayload } from "./index.ts";
import { publishGlossary } from "./store.ts";
import type { TermSummary } from "./store.ts";

/** The server caps `limit` at 200 and the envelope carries no total, so paging is the only
 *  mechanism there is. Ten pages is 2,000 terms against 87 served today: a bound on a runaway
 *  cursor, not a budget for the vocabulary. */
const PAGE_LIMIT = "200";
const MAX_PAGES = 10;

let truncated = false;

/** Whether the loop stopped at its page cap with terms still unread. */
export function glossaryTruncated(): boolean {
  return truncated;
}

/**
 * DIR-8: one boot fetch of the index and the definitions, so a hover never costs a request.
 *
 * The definitions are paged and this used to read one page and declare itself loaded, so the
 * 201st term onward would render "Definition loading…" for the life of the page -- `show()`
 * never re-fetches -- while the client believed it held the vocabulary. The index is not paged:
 * `/v1/glossary/index` is uncapped, so the highlighter never had this ceiling.
 *
 * Its own module, and not for tidiness: `main.ts` is the entry chunk and the entry chunk has
 * 50 bytes of headroom, so a fetch path that runs exactly once per boot is imported when it is
 * needed rather than paid for in every reader's first paint.
 */
export async function loadGlossary(): Promise<void> {
  const [indexEnvelope, firstPage] = await Promise.all([
    getEnvelope<GlossaryIndexPayload>("/v1/glossary/index"),
    getEnvelope<TermSummary[]>("/v1/glossary", { limit: PAGE_LIMIT }),
  ]);
  const terms = new Map<string, TermSummary>();
  let envelope: Envelope<TermSummary[]> = firstPage;
  truncated = false;
  for (let page = 1; ; page += 1) {
    for (const term of unwrap(envelope)) terms.set(term.term_id, term);
    const cursor = envelope.meta.next_cursor;
    if (cursor === null) break;
    if (page >= MAX_PAGES) {
      // Kept, not thrown. A throw at boot leaves the store unloaded and renders the
      // placeholder on every term, which is the defect this loop exists to fix.
      truncated = true;
      console.warn(`glossary: stopped after ${MAX_PAGES} pages with more terms unread`);
      break;
    }
    envelope = await getEnvelope<TermSummary[]>("/v1/glossary", {
      limit: PAGE_LIMIT,
      cursor,
    });
  }
  publishGlossary(buildIndex(unwrap(indexEnvelope)), terms);
}
