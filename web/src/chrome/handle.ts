/**
 * R6's one provenance affordance. Every served figure carries a ⌾ that resolves its
 * derivation, so the control that exposes traceability is built here and nowhere else —
 * seven private copies had drifted into three different accessibility contracts.
 */

export const EXPLAIN_EVENT = "gw-explain";

/** The one spelling of the mark. `style.css` pins U+233E to the GW Symbols face because
 * Inter carries neither it nor `✕`; a second literal is a second thing to keep in step. */
export const HANDLE_GLYPH = "⌾";

const NAME_PREFIX = "Lineage for ";

// The same discipline `gw-figure.ts:6` applies to a naked number: dev logs the defect, the test
// build throws. A caller that pre-writes the prefix names the button twice, and every label
// here is interpolated from data, so the check has to run rather than be remembered.
const STRICT = import.meta.env.MODE === "test";

/** The figure's own words, kept so the handle can be re-titled when its derivation arrives. */
const labels = new WeakMap<HTMLButtonElement, string>();

export interface ExplainHandleOptions {
  /** Names the figure, never the derivation: the id is machine detail and rides `title`. */
  label: string;
  handle?: string | null;
  className?: string;
  /** Replaces the default dispatch, for hosts that route explain through their own callback. */
  activate?: (handle: string, event: MouseEvent) => void;
}

export function dispatchExplain(source: EventTarget, handle: string): void {
  source.dispatchEvent(new CustomEvent(EXPLAIN_EVENT, { detail: { handle }, bubbles: true }));
}

export function explainHandle(options: ExplainHandleOptions): HTMLButtonElement {
  if (options.label.includes(NAME_PREFIX)) {
    const error = new Error(
      `handle label ${JSON.stringify(options.label)} already carries "${NAME_PREFIX.trim()}";` +
        " pass the figure's name alone",
    );
    if (STRICT) throw error;
    console.error(error);
  }
  const button = document.createElement("button");
  button.type = "button";
  button.className = options.className ? `gw-handle ${options.className}` : "gw-handle";
  button.textContent = HANDLE_GLYPH;
  // Set once and never blanked: a nameless ⌾ reads as the bare glyph to a screen reader.
  button.setAttribute("aria-label", `${NAME_PREFIX}${options.label}`);
  labels.set(button, options.label);
  setExplainHandle(button, options.handle ?? null);
  button.addEventListener("click", (event) => {
    const handle = button.dataset["handle"];
    if (!handle) return;
    if (options.activate) options.activate(handle, event);
    else dispatchExplain(button, handle);
  });
  return button;
}

/**
 * A handle that reads as a line rather than a bare mark, for the few hosts whose row spells the
 * affordance out. The glyph stays this module's, and `aria-label` is untouched — the caption is
 * for the eye, the label is what a screen reader gets.
 */
export function setHandleCaption(button: HTMLButtonElement, caption: string): void {
  button.textContent = `${HANDLE_GLYPH} ${caption}`;
}

/** Visible exactly when it has a derivation to resolve — a ⌾ that explains nothing is a dead end. */
export function setExplainHandle(button: HTMLButtonElement, handle: string | null): void {
  button.dataset["handle"] = handle ?? "";
  button.hidden = handle === null || handle === "";
  const label = labels.get(button) ?? "this figure";
  button.title = handle ? `Show where ${label} came from: ${handle}` : "";
}
