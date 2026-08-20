import { registerOverlay } from "./overlays.ts";
import { mountStatus } from "./status.ts";
import { mountThemeToggle } from "./theme.ts";

export const HEADER_IDS = [
  "gw-search-slot",
  "gw-key-btn",
  "gw-theme-btn",
  "gw-help-btn",
  "gw-help-panel",
  "gw-asof",
  "gw-status",
] as const;

export interface HeaderOptions {
  search: HTMLElement;
  onKeyPanel(): void;
}

/** Harvest §7.3: brand, one control cluster, one capped meta slot — one row at every width. */
export function wireHeader(options: HeaderOptions): void {
  const hosts = Object.fromEntries(
    HEADER_IDS.map((id) => [id, byId(id)]),
  ) as Record<(typeof HEADER_IDS)[number], HTMLElement>;

  hosts["gw-search-slot"].appendChild(options.search);

  mountStatus({
    status: hosts["gw-status"],
    vintage: hosts["gw-asof"],
    toasts: byId("gw-toasts"),
    keyState: hosts["gw-key-btn"],
  });

  hosts["gw-key-btn"].addEventListener("click", () => options.onKeyPanel());
  mountThemeToggle(hosts["gw-theme-btn"]);

  const help = hosts["gw-help-panel"];
  const helpButton = hosts["gw-help-btn"];
  registerOverlay(help);

  function setHelp(open: boolean): void {
    help.hidden = !open;
    helpButton.setAttribute("aria-expanded", String(open));
    if (!open && help.contains(document.activeElement)) helpButton.focus();
  }

  helpButton.addEventListener("click", () => setHelp(help.hidden));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !help.hidden) {
      setHelp(false);
      helpButton.focus();
    }
  });
  document.addEventListener("mousedown", (event) => {
    if (help.hidden) return;
    const target = event.target;
    if (target instanceof Node && (help.contains(target) || helpButton.contains(target))) return;
    setHelp(false);
  });
}

function byId(id: string): HTMLElement {
  const element = document.getElementById(id);
  if (!element) throw new Error(`missing #${id} in index.html`);
  return element;
}
