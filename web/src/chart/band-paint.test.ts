import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// vitest roots at web/, so this is the shipped stylesheet, not a fixture of it. What is
// asserted here is what a screenshot showed and no DOM test could: a mark whose fill is the
// surface token is drawn, is measured, and is invisible in both themes.
const CSS = readFileSync("src/style.css", "utf8");

// Comments carry commas, and a comma is what splits a selector list.
const RULES = [...CSS.replace(/\/\*[\s\S]*?\*\//g, "").matchAll(/([^{}]+)\{([^}]*)\}/g)].map((match) => ({
  selectors: (match[1] ?? "").split(",").map((selector) => selector.trim()),
  body: match[2] ?? "",
}));

function paintOf(selector: string): string {
  return RULES.filter((rule) => rule.selectors.includes(selector))
    .map((rule) => rule.body)
    .join("");
}

describe("what the allocation band is painted with", () => {
  const CLASSES = [
    ".gw-alloc-observed-gas-well",
    ".gw-alloc-observed-single-well",
    ".gw-alloc-equal-share",
    ".gw-alloc-after-status-change",
    ".gw-alloc-excluded-after-plug",
    ".gw-alloc-unallocated",
  ];

  it("paints no mark in the surface token, which inverts with the theme", () => {
    // --ink is the page's surface, not a near-black constant: in the dark theme it is darker
    // than the strip and in the light theme it is lighter, so a mark drawn in it measures
    // 1.09:1 and 1.12:1 against a 3:1 floor. The e2e audit measures it; this catches it here.
    for (const selector of CLASSES) {
      expect(paintOf(selector), selector).not.toMatch(/var\(--ink\)/);
    }
  });

  it("gives every class a fill of its own, so no two are one class to a reader", () => {
    const paints = CLASSES.map((selector) => paintOf(selector));

    expect(paints.every((paint) => /background/.test(paint))).toBe(true);
    expect(new Set(paints).size).toBe(CLASSES.length);
  });
});

describe("what the cumulative chips are painted with", () => {
  it("keeps the share chip in one box, whatever its content does", () => {
    // A border is painted once per line box. `display: inline` and a chip that wraps
    // mid-content paints two of them, one containing `100%` and nothing else -- a bordered
    // naked number on the surface built to prevent them (M4).
    expect(paintOf(".gw-alloc-share")).toMatch(/display:\s*inline-block/);
  });
});

describe("what the state band is painted with", () => {
  it("draws the lease's filing as its own mark, not as this well's report", () => {
    // Two rows in one key with one swatch and two subjects is the same defect as two classes
    // with one encoding: the reader has the words and the picture disagreeing.
    const lease = paintOf(".gw-state-lease-reported");

    expect(lease).toMatch(/background/);
    expect(lease).not.toBe(paintOf(".gw-state-reported"));
  });
});
