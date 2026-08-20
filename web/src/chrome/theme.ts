/**
 * Chrome theme. Dark is the default rather than `prefers-color-scheme`: the default basemap
 * is dark, and a light rail framing a dark map is the incoherence VF-3 is already about.
 * The choice is an override, so it persists; it is not URL state, because app/state.ts is
 * a frozen file and a theme is a reader preference, not a view someone would share.
 */
export type Theme = "dark" | "light";

export const THEME_STORAGE_KEY = "glasswell.theme";

/** The production plot is a canvas: it cannot inherit a CSS variable, so it is told. */
export const THEME_EVENT = "gw:theme";

const NEXT: Record<Theme, Theme> = { dark: "light", light: "dark" };
const COPY: Record<Theme, { label: string; title: string }> = {
  dark: { label: "Light", title: "Switch to the light theme" },
  light: { label: "Dark", title: "Switch to the dark theme" },
};

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null; // A privacy-mode browser throws on access; a theme is not worth failing boot over.
  }
}

export function storedTheme(): Theme | null {
  let raw: string | null = null;
  try {
    raw = storage()?.getItem(THEME_STORAGE_KEY) ?? null;
  } catch {
    return null; // Same class as above: getItem itself can throw once storage is blocked.
  }
  return raw === "dark" || raw === "light" ? raw : null;
}

export function currentTheme(): Theme {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  document.dispatchEvent(new CustomEvent(THEME_EVENT, { detail: { theme } }));
  try {
    storage()?.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Quota or a blocked store: the attribute is applied either way, the choice just
    // does not survive a reload.
  }
}

export function mountThemeToggle(button: HTMLElement): void {
  function render(theme: Theme): void {
    button.setAttribute("aria-pressed", String(theme === "light"));
    // The control is labelled with the destination, not the current state.
    button.title = COPY[theme].title;
    const label = button.querySelector(".gw-ctl-lbl");
    if (label) label.textContent = COPY[theme].label;
  }

  const initial = storedTheme() ?? "dark";
  document.documentElement.dataset.theme = initial;
  render(initial);

  button.addEventListener("click", () => {
    const theme = NEXT[currentTheme()];
    applyTheme(theme);
    render(theme);
  });
}
