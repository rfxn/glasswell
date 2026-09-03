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
    // One posture per width the column exists at; what must not differ is that each one is a
    // fixed width. A media query that sets .gw-meta { max-width } reopens the blocker.
    const widths = [...CSS.matchAll(/--gw-meta-w:\s*(\d+)px/g)].map((match) => match[1]);

    expect(widths.length).toBeGreaterThanOrEqual(3);
    expect(new Set(widths).size).toBeGreaterThanOrEqual(3);
    expect(CSS).not.toMatch(/\.gw-meta\s*\{[^}]*max-width/);
  });

  it("keeps the column narrow enough that the tools stay where the owner asked for them", () => {
    // The column holds `as_of YYYY-MM-DD` over `build <hash>` — two strings whose width is
    // known. 340 px of it was a status line, and every pixel of that pushed search and help
    // left of where the hand goes (owner observation 3). This is that width, given back.
    const widths = [...CSS.matchAll(/--gw-meta-w:\s*(\d+)px/g)].map((match) => Number(match[1]));

    expect(Math.max(...widths)).toBeLessThanOrEqual(180);
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
  it("budgets 20 px for the vintage, 16 for the build stamp and 4 between them", () => {
    // The stamp took the row the status vacated rather than adding a third one: 20 + 4 + 16
    // is the 40 px band the controls beside it stand in, and a third line would break it.
    expect(block(".gw-asof")).toMatch(/line-height:\s*20px/);
    expect(block(".gw-build")).toMatch(/line-height:\s*16px/);
    expect(block(".gw-meta")).toMatch(/gap:\s*var\(--gw-space-1\)/);
  });

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
  it("keeps the key chip out of the act group, whatever else moves", () => {
    // The chip is a status readout that happens to be pressable. Left in the act group it
    // widened that group by ~100 px whenever a key went bad, which shoved search leftwards.
    // It now stands with the status; what it may never do is stand with the buttons.
    const signal = /<div id="gw-signal"[^>]*>([\s\S]*?)<\/div>\s*<div class="gw-controls">/.exec(
      RAIL,
    )?.[1];

    expect(signal).toMatch(/id="gw-key-btn"/);
    expect(/<div class="gw-tools gw-tools-act">([\s\S]*?)<\/div>\s*<div/.exec(RAIL)?.[1]).not.toMatch(
      /id="gw-key-btn"/,
    );
  });

  it("keeps the chip and the status on one row, in the rail's slack rather than the cluster", () => {
    // The signal group sits before `.gw-controls`, which is `margin-left: auto` — so however
    // wide a degraded warning gets, the right-packed groups do not translate (BLOCKER-1).
    expect(block(".gw-signal")).toMatch(/display:\s*flex/);
    expect(block(".gw-signal")).toMatch(/min-width:\s*0/);
    expect(block(".gw-controls")).toMatch(/margin-left:\s*auto/);
    expect(RAIL.indexOf('id="gw-signal"')).toBeLessThan(RAIL.indexOf('class="gw-controls"'));
  });
});

/**
 * The 390 px rail wanted 472 px of content and the browser paid for it by drawing help over
 * search and clipping the date — measured, not inferred (work-output/header-polish-status.md).
 * The phone posture drops the read column instead, so what is left fits.
 */
describe("the phone posture drops a column rather than overlapping two controls", () => {
  const PHONE = /@media \(max-width: 520px\) \{([\s\S]*?)\n\}/.exec(CSS)?.[1] ?? "";

  it("takes the read column out of the rail below 520px", () => {
    expect(PHONE).toMatch(/\.gw-meta\s*\{\s*display:\s*none/);
  });

  it("keeps both of its facts reachable, in the panel that exists at every width", () => {
    // Dropping the corner is only honest if the vintage and the build are still one tap away.
    const panel = /<div id="gw-help-panel"[\s\S]*?<\/div>\s*<\/div>/.exec(INDEX)?.[0] ?? "";

    expect(panel).toContain('id="gw-help-asof"');
    expect(panel).toContain('id="gw-help-build"');
  });

  it("spends the wordmark or the status, never a control, when a warning needs the room", () => {
    // Everything a state rule may touch lives in the rail's left half. A rule that moved a
    // right-packed group under the reader's thumb because a source degraded is BLOCKER-1 in
    // its phone clothes — measured at 0 px of movement, idle to degraded, at 1600 and at 390.
    const borrowed = [...PHONE.matchAll(/#gw-header:has\([^)]*\)\s*([^{,]*)[,{]/g)].map((match) =>
      (match[1] ?? "").trim(),
    );

    expect(borrowed.length).toBeGreaterThan(0);
    for (const target of borrowed)
      expect(target, target).toMatch(/\.gw-wordmark|\.gw-signal|#gw-status/);
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

/**
 * gate-v078 N9. The DIR-11 ladder is 1600 full · 1366 full · 1024 hidden · 820 · 390 hidden,
 * and at 820 signed out the strapline read `— NO NAKED NUM` with no ellipsis to say so. v0.76
 * N1 keyed the compact-rail rules on the session on the reading that signed out already held;
 * it did not, and every surface this project shoots is signed out.
 */
describe("the compact rail does not cut the positioning line at either posture", () => {
  const band =
    /@media \(min-width: 621px\) and \(max-width: 900px\) \{([\s\S]*?)\n\}/.exec(CSS)?.[1] ?? "";
  const rules = [...band.matchAll(/([^{}]+)\{([^}]*)\}/g)].map((rule) => ({
    selector: (rule[1] ?? "").replace(/\/\*[\s\S]*?\*\//g, "").trim(),
    body: rule[2] ?? "",
  }));
  const ruleFor = (selector: string) => rules.filter((rule) => rule.selector === selector);

  it("stops the brand paying for the rail whether or not a session is open", () => {
    expect(band, "the 621-900 band is gone").not.toBe("");
    expect(ruleFor(".gw-brand").map((rule) => rule.body.trim())).toEqual(["flex: none;"]);
    expect(ruleFor(".gw-search-input")[0]?.body).toMatch(/width:\s*min\(/);
  });

  it("lets the strap take a second line rather than be cut where it is still shown", () => {
    const strap = ruleFor(".gw-strap")[0]?.body ?? "";

    expect(strap).toMatch(/white-space:\s*normal/);
    expect(strap).toMatch(/overflow:\s*visible/);
  });

  it("hides it only where a Sign-out control is competing for the same row", () => {
    const hidden = rules.filter((rule) => /display:\s*none/.test(rule.body));

    expect(hidden).toHaveLength(1);
    expect(hidden[0]?.selector).toContain("gw-logout-btn");
    expect(hidden[0]?.selector).toContain(".gw-strap");
  });
});
