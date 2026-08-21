import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

// The chrome/*.test.ts precedent: read the shipped stylesheets, not a fixture of them.
const SHEETS = ["src/explore/grid/grid.css", "src/explore/facets/facets.css"].map((path) => ({
  path,
  css: readFileSync(path, "utf8"),
}));

/**
 * Every class the explorer hides with the `hidden` property. A `display` declaration outranks
 * the UA's `[hidden] { display: none }`, so a class in this list that also carries an
 * unconditional `display` renders a closed popover into the layout — which is exactly what
 * made an exempt column's rows 86 px tall before the C7 visual pass caught it.
 */
const HIDDEN_CLASSES = ["gw-count-reason", "gw-cursor-decoded", "gw-grid-more"];

function sources(directory: string): string[] {
  const found: string[] = [];
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) found.push(...sources(path));
    else if (entry.name.endsWith(".ts") && !entry.name.endsWith(".test.ts")) found.push(path);
  }
  return found;
}

function rules(css: string): { selector: string; body: string }[] {
  const stripped = css.replace(/\/\*[\s\S]*?\*\//g, "");
  return [...stripped.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((match) => ({
    selector: (match[1] ?? "").trim().replace(/\s+/g, " "),
    body: match[2] ?? "",
  }));
}

describe("C7's stylesheets obey the rules C6 wrote down for the explorer's own (G-3)", () => {
  it("declares no z-index at all — the grid and the facet bar do not overlap anything", () => {
    for (const sheet of SHEETS) {
      expect(sheet.css.replace(/\/\*[\s\S]*?\*\//g, ""), sheet.path).not.toMatch(/z-index/);
    }
  });

  it("never lets a display rule outrank the hidden attribute on something it hides", () => {
    for (const name of HIDDEN_CLASSES) {
      const owning = SHEETS.flatMap((sheet) => rules(sheet.css)).filter((rule) =>
        rule.selector.split(",").some((part) => part.trim().startsWith(`.${name}`)),
      );
      expect(owning.length, name).toBeGreaterThan(0);
      for (const rule of owning) {
        if (!/display\s*:/.test(rule.body)) continue;
        expect(rule.selector, `${name}: ${rule.selector}`).toContain(":not([hidden])");
      }
    }
  });

  it("keeps that list honest by counting what the source actually hides", () => {
    const hidden = new Set(
      sources("src/explore").flatMap((path) =>
        [...readFileSync(path, "utf8").matchAll(/(\w+)\.hidden = /g)].map((match) => match[1]),
      ),
    );
    // Three elements today. A fourth has to join HIDDEN_CLASSES or this reddens, which is the
    // only thing that stops the list above rotting into a comment.
    expect(hidden.size).toBe(HIDDEN_CLASSES.length);
  });
});
