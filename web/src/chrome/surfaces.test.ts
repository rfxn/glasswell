import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

// The overlay family's layout contract, read off the shipped sheets. happy-dom lays nothing
// out, so what a browser measures belongs in tests/e2e; what is pinnable here is the
// declaration each of these defects was fixed by, so a later sheet edit cannot quietly undo
// one. The precedent is map/legend.test.ts and explore/grid/styles.test.ts.
const STYLE = readFileSync("src/style.css", "utf8");
const MAP = readFileSync("src/map.css", "utf8");

const rule = (css: string, selector: string): string => {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(^|\\})[^{}]*?${escaped}\\s*\\{[^}]*\\}`, "m").exec(css)?.[0] ?? "";
};

describe("a capped panel caps what it renders inside itself", () => {
  // card.ts renders .gw-panel-head and .gw-panel-body inside an <article>, so the shell's cap
  // and the body's `overflow-y: auto` had an unstyled flex item between them: the article
  // sized to its content and the body never got a height to scroll against. Measured before
  // the fix at 1024x768 — 971 px of card in a 685 px shell, the last 286 px off the viewport
  // with nothing on screen saying more existed.
  it("passes the shell's cap through the card's own wrapper", () => {
    const card = rule(STYLE, ".gw-card");
    expect(card).toContain("flex-direction: column");
    expect(card).toContain("min-height: 0");
  });

  it("keeps the shell a flex column that only its body scrolls", () => {
    expect(rule(STYLE, "#gw-card")).toBeTruthy();
    expect(STYLE).toContain("flex-direction: column");
    expect(rule(STYLE, ".gw-panel-body")).toContain("overflow-y: auto");
  });
});

describe("a popover states how much of itself it is showing", () => {
  it("caps the glossary popover and scrolls it rather than clipping it", () => {
    const popover = rule(STYLE, ".gw-popover");
    expect(popover).toContain("max-height:");
    expect(popover).toContain("overflow-y: auto");
    expect(popover).toContain("overscroll-behavior: contain");
  });
});

describe("the map's top band is one column, not three surfaces on one spot", () => {
  // The fault line is `role="status"` map chrome; the coach mark is a rail popout at
  // --gw-z-rail-pop, which is above it. Measured before the fix: the mark covered the banner
  // at 1366, 1024, 820 and 390 — every width but the widest.
  it("drops the fault banner clear of the coach mark", () => {
    expect(MAP).toMatch(/body:has\(\.gw-hint:not\(\[hidden\]\)\)\s*\.gw-banner\s*\{[^}]*top:\s*4rem/);
  });

  // Absolutely positioned with `left: 50%` and no `right`, the banner's available width is
  // half the viewport, so its declared 32rem cap was unreachable: 195 px of a 358 px
  // allowance at 390, and the sentence wrapped to three lines inside it.
  it("sizes the banner to its sentence rather than to half the viewport", () => {
    expect(rule(MAP, ".gw-banner")).toContain("width: max-content");
  });

  it("stacks the banner and the pill strip instead of overlaying them at phone width", () => {
    const narrow = /@media \(width <= 520px\) \{[\s\S]*?\n\}/.exec(MAP)?.[0] ?? "";
    expect(narrow).toContain("flex-direction: column");
    expect(narrow).toMatch(/\.gw-banner,\s*\n\s*\.gw-pills\s*\{[^}]*position: static/);
  });
});

describe("the two map keys do not land on each other", () => {
  // At 390 the status key is capped at 11rem and the thematic key at 16rem: 432 px of key in
  // a 390 px viewport. Measured before the fix — the thematic key covered 62 px of the open
  // status key, including its rows' ⌾ handles.
  it("reserves the status key's column out of the thematic key's width", () => {
    // In thematics.css, not map.css: the base `max-width: 16rem` is that sheet's, the two
    // selectors weigh the same, and which sheet the bundler emits last would otherwise decide
    // it — the cascade trap explore/grid/grid.css already carries a note about.
    const thematics = readFileSync("src/map/thematics.css", "utf8");
    expect(rule(MAP, ".gw-map-chrome")).toContain("--gw-key-col");
    expect(thematics).toMatch(
      /@media \(width <= 520px\) \{[^}]*\.gw-thm\s*\{[^}]*max-width:\s*calc\([^)]*var\(--gw-key-col\)/,
    );
  });

  // The status key folds because its rows and its vocabulary note both grow with the data;
  // the thematic key's copy is fixed, so it is sized, not folded — and a fold would scroll
  // its own ⌾ out of frame, since the handle is positioned against the key.
  it("leaves the thematic key's explain handle pinned to the key", () => {
    const thematics = readFileSync("src/map/thematics.css", "utf8");
    expect(rule(thematics, ".gw-thm")).not.toContain("overflow-y");
    expect(rule(thematics, ".gw-thm-handle")).toContain("position: absolute");
  });
});

describe("the z-index ladder has no raw numbers outside style.css", () => {
  // style.css declares the ladder and says a raw z-index anywhere else is a bug. The map
  // chrome carried a literal 6 against a token that reads 5.
  it("takes the map chrome's layer from the ladder", () => {
    expect(rule(MAP, ".gw-map-chrome")).toContain("z-index: var(--gw-z-map-chrome)");
  });
});
