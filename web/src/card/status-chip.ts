import { labelElement } from "../glossary/gw-term.ts";
import { statusClass } from "../map/status.ts";
import { statusSwatch } from "../map/swatch.ts";
import type { WellDetail } from "./card.ts";

/**
 * Its own module so the card can reach it dynamically. The status vocabulary and the glyph live
 * under `src/map/`, and a static edge would put both on every reader's entry chunk and on the
 * explorer route, where no well card is ever rendered.
 */
export function fillStatusChip(chip: HTMLElement, detail: WellDetail, termId: string | null): void {
  const status = statusClass(detail.status_canonical);
  chip.dataset["status"] = status.id;
  chip.title = status.note;
  chip.appendChild(statusSwatch(status.colour, status.glyph, 12));
  const label = document.createElement("span");
  label.className = "gw-card-status-label";
  label.appendChild(labelElement(status.label, termId));
  chip.appendChild(label);
  // The class the app serves and the code the regulator filed, together: the card showed only
  // the class, which hid the mapping rather than making it readable.
  if (detail.status_reported) {
    const reported = document.createElement("span");
    reported.className = "gw-card-status-reported";
    reported.setAttribute("data-no-glossary", "");
    reported.textContent = `filed ${detail.status_reported}`;
    chip.appendChild(reported);
  }
  chip.hidden = false;
}
