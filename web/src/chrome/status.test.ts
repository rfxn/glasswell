// @vitest-environment happy-dom
import { readFileSync } from "node:fs";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { mountStatus, setKeyState, setStatus, setVintage, toast } from "./status.ts";

let status: HTMLElement;
let vintage: HTMLElement;
let toasts: HTMLElement;
let keyState: HTMLButtonElement;

// A hand-rolled MediaQueryList: the rail's brief copy is chosen by a media query, and the
// test has to be able to cross that boundary in both directions.
const listeners: ((event: MediaQueryListEvent) => void)[] = [];
const media = {
  matches: false,
  addEventListener: (_: string, handler: (event: MediaQueryListEvent) => void) =>
    listeners.push(handler),
  removeEventListener: () => {},
};

function narrow(value: boolean): void {
  media.matches = value;
  for (const handler of [...listeners]) handler({ matches: value } as MediaQueryListEvent);
}

beforeEach(() => {
  vi.useFakeTimers();
  listeners.length = 0;
  media.matches = false;
  vi.stubGlobal("matchMedia", () => media);
  document.body.innerHTML = "";
  status = document.createElement("p");
  vintage = document.createElement("p");
  toasts = document.createElement("div");
  keyState = document.createElement("button");
  document.body.append(status, vintage, toasts, keyState);
  mountStatus({ status, vintage, toasts, keyState });
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("the four status channels are not interchangeable (harvest item 10)", () => {
  it("writes the persistent app status to its own slot", () => {
    setStatus("43,102 wells in this slice");

    expect(status.textContent).toBe("43,102 wells in this slice");
  });

  it("keeps the long form in the tooltip so the slot never has to grow", () => {
    setStatus("degraded", "nd_mpr_xlsx has not reported since 2026-06-01");

    expect(status.title).toBe("nd_mpr_xlsx has not reported since 2026-06-01");
  });

  it("marks a degraded status as a chip rather than as ordinary muted text", () => {
    setStatus("glossary unavailable", undefined, { degraded: true });
    expect(status.classList.contains("gw-degraded")).toBe(true);

    setStatus("ready");
    expect(status.classList.contains("gw-degraded")).toBe(false);
  });

  it("says something shorter on a phone rather than truncating to a stub", () => {
    // gate-v MINOR-1: at 390 the healthy line ellipsised to "Click any ⌾ to…", which spends
    // rail width to convey nothing. The slot is a fixed column now, so the copy has to fit
    // it — the brief form is a sentence, not the long one with its end cut off.
    narrow(true);

    setStatus("Click any ⌾ to see where a number came from.", undefined, { brief: "⌾ traces it" });

    expect(status.textContent).toBe("⌾ traces it");
    expect(status.title).toBe("Click any ⌾ to see where a number came from.");
  });

  it("swaps back to the long form when the rail is wide enough for it", () => {
    narrow(true);
    setStatus("Glossary unavailable", undefined, { brief: "glossary down", degraded: true });
    expect(status.textContent).toBe("glossary down");

    narrow(false);

    expect(status.textContent).toBe("Glossary unavailable");
    expect(status.classList.contains("gw-degraded")).toBe(true);
  });

  it("falls back to the one string it was given when no brief form exists", () => {
    narrow(true);

    setStatus("43,102 wells in this slice");

    expect(status.textContent).toBe("43,102 wells in this slice");
  });

  it("never lets a transient failure erase the freshness slot", () => {
    // Routing gesture failures through the status slot is the incident responder recorded:
    // the board read healthier than it was because a live warning had been overwritten.
    setStatus("degraded", undefined, { degraded: true });

    toast("Search failed. Try again.");

    expect(status.textContent).toBe("degraded");
    expect(toasts.textContent).toContain("Search failed");
  });

  it("auto-dismisses a toast, because gesture feedback is not a statement about the data", () => {
    toast("Search failed. Try again.");

    vi.advanceTimersByTime(6000);

    expect(toasts.children).toHaveLength(0);
  });

  it("writes the vintage as a machine-readable time in its own slot", () => {
    setVintage("2026-08-20");

    expect(vintage.textContent).toContain("2026-08-20");
    expect(vintage.querySelector("time")?.getAttribute("datetime")).toBe("2026-08-20");
  });

  it("says so honestly when no vintage has been resolved yet", () => {
    setVintage(null);

    expect(vintage.textContent).toContain("as_of —");
  });

  it("keeps the key channel apart from the status channel", () => {
    setStatus("ready");

    setKeyState("rejected");

    expect(keyState.textContent).toContain("key rejected");
    expect(keyState.hidden).toBe(false);
    expect(status.textContent).toBe("ready");
  });

  it("hides the key chip once a key is working, so chrome reports only what matters", () => {
    setKeyState("rejected");

    setKeyState("ok");

    expect(keyState.hidden).toBe(true);
  });
});

// gate-v m-2: `status.ts` justifies keying BRIEF on main.ts's literals with "main.ts is
// frozen". Nothing asserted the two still matched, so a rename would have silently restored
// the long form at the width the brief one exists for. vitest roots at web/.
const MAIN_SOURCE = readFileSync("src/main.ts", "utf8");
const STATUS_SOURCE = readFileSync("src/chrome/status.ts", "utf8");

describe("the brief rail copy is keyed on strings the frozen call site actually sets", () => {
  it("finds every BRIEF key verbatim in main.ts", () => {
    const table = /const BRIEF: Record<string, string> = \{([\s\S]*?)\n\};/.exec(STATUS_SOURCE);
    const keys = [...(table?.[1] ?? "").matchAll(/^\s*"([^"]*)":/gm)].map((match) => match[1]);

    expect(keys).toHaveLength(2);
    for (const key of keys) expect(MAIN_SOURCE, key).toContain(`setStatus("${key}"`);
  });
});
