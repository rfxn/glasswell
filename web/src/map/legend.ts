import { STATUS_CLASSES, STATUS_VOCAB_RULE, UNMAPPED_STATUS, statusClass } from "./status.ts";
import type { StatusClass } from "./status.ts";
import { statusSwatch } from "./swatch.ts";

const NUMBER = new Intl.NumberFormat("en-US");

export interface LegendOptions {
  onFilter(on: Set<string>): void;
}

/**
 * `?legend=0` takes the key off the canvas for an embed or a screenshot. Only that exact
 * value suppresses it: the panel carries the status vocabulary and the geometry-provenance
 * line, so a value nobody defined leaves it standing rather than guessing at intent.
 */
export function legendEnabled(search: string): boolean {
  return new URLSearchParams(search).get("legend") !== "0";
}

export interface LegendHandle {
  element: HTMLElement;
  /** Counts come from what is actually drawn, so the key can never describe an absent class. */
  setCounts(counts: Record<string, number>, zoom: number): void;
  activeStatuses(): Set<string>;
}

/**
 * The key is also the filter. Every row carries its own swatch, its own live count and its
 * own checkbox, so there is no state the map can be in that the legend cannot describe and
 * the reader cannot reach.
 */
export function createLegend(options: LegendOptions): LegendHandle {
  const element = document.createElement("div");
  element.className = "gw-lg";

  const title = document.createElement("button");
  title.type = "button";
  title.className = "gw-lg-title";
  title.textContent = "Well status";
  title.setAttribute("aria-expanded", "false");
  element.appendChild(title);

  const body = document.createElement("div");
  body.className = "gw-lg-body";
  element.appendChild(body);

  const rows = new Map<string, HTMLElement>();
  for (const status of STATUS_CLASSES) rows.set(status.id, appendRow(body, status));

  const note = document.createElement("p");
  note.className = "gw-lg-note";
  note.textContent =
    `Status colours are data colours, not severity colours. Vocabulary: ${STATUS_VOCAB_RULE}.` +
    " Laterals are ND DMR GIS bore geometry — not a directional survey trace.";
  body.appendChild(note);

  const activeStatuses = (): Set<string> => {
    const on = new Set<string>();
    for (const [id, row] of rows) {
      if (id === UNMAPPED_STATUS.id) continue;
      if (row.querySelector<HTMLInputElement>("input")?.checked) on.add(id);
    }
    return on;
  };

  element.addEventListener("click", (event) => {
    // A filter row is a control, not the expand target.
    if ((event.target as HTMLElement).closest(".gw-lg-row")) return;
    const open = element.classList.toggle("gw-open");
    title.setAttribute("aria-expanded", String(open));
  });

  element.addEventListener("change", (event) => {
    if (!(event.target as HTMLElement).closest(".gw-lg-row")) return;
    options.onFilter(activeStatuses());
  });

  function setCounts(counts: Record<string, number>, zoom: number): void {
    if (counts[UNMAPPED_STATUS.id] !== undefined && !rows.has(UNMAPPED_STATUS.id)) {
      rows.set(UNMAPPED_STATUS.id, body.insertBefore(buildRow(UNMAPPED_STATUS), note));
    }
    for (const [id, row] of rows) {
      const status = statusClass(id);
      const count = counts[id];
      const cell = row.querySelector<HTMLElement>(".gw-lg-count");
      // Patched in place: replacing the markup would tear the checkbox out from under
      // the pointer mid-click, and reset the row's focus.
      if (cell) cell.textContent = count === undefined ? "—" : NUMBER.format(count);
      const outOfScale = zoom < status.minZoom;
      const box = row.querySelector<HTMLInputElement>("input");
      if (box) box.disabled = outOfScale || id === UNMAPPED_STATUS.id;
      if (outOfScale) {
        row.setAttribute("data-out-of-scale", "true");
        row.title = `Zoom to ${status.minZoom} to see ${status.label.toLowerCase()} wells`;
      } else {
        row.removeAttribute("data-out-of-scale");
        row.title = status.note;
      }
    }
  }

  return { element, setCounts, activeStatuses };
}

function appendRow(body: HTMLElement, status: StatusClass): HTMLElement {
  const row = buildRow(status);
  body.appendChild(row);
  return row;
}

function buildRow(status: StatusClass): HTMLElement {
  const row = document.createElement("label");
  row.className = "gw-lg-row";
  row.dataset["status"] = status.id;
  row.title = status.note;

  const box = document.createElement("input");
  box.type = "checkbox";
  box.checked = true;
  box.disabled = status.id === UNMAPPED_STATUS.id;
  box.setAttribute("aria-label", `Show ${status.label} wells`);
  row.appendChild(box);

  const swatch = document.createElement("span");
  swatch.className = "gw-lg-swatch";
  swatch.appendChild(statusSwatch(status.colour, status.glyph));
  row.appendChild(swatch);

  const label = document.createElement("span");
  label.className = "gw-lg-label";
  label.textContent = status.label;
  row.appendChild(label);

  const count = document.createElement("span");
  count.className = "gw-lg-count";
  count.textContent = "—";
  row.appendChild(count);
  return row;
}
