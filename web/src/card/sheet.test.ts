// @vitest-environment happy-dom
import { readFileSync, readdirSync } from "node:fs";

import { beforeEach, describe, expect, it } from "vitest";

import { wireSheet } from "./sheet.ts";

// The chrome/surfaces.test.ts precedent: read the shipped sheet, not a fixture of it. happy-dom
// lays nothing out, so the pixel geometry is tests/e2e's; what is pinnable here is the
// declaration each requirement rests on, so a later edit cannot quietly undo one.
const STYLE = readFileSync("src/style.css", "utf8");
const INDEX = readFileSync("index.html", "utf8");
const MAP = readFileSync("src/map/map.ts", "utf8");

const rule = (css: string, selector: string): string => {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(^|\\})[^{}]*?${escaped}\\s*\\{[^}]*\\}`, "m").exec(css)?.[0] ?? "";
};

/** The body of the first `@media (<query>)` block, so a rule can be pinned to its arm. */
const media = (css: string, query: string): string => {
  const start = css.indexOf(`@media (${query})`);
  if (start < 0) return "";
  let depth = 0;
  for (let i = css.indexOf("{", start); i < css.length; i += 1) {
    if (css[i] === "{") depth += 1;
    if (css[i] === "}") {
      depth -= 1;
      if (depth === 0) return css.slice(start, i + 1);
    }
  }
  return "";
};

describe("the card is a column of the shell's grid, not a panel over it", () => {
  it("makes main a grid whose rail track is attribute-driven", () => {
    const main = rule(STYLE, "main");
    expect(main).toContain("display: grid");
    // Declared unconditionally the track would still be reserved from Explore and from a map
    // with no well open, which is the whole reason the attribute exists.
    expect(main).not.toContain("grid-template-columns: minmax(0, 1fr) calc");
    expect(STYLE).toContain('main[data-rail="open"]');
    expect(STYLE).toContain('main[data-rail="collapsed"]');
  });

  it("takes #gw-map out of absolute positioning and leaves the chrome anchored to it", () => {
    const map = rule(STYLE, "#gw-map");
    // Out of flow it stays the size of the whole padding box, and the rail lands on top of a
    // full-width map however the grid is declared.
    expect(map).not.toContain("position: absolute");
    expect(map).toContain("position: relative");
    expect(map).not.toContain("inset: 0");
  });

  it("gives each panel column its width plus one hairline", () => {
    // 1600 - 540 - 480 - 2 = 578 and 1024 - 389 - 1 = 634 are the two numbers the rail is
    // judged on, and both come from counting one hairline per panel column.
    expect(STYLE).toContain("calc(var(--gw-card-w) + 1px)");
    expect(STYLE).toContain("calc(var(--gw-drawer-w) + 1px)");
    expect(rule(STYLE, "#gw-card,\n#gw-drawer")).toContain("border-left: 1px solid var(--hairline)");
  });

  it("keeps the card at the width the flyout had", () => {
    expect(STYLE).toContain("--gw-card-w: min(38vw, 540px)");
  });

  it("names only tokens something declares", () => {
    // An undeclared custom property makes the whole declaration invalid and the rule silently
    // does nothing: `var(--text)` is not a token anywhere in this app and the rail's hover
    // state was dead on arrival. Tokens a module sets from script count as declared, which is
    // how the chart's band geometry reaches the sheet.
    const declared = new Set([...STYLE.matchAll(/(--[a-z0-9-]+)\s*:/g)].map((match) => match[1]));
    for (const file of readdirSync("src", { recursive: true, encoding: "utf8" })) {
      if (!file.endsWith(".ts") && !file.endsWith(".css")) continue;
      const source = readFileSync(`src/${file}`, "utf8");
      for (const match of source.matchAll(/["'`](--[a-z0-9-]+)["'`]|(--[a-z0-9-]+)\s*:/g)) {
        declared.add(match[1] ?? match[2]);
      }
    }
    const used = new Set([...STYLE.matchAll(/var\((--[a-z0-9-]+)/g)].map((match) => match[1]));
    expect([...used].filter((token) => !declared.has(token))).toEqual([]);
  });

  it("columns the drawer only where three columns still leave the map 500 px", () => {
    const wide = media(STYLE, "min-width: 1600px");
    expect(wide).toContain("grid-column: 2");
    expect(wide).toContain("--gw-drawer-w");
    // Below it the drawer stacks in the rail, so the map does not move when a handle opens.
    expect(STYLE).toContain('main[data-rail="open"][data-drawer="open"]');
  });

  it("steps the teaching hint aside by the strip, not by the open rail, when collapsed", () => {
    expect(STYLE).toContain('body:has(#gw-main[data-rail="collapsed"]) .gw-hint');
    expect(rule(STYLE, 'body:has(#gw-main[data-rail="collapsed"]) .gw-hint')).toContain(
      "calc(var(--gw-rail-strip) + var(--gw-space-4))",
    );
  });
});

describe("the phone sheet has three stops and the keyboard can reach every one", () => {
  const phone = media(STYLE, "max-width: 900px");

  it("declares the three snap heights, the top one unchanged from the single stop", () => {
    expect(phone).toContain("--gw-sheet-h: 160px");
    expect(phone).toContain("--gw-sheet-h: 46dvh");
    expect(phone).toContain("--gw-sheet-h: 78dvh");
  });

  it("resets the rail's track so a hidden sheet reserves no column at 820", () => {
    expect(phone).toContain("main[data-rail],");
    expect(phone).toContain("grid-template-columns: minmax(0, 1fr)");
  });

  it("drops the collapse control through the parent, because a bare id loses to it", () => {
    // `#gw-rail-chrome button` is (1,0,1) and `#gw-rail-toggle` is (1,0,0), so the shorter
    // selector lost and the phone shipped a control with no posture behind it.
    expect(phone).toContain("#gw-rail-chrome #gw-rail-toggle");
  });

  it("gives the rail's controls, the grab bar and a section disclosure their own 44 px", () => {
    // style.css's existing 44 px rules scope to .gw-controls button, .gw-mode-switch and
    // .gw-mode-btn, which are the header cluster and the surface switch. None of them reaches
    // a control the card owns.
    expect(phone).toContain("#gw-rail-chrome button,");
    expect(phone).toContain(".gw-section-toggle,");
    expect(phone).toContain(".gw-card-chip");
    expect(rule(phone, "#gw-rail-grab::before")).toContain("width: 44px");
  });

  it("is a three-value slider in the markup, not a boolean disclosure", () => {
    // aria-expanded cannot express three states, and a drag-only sheet is not operable from a
    // keyboard at all.
    expect(INDEX).toContain('role="slider"');
    expect(INDEX).toContain('aria-label="Well card size"');
    expect(INDEX).toContain('aria-valuemin="1"');
    expect(INDEX).toContain('aria-valuemax="3"');
    expect(INDEX).toContain('aria-valuetext="full"');
  });

  it("names the collapse strip so a stylesheet cannot take its name away", () => {
    const toggle = /<button id="gw-rail-toggle"[^>]*>/.exec(INDEX)?.[0] ?? "";
    expect(toggle).toContain("aria-expanded");
    expect(toggle).toContain('aria-controls="gw-card"');
  });
});

describe("wireSheet", () => {
  let main: HTMLElement;
  let grab: HTMLElement;

  beforeEach(() => {
    document.body.replaceChildren();
    main = document.createElement("main");
    grab = document.createElement("div");
    grab.setAttribute("role", "slider");
    main.appendChild(grab);
    document.body.appendChild(main);
  });

  it("opens at the stop that shipped before it and says so in words", () => {
    wireSheet(main, grab);
    expect(main.getAttribute("data-sheet-snap")).toBe("full");
    expect(grab.getAttribute("aria-valuenow")).toBe("3");
    expect(grab.getAttribute("aria-valuetext")).toBe("full");
  });

  it("steps down and up with the arrow keys the slider role contracts for", () => {
    wireSheet(main, grab);
    grab.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
    expect(grab.getAttribute("aria-valuetext")).toBe("half");
    grab.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
    expect(grab.getAttribute("aria-valuetext")).toBe("peek");
    // Clamped, not wrapped: a slider at its minimum stays there.
    grab.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
    expect(grab.getAttribute("aria-valuetext")).toBe("peek");
    grab.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowUp", bubbles: true }));
    expect(grab.getAttribute("aria-valuetext")).toBe("half");
  });

  it("jumps to either end with Home and End", () => {
    wireSheet(main, grab);
    grab.dispatchEvent(new KeyboardEvent("keydown", { key: "Home", bubbles: true }));
    expect(main.getAttribute("data-sheet-snap")).toBe("peek");
    expect(grab.getAttribute("aria-valuenow")).toBe("1");
    grab.dispatchEvent(new KeyboardEvent("keydown", { key: "End", bubbles: true }));
    expect(main.getAttribute("data-sheet-snap")).toBe("full");
    expect(grab.getAttribute("aria-valuenow")).toBe("3");
  });

  it("resumes the stop the shell already carries rather than resetting it", () => {
    main.setAttribute("data-sheet-snap", "peek");
    wireSheet(main, grab);
    expect(grab.getAttribute("aria-valuetext")).toBe("peek");
  });
});

describe("the map resizes itself, and reserves nothing for a card that no longer overlaps", () => {
  it("calls no resize anywhere: maplibre installs its own ResizeObserver", () => {
    // trackResize defaults true and createMap passes none, so the Map constructor observes its
    // own container. A hand-rolled resize path would be a second one.
    expect(MAP).not.toMatch(/\.resize\(/);
  });

  it("holds back no right padding on a fly-to", () => {
    expect(MAP).toContain("const padding = { top: 0, bottom: 0, left: 0, right: 0 }");
    expect(MAP).not.toContain("Math.min(520");
  });
});
