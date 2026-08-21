import type { LayerSwatch } from "./registry.ts";
import type { StatusGlyph } from "./status.ts";

const SVG_NS = "http://www.w3.org/2000/svg";

function svg(size: number): SVGSVGElement {
  const node = document.createElementNS(SVG_NS, "svg");
  node.setAttribute("viewBox", `0 0 ${size} ${size}`);
  node.setAttribute("width", String(size));
  node.setAttribute("height", String(size));
  node.setAttribute("aria-hidden", "true");
  node.setAttribute("focusable", "false");
  return node;
}

function el<K extends keyof SVGElementTagNameMap>(
  name: K,
  attributes: Record<string, string>,
): SVGElementTagNameMap[K] {
  const node = document.createElementNS(SVG_NS, name);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  return node;
}

/**
 * The legend key is drawn from the same glyph grammar the map paints with — solid for a
 * producing fluid, hollow for a location, a struck line for plugging as a modifier rather
 * than a colour of its own (ND DMR `STATUS-TYPE`, Shell Standard Legend §2.1.2).
 */
export function statusSwatch(colour: string, glyph: StatusGlyph, size = 14): SVGSVGElement {
  const node = svg(size);
  const c = size / 2;
  const r = size * 0.32;
  const hollow = glyph === "hollow" || glyph === "struck-hollow" || glyph === "dashed" || glyph === "bar";
  const circle = el("circle", {
    cx: String(c),
    cy: String(c),
    r: String(r),
    fill: hollow ? "none" : colour,
    stroke: colour,
    "stroke-width": "1.4",
  });
  if (glyph === "dashed") circle.setAttribute("stroke-dasharray", "2 1.6");
  node.appendChild(circle);
  if (glyph === "bar") {
    node.appendChild(
      el("line", {
        x1: String(c - r),
        y1: String(c),
        x2: String(c + r),
        y2: String(c),
        stroke: colour,
        "stroke-width": "1.4",
      }),
    );
  }
  if (glyph === "struck" || glyph === "struck-hollow") {
    node.appendChild(
      el("line", {
        x1: String(c - r - 1.6),
        y1: String(c + r + 1.6),
        x2: String(c + r + 1.6),
        y2: String(c - r - 1.6),
        stroke: "#C4D0D8",
        "stroke-width": "1.4",
        "stroke-linecap": "round",
      }),
    );
  }
  return node;
}

export function layerSwatch(swatch: LayerSwatch, size = 14): SVGSVGElement {
  const node = svg(size);
  const c = size / 2;
  // A dot, a fill and an outline each have one ink; only the line divides. The registry test
  // holds a multi-colour swatch to the line kind so nothing is dropped here in silence.
  const [ink] = swatch.colours;
  if (swatch.kind === "dot") {
    node.appendChild(el("circle", { cx: String(c), cy: String(c), r: String(size * 0.3), fill: ink }));
  } else if (swatch.kind === "line") {
    const [x1, y1, x2, y2] = [1, size - 3, size - 1, 3];
    const stops = swatch.colours.length;
    const at = (step: number): [string, string] => [
      String(x1 + ((x2 - x1) * step) / stops),
      String(y1 + ((y2 - y1) * step) / stops),
    ];
    for (const [step, colour] of swatch.colours.entries()) {
      const [startX, startY] = at(step);
      const [endX, endY] = at(step + 1);
      node.appendChild(
        el("line", {
          x1: startX,
          y1: startY,
          x2: endX,
          y2: endY,
          stroke: colour,
          "stroke-width": "2",
          // Butt, or a rounded cap paints each segment over the next one's start.
          "stroke-linecap": stops === 1 ? "round" : "butt",
        }),
      );
    }
  } else {
    node.appendChild(
      el("rect", {
        x: "2",
        y: "2",
        width: String(size - 4),
        height: String(size - 4),
        fill: swatch.kind === "fill" ? ink : "none",
        stroke: ink,
        "stroke-width": "1.4",
      }),
    );
  }
  return node;
}
