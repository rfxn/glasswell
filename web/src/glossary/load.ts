import { getEnvelope } from "../api/client.ts";
import { unwrap } from "../api/envelope.ts";
import type { Envelope } from "../api/envelope.ts";
import { buildIndex } from "./index.ts";
import type { GlossaryIndexPayload } from "./index.ts";
import { publishGlossary } from "./store.ts";
import type { TermSummary } from "./store.ts";

/** The server caps `limit` at 200 and the envelope carries no total, so paging is the only
 *  mechanism there is. The bound is the vocabulary the server actually serves rather than a
 *  page count: every page has to add a term the loop did not already hold, so the loop cannot
 *  outrun the data, and a cursor that offers a next page while yielding nothing new is the
 *  runaway shape itself and is refused where it starts. */
const PAGE_LIMIT = "200";

let truncated = false;

/** Whether the loop stopped with terms still unread. */
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
 * Its own module, and not for tidiness: `main.ts` is the entry chunk, this loop costs more than
 * the budget's remaining headroom, and a fetch path that runs exactly once per boot is imported
 * when it runs rather than paid for in every reader's first paint. web/PERF.md holds the
 * measurement and the tree it was taken on -- three copies of a byte count is how the last one
 * went stale.
 */
export async function loadGlossary(): Promise<void> {
  const [indexEnvelope, firstPage] = await Promise.all([
    getEnvelope<GlossaryIndexPayload>("/v1/glossary/index"),
    getEnvelope<TermSummary[]>("/v1/glossary", { limit: PAGE_LIMIT }),
  ]);
  const terms = new Map<string, TermSummary>();
  let envelope: Envelope<TermSummary[]> = firstPage;
  truncated = false;
  for (;;) {
    const held = terms.size;
    for (const term of unwrap(envelope)) terms.set(term.term_id, term);
    // Absent counts as offered-nothing, not as unknown. `=== null` read a `meta` without the
    // key as "keep going", so an envelope that omits `next_cursor` drove the loop to its cap
    // and reported a vocabulary unread against a server that had served all of it.
    const cursor = envelope.meta.next_cursor ?? null;
    if (cursor === null) break;
    if (terms.size === held) {
      // Kept, not thrown. A throw at boot leaves the store unloaded and renders the
      // placeholder on every term, which is the defect this loop exists to fix.
      truncated = true;
      console.warn(
        `glossary: cursor offered another page after ${terms.size} terms and returned none` +
          " that were new; stopped rather than paging forever",
      );
      break;
    }
    envelope = await getEnvelope<TermSummary[]>("/v1/glossary", {
      limit: PAGE_LIMIT,
      cursor,
    });
  }
  publishGlossary(buildIndex(unwrap(indexEnvelope)), terms);
}
