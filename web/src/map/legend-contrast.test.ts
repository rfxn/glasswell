import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// vitest roots at web/, so this is the shipped stylesheet.
const MAP_CSS = readFileSync("src/map.css", "utf8");

/**
 * gate-v078 N8 measured the key's own pixels at 1600, 1024 and 390: the panel paints on
 * `#111920`, a full row's class label at `#E3EAF0`, its count digits at `#9FB0BC` and its
 * derivation handle at `#56BFD3`. An out-of-scale row is the same paint under one `opacity`,
 * so what that declaration composites to is arithmetic and belongs in the suite rather than in
 * a screenshot. The count is not decoration: it is what makes the classes sum to the extent at
 * a zoom where four of them are not drawn.
 */
const PANEL = "#111920";
const FULL_BRIGHTNESS = {
  label: { colour: "#E3EAF0", floor: 4.5 },
  count: { colour: "#9FB0BC", floor: 4.5 },
  handle: { colour: "#56BFD3", floor: 3 },
};

function channels(hex: string): [number, number, number] {
  const value = hex.replace("#", "");
  return [0, 2, 4].map((index) => Number.parseInt(value.slice(index, index + 2), 16)) as [
    number,
    number,
    number,
  ];
}

function luminance(hex: string): number {
  const [r, g, b] = channels(hex).map((channel) => {
    const unit = channel / 255;
    return unit <= 0.03928 ? unit / 12.92 : ((unit + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function ratio(foreground: string, background: string): number {
  const [high, low] = [luminance(foreground), luminance(background)].sort((a, b) => b - a) as [
    number,
    number,
  ];
  return (high + 0.05) / (low + 0.05);
}

/** `opacity` on the row composites its paint onto the panel; this is that composite. */
function composite(foreground: string, background: string, opacity: number): string {
  const front = channels(foreground);
  const back = channels(background);
  return `#${front
    .map((channel, index) =>
      Math.round(back[index]! + opacity * (channel - back[index]!))
        .toString(16)
        .padStart(2, "0"),
    )
    .join("")}`;
}

const declaredOpacity = (): number => {
  const block = /\.gw-lg-row\[data-out-of-scale\]\s*\{([^}]*)\}/.exec(MAP_CSS)?.[1] ?? "";
  const value = /opacity:\s*([\d.]+)/.exec(block)?.[1];
  expect(value, "the out-of-scale row declares no opacity").toBeTruthy();
  return Number(value);
};

describe("an out-of-scale legend row recedes without taking its served figure below the floor", () => {
  it("clears the text floor on every string the row paints", () => {
    const opacity = declaredOpacity();

    for (const [name, { colour, floor }] of Object.entries(FULL_BRIGHTNESS)) {
      const measured = ratio(composite(colour, PANEL, opacity), PANEL);
      expect(measured, `${name} at opacity ${opacity} measures ${measured.toFixed(2)}:1`)
        .toBeGreaterThanOrEqual(floor);
    }
  });

  it("still reads as receded beside a full row", () => {
    const opacity = declaredOpacity();
    const full = ratio(FULL_BRIGHTNESS.count.colour, PANEL);
    const receded = ratio(composite(FULL_BRIGHTNESS.count.colour, PANEL, opacity), PANEL);

    expect(opacity).toBeLessThan(1);
    expect(receded).toBeLessThan(full);
  });

  it("keeps a margin over the floor rather than sitting on it", () => {
    // 0.70 clears 4.5:1 by 0.03, which is inside what the gate's own pixel measurement varied
    // by against this arithmetic (it read 2.60 where this reads 2.62).
    const measured = ratio(
      composite(FULL_BRIGHTNESS.count.colour, PANEL, declaredOpacity()),
      PANEL,
    );

    expect(measured).toBeGreaterThanOrEqual(4.6);
  });
});
