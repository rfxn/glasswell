// @vitest-environment happy-dom
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

beforeEach(() => {
  document.body.replaceChildren();
});

describe("<gw-count> is the exemption register reaching the reader (§6.3)", () => {
  it("renders the number and a mark whose popover is the exemption reason, verbatim", () => {
    const element = count({ value: "1284", reason: REASON });

    expect(element.querySelector(".gw-count-value")?.textContent).toBe("1,284");
    const marker = element.querySelector(".gw-count-mark") as HTMLElement;
    // F5: `ⓔ` (U+24D4) is in none of the three self-hosted faces and `style.css` pins GW
    // Symbols to U+233E/U+2715, so the browser resolves it to the reader's system font or to
    // tofu. A ringed ASCII `e` is the same idea composed from a glyph every face ships.
    expect(marker.textContent).toBe("e");
    expect(marker.textContent?.codePointAt(0)).toBeLessThan(128);
    expect(element.querySelector(".gw-count-reason")?.textContent).toBe(REASON);
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

  it("keeps the reason hidden until it is asked for, and shows it on the ⓔ", () => {
    const element = count({ value: "3", reason: REASON });
    const popover = element.querySelector(".gw-count-reason") as HTMLElement;

    expect(popover.hidden).toBe(true);
    (element.querySelector(".gw-count-mark") as HTMLElement).click();
    expect(popover.hidden).toBe(false);
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
