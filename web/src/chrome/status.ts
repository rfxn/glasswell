/**
 * Five channels that must never be routed into one another (responder's incident: a
 * transient failure written to the freshness slot erased a live degraded warning and the
 * board read healthier than it was). Persistent status, resolved vintage, transient toast,
 * session state, one-time coaching — one writer each. Coaching is chrome/hint.ts, and this
 * module's only part in it is refusing to print it as a status.
 */
import { showHint } from "./hint.ts";

export type SessionState = "ok" | "required" | "expired";

interface StatusHosts {
  status: HTMLElement;
  vintage: HTMLElement;
  /** The phone posture has no room for the read column, so Help carries the same fact. */
  vintageEcho?: HTMLElement;
  toasts: HTMLElement;
  session: HTMLElement;
}

const TOAST_MS = 6000;
const SESSION_COPY: Record<SessionState, string> = {
  ok: "signed in",
  required: "sign in",
  expired: "session ended",
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
  "Glossary unavailable": "glossary down",
};

/** The one string main.ts sets that is a lesson rather than a status. Routed, not printed. */
const COACHED = "Click any ⌾ to see where a number came from.";

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
  setSessionState("ok");
}

export function setStatus(
  short: string,
  detail?: string,
  options?: { degraded?: boolean; brief?: string },
): void {
  if (!hosts) return;
  if (short === COACHED) {
    showHint(short);
    return;
  }
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
  // One writer, two places to read it: the rail's corner, and Help, which is where the fact
  // still is at the width the corner does not exist.
  renderVintage(hosts.vintage, resolved);
  if (hosts.vintageEcho) renderVintage(hosts.vintageEcho, resolved);
}

function renderVintage(host: HTMLElement, resolved: string | null): void {
  host.replaceChildren();
  // The label is its own element so the rail can set it as an eyebrow beside a mono figure;
  // the slot's text still reads "as_of <date>" to anything that reads text.
  const label = document.createElement("span");
  label.className = "gw-asof-label";
  label.setAttribute("data-no-glossary", "");
  label.textContent = "as_of";
  host.append(label, document.createTextNode(" "));
  if (!resolved) {
    host.appendChild(document.createTextNode("—"));
    return;
  }
  const time = document.createElement("time");
  time.dateTime = resolved;
  time.textContent = resolved;
  host.appendChild(time);
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

export function setSessionState(state: SessionState): void {
  if (!hosts) return;
  hosts.session.textContent = SESSION_COPY[state];
  hosts.session.hidden = state === "ok";
}
