import { readState, writeState } from "../app/state.ts";
import type { ViewMode } from "../app/state.ts";
import { crossTo } from "../explore/router.ts";
import { registerOverlay } from "./overlays.ts";
import { mountStatus } from "./status.ts";
import { mountThemeToggle } from "./theme.ts";

export const HEADER_IDS = [
  "gw-mode-switch",
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

const SURFACES: { view: ViewMode; title: string }[] = [
  { view: "map", title: "Map" },
  { view: "explore", title: "Explore" },
];

let followsHistory = false;

export interface ModeSwitchOptions {
  view: ViewMode;
  onSwitch(next: ViewMode): void;
}

export function mountModeSwitch(host: HTMLElement, options: ModeSwitchOptions): void {
  host.replaceChildren(
    ...SURFACES.map((surface) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "gw-mode-btn";
      button.dataset["view"] = surface.view;
      button.textContent = surface.title;
      button.setAttribute("aria-pressed", String(surface.view === options.view));
      button.addEventListener("click", () => options.onSwitch(surface.view));
      return button;
    }),
  );
}

function pressModeSwitch(view: ViewMode): void {
  const host = document.getElementById("gw-mode-switch");
  for (const button of host?.querySelectorAll("button") ?? []) {
    button.setAttribute("aria-pressed", String(button.dataset["view"] === view));
  }
}

/** Harvest §7.3: brand, one control cluster, one capped meta slot — one row at every width. */
export function wireHeader(options: HeaderOptions): void {
  const hosts = Object.fromEntries(
    HEADER_IDS.map((id) => [id, byId(id)]),
  ) as Record<(typeof HEADER_IDS)[number], HTMLElement>;

  hosts["gw-search-slot"].appendChild(options.search);

  mountModeSwitch(hosts["gw-mode-switch"], {
    view: readState().view,
    onSwitch: (next) => {
      const state = readState();
      if (next === state.view) return;
      // pushState so the back button returns the reader to the surface they left, then a
      // synthetic popstate so main.ts's one dispatch renders it — the same route the back
      // button takes, rather than a second entry point into the same decision.
      writeState(crossTo(next, state), "push");
      pressModeSwitch(next);
      window.dispatchEvent(new PopStateEvent("popstate"));
    },
  });
  if (!followsHistory) {
    followsHistory = true;
    window.addEventListener("popstate", () => pressModeSwitch(readState().view));
  }

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
