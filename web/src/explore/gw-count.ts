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
    marker.textContent = reason ? "ⓔ" : "?";
    marker.title = text;
    marker.setAttribute("aria-label", reason ? "Why this is not a figure" : "Exemption not served");
    marker.addEventListener("click", (event) => {
      event.stopPropagation();
      popover.hidden = !popover.hidden;
    });

    this.replaceChildren(value, marker, popover);
  }
}

if (!customElements.get("gw-count")) customElements.define("gw-count", GwCount);
