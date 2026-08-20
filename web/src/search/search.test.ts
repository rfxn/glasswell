// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createSearch } from "./search.ts";
import type { SearchResult } from "./query.ts";

const listBody = {
  data: [
    {
      api10: "3302501169",
      well_name: "MANDAREE 30-31H",
      operator_name_reported: "MARATHON OIL COMPANY",
      status_canonical: "active",
    },
    {
      api10: "3302501170",
      well_name: "MANDAREE 30-32H",
      operator_name_reported: "MARATHON OIL COMPANY",
      status_canonical: "plugged",
    },
  ],
  meta: {},
  links: {},
};

const calls: { url: string; signal: AbortSignal | undefined }[] = [];
const picked: SearchResult[] = [];
let host: HTMLElement;
let input: HTMLInputElement;
let body: unknown = listBody;

function stub(): void {
  vi.stubGlobal("fetch", (url: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(url), signal: init?.signal ?? undefined });
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
  });
}

async function type(term: string): Promise<void> {
  input.value = term;
  input.dispatchEvent(new Event("input"));
  await vi.advanceTimersByTimeAsync(300);
  await Promise.resolve();
}

function key(name: string): void {
  input.dispatchEvent(new KeyboardEvent("keydown", { key: name, bubbles: true, cancelable: true }));
}

function options(): HTMLElement[] {
  return [...host.querySelectorAll<HTMLElement>("[role='option']")];
}

beforeEach(() => {
  vi.useFakeTimers();
  document.body.innerHTML = "";
  calls.length = 0;
  picked.length = 0;
  body = listBody;
  stub();
  host = createSearch({ onPick: (result) => picked.push(result), onError: () => {} });
  document.body.appendChild(host);
  input = host.querySelector("input") as HTMLInputElement;
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("the search box", () => {
  it("exists at all — the app shipped with no text input anywhere", () => {
    expect(input).toBeTruthy();
    expect(input.type).toBe("search");
    expect(input.getAttribute("aria-label")).toBeTruthy();
  });

  it("carries its glyph inside the field, and the glyph says nothing to a screen reader", () => {
    const icon = host.querySelector(".gw-search-icon");

    expect(icon).toBeTruthy();
    expect(icon?.getAttribute("aria-hidden")).toBe("true");
    expect(host.querySelectorAll("[aria-label]")).toHaveLength(2); // the input and the list
  });

  it("debounces to one request per burst of typing", async () => {
    input.value = "man";
    input.dispatchEvent(new Event("input"));
    input.value = "mand";
    input.dispatchEvent(new Event("input"));
    await type("mandaree");

    expect(calls).toHaveLength(1);
    expect(calls[0]?.url).toContain("q=mandaree");
  });

  it("sends a ten-digit term to the well route", async () => {
    body = { data: { api10: "3305310451", well_name: "Mandaree 50-2008H" }, meta: {}, links: {} };

    await type("3305310451");

    expect(calls[0]?.url).toContain("/v1/wells/3305310451");
  });

  it("aborts the superseded request rather than racing it", async () => {
    await type("mandaree");
    await type("mandaree 3");

    expect(calls[0]?.signal?.aborted).toBe(true);
    expect(calls[1]?.signal?.aborted).toBe(false);
  });

  it("renders the name, the api10 and the operator on every row", async () => {
    await type("mandaree");

    expect(options()).toHaveLength(2);
    expect(options()[0]?.textContent).toContain("MANDAREE 30-31H");
    expect(options()[0]?.textContent).toContain("3302501169");
    expect(options()[0]?.textContent).toContain("MARATHON OIL COMPANY");
  });

  it("says so in the product's voice when nothing matches", async () => {
    body = { data: [], meta: {}, links: {} };

    await type("zzz");

    expect(host.textContent).toContain("No well matches");
    expect(options()).toHaveLength(0);
  });

  it("picks the highlighted row on Enter", async () => {
    await type("mandaree");
    key("ArrowDown");
    key("ArrowDown");
    key("Enter");

    expect(picked).toHaveLength(1);
    expect(picked[0]?.api10).toBe("3302501170");
  });

  it("picks the first row on Enter without arrowing", async () => {
    await type("mandaree");
    key("Enter");

    expect(picked[0]?.api10).toBe("3302501169");
  });

  it("picks on click", async () => {
    await type("mandaree");
    options()[1]?.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));

    expect(picked[0]?.api10).toBe("3302501170");
  });

  it("closes on Escape and stops advertising results", async () => {
    await type("mandaree");
    expect(input.getAttribute("aria-expanded")).toBe("true");

    key("Escape");

    expect(input.getAttribute("aria-expanded")).toBe("false");
    expect(options()).toHaveLength(0);
  });

  it("closes when the term is emptied, without asking the API for every well", async () => {
    await type("mandaree");
    await type("");

    expect(calls).toHaveLength(1);
    expect(options()).toHaveLength(0);
  });
});

describe("the / shortcut", () => {
  it("focuses the box from anywhere in the document", () => {
    document.body.focus();

    document.dispatchEvent(new KeyboardEvent("keydown", { key: "/", bubbles: true, cancelable: true }));

    expect(document.activeElement).toBe(input);
  });

  it("stays out of the way once focus is already in a text field", () => {
    const other = document.createElement("input");
    document.body.appendChild(other);
    other.focus();

    const event = new KeyboardEvent("keydown", { key: "/", bubbles: true, cancelable: true });
    document.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(false);
    expect(document.activeElement).toBe(other);
  });
});
