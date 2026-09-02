/**
 * Chrome theme. Dark is the default rather than `prefers-color-scheme`: the default basemap
 * is dark, and a light rail framing a dark map is the incoherence VF-3 is already about.
 * The choice is an override, so it persists; it is not URL state, because app/state.ts is
 * a frozen file and a theme is a reader preference, not a view someone would share.
 */
import { readSetting, writeSetting } from "./store.ts";

export type Theme = "dark" | "light";

export const THEME_STORAGE_KEY = "glasswell.theme";

/** The production plot is a canvas: it cannot inherit a CSS variable, so it is told. */
export const THEME_EVENT = "gw:theme";

const NEXT: Record<Theme, Theme> = { dark: "light", light: "dark" };
const COPY: Record<Theme, { label: string; title: string }> = {
  dark: { label: "Light", title: "Switch to the light theme" },
  light: { label: "Dark", title: "Switch to the dark theme" },
};

export function storedTheme(): Theme | null {
  const raw = readSetting(THEME_STORAGE_KEY);
  return raw === "dark" || raw === "light" ? raw : null;
}

export function currentTheme(): Theme {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  document.dispatchEvent(new CustomEvent(THEME_EVENT, { detail: { theme } }));
  writeSetting(THEME_STORAGE_KEY, theme);
}

/**
 * Off until Track M lands basemap and overlay theming. map.css hardcodes a dark overlay
 * surface while taking `color: var(--paper)`, which the light theme inverts, so the legend
 * and the tile-failure toast render black-on-black — and the basemap does not follow the
 * theme at all. The theme is finished; the map is not, and map.css is not this track's file.
 */
export function themeToggleEnabled(): boolean {
  return import.meta.env.VITE_GW_THEME_TOGGLE === "1";
}

export function mountThemeToggle(button: HTMLElement): void {
  if (!themeToggleEnabled()) {
    // Removed, not hidden: a hidden control is still reachable by keyboard and by script.
    // Dark is forced past any stored preference, or a reader who chose light before the
    // flag would be stranded in it with nothing left in the rail to change it back.
    document.documentElement.dataset.theme = "dark";
    button.remove();
    return;
  }

  function render(theme: Theme): void {
    button.setAttribute("aria-pressed", String(theme === "light"));
    // The control is labelled with the destination, not the current state.
    button.title = COPY[theme].title;
    const label = button.querySelector(".gw-ctl-lbl");
    if (label) label.textContent = COPY[theme].label;
    // Set with the label rather than once at mount: the compact rail hides that span below
    // 901 px, and a name frozen at the initial state would announce the wrong destination.
    button.setAttribute("aria-label", COPY[theme].label);
  }

  // The markup ships it hidden so the flag-off build never paints a control it then removes.
  button.hidden = false;

  const initial = storedTheme() ?? "dark";
  document.documentElement.dataset.theme = initial;
  render(initial);

  button.addEventListener("click", () => {
    const theme = NEXT[currentTheme()];
    applyTheme(theme);
    render(theme);
  });
}
