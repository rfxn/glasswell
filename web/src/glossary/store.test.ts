// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { termSummary } = await import("./store.ts");
const { glossaryTruncated, loadGlossary } = await import("./load.ts");

const PAGE = 200;

function term(ordinal: number) {
  return {
    term_id: `gt_${ordinal}`,
    term: `Term ${ordinal}`,
    aliases: [],
    short_definition: `Definition ${ordinal}`,
    domain_tags: [],
    highlightable: false,
  };
}

/** The server's own shape: 200 a page, a cursor while more remain, null on the last. */
function servingTerms(total: number) {
  return (input: string) => {
    const url = new URL(input, "https://gw.invalid");
    if (url.pathname.endsWith("/glossary/index")) {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            data: { index_version: "gix_test", entries: [], stopwords: [] },
            meta: { as_of: "2026-09-02", labels: {}, warnings: [], next_cursor: null },
            links: {},
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      );
    }
    const offset = Number(url.searchParams.get("cursor") ?? "0");
    const items = Array.from(
      { length: Math.max(0, Math.min(PAGE, total - offset)) },
      (_, position) => term(offset + position),
    );
    const next = offset + items.length < total ? String(offset + items.length) : null;
    return Promise.resolve(
      new Response(
        JSON.stringify({
          data: items,
          meta: { as_of: "2026-09-02", labels: {}, warnings: [], next_cursor: next },
          links: {},
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
  };
}

describe("a vocabulary larger than one page", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("loads every term of a 250-term vocabulary rather than the first 200", async () => {
    fetchMock = vi.fn(servingTerms(250));
    vi.stubGlobal("fetch", fetchMock);

    await loadGlossary();

    // The defect: term 200 onward rendered "Definition loading…" for the life of the page,
    // because show() never re-fetches and the client believed it held the vocabulary.
    expect(termSummary("gt_0")).not.toBeNull();
    expect(termSummary("gt_200")).not.toBeNull();
    expect(termSummary("gt_249")).not.toBeNull();
    expect(glossaryTruncated()).toBe(false);
  });

  it("stops at its page cap without throwing, and keeps what it already read", async () => {
    fetchMock = vi.fn(servingTerms(2_100));
    vi.stubGlobal("fetch", fetchMock);

    await expect(loadGlossary()).resolves.toBeUndefined();

    // A throw at boot would leave `loaded` false and render the placeholder on every term,
    // which is the defect the loop exists to fix rather than a stricter version of it.
    expect(termSummary("gt_1999")).not.toBeNull();
    expect(termSummary("gt_2000")).toBeNull();
    expect(glossaryTruncated()).toBe(true);
    expect(console.warn).toHaveBeenCalledTimes(1);
  });

  it("reads the resident vocabulary in one round trip", async () => {
    fetchMock = vi.fn(servingTerms(87));
    vi.stubGlobal("fetch", fetchMock);

    await loadGlossary();

    const glossaryCalls = fetchMock.mock.calls.filter(
      (call) => String(call[0]).includes("/glossary") && !String(call[0]).includes("/index"),
    );
    expect(glossaryCalls).toHaveLength(1);
    expect(glossaryTruncated()).toBe(false);
  });
});
