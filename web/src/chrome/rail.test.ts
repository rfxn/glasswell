import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// vitest roots at web/, so these are the shipped files, not a fixture of them.
const CSS = readFileSync("src/style.css", "utf8");
const INDEX = readFileSync("index.html", "utf8");
const RAIL = /<header id="gw-header"[\s\S]*?<\/header>/.exec(INDEX)?.[0] ?? "";

function block(selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(?:^|\\})\\s*${escaped}\\s*\\{([^}]*)\\}`, "m").exec(CSS)?.[1] ?? "";
}

/**
 * gate-v BLOCKER-1: the find and act groups translated 69-117 px when the read slot's
 * content changed, because the slot was `max-width`-capped inside a right-packed row —
 * a cap bounds growth, it does not fix position. These are the invariants that keep the
 * interactive groups still while state churns around them.
 */
describe("the rail's read slot is a fixed column", () => {
  it("sizes .gw-meta from a token rather than its content", () => {
    const meta = block(".gw-meta");

    expect(meta).toMatch(/flex:\s*0\s+0\s+var\(--gw-meta-w\)/);
    expect(meta).toMatch(/width:\s*var\(--gw-meta-w\)/);
  });

  it("never caps the slot with max-width, which would leave it shrink-to-fit", () => {
    expect(block(".gw-meta")).not.toMatch(/max-width/);
  });

  it("re-sizes the slot per breakpoint by re-declaring the token, not the rule", () => {
    // Four postures, so the widths differ; what must not differ is that each one is a
    // fixed width. A media query that sets .gw-meta { max-width } reopens the blocker.
    const widths = [...CSS.matchAll(/--gw-meta-w:\s*(\d+)px/g)].map((match) => match[1]);

    expect(widths.length).toBeGreaterThanOrEqual(4);
    expect(new Set(widths).size).toBeGreaterThanOrEqual(4);
    expect(CSS).not.toMatch(/\.gw-meta\s*\{[^}]*max-width/);
  });

  it("lets no state selector resize or drop the slot, or the groups move again", () => {
    // `:has()` on the header is how a passive state (a degraded source, a rejected key)
    // reaches the rail. It may restyle inside the slot; it may not change the slot's box.
    const stateRules = [...CSS.matchAll(/#gw-header:has\([^)]*\)\s*([^{]*)\{([^}]*)\}/g)];
    const touchingMeta = stateRules.filter((rule) => /\.gw-meta\b/.test(rule[1] ?? ""));

    for (const rule of touchingMeta) {
      expect(rule[1], rule[1]).toMatch(/search-input/);
    }
  });
});

/**
 * gate-v M-1: the slot clipped the bottom border off the key chip and the degraded pill at
 * 1600 and 1024. The CSS comment on `.gw-meta` states the band as 20 + 4 + 16 = 40 px; the
 * layout came to 21 + 4 + 18. Both deltas are here, and neither is the `line-height` the
 * finding named — that was already 16 px. Measured: work-output/train-railprobe.mjs.
 */
describe("the read slot's two rows add up to the band the slot declares", () => {
  it("does not baseline-align the as_of row, which grew it to 21px", () => {
    // The row's strut is 12px mono; the eyebrow inside it is 10.56px display. Baseline
    // alignment offsets the smaller box to make the baselines meet, and the offset is height
    // the row does not have. Centring two 20px line boxes cannot exceed 20px.
    expect(block(".gw-asof")).not.toMatch(/align-items:\s*baseline/);
  });

  it("draws the degraded pill's rule inside its box rather than around it", () => {
    // A border on an auto-height inline-block adds to the border box — 16px of line box plus
    // two 1px rules is the 18px signal row. An inset ring is the same pixel, off the layout.
    const pill = block(".gw-status.gw-degraded");

    expect(pill).not.toMatch(/border:\s*\d/);
    expect(pill).toMatch(/box-shadow:\s*inset/);
  });
});

describe("the act group holds only the controls whose width never changes", () => {
  it("puts the key chip in the read group, not beside the theme and help buttons", () => {
    // The chip is a status readout that happens to be pressable. Left in the act group it
    // widened that group by ~100 px whenever a key went bad, which shoved search leftwards.
    const meta = /<div class="gw-tools gw-meta">([\s\S]*?)<\/div>\s*<\/div>/.exec(RAIL)?.[1] ?? "";

    expect(meta).toMatch(/id="gw-key-btn"/);
    expect(/<div class="gw-tools gw-tools-act">([\s\S]*?)<\/div>\s*<div/.exec(RAIL)?.[1]).not.toMatch(
      /id="gw-key-btn"/,
    );
  });

  it("keeps the chip and the status on one row inside the slot", () => {
    expect(block(".gw-meta-signal")).toMatch(/justify-content:\s*flex-end/);
  });
});

/** gate-v MAJOR-1: 3.25:1 at the 18.4 px phone size, below the large-text threshold. */
describe("the wordmark accent is text, so it clears AA as text", () => {
  it("takes the text-safe cyan rather than the swatch cyan", () => {
    expect(block(".gw-wordmark-well")).toMatch(/color:\s*var\(--cyan-text\)/);
  });

  it("darkens that cousin in the light theme, where the swatch value fails", () => {
    const light = /:root\[data-theme="light"\]\s*\{([^}]*)\}/.exec(CSS)?.[1] ?? "";

    expect(light).toMatch(/--cyan-text:\s*#1f7c92/i);
    expect(light).not.toMatch(/--cyan-text:\s*var\(--cyan\)/);
  });
});
