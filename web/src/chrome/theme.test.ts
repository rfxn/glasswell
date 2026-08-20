// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  THEME_EVENT,
  THEME_STORAGE_KEY,
  applyTheme,
  currentTheme,
  mountThemeToggle,
  storedTheme,
  themeToggleEnabled,
} from "./theme.ts";

let button: HTMLButtonElement;

function mount(): void {
  button = document.createElement("button");
  button.appendChild(Object.assign(document.createElement("span"), { className: "gw-ctl-lbl" }));
  document.body.appendChild(button);
  mountThemeToggle(button);
}

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
  document.body.innerHTML = "";
  // The theme itself is finished; what is gated is reaching it from the rail. Everything
  // below this line describes the flag-on surface, so it says so rather than inheriting it.
  vi.stubEnv("VITE_GW_THEME_TOGGLE", "1");
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

/**
 * gate-v BLOCKER-2: the theme is reachable from the rail and breaks where the chrome meets
 * the map — map.css hardcodes a dark overlay surface while taking `color: var(--paper)`,
 * which the light theme inverts. That file belongs to Track M, so the fix here is to make
 * the surface unreachable rather than to cross the boundary. The theme and its tests stay.
 */
describe("with the toggle flag off, which is the shipped default", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_GW_THEME_TOGGLE", "");
  });

  it("leaves no toggle in the rail to press", () => {
    mount();

    expect(document.body.contains(button)).toBe(false);
    expect(themeToggleEnabled()).toBe(false);
  });

  it("holds the document on dark even for a reader who stored light before the flag", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "light");

    mount();

    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(currentTheme()).toBe("dark");
  });

  it("keeps applyTheme working, so un-flagging needs no second change", () => {
    mount();

    applyTheme("light");

    expect(document.documentElement.dataset.theme).toBe("light");
  });
});

describe("the theme the reader gets", () => {
  it("is dark when nothing has been chosen, because the default basemap is dark", () => {
    mount();

    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(currentTheme()).toBe("dark");
  });

  it("is the one stored on the last visit", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "light");

    mount();

    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("ignores a stored value it would never have written", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "satellite");

    expect(storedTheme()).toBeNull();
    mount();
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("survives a browser that throws on storage rather than failing boot", () => {
    vi.spyOn(window.localStorage, "getItem").mockImplementation(() => {
      throw new Error("privacy mode");
    });

    expect(() => mount()).not.toThrow();
    expect(document.documentElement.dataset.theme).toBe("dark");
  });
});

describe("the theme control", () => {
  it("flips the document attribute and remembers the choice", () => {
    mount();

    button.click();
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");

    button.click();
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
  });

  it("still flips when storage refuses the write", () => {
    vi.spyOn(window.localStorage, "setItem").mockImplementation(() => {
      throw new Error("quota");
    });
    mount();

    expect(() => button.click()).not.toThrow();
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("says what the next click will do, not what the theme is now", () => {
    // A toggle labelled with its current state is the oldest ambiguity in chrome design.
    mount();

    expect(button.getAttribute("aria-pressed")).toBe("false");
    expect(button.title).toContain("light");
    expect(button.querySelector(".gw-ctl-lbl")?.textContent).toBe("Light");

    button.click();

    expect(button.getAttribute("aria-pressed")).toBe("true");
    expect(button.title).toContain("dark");
    expect(button.querySelector(".gw-ctl-lbl")?.textContent).toBe("Dark");
  });

  it("writes only values it can read back", () => {
    mount();

    button.click();

    expect(storedTheme()).toBe(currentTheme());
  });

  it("announces the change, because a canvas cannot inherit a CSS variable", () => {
    // The production plot is painted, not styled: it re-reads the palette when this fires.
    const seen: string[] = [];
    document.addEventListener(THEME_EVENT, (event) =>
      seen.push((event as CustomEvent<{ theme: string }>).detail.theme),
    );
    mount();

    button.click();
    button.click();

    expect(seen).toEqual(["light", "dark"]);
  });
});
