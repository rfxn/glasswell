/**
 * R6's one provenance affordance. Every served figure carries a ⌾ that resolves its
 * derivation, so the control that exposes traceability is built here and nowhere else —
 * seven private copies had drifted into three different accessibility contracts.
 */

export const EXPLAIN_EVENT = "gw-explain";

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
  const button = document.createElement("button");
  button.type = "button";
  button.className = options.className ? `gw-handle ${options.className}` : "gw-handle";
  button.textContent = "⌾";
  // Set once and never blanked: a nameless ⌾ reads as the bare glyph to a screen reader.
  button.setAttribute("aria-label", `Lineage for ${options.label}`);
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

/** Visible exactly when it has a derivation to resolve — a ⌾ that explains nothing is a dead end. */
export function setExplainHandle(button: HTMLButtonElement, handle: string | null): void {
  button.dataset["handle"] = handle ?? "";
  button.hidden = handle === null || handle === "";
  const label = labels.get(button) ?? "this figure";
  button.title = handle ? `Show where ${label} came from: ${handle}` : "";
}
