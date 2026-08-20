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

let hosts: StatusHosts | null = null;

export function mountStatus(elements: StatusHosts): void {
  hosts = elements;
  setVintage(null);
  setKeyState("ok");
}

export function setStatus(short: string, detail?: string, options?: { degraded?: boolean }): void {
  if (!hosts) return;
  hosts.status.textContent = short;
  hosts.status.title = detail ?? "";
  hosts.status.classList.toggle("gw-degraded", options?.degraded === true);
}

export function setVintage(resolved: string | null): void {
  if (!hosts) return;
  hosts.vintage.replaceChildren();
  hosts.vintage.appendChild(document.createTextNode("as_of "));
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
