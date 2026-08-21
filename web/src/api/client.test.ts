// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ResponseMeta } from "./client.ts";

const { ApiError, apiKey, authHeaders, clearKey, getEnvelope, isKeyShaped, saveKey, storedKey } =
  await import("./client.ts");

const KEY = "a".repeat(64);
const ENVELOPE = { data: { api10: "3305310451" }, meta: { as_of: "2026-08-01" } };

function visit(url: string): void {
  window.history.replaceState(null, "", url);
}

function responds(status: number, body: unknown, headers: Record<string, string> = {}) {
  return vi.fn(() =>
    Promise.resolve(
      new Response(JSON.stringify(body), {
        status,
        headers: { "content-type": "application/json", ...headers },
      }),
    ),
  );
}

beforeEach(() => {
  window.localStorage.clear();
  visit(`/`);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the owner key never travels in a place the server logs", () => {
  it("reads the key from the fragment, which is never sent to the server", () => {
    visit(`/#key=${KEY}`);

    expect(apiKey()).toBe(KEY);
  });

  it("strips the key from the fragment once it is stored", () => {
    visit(`/?map=7.00/47.80000/-102.80000#key=${KEY}`);

    apiKey();

    expect(window.location.hash).toBe("");
    expect(window.location.href).not.toContain(KEY);
    expect(window.location.search).toBe("?map=7.00/47.80000/-102.80000");
  });

  it("keeps the rest of the fragment when it strips the key", () => {
    visit(`/#key=${KEY}&note=hello`);

    apiKey();

    expect(window.location.hash).toBe("#note=hello");
  });

  it("refuses the query-string form, because uvicorn writes it to the journal", () => {
    visit(`/?key=${KEY}`);

    expect(apiKey()).toBeNull();
    expect(window.localStorage.getItem("glasswell.key")).toBeNull();
  });

  it("remembers the key for later visits that carry no fragment", () => {
    visit(`/#key=${KEY}`);
    apiKey();
    visit(`/`);

    expect(apiKey()).toBe(KEY);
    expect(authHeaders()).toEqual({ "X-Glasswell-Key": KEY });
  });

  it("sends no header at all when no key has been seen", () => {
    expect(apiKey()).toBeNull();
    expect(authHeaders()).toEqual({});
  });
});

describe("a stored key can be replaced without devtools (UX P1-6)", () => {
  it("stores a key the UI collected", () => {
    saveKey(KEY);

    expect(storedKey()).toBe(KEY);
    expect(authHeaders()).toEqual({ "X-Glasswell-Key": KEY });
  });

  it("forgets a wrong key, so the next load is the honest no-key state", () => {
    saveKey(KEY);

    clearKey();

    expect(storedKey()).toBeNull();
    expect(authHeaders()).toEqual({});
  });

  it("recognises the 64-hex shape in either case, and nothing else", () => {
    expect(isKeyShaped(KEY)).toBe(true);
    expect(isKeyShaped("A".repeat(64))).toBe(true);
    expect(isKeyShaped("a".repeat(63))).toBe(false);
    expect(isKeyShaped(`${"a".repeat(63)}z`)).toBe(false);
    expect(isKeyShaped("")).toBe(false);
  });

  it("trims a pasted key rather than storing the whitespace with it", () => {
    saveKey(`  ${KEY}\n`);

    expect(storedKey()).toBe(KEY);
  });
});

describe("a response can report itself, so the API pane can quote it (SB-08 §4.4)", () => {
  it("fills the out-parameter with the status, the headers and the elapsed milliseconds", async () => {
    vi.stubGlobal("fetch", responds(200, ENVELOPE, { "X-Glasswell-Vintage": "2026-08-01" }));
    const meta: { out?: ResponseMeta } = {};

    const envelope = await getEnvelope<{ api10: string }>("/v1/wells", {}, undefined, meta);

    expect(envelope).toEqual(ENVELOPE);
    expect(meta.out?.status).toBe(200);
    expect(meta.out?.headers.get("x-glasswell-vintage")).toBe("2026-08-01");
    expect(Number.isFinite(meta.out?.elapsed_ms)).toBe(true);
    expect(meta.out?.elapsed_ms).toBeGreaterThanOrEqual(0);
  });

  it("returns the same envelope when nobody asks, so every existing call site is unchanged", async () => {
    const fetchSpy = responds(200, ENVELOPE);
    vi.stubGlobal("fetch", fetchSpy);

    expect(await getEnvelope("/v1/wells")).toEqual(ENVELOPE);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  // §4.7: a failed request keeps its REQUEST block, so it has to keep its status and its timing.
  it("fills the out-parameter before it throws, so a failure is still quotable", async () => {
    vi.stubGlobal(
      "fetch",
      responds(404, { type: "/v1/problems/not_found", title: "Not found", status: 404 }),
    );
    const meta: { out?: ResponseMeta } = {};

    await expect(getEnvelope("/v1/wells/0000000000", {}, undefined, meta)).rejects.toBeInstanceOf(
      ApiError,
    );

    expect(meta.out?.status).toBe(404);
    expect(Number.isFinite(meta.out?.elapsed_ms)).toBe(true);
  });
});
