import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

// The chrome/*.test.ts precedent: read the shipped stylesheets, not a fixture of them.
const SHEETS = [
  "src/explore/grid/grid.css",
  "src/explore/facets/facets.css",
  "src/explore/detail/detail.css",
  "src/explore/api/pane.css",
].map((path) => ({
  path,
  css: readFileSync(path, "utf8"),
}));

/**
 * Every class the explorer hides with the `hidden` property. A `display` declaration outranks
 * the UA's `[hidden] { display: none }`, so a class in this list that also carries an
 * unconditional `display` renders a closed popover into the layout — which is exactly what
 * made an exempt column's rows 86 px tall before the C7 visual pass caught it.
 */
const HIDDEN_CLASSES = [
  "gw-count-reason",
  "gw-cursor-decoded",
  "gw-grid-more",
  "gw-trail-curl",
  "gw-api-param-body",
];

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

describe("the explorer's stylesheets obey the rules C6 wrote down for its own (G-3)", () => {
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

  /**
   * §2.5's two narrow postures are CSS, not a second renderer, so this is where they are pinned.
   * A resize listener re-rendering the grid would be the alternative, and it would tear the open
   * row's panel out from under the reader every time the keyboard opened.
   */
  it("turns the grid into a card list at 820, with the column name beside each value", () => {
    const grid = SHEETS.find((sheet) => sheet.path.endsWith("grid/grid.css"))?.css ?? "";
    const posture = /@media \(max-width: 820px\) \{([\s\S]*?)\n\}/.exec(grid)?.[1] ?? "";

    expect(posture, "820 arm is missing").not.toBe("");
    expect(posture).toMatch(/\.gw-grid-td-name \{\s*display: block/);
    expect(posture).toMatch(/\.gw-explore-grid-head \{\s*display: none/);
    expect(posture).toMatch(/\.gw-grid-table \{[\s\S]*?display: block/);
    expect(readFileSync("src/explore/grid/grid.ts", "utf8")).toContain(
      'cell.dataset["name"] = column.name',
    );
  });

  /**
   * gate-c10 R3. `content: attr(data-name)` painted the label and carried it nowhere else: a
   * pseudo-element cannot be selected, cannot be copied, and is not reliably exposed to
   * assistive technology as the value's label. At 820 the header row is gone, so that was the
   * only label the cell had.
   */
  it("carries that name in a real element, not in generated content", () => {
    const grid = SHEETS.find((sheet) => sheet.path.endsWith("grid/grid.css"))?.css ?? "";

    expect(grid).not.toContain("attr(data-name)");
    expect(grid).toMatch(/\.gw-grid-td-name \{\s*display: none;\s*\}/);
    expect(readFileSync("src/explore/grid/grid.ts", "utf8")).toContain(
      'name.className = "gw-grid-td-name"',
    );
  });

  it("refuses the grid at 390 and says so, rather than rendering twelve columns into 390px", () => {
    const grid = SHEETS.find((sheet) => sheet.path.endsWith("grid/grid.css"))?.css ?? "";
    const refusal = /@media \(max-width: 520px\) \{([\s\S]*?)\n\}/.exec(grid)?.[1] ?? "";

    expect(refusal, "390 arm is missing").not.toBe("");
    expect(refusal).toMatch(/\.gw-grid-narrow \{\s*display: block/);
    expect(refusal).toMatch(/\.gw-grid-table,[\s\S]*?display: none/);
    // Absent at every other width, not merely invisible: nothing reads out a refusal that does
    // not apply. The unconditional rule below the media block is what makes that true.
    expect(grid).toMatch(/\.gw-grid-narrow \{\s*display: none;\s*\}/);
  });

  it("keeps that list honest by counting what the source actually hides", () => {
    const hidden = new Set(
      sources("src/explore").flatMap((path) =>
        [...readFileSync(path, "utf8").matchAll(/(\w+)\.hidden = /g)].map((match) => match[1]),
      ),
    );
    // Five elements today — C9's parameter body was the fifth, and this is what caught it. A
    // sixth has to join HIDDEN_CLASSES or this reddens, which is the only thing that stops the
    // list above rotting into a comment.
    expect(hidden.size).toBe(HIDDEN_CLASSES.length);
  });
});
