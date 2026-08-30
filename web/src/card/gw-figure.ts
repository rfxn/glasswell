import type { Figure } from "../api/envelope.ts";
import { dispatchExplain, explainHandle } from "../chrome/handle.ts";
import { formatFigure } from "./format.ts";

// SB-05 §3.1: dev renders a NAKED badge and logs; the test build throws. Either way the
// defect is visible — this element is the browser-side end of the no-naked-numbers rule.
const STRICT = import.meta.env.MODE === "test";

export class GwFigure extends HTMLElement {
  static observedAttributes = [
    "value",
    "unit",
    "handle",
    "label",
    "label-hidden",
    "granularity",
    "vintage",
  ];

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
    if (label && !this.hasAttribute("label-hidden")) {
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
    // No vintage chip: the handle below opens the chain, which states the vintage it resolved
    // at. The attribute stays the element's contract — callers set it, the surface stays clean.
    parts.push(
      explainHandle({
        label: label ?? "this figure",
        handle: figure.d,
        // The host carries the event so a row listening above the element still hears it,
        // and the click stops here rather than also selecting whatever encloses the figure.
        activate: (id, event) => {
          event.stopPropagation();
          dispatchExplain(this, id);
        },
      }),
    );

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
