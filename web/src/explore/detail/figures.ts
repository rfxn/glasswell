import "../../card/gw-figure.ts";

import { isFigure } from "../../api/envelope.ts";

/**
 * A served figure nested inside a structural value — the publication receipt's acceptance
 * gates and its peer-ladder support distribution — carried its handle in the payload and
 * rendered as a line of a JSON block, which no reader can click. The handles were there and
 * the explain affordance was not.
 */

export function containsFigure(value: unknown): boolean {
  if (isFigure(value)) return true;
  if (Array.isArray(value)) return value.some(containsFigure);
  if (typeof value === "object" && value !== null) {
    return Object.values(value as Record<string, unknown>).some(containsFigure);
  }
  return false;
}

/** A nested block of figures, each one addressable, rather than a pre block of its JSON. */
export function figureTree(value: unknown): HTMLElement {
  const list = document.createElement("dl");
  list.className = "gw-figure-tree";
  appendFigures(list, value);
  return list;
}

function appendFigures(list: HTMLElement, value: unknown): void {
  const entries = Array.isArray(value)
    ? value.map((item, index) => [String(index), item] as const)
    : Object.entries((value ?? {}) as Record<string, unknown>);
  for (const [name, item] of entries) {
    const key = document.createElement("dt");
    key.className = "gw-figure-tree-key";
    key.textContent = name;
    const slot = document.createElement("dd");
    slot.className = "gw-figure-tree-value";
    if (isFigure(item)) {
      slot.append(figureElement(item as FigureValue, name));
    } else if (typeof item === "object" && item !== null) {
      const nested = document.createElement("dl");
      nested.className = "gw-figure-tree";
      appendFigures(nested, item);
      slot.append(nested);
    } else {
      slot.textContent = item === null ? "—" : String(item);
    }
    list.append(key, slot);
  }
}

interface FigureValue {
  value: string;
  unit?: string;
  basis?: string;
  d: string;
}

function figureElement(source: FigureValue, label: string): HTMLElement {
  const figure = document.createElement("gw-figure");
  figure.setAttribute("value", source.value);
  figure.setAttribute("unit", source.unit ?? "");
  figure.setAttribute("handle", source.d);
  figure.setAttribute("label", label);
  figure.setAttribute("label-hidden", "");
  figure.title = `${source.value}${source.unit ? ` ${source.unit}` : ""} as served`;
  return figure;
}
