import { describe, expect, it } from "vitest";

import { contrastRatio, NON_TEXT_FLOOR } from "./contrast.ts";
import { SEEDED_STATUS_CLASSES } from "./status-classes.generated.ts";

/**
 * Every served swatch, against every substrate a reader can put it on.
 *
 * A swatch is a non-text mark, so 1.4.11's 3:1 is its floor. The domain rule publishes that bar
 * and the four backgrounds beside the classes, so this is the rule read back rather than a
 * number someone chose here: `cr_status_class_domain_1.spec.min_contrast_ratio` and
 * `.contrast_measured_against`.
 *
 * It went red on the two the visual gate measured: the absence class at 2.19:1 against the dark
 * panel and `expired` at 2.94:1, on the substrate the app opens on and on the one class this
 * train turns from a negation nobody could tick into a row drawn over five jurisdictions.
 */
const SUBSTRATES = {
  // `--panel` and `--ink` in style.css, dark and light, and the two map substrates
  // variant-style.ts declares for the same two themes.
  "dark panel": "#121A21",
  "dark map": "#0E151B",
  "light panel": "#FFFFFF",
  "light map": "#F2F5F8",
} as const;

/**
 * The palette was designed for the dark theme and four classes do not clear the bar on the
 * light one. Named with their measured values rather than excluded by a looser rule, because
 * what they are is a BRAND.md question about the palette and not a defect this track
 * introduces: every one of these values is byte-identical to what shipped before it.
 */
const CARRIED_FORWARD: Readonly<Record<string, readonly string[]>> = {
  active: ["light map"],
  confidential: ["light panel", "light map"],
  permitted: ["light panel", "light map"],
};

describe("every served status swatch is legible where a reader can put it", () => {
  it("clears the non-text floor on every substrate, but for the carried-forward four", () => {
    const shortfalls: Record<string, string[]> = {};
    for (const row of SEEDED_STATUS_CLASSES) {
      for (const [where, background] of Object.entries(SUBSTRATES)) {
        if (contrastRatio(row.colour, background) < NON_TEXT_FLOOR) {
          (shortfalls[row.status_canonical] ??= []).push(where);
        }
      }
    }

    expect(shortfalls).toEqual(CARRIED_FORWARD);
  });

  it("clears it on all four for the absence class and for expired", () => {
    // The two this round repaints. Asserted separately from the sweep above so the exemption
    // list can never quietly grow to cover them again.
    for (const id of ["unmapped", "expired"]) {
      const row = SEEDED_STATUS_CLASSES.find((item) => item.status_canonical === id)!;
      for (const [where, background] of Object.entries(SUBSTRATES)) {
        expect(contrastRatio(row.colour, background), `${id} on ${where}`).toBeGreaterThanOrEqual(
          NON_TEXT_FLOOR,
        );
      }
    }
  });

  it("keeps the absence class the least salient mark that clears the bar", () => {
    // The design argument the colour carries: absence must not be the thing that hides, and it
    // should not be the thing that shouts either.
    const absence = SEEDED_STATUS_CLASSES.find((row) => row.is_absence)!;
    const onPanel = (colour: string) => contrastRatio(colour, SUBSTRATES["dark panel"]);
    const brighter = SEEDED_STATUS_CLASSES.filter(
      (row) => !row.is_absence && onPanel(row.colour) > onPanel(absence.colour),
    );

    expect(brighter).toHaveLength(SEEDED_STATUS_CLASSES.length - 1);
  });
});
