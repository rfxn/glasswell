/**
 * WCAG 2.1 relative luminance and contrast ratio, so a legibility claim about a label is a
 * number the tests can hold the style to rather than a judgement someone made once.
 */

/** 1.4.3 AA, text. */
export const CONTRAST_FLOOR = 4.5;

/** 1.4.11 AA, non-text: lines, boundaries and the edge of a chrome surface. */
export const NON_TEXT_FLOOR = 3;

const HEX = /^#(?:[0-9a-f]{3}|[0-9a-f]{6})$/i;

export function relativeLuminance(colour: string): number {
  if (!HEX.test(colour)) throw new Error(`not a measurable colour: ${colour}`);
  const digits = colour.slice(1);
  const wide = digits.length === 6 ? digits : [...digits].map((digit) => digit + digit).join("");
  const channels = [0, 2, 4].map((at) => parseInt(wide.slice(at, at + 2), 16) / 255);
  const [red, green, blue] = channels.map((channel) =>
    channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4,
  ) as [number, number, number];
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
}

export function contrastRatio(a: string, b: string): number {
  const [light, dark] = [relativeLuminance(a), relativeLuminance(b)].sort((x, y) => y - x) as [
    number,
    number,
  ];
  return (light + 0.05) / (dark + 0.05);
}
