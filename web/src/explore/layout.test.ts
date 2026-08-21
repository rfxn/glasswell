import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

// The chrome/*.test.ts precedent: read the shipped stylesheets, not a fixture of them.
const LAYOUT = readFileSync("src/explore/layout.css", "utf8");
const GLOBAL = readFileSync("src/style.css", "utf8");

interface Rule {
  selector: string;
  body: string;
}

function rules(css: string): Rule[] {
  const stripped = css.replace(/\/\*[\s\S]*?\*\//g, "");
  return [...stripped.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((match) => ({
    selector: (match[1] ?? "").trim().replace(/\s+/g, " "),
    body: match[2] ?? "",
  }));
}

function rungs(): Record<string, number> {
  const found: Record<string, number> = {};
  for (const match of GLOBAL.matchAll(/(--gw-z-[a-z-]+)\s*:\s*(\d+)\s*;/g)) {
    found[match[1] as string] = Number(match[2]);
  }
  return found;
}

const LAYOUT_RULES = rules(LAYOUT);
const SLOTS = [...LAYOUT.matchAll(/(--gw-z-explore-[a-z-]+)\s*:\s*([^;]+);/g)].map((match) => ({
  slot: match[1] as string,
  value: (match[2] ?? "").trim(),
}));

describe("the explorer aliases the global ladder and declares none of its own (G-3)", () => {
  it("declares every slot as a var() naming a rung style.css actually has", () => {
    const ladder = rungs();
    expect(Object.keys(ladder).length).toBeGreaterThan(0);
    expect(SLOTS.length).toBeGreaterThan(0);

    for (const { slot, value } of SLOTS) {
      const named = /^var\((--gw-z-[a-z-]+)\)$/.exec(value);
      expect(named, `${slot}: ${value}`).not.toBeNull();
      expect(ladder, slot).toHaveProperty(named?.[1] as string);
    }
  });

  it("resolves the two slots that exist onto panel and rail-pop, in the ladder's own order", () => {
    const ladder = rungs();
    const resolved = Object.fromEntries(
      SLOTS.map(({ slot, value }) => [
        slot,
        ladder[/^var\((--gw-z-[a-z-]+)\)$/.exec(value)?.[1] as string] as number,
      ]),
    );

    expect(resolved["--gw-z-explore-pane"]).toBe(ladder["--gw-z-panel"]);
    expect(resolved["--gw-z-explore-rail-pop"]).toBe(ladder["--gw-z-rail-pop"]);
    // Renumbering the global ladder underneath the explorer reddens this, which is the whole
    // reason the slots alias rungs instead of copying their integers.
    const order = [
      resolved["--gw-z-explore-pane"] as number,
      ladder["--gw-z-drawer"] as number,
      resolved["--gw-z-explore-rail-pop"] as number,
      ladder["--gw-z-popover"] as number,
      ladder["--gw-z-toast"] as number,
    ];
    expect(order).toEqual([...order].sort((a, b) => a - b));
    expect(new Set(order).size).toBe(order.length);
  });

  it("carries exactly one numeric z-index, and it is the sticky grid header's", () => {
    const numeric = LAYOUT_RULES.filter((rule) => /z-index\s*:\s*\d+\s*;/.test(rule.body));

    expect(numeric).toHaveLength(1);
    expect(/z-index\s*:\s*(\d+)/.exec(numeric[0]?.body ?? "")?.[1]).toBe("1");
    expect(numeric[0]?.body).toMatch(/position\s*:\s*sticky/);
  });

  it("scopes that z-index to a declared local stacking context, rather than assuming one", () => {
    const numeric = LAYOUT_RULES.find((rule) => /z-index\s*:\s*\d+\s*;/.test(rule.body)) as Rule;
    const isolated = LAYOUT_RULES.filter((rule) => /isolation\s*:\s*isolate/.test(rule.body));

    expect(isolated.length).toBeGreaterThan(0);
    // A z-index:1 inside an isolated ancestor cannot escape it, so it is not a rung on the
    // global ladder and cannot collide with the drawer. Stated, not hoped for.
    expect(
      isolated.some((container) => numeric.selector.startsWith(`${container.selector} `)),
      `${numeric.selector} is not inside any isolation: isolate container`,
    ).toBe(true);
  });

  it("gives the rail, the facet bar and the grid no z-index at all — they do not overlap", () => {
    for (const selector of [".gw-explore-rail", ".gw-explore-facets", ".gw-explore-grid"]) {
      const own = LAYOUT_RULES.filter((rule) =>
        rule.selector.split(",").some((part) => part.trim() === selector),
      );
      expect(own.length, selector).toBeGreaterThan(0);
      for (const rule of own) expect(rule.body, selector).not.toMatch(/z-index/);
    }
  });

  it("leaves the global ladder untouched — seven rungs, still declared once", () => {
    expect(Object.keys(rungs())).toHaveLength(7);
    expect(LAYOUT).not.toMatch(/--gw-z-(map-chrome|panel|drawer|rail-pop|modal|popover|toast)\s*:/);
  });
});

/**
 * C9 regression. Where the pane stacks it shares a column with the grid, and a row sized `auto`
 * takes the pane's whole content — which, once the pane had content, left the grid a zero-height
 * row and two thirds of the window empty. The row has to be capped, not the item: a percentage
 * `max-height` on a grid item cannot resolve against a row that item is sizing.
 */
describe("the stacked pane is capped by its row, not by its content", () => {
  const stacked = [...LAYOUT.matchAll(/@media \(max-width: (1365|1023)px\)([\s\S]*?)\n}/g)];

  it("caps the pane's row in both stacked arms", () => {
    expect(stacked).toHaveLength(2);
    for (const [, width, block] of stacked) {
      const rows = /grid-template-rows:\s*([^;]+);/.exec(block as string)?.[1];
      expect(rows, `${width}px`).toContain("fit-content(40%)");
      expect(rows, `${width}px`).not.toMatch(/\bauto\s*;?\s*$/);
    }
  });

  it("keeps the grid's own row able to shrink to nothing rather than overflow the window", () => {
    for (const [, width, block] of stacked) {
      expect(/grid-template-rows:\s*([^;]+);/.exec(block as string)?.[1], `${width}px`).toContain(
        "minmax(0, 1fr)",
      );
    }
  });
});
