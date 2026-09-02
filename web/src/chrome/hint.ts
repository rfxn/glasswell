/**
 * The fifth channel, and the only one that is allowed to disappear for good: a one-time
 * lesson. `⌾ opens the lineage` is the app's whole thesis and has to be taught, but it is
 * not a statement about the data, so it does not belong in the status slot — it held the
 * rail's widest column open to repeat something the reader learned on their first click.
 * It is coached once, beside the control that documents it permanently, and then it is gone.
 */
import { readSetting, writeSetting } from "./store.ts";

export const HINT_STORAGE_KEY = "glasswell.hint.lineage";

// chrome/handle.ts's EXPLAIN_EVENT, kept as a literal so the rail carries no import edge into
// the affordance it only coaches; hint.test.ts asserts the two still agree.
export const HINT_EVENT = "gw-explain";

let host: HTMLElement | null = null;
let listening = false;

export function mountHint(element: HTMLElement): void {
  host = element;
  element.hidden = true;
  element.querySelector(".gw-hint-close")?.addEventListener("click", () => dismiss());
  if (listening) return;
  listening = true;
  // Document-level, and bound once: the lesson ends the moment the reader does the thing it
  // was teaching, wherever in the app they do it.
  document.addEventListener(HINT_EVENT, () => dismiss());
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") dismiss();
  });
  // pointerdown, not mousedown: on touch the synthetic mouse event arrives after the tap has
  // already been routed, so the first tap outside was spent dismissing and never reached what
  // it was aimed at. Nothing is prevented or stopped here -- the coach mark gets out of the
  // way and the tap carries on to its target (gate-v076 D3).
  document.addEventListener("pointerdown", (event) => {
    const target = event.target;
    if (target instanceof Node && host?.contains(target)) return;
    dismiss();
  });
}

/** Never focuses itself: nobody asked for it, so it may not take the caret out of the field. */
export function showHint(text: string): void {
  if (!host || readSetting(HINT_STORAGE_KEY) !== null) return;
  const slot = host.querySelector(".gw-hint-text");
  if (slot) slot.textContent = text;
  host.hidden = false;
}

function dismiss(): void {
  if (!host || host.hidden) return;
  host.hidden = true;
  // Spent on dismissal rather than on display: a reader who reloads mid-glance has not been
  // taught anything yet, and would never be offered the sentence again.
  writeSetting(HINT_STORAGE_KEY, "seen");
}
