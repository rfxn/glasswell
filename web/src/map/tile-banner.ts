export interface TileBannerHandle {
  element: HTMLElement;
  report(source: string, fellBackTo?: string): void;
}

/**
 * A basemap that fails silently looks identical to a basemap that was never configured.
 * One line per failing source, named, with the substitution stated if one was made.
 */
export function createTileBanner(): TileBannerHandle {
  const element = document.createElement("div");
  element.className = "gw-banner";
  element.hidden = true;
  element.setAttribute("role", "status");

  const lines = document.createElement("div");
  lines.className = "gw-banner-lines";
  element.appendChild(lines);

  const dismiss = document.createElement("button");
  dismiss.type = "button";
  dismiss.className = "gw-banner-x";
  dismiss.textContent = "✕";
  dismiss.setAttribute("aria-label", "Dismiss");
  element.appendChild(dismiss);

  const seen = new Map<string, HTMLElement>();
  let dismissed = false;
  dismiss.addEventListener("click", () => {
    dismissed = true;
    element.hidden = true;
  });

  return {
    element,
    report(source, fellBackTo) {
      const text = fellBackTo
        ? `Tiles for ${source} did not load — showing ${fellBackTo} instead.`
        : `Tiles for ${source} did not load.`;
      const existing = seen.get(source);
      if (existing) {
        existing.textContent = text;
      } else {
        const line = document.createElement("p");
        line.className = "gw-banner-line";
        line.textContent = text;
        lines.appendChild(line);
        seen.set(source, line);
      }
      if (!dismissed) element.hidden = false;
    },
  };
}
