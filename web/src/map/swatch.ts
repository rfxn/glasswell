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
  if (swatch.kind === "dot") {
    node.appendChild(el("circle", { cx: String(c), cy: String(c), r: String(size * 0.3), fill: swatch.colour }));
  } else if (swatch.kind === "line") {
    node.appendChild(
      el("line", {
        x1: "1",
        y1: String(size - 3),
        x2: String(size - 1),
        y2: "3",
        stroke: swatch.colour,
        "stroke-width": "2",
        "stroke-linecap": "round",
      }),
    );
  } else {
    node.appendChild(
      el("rect", {
        x: "2",
        y: "2",
        width: String(size - 4),
        height: String(size - 4),
        fill: swatch.kind === "fill" ? swatch.colour : "none",
        stroke: swatch.colour,
        "stroke-width": "1.4",
      }),
    );
  }
  return node;
}
