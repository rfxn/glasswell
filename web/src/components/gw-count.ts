import "./gw-count.css";

import { formatValue } from "../card/format.ts";
import { placePopover } from "../chrome/popover.ts";

// The same rule `gw-figure.ts:6` states for a missing handle: dev makes the defect visible,
// test makes it fatal. A number nobody wrote an exemption for is the defect either way.
const STRICT = import.meta.env.MODE === "test";

const UNSERVED =
  "The API does not state why this number is not a figure. The exemption exists in" +
  " tests/contract/non_figure_allowlist.yml and is not served yet (SB-08 A-2).";

const REASON_ID = "gw-count-reason";

let popover: HTMLElement | null = null;
let openMark: HTMLElement | null = null;

/**
 * N1: one panel on document.body, `gw-term`'s pattern and its `.gw-popover` chrome. In flow
 * inside a right-aligned cell the reason widened its own track — the clicked row's count moved
 * 240 px and the last column went 148.6 px past the panel — and `offScreenColumns` measures at
 * mount, so the off-edge sentence could not answer for a state that arrives on a click.
 */
function openReason(mark: HTMLElement, text: string): void {
  if (!popover) {
    popover = document.createElement("span");
    popover.className = "gw-popover gw-count-reason";
    popover.id = REASON_ID;
    popover.setAttribute("role", "tooltip");
  }
  if (!popover.isConnected) document.body.append(popover);

  const reopening = openMark === mark && !popover.hidden;
  hideReason();
  if (reopening) return;

  popover.textContent = text;
  popover.hidden = false;
  openMark = mark;
  mark.setAttribute("aria-expanded", "true");
  mark.setAttribute("aria-describedby", REASON_ID);
  placePopover(popover, mark);
}

function hideReason(): void {
  openMark?.setAttribute("aria-expanded", "false");
  openMark?.removeAttribute("aria-describedby");
  openMark = null;
  if (popover) popover.hidden = true;
}

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape" || !openMark) return;
  const focused = openMark;
  hideReason();
  focused.focus();
});

// The panel is the body's child, so scrolling the grid or the pane slides the mark out from
// under it. Closing beats letting a reason float over a row it does not belong to.
document.addEventListener("scroll", () => hideReason(), { capture: true, passive: true });

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

    if (openMark && this.contains(openMark)) hideReason();

    const value = document.createElement("span");
    value.className = "gw-count-value";
    value.setAttribute("data-no-glossary", "");
    value.textContent = formatValue(raw);

    const text = reason ?? UNSERVED;
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
      openReason(marker, text);
    });

    this.replaceChildren(value, marker);
  }
}

if (!customElements.get("gw-count")) customElements.define("gw-count", GwCount);
