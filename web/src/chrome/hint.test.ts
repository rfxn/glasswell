// @vitest-environment happy-dom
import { readFileSync } from "node:fs";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Test-only import: hint.ts keys on the event name rather than importing the affordance it
// only coaches, so the rail carries no edge into it. This is what proves the two still agree.
import { EXPLAIN_EVENT } from "./handle.ts";
import { HINT_EVENT, HINT_STORAGE_KEY, mountHint, showHint } from "./hint.ts";

const SENTENCE = "Click any ⌾ to see where a number came from.";

let hint: HTMLElement;

function mount(): void {
  document.body.innerHTML = "";
  hint = document.createElement("div");
  hint.hidden = true;
  const text = document.createElement("p");
  text.className = "gw-hint-text";
  const close = document.createElement("button");
  close.type = "button";
  close.className = "gw-hint-close";
  hint.append(text, close);
  document.body.appendChild(hint);
  mountHint(hint);
}

function closeButton(): HTMLButtonElement {
  return hint.querySelector(".gw-hint-close") as HTMLButtonElement;
}

beforeEach(() => {
  window.localStorage.clear();
  mount();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("the ⌾ lesson is coaching, not status", () => {
  it("ships hidden and stays hidden until something asks for it", () => {
    expect(hint.hidden).toBe(true);
  });

  it("carries the sentence it was given, so the frozen call site still owns the words", () => {
    showHint(SENTENCE);

    expect(hint.hidden).toBe(false);
    expect(hint.querySelector(".gw-hint-text")?.textContent).toBe(SENTENCE);
  });

  it("does not take focus from the reader, because nobody asked it to appear", () => {
    const input = document.createElement("input");
    document.body.appendChild(input);
    input.focus();

    showHint(SENTENCE);

    expect(document.activeElement).toBe(input);
  });

  it("names the event the card actually dispatches", () => {
    expect(HINT_EVENT).toBe(EXPLAIN_EVENT);
  });
});

describe("it leaves the moment the lesson has been learned", () => {
  it("goes on the first ⌾ click and does not come back this session", () => {
    showHint(SENTENCE);

    document.dispatchEvent(new CustomEvent(EXPLAIN_EVENT, { bubbles: true }));

    expect(hint.hidden).toBe(true);
    showHint(SENTENCE);
    expect(hint.hidden).toBe(true);
  });

  it("goes when the reader dismisses it", () => {
    showHint(SENTENCE);

    closeButton().click();

    expect(hint.hidden).toBe(true);
  });

  it("goes on Escape, like every other layer in this app", () => {
    showHint(SENTENCE);

    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));

    expect(hint.hidden).toBe(true);
  });

  it("goes when the reader gets on with their work somewhere else", () => {
    showHint(SENTENCE);

    document.body.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));

    expect(hint.hidden).toBe(true);
  });

  it("stays while the reader is inside it, or the close button could never be pressed", () => {
    showHint(SENTENCE);

    closeButton().dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));

    expect(hint.hidden).toBe(false);
  });
});

describe("it is a one-time lesson across visits, not a recurring interruption", () => {
  it("remembers that it was dismissed", () => {
    showHint(SENTENCE);
    closeButton().click();

    expect(window.localStorage.getItem(HINT_STORAGE_KEY)).toBe("seen");
  });

  it("never coaches a returning reader who has already been told", () => {
    window.localStorage.setItem(HINT_STORAGE_KEY, "seen");
    mount();

    showHint(SENTENCE);

    expect(hint.hidden).toBe(true);
  });

  it("only spends the flag when it was actually dismissed, not when it was shown", () => {
    // A reader who reloads mid-glance has not been taught anything yet.
    showHint(SENTENCE);

    expect(window.localStorage.getItem(HINT_STORAGE_KEY)).toBeNull();
  });

  it("survives a browser that throws on storage rather than failing boot", () => {
    vi.spyOn(window.localStorage, "getItem").mockImplementation(() => {
      throw new Error("privacy mode");
    });
    vi.spyOn(window.localStorage, "setItem").mockImplementation(() => {
      throw new Error("privacy mode");
    });
    mount();

    expect(() => showHint(SENTENCE)).not.toThrow();
    expect(hint.hidden).toBe(false);
    expect(() => closeButton().click()).not.toThrow();
  });

  it("follows a second mount rather than leaving the first element driving", () => {
    const first = hint;
    mount();

    showHint(SENTENCE);

    expect(hint.hidden).toBe(false);
    expect(first.hidden).toBe(true);
  });
});

describe("at phone width it does not sit on the pill strip (visual-m23 V-3)", () => {
  // happy-dom does no layout, so the pact is pinned in the shipped CSS: style.css fixes the
  // hint to the viewport band under the rail at <=520px, and map.css moves the pill strip
  // out of that band for exactly as long as the hint is showing.
  const GLOBAL = readFileSync("src/style.css", "utf8");
  const MAP = readFileSync("src/map.css", "utf8");

  function mediaBlock(css: string, query: RegExp): string {
    const start = css.search(query);
    if (start === -1) return "";
    let depth = 0;
    for (let index = css.indexOf("{", start); index < css.length; index += 1) {
      if (css[index] === "{") depth += 1;
      if (css[index] === "}") {
        depth -= 1;
        if (depth === 0) return css.slice(start, index + 1);
      }
    }
    return "";
  }

  it("is viewport-fixed under the rail in the 520px posture — the band the pact is about", () => {
    const posture = mediaBlock(GLOBAL, /@media \(max-width: 520px\)/);
    expect(posture).toMatch(/\.gw-hint\s*\{[^}]*position:\s*fixed/);
  });

  it("moves the band below it while it shows, and only at that width", () => {
    // The pill strip is no longer alone in that band — the fault banner opens in it too — so
    // the clearance is taken by the column the two of them are laid out in rather than by the
    // strip's own offset. Same pact, one row up.
    const clearance = mediaBlock(MAP, /@media \(width <= 520px\)/);
    expect(clearance).toMatch(
      /body:has\(\.gw-hint:not\(\[hidden\]\)\)\s+\.gw-map-chrome\s*\{[^}]*padding-top:\s*4rem/,
    );
    // Unkeyed to the hint's visibility, the band would sit 4rem low forever.
    expect(MAP).not.toMatch(/^\s*\.gw-map-chrome\s*\{[^}]*padding-top:\s*4rem/m);
  });

  it("moves the zoom controls below it the same way, so the + stays reachable (O1)", () => {
    // The same pact as the pills, for the same band: the top-right cluster yields only
    // while the hint shows, and only in the 520px posture.
    const clearance = mediaBlock(MAP, /@media \(width <= 520px\)/);
    expect(clearance).toMatch(
      /body:has\(\.gw-hint:not\(\[hidden\]\)\)\s+\.maplibregl-ctrl-top-right\s*\{[^}]*top/,
    );
    // Unkeyed to the hint's visibility, the cluster would sit 3.4rem low forever.
    expect(MAP).not.toMatch(/^\s*\.maplibregl-ctrl-top-right\s*\{[^}]*top/m);
  });
});
