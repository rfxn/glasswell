import { statusClass } from "./status.ts";
import { statusSwatch } from "./swatch.ts";

export interface HoverCardHandle {
  element: HTMLElement;
  show(properties: Record<string, unknown>, point: { x: number; y: number }): void;
  hide(): void;
}

/**
 * Hover identifies, click inspects. Everything shown here is already in the tile, so a
 * hover costs one lookup — never a request, and never the full card.
 */
export function createHoverCard(): HoverCardHandle {
  const element = document.createElement("div");
  element.className = "gw-hover";
  element.hidden = true;
  element.setAttribute("aria-hidden", "true");

  const name = document.createElement("p");
  name.className = "gw-hover-name";
  element.appendChild(name);

  const meta = document.createElement("p");
  meta.className = "gw-hover-meta";
  element.appendChild(meta);

  return {
    element,
    show(properties, point) {
      const api10 = String(properties["api10"] ?? "");
      const wellName = String(properties["well_name"] ?? "").trim();
      const status = statusClass(properties["status_canonical"] as string | undefined);
      name.textContent = wellName || api10;
      meta.replaceChildren(statusSwatch(status.colour, status.glyph, 11));
      // The tile carries no well name today, so repeating the api10 under itself would be
      // the only thing this line said.
      meta.appendChild(document.createTextNode(wellName ? ` ${status.label} · ${api10}` : ` ${status.label}`));
      element.style.transform = `translate(${point.x + 14}px, ${point.y + 14}px)`;
      element.hidden = false;
    },
    hide() {
      element.hidden = true;
    },
  };
}
