/**
 * Four channels that must never be routed into one another (responder's incident: a
 * transient failure written to the freshness slot erased a live degraded warning and the
 * board read healthier than it was). Persistent status, resolved vintage, transient toast,
 * key state — one writer each.
 */

export type KeyState = "ok" | "missing" | "rejected";

interface StatusHosts {
  status: HTMLElement;
  vintage: HTMLElement;
  toasts: HTMLElement;
  keyState: HTMLElement;
}

const TOAST_MS = 6000;
const KEY_COPY: Record<KeyState, string> = {
  ok: "key ok",
  missing: "key needed",
  rejected: "key rejected",
};

// Matches the ≤520 posture in style.css, where the read slot is 104 px wide. Below that the
// long forms do not shrink, they truncate, and a truncated sentence spends rail width to say
// nothing (gate-v MINOR-1).
const NARROW_QUERY = "(max-width: 520px)";

/**
 * The brief forms for the strings main.ts sets. They live here rather than at the call site
 * because main.ts is frozen — which is also what makes keying on its literals safe: they
 * cannot drift without the freeze being lifted. An unrecognised string keeps its long form.
 */
const BRIEF: Record<string, string> = {
  "Click any ⌾ to see where a number came from.": "tap ⌾ for source",
  "Glossary unavailable": "glossary down",
};

let hosts: StatusHosts | null = null;
let narrow: MediaQueryList | null = null;
let current = { long: "", brief: "" };

export function mountStatus(elements: StatusHosts): void {
  hosts = elements;
  // Rebound rather than bound once: a second mount must not leave the first mount's query
  // still driving the slot, and must not stack a second listener on the same one.
  narrow?.removeEventListener("change", renderStatus);
  narrow = window.matchMedia(NARROW_QUERY);
  narrow.addEventListener("change", renderStatus);
  setVintage(null);
  setKeyState("ok");
}

export function setStatus(
  short: string,
  detail?: string,
  options?: { degraded?: boolean; brief?: string },
): void {
  if (!hosts) return;
  current = { long: short, brief: options?.brief ?? BRIEF[short] ?? short };
  renderStatus();
  // The long form is always the tooltip, so the brief form never costs the reader detail.
  hosts.status.title = detail ?? (current.brief === current.long ? "" : current.long);
  hosts.status.classList.toggle("gw-degraded", options?.degraded === true);
}

function renderStatus(): void {
  if (!hosts) return;
  hosts.status.textContent = narrow?.matches ? current.brief : current.long;
}

export function setVintage(resolved: string | null): void {
  if (!hosts) return;
  hosts.vintage.replaceChildren();
  // The label is its own element so the rail can set it as an eyebrow beside a mono figure;
  // the slot's text still reads "as_of <date>" to anything that reads text.
  const label = document.createElement("span");
  label.className = "gw-asof-label";
  label.setAttribute("data-no-glossary", "");
  label.textContent = "as_of";
  hosts.vintage.append(label, document.createTextNode(" "));
  if (!resolved) {
    hosts.vintage.appendChild(document.createTextNode("—"));
    return;
  }
  const time = document.createElement("time");
  time.dateTime = resolved;
  time.textContent = resolved;
  hosts.vintage.appendChild(time);
}

export function toast(message: string): void {
  if (!hosts) return;
  const item = document.createElement("p");
  item.className = "gw-toast";
  item.setAttribute("role", "status");
  item.setAttribute("data-no-glossary", "");
  item.textContent = message;
  hosts.toasts.appendChild(item);
  setTimeout(() => item.remove(), TOAST_MS);
}

export function setKeyState(state: KeyState): void {
  if (!hosts) return;
  hosts.keyState.textContent = KEY_COPY[state];
  hosts.keyState.hidden = state === "ok";
  hosts.keyState.classList.toggle("gw-key-bad", state !== "ok");
}
