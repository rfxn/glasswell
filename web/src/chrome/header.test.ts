// @vitest-environment happy-dom
import { readFileSync } from "node:fs";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { HEADER_IDS, wireHeader } from "./header.ts";

// vitest roots at web/, and happy-dom gives import.meta.url an http scheme.
const INDEX = readFileSync("index.html", "utf8");
const MARKUP = /<header id="gw-header"[\s\S]*?<\/header>/.exec(INDEX)?.[0] ?? "";

const onKeyPanel = vi.fn();
let search: HTMLElement;

function element(id: string): HTMLElement {
  return document.getElementById(id) as HTMLElement;
}

beforeEach(() => {
  document.body.innerHTML = `${MARKUP}<div id="gw-toasts"></div>`;
  onKeyPanel.mockClear();
  search = document.createElement("div");
  search.appendChild(document.createElement("input"));
  wireHeader({ search, onKeyPanel });
});

describe("the header is a control surface, not a paragraph", () => {
  it("carries every id the wiring depends on", () => {
    // The fixture is the shipped index.html, so a renamed id fails here, not in a browser.
    for (const id of HEADER_IDS) expect(document.getElementById(id), id).toBeTruthy();
  });

  it("shows the brand lockup and the small mark from web/public/brand", () => {
    const sources = [...document.querySelectorAll("img")].map((image) => image.getAttribute("src"));

    expect(sources).toContain("/brand/logo-horizontal-dark.svg");
    expect(sources).toContain("/brand/logo-mark-small.svg");
  });

  it("keeps the strap to a micro-line and moves the sentence into Help", () => {
    const strap = document.querySelector(".gw-strap")?.textContent?.trim() ?? "";

    expect(strap.split(/\s+/)).toHaveLength(3);
    expect(element("gw-help-panel").textContent).toContain("derivation");
  });

  it("mounts the search box into the header's control cluster", () => {
    expect(element("gw-search-slot").querySelector("input")).toBeTruthy();
  });
});

describe("the help disclosure", () => {
  it("opens and closes, keeping aria-expanded truthful", () => {
    const button = element("gw-help-btn");

    button.click();
    expect(button.getAttribute("aria-expanded")).toBe("true");
    expect(element("gw-help-panel").hidden).toBe(false);

    button.click();
    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(element("gw-help-panel").hidden).toBe(true);
  });

  it("closes on Escape and hands focus back to the button", () => {
    const button = element("gw-help-btn");
    button.click();

    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));

    expect(element("gw-help-panel").hidden).toBe(true);
    expect(document.activeElement).toBe(button);
  });

  it("closes when a click lands outside it", () => {
    element("gw-help-btn").click();

    document.body.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));

    expect(element("gw-help-panel").hidden).toBe(true);
  });
});

describe("the key chip", () => {
  it("starts hidden, because a working key is not news", () => {
    expect(element("gw-key-btn").hidden).toBe(true);
  });

  it("opens the key panel when a rejected key makes it visible", () => {
    const chip = element("gw-key-btn");
    chip.hidden = false;

    chip.click();

    expect(onKeyPanel).toHaveBeenCalledOnce();
  });
});
