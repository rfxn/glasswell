// @vitest-environment happy-dom
import { readFileSync } from "node:fs";

import { beforeEach, describe, expect, it } from "vitest";

import "./gw-count.ts";

const REASON =
  "An occurrence count is bookkeeping about how many fetches re-presented the row, not a" +
  " measured quantity about the well.";

function count(attributes: Record<string, string>): HTMLElement {
  const element = document.createElement("gw-count");
  for (const [name, value] of Object.entries(attributes)) element.setAttribute(name, value);
  document.body.append(element);
  return element;
}

function mark(element: HTMLElement): HTMLElement {
  return element.querySelector(".gw-count-mark") as HTMLElement;
}

function reasonPanel(): HTMLElement | null {
  return document.querySelector(".gw-count-reason");
}

beforeEach(() => {
  document.body.replaceChildren();
});

describe("<gw-count> is the exemption register reaching the reader (§6.3)", () => {
  it("renders the number and a mark whose popover is the exemption reason, verbatim", () => {
    const element = count({ value: "1284", reason: REASON });

    expect(element.querySelector(".gw-count-value")?.textContent).toBe("1,284");
    const marker = mark(element);
    // F5: `ⓔ` (U+24D4) is in none of the three self-hosted faces and `style.css` pins GW
    // Symbols to U+233E/U+2715, so the browser resolves it to the reader's system font or to
    // tofu. A ringed ASCII `e` is the same idea composed from a glyph every face ships.
    expect(marker.textContent).toBe("e");
    expect(marker.textContent?.codePointAt(0)).toBeLessThan(128);
    marker.click();
    expect(reasonPanel()?.textContent).toBe(REASON);
    expect(marker.title).toBe(REASON);
  });

  it("reads as a target rather than as a stray character, in both of its states", () => {
    const served = count({ value: "1284", reason: REASON });
    const unserved = count({ value: "12", "no-reason": "" });

    // F4's other half: the mark is the one interactive thing in the cell and was the quietest.
    for (const element of [served, unserved]) {
      const marker = element.querySelector(".gw-count-mark") as HTMLElement;
      expect(marker.tagName).toBe("BUTTON");
      expect(marker.getAttribute("aria-expanded")).toBe("false");
    }
    (served.querySelector(".gw-count-mark") as HTMLElement).click();
    expect(served.querySelector(".gw-count-mark")?.getAttribute("aria-expanded")).toBe("true");
  });

  it("keeps the reason hidden until it is asked for, and closes it on a second ask", () => {
    const element = count({ value: "3", reason: REASON });

    expect(reasonPanel()?.hidden ?? true).toBe(true);
    mark(element).click();
    expect(reasonPanel()?.hidden).toBe(false);
    mark(element).click();
    expect(reasonPanel()?.hidden).toBe(true);
    expect(mark(element).getAttribute("aria-expanded")).toBe("false");
  });

  it("throws in test mode when a count carries no reason at all", () => {
    // The same discipline `gw-figure.ts:6,39` applies to a missing handle, and for the same
    // reason: a number whose exemption nobody wrote down is a defect, not a rendering choice.
    expect(() => count({ value: "12" })).toThrow(/reason/);
  });

  it("renders the counted-unbound treatment where the document serves no reason yet", () => {
    const element = count({ value: "12", "no-reason": "" });

    expect(element.querySelector(".gw-count-value")?.textContent).toBe("12");
    const marker = element.querySelector(".gw-count-mark") as HTMLElement;
    expect(marker.textContent).toBe("?");
    expect(marker.title).toMatch(/does not state/i);
    // Never identical to a reasoned count: the two facts are different and must look different.
    expect(marker.className).not.toBe(
      (count({ value: "12", reason: REASON }).querySelector(".gw-count-mark") as HTMLElement)
        .className,
    );
  });

  it("names its own state so a pane or a detail row can say which of the three it is (F4)", () => {
    // The vocabulary C8 and C9 inherit: an exemption mark is `exempt` or `exempt-unstated`, and
    // an unbound *header* is neither — three states, three names, one place they are written.
    expect(
      count({ value: "1", reason: REASON }).querySelector(".gw-count-mark")?.getAttribute("data-mark"),
    ).toBe("exempt");
    expect(
      count({ value: "1", "no-reason": "" }).querySelector(".gw-count-mark")?.getAttribute("data-mark"),
    ).toBe("exempt-unstated");
  });

  it("keeps the glossary highlighter out of the number itself", () => {
    const element = count({ value: "1284", reason: REASON });

    expect(element.querySelector(".gw-count-value")?.hasAttribute("data-no-glossary")).toBe(true);
  });

  it("re-renders when its value changes rather than keeping the number it first had", () => {
    const element = count({ value: "1", reason: REASON });
    element.setAttribute("value", "2");

    expect(element.querySelector(".gw-count-value")?.textContent).toBe("2");
  });
});

/**
 * N1: the reason was an in-flow block inside a right-aligned cell, so opening one widened its
 * track — the clicked row's count moved 240 px, the last column went 148.6 px past the panel,
 * and the off-edge sentence stayed silent because `offScreenColumns` runs once at mount. Out of
 * flow and off the row entirely, opening a reason cannot change the grid's box at all, which is
 * what makes the mount-time measurement still true rather than merely usually true.
 */
describe("<gw-count>'s reason is a popover, on gw-term's pattern (N1)", () => {
  it("renders the reason on document.body, never inside the row that owns the number", () => {
    const element = count({ value: "295", reason: REASON });
    const before = { nodes: element.querySelectorAll("*").length, text: element.textContent };

    mark(element).click();
    const popover = reasonPanel() as HTMLElement;

    expect(popover.parentElement).toBe(document.body);
    expect(element.contains(popover)).toBe(false);
    // Nodes and text are what decide the cell's width; the open state adds neither. ARIA
    // attributes on the mark do change, and they cost no width.
    expect(element.querySelectorAll("*").length).toBe(before.nodes);
    expect(element.textContent).toBe(before.text);
  });

  it("borrows .gw-popover, whose rule is what takes it out of flow", () => {
    const element = count({ value: "295", reason: REASON });
    mark(element).click();
    const popover = reasonPanel() as HTMLElement;

    expect(popover.classList.contains("gw-popover")).toBe(true);
    // The out-of-flow claim rests on a rule in another track's stylesheet, so it is read rather
    // than assumed — a declaration that outlives its relation is this codebase's own N-11.
    const rule = /\.gw-popover\s*\{([^}]*)\}/.exec(readFileSync("src/style.css", "utf8"));
    expect(rule?.[1]).toMatch(/position:\s*absolute/);
  });

  it("keeps one reason open at a time, so a second mark takes the panel from the first", () => {
    const first = count({ value: "295", reason: REASON });
    const second = count({ value: "12", "no-reason": "" });

    mark(first).click();
    mark(second).click();

    expect(mark(first).getAttribute("aria-expanded")).toBe("false");
    expect(mark(second).getAttribute("aria-expanded")).toBe("true");
    expect(document.querySelectorAll(".gw-count-reason")).toHaveLength(1);
    expect(reasonPanel()?.textContent).toMatch(/does not state/i);
  });

  it("points the reader at the reason it opened, and stops pointing when it closes", () => {
    const element = count({ value: "295", reason: REASON });

    mark(element).click();
    const popover = reasonPanel() as HTMLElement;
    expect(mark(element).getAttribute("aria-describedby")).toBe(popover.id);
    expect(popover.id).not.toBe("");

    mark(element).click();
    expect(mark(element).hasAttribute("aria-describedby")).toBe(false);
  });

  it("closes on Escape and gives the mark its focus back", () => {
    const element = count({ value: "295", reason: REASON });
    mark(element).click();

    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));

    expect(reasonPanel()?.hidden).toBe(true);
    expect(document.activeElement).toBe(mark(element));
  });

  it("closes when the count re-renders, rather than describing a mark that no longer exists", () => {
    const element = count({ value: "295", reason: REASON });
    mark(element).click();

    element.setAttribute("value", "296");

    expect(reasonPanel()?.hidden).toBe(true);
    expect(mark(element).getAttribute("aria-expanded")).toBe("false");
  });
});
