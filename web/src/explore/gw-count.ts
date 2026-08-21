import { formatValue } from "../card/format.ts";

// The same rule `gw-figure.ts:6` states for a missing handle: dev makes the defect visible,
// test makes it fatal. A number nobody wrote an exemption for is the defect either way.
const STRICT = import.meta.env.MODE === "test";

const UNSERVED =
  "The API does not state why this number is not a figure. The exemption exists in" +
  " tests/contract/non_figure_allowlist.yml and is not served yet (SB-08 A-2).";

/**
 * The exempted number, wearing its exemption. `reason` is the allowlist's own words; `no-reason`
 * is the honest interim state until A-2 serves them, and it looks nothing like a reasoned count.
 */
export class GwCount extends HTMLElement {
  static observedAttributes = ["value", "reason", "no-reason"];

  connectedCallback(): void {
    this.render();
  }

  attributeChangedCallback(): void {
    if (this.isConnected) this.render();
  }

  render(): void {
    const raw = this.getAttribute("value") ?? "";
    const reason = this.getAttribute("reason");
    const unserved = this.hasAttribute("no-reason");
    if (!reason && !unserved) {
      const error = new Error(
        `count ${raw} carries no exemption reason; an exempt number states why it is exempt`,
      );
      if (STRICT) throw error;
      console.error(error);
    }

    const value = document.createElement("span");
    value.className = "gw-count-value";
    value.setAttribute("data-no-glossary", "");
    value.textContent = formatValue(raw);

    const text = reason ?? UNSERVED;
    const popover = document.createElement("span");
    popover.className = "gw-count-reason";
    popover.setAttribute("role", "tooltip");
    popover.hidden = true;
    popover.textContent = text;

    const marker = document.createElement("button");
    marker.type = "button";
    marker.className = reason ? "gw-count-mark" : "gw-count-mark gw-count-mark-unserved";
    // F5: a ringed ASCII glyph, not `ⓔ` (U+24D4), which none of the three self-hosted faces
    // carries — `style.css` pins GW Symbols to U+233E/U+2715, so the browser never even tries
    // it and the mark lands on the reader's system font or on tofu. The ring is drawn in CSS.
    marker.textContent = reason ? "e" : "?";
    // F4: the state, named once, so the pane and the detail row can say which it is rather
    // than each deciding what a `?` in a cell means.
    marker.dataset["mark"] = reason ? "exempt" : "exempt-unstated";
    marker.title = text;
    marker.setAttribute("aria-expanded", "false");
    marker.setAttribute("aria-label", reason ? "Why this is not a figure" : "Exemption not served");
    marker.addEventListener("click", (event) => {
      event.stopPropagation();
      popover.hidden = !popover.hidden;
      marker.setAttribute("aria-expanded", String(!popover.hidden));
    });

    this.replaceChildren(value, marker, popover);
  }
}

if (!customElements.get("gw-count")) customElements.define("gw-count", GwCount);
