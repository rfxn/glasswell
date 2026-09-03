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

  it("reads a vocabulary past the old ten-page cap to its end", async () => {
    // 2,100 terms is eleven pages: one more than the fixed cap this loop used to carry, which
    // silently dropped term 2,000 onward and reported the vocabulary unread. The bound is the
    // data now, so the only limit is what the server serves.
    fetchMock = vi.fn(servingTerms(2_100));
    vi.stubGlobal("fetch", fetchMock);

    await expect(loadGlossary()).resolves.toBeUndefined();

    expect(termSummary("gt_1999")).not.toBeNull();
    expect(termSummary("gt_2000")).not.toBeNull();
    expect(termSummary("gt_2099")).not.toBeNull();
    expect(glossaryTruncated()).toBe(false);
    expect(console.warn).not.toHaveBeenCalled();
  });

  it("treats an envelope with no next_cursor key as the last page", async () => {
    // The shape every mocked fixture serves and the deployed API never does: `meta: {}`.
    // `=== null` read the absent key as "keep going", so the loop re-requested the same page
    // until its cap and warned about terms nobody was withholding.
    fetchMock = vi.fn((input: string) => {
      const url = new URL(input, "https://gw.invalid");
      const data = url.pathname.endsWith("/glossary/index")
        ? { index_version: "gix_test", entries: [], stopwords: [] }
        : [term(1)];
      return Promise.resolve(
        new Response(JSON.stringify({ data, meta: {}, links: {} }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    await loadGlossary();

    const glossaryCalls = fetchMock.mock.calls.filter(
      (call) => String(call[0]).includes("/glossary") && !String(call[0]).includes("/index"),
    );
    expect(glossaryCalls).toHaveLength(1);
    expect(glossaryTruncated()).toBe(false);
    expect(console.warn).not.toHaveBeenCalled();
  });

  it("refuses a cursor that offers a page and returns nothing new, naming the count", async () => {
    // The runaway the old page cap was standing in for, caught where it starts rather than
    // ten requests later: a cursor that never advances can never terminate.
    fetchMock = vi.fn((input: string) => {
      const url = new URL(input, "https://gw.invalid");
      const data = url.pathname.endsWith("/glossary/index")
        ? { index_version: "gix_test", entries: [], stopwords: [] }
        : [term(1), term(2)];
      return Promise.resolve(
        new Response(
          JSON.stringify({ data, meta: { next_cursor: "stuck" }, links: {} }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(loadGlossary()).resolves.toBeUndefined();

    // Two terms are held rather than none: stopping is not the same as discarding.
    expect(termSummary("gt_1")).not.toBeNull();
    expect(glossaryTruncated()).toBe(true);
    expect(console.warn).toHaveBeenCalledTimes(1);
    expect(vi.mocked(console.warn).mock.calls[0]?.[0]).toContain("after 2 terms");
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
