// @vitest-environment happy-dom
import { beforeEach, describe, expect, it } from "vitest";

const { apiKey, authHeaders, clearKey, isKeyShaped, saveKey, storedKey } = await import(
  "./client.ts"
);

const KEY = "a".repeat(64);

function visit(url: string): void {
  window.history.replaceState(null, "", url);
}

beforeEach(() => {
  window.localStorage.clear();
  visit(`/`);
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
