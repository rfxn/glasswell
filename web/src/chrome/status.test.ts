// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { mountStatus, setKeyState, setStatus, setVintage, toast } from "./status.ts";

let status: HTMLElement;
let vintage: HTMLElement;
let toasts: HTMLElement;
let keyState: HTMLButtonElement;

beforeEach(() => {
  vi.useFakeTimers();
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
