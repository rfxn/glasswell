import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/**
 * `[hidden]` is a single attribute selector. Any class rule that sets `display` outranks it,
 * and the element renders anyway with the attribute still on it — nothing in the DOM looks
 * wrong, so the bug is invisible to a test that asserts `hidden === true`.
 *
 * That is how the sign-out control shipped visible to signed-out readers on every surface,
 * and overflowed the 320 px rail by 34 px where there is no room for a control nobody can use.
 */
const INDEX = readFileSync("index.html", "utf8");
const CSS = readFileSync("src/style.css", "utf8");

function classesOnHiddenElements(): string[] {
  const found = new Set<string>();
  for (const tag of INDEX.match(/<[a-z][^>]*>/gi) ?? []) {
    if (!/\shidden(\s|>|=)/.test(tag)) continue;
    const cls = /\sclass="([^"]+)"/.exec(tag)?.[1];
    if (!cls) continue;
    for (const name of cls.split(/\s+/).filter(Boolean)) found.add(name);
  }
  return [...found].sort();
}

describe("a control hidden by attribute is actually not rendered", () => {
  it("gives every class on a hidden element a [hidden] display rule", () => {
    const missing = classesOnHiddenElements().filter(
      (name) => !new RegExp(`\\.${name}\\[hidden\\]`).test(CSS),
    );

    expect(missing).toEqual([]);
  });

  it("finds classes to check, so the assertion above is not vacuous", () => {
    expect(classesOnHiddenElements().length).toBeGreaterThan(0);
  });

  it("covers the sign-out control specifically", () => {
    expect(classesOnHiddenElements()).toContain("gw-icon-btn");
    expect(CSS).toMatch(/\.gw-icon-btn\[hidden\]\s*\{\s*display:\s*none/);
  });
});
