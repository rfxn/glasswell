import type { Figure } from "../api/envelope.ts";
import { formatFigure } from "./format.ts";

// SB-05 §3.1: dev renders a NAKED badge and logs; the test build throws. Either way the
// defect is visible — this element is the browser-side end of the no-naked-numbers rule.
const STRICT = import.meta.env.MODE === "test";

export const EXPLAIN_EVENT = "gw-explain";

export class GwFigure extends HTMLElement {
  static observedAttributes = ["value", "unit", "handle", "label", "granularity", "vintage"];

  connectedCallback(): void {
    this.render();
  }

  attributeChangedCallback(): void {
    if (this.isConnected) this.render();
  }

  render(): void {
    const figure: Figure = {
      value: this.getAttribute("value") ?? "",
      unit: this.getAttribute("unit") ?? "",
      d: this.getAttribute("handle") ?? "",
    };
    let text: string;
    try {
      text = formatFigure(figure);
    } catch (error) {
      if (STRICT) throw error;
      console.error(error);
      this.replaceChildren(badge(this.ownerDocument, figure.value));
      return;
    }

    const document_ = this.ownerDocument;
    const parts: Node[] = [];
    const label = this.getAttribute("label");
    if (label) {
      const element = document_.createElement("span");
      element.className = "gw-figure-label";
      element.textContent = label;
      parts.push(element);
    }
    const value = document_.createElement("span");
    value.className = "gw-figure-value";
    value.setAttribute("data-no-glossary", "");
    value.textContent = text;
    parts.push(value);

    const granularity = this.getAttribute("granularity");
    if (granularity && granularity !== "well_observed") {
      const chip = document_.createElement("span");
      chip.className = "gw-chip gw-chip-granularity";
      chip.textContent = granularity;
      parts.push(chip);
    }
    const vintage = this.getAttribute("vintage");
    if (vintage) {
      const chip = document_.createElement("span");
      chip.className = "gw-chip gw-chip-vintage";
      chip.textContent = `vintage ${vintage}`;
      parts.push(chip);
    }

    const handle = document_.createElement("button");
    handle.type = "button";
    handle.className = "gw-handle";
    handle.setAttribute("data-handle", figure.d);
    handle.title = `Show where this number came from: ${figure.d}`;
    handle.setAttribute("aria-label", `Lineage for ${label ?? "this figure"}`);
    handle.textContent = "⌾";
    handle.addEventListener("click", (event) => {
      event.stopPropagation();
      this.dispatchEvent(
        new CustomEvent(EXPLAIN_EVENT, { detail: { handle: figure.d }, bubbles: true }),
      );
    });
    parts.push(handle);

    this.replaceChildren(...parts);
  }
}

function badge(document_: Document, value: string): HTMLElement {
  const element = document_.createElement("span");
  element.className = "gw-naked";
  element.textContent = `${value} NAKED`;
  element.title = "This number reached the UI without a unit or a handle. That is a defect.";
  return element;
}

if (!customElements.get("gw-figure")) customElements.define("gw-figure", GwFigure);
