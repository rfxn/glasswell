import { placePopover } from "../chrome/popover.ts";
import { termDetail, termSummary } from "./store.ts";

const OPEN_DELAY_MS = 150;
const CLOSE_GRACE_MS = 300;

let popover: HTMLElement | null = null;
let openTimer: number | undefined;
let closeTimer: number | undefined;
let anchor: GwTerm | null = null;

export class GwTerm extends HTMLElement {
  connectedCallback(): void {
    if (!this.hasAttribute("tabindex")) this.setAttribute("tabindex", "0");
    if (!this.hasAttribute("role")) this.setAttribute("role", "button");
    this.classList.add("gw-term");
    this.addEventListener("mouseenter", () => this.scheduleOpen(false));
    this.addEventListener("focus", () => this.scheduleOpen(false));
    this.addEventListener("mouseleave", () => scheduleClose());
    this.addEventListener("blur", () => scheduleClose());
    this.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      this.scheduleOpen(true);
    });
    this.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        this.scheduleOpen(true);
      }
    });
  }

  get termId(): string {
    return this.getAttribute("term-id") ?? "";
  }

  private scheduleOpen(expanded: boolean): void {
    window.clearTimeout(closeTimer);
    window.clearTimeout(openTimer);
    if (expanded) {
      show(this, true);
      return;
    }
    openTimer = window.setTimeout(() => show(this, false), OPEN_DELAY_MS);
  }
}

function panel(): HTMLElement {
  if (popover) return popover;
  const element = document.createElement("div");
  element.className = "gw-popover";
  element.id = "gw-popover";
  element.hidden = true;
  element.addEventListener("mouseenter", () => window.clearTimeout(closeTimer));
  element.addEventListener("mouseleave", () => scheduleClose());
  document.body.appendChild(element);
  popover = element;
  return element;
}

function show(term: GwTerm, expanded: boolean): void {
  const element = panel();
  anchor = term;
  term.setAttribute("aria-describedby", "gw-popover");
  const summary = termSummary(term.termId);
  element.replaceChildren();
  element.hidden = false;

  const heading = document.createElement("h4");
  heading.textContent = summary?.term ?? term.textContent ?? term.termId;
  element.appendChild(heading);

  const short = document.createElement("p");
  short.textContent = summary?.short_definition ?? "Definition loading…";
  element.appendChild(short);

  if (summary?.domain_tags.length) {
    const tags = document.createElement("p");
    tags.className = "gw-popover-tags";
    tags.textContent = summary.domain_tags.join(" · ");
    element.appendChild(tags);
  }

  if (!expanded) {
    const more = document.createElement("button");
    more.type = "button";
    more.className = "gw-popover-expand";
    more.textContent = "expand";
    more.addEventListener("click", () => show(term, true));
    element.appendChild(more);
  } else {
    const loading = document.createElement("p");
    loading.className = "gw-popover-loading";
    loading.textContent = "loading the full definition…";
    element.appendChild(loading);
    void termDetail(term.termId)
      .then((detail) => {
        if (anchor !== term) return;
        loading.remove();
        const full = document.createElement("p");
        full.className = "gw-popover-expanded";
        full.textContent = detail.expanded_definition;
        element.appendChild(full);
        if (detail.related_terms.length) element.appendChild(relatedChips(detail.related_terms));
        if (detail.appears_in.length) {
          const where = document.createElement("p");
          where.className = "gw-popover-where";
          where.textContent = `appears in ${detail.appears_in.map((site) => site.ref).join(", ")}`;
          element.appendChild(where);
        }
        placePopover(element, term);
      })
      .catch((error: unknown) => {
        loading.textContent = `could not load this definition: ${String(error)}`;
      });
  }

  placePopover(element, term);
}

function relatedChips(related: string[]): HTMLElement {
  const wrapper = document.createElement("p");
  wrapper.className = "gw-popover-related";
  for (const relatedId of related) {
    const chip = document.createElement("gw-term");
    chip.setAttribute("term-id", relatedId);
    chip.className = "gw-chip";
    chip.textContent = termSummary(relatedId)?.term ?? relatedId;
    wrapper.appendChild(chip);
  }
  return wrapper;
}

function scheduleClose(): void {
  window.clearTimeout(openTimer);
  closeTimer = window.setTimeout(hide, CLOSE_GRACE_MS);
}

export function hide(): void {
  anchor?.removeAttribute("aria-describedby");
  anchor = null;
  if (popover) popover.hidden = true;
}

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && anchor) {
    const focused = anchor;
    hide();
    focused.focus();
  }
});

if (!customElements.get("gw-term")) customElements.define("gw-term", GwTerm);

/** The authoritative path (SB-05 §5.1): meta.labels already named the term, so no matching. */
export function labelElement(text: string, termId: string | null): HTMLElement {
  if (!termId) {
    const plain = document.createElement("span");
    plain.className = "gw-label";
    plain.textContent = text;
    return plain;
  }
  const term = document.createElement("gw-term");
  term.setAttribute("term-id", termId);
  term.classList.add("gw-label");
  term.textContent = text;
  return term;
}
