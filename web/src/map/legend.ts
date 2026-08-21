import { STATUS_CLASSES, STATUS_VOCAB_RULES, UNMAPPED_STATUS, statusClass } from "./status.ts";
import type { StatusClass } from "./status.ts";
import { statusSwatch } from "./swatch.ts";

const NUMBER = new Intl.NumberFormat("en-US");

export interface LegendOptions {
  /** The classes to open with; absent means every one of them. */
  on?: ReadonlySet<string>;
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

  const head = document.createElement("div");
  head.className = "gw-lg-head";
  element.appendChild(head);

  const title = document.createElement("button");
  title.type = "button";
  title.className = "gw-lg-title";
  title.textContent = "Well status";
  title.setAttribute("aria-expanded", "false");
  head.appendChild(title);

  // Hidden while the key is a pill: nine rows are what is being bulk-toggled, and a click
  // whose whole effect is off screen is worse than no affordance.
  const actions = document.createElement("div");
  actions.className = "gw-lg-actions";
  actions.hidden = true;
  actions.setAttribute("role", "group");
  actions.setAttribute("aria-label", "Show or hide every status class");
  const all = bulkButton("all", "All", "Show every status class");
  const none = bulkButton("none", "None", "Hide every status class");
  actions.append(all, none);
  head.appendChild(actions);

  const body = document.createElement("div");
  body.className = "gw-lg-body";
  element.appendChild(body);

  const rows = new Map<string, HTMLElement>();
  for (const status of STATUS_CLASSES) {
    rows.set(status.id, appendRow(body, status, options.on?.has(status.id) ?? true));
  }

  const note = document.createElement("p");
  note.className = "gw-lg-note";
  note.textContent =
    "Status colours are data colours, not severity colours. Vocabulary: " +
    `${STATUS_VOCAB_RULES.join(", ")}.` +
    " Laterals are regulator GIS bore geometry — not a directional survey trace.";
  body.appendChild(note);

  const activeStatuses = (): Set<string> => {
    const on = new Set<string>();
    for (const [id, row] of rows) {
      if (id === UNMAPPED_STATUS.id) continue;
      if (row.querySelector<HTMLInputElement>("input")?.checked) on.add(id);
    }
    return on;
  };

  /**
   * Collapsed, the key is a pill with no rows on it — and with the filter now surviving a
   * reload, a reader can arrive at a map missing classes with nothing on the canvas saying
   * so. The count is that statement, and it is why the pill is not silent about a filter.
   */
  function syncTitle(): void {
    const count = activeStatuses().size;
    const total = STATUS_CLASSES.length;
    title.textContent = count === total ? "Well status" : `Well status · ${count}/${total}`;
  }

  const report = (): void => {
    syncTitle();
    options.onFilter(activeStatuses());
  };

  /**
   * The bulk control owns `checked` and nothing else. `disabled` and the out-of-scale mark
   * belong to setCounts, so "All" cannot promote a class the zoom has withdrawn; and a class
   * the zoom has withdrawn is still cleared by "None", so zooming in does not resurrect what
   * the reader dismissed.
   */
  function setAll(next: boolean): void {
    for (const [id, row] of rows) {
      if (id === UNMAPPED_STATUS.id) continue;
      const box = row.querySelector<HTMLInputElement>("input");
      if (box) box.checked = next;
    }
    report();
  }

  all.addEventListener("click", () => setAll(true));
  none.addEventListener("click", () => setAll(false));

  element.addEventListener("click", (event) => {
    // A filter row and the bulk control are controls, not the expand target.
    if ((event.target as HTMLElement).closest(".gw-lg-row, .gw-lg-actions")) return;
    const open = element.classList.toggle("gw-open");
    title.setAttribute("aria-expanded", String(open));
    actions.hidden = !open;
  });

  element.addEventListener("change", (event) => {
    if (!(event.target as HTMLElement).closest(".gw-lg-row")) return;
    report();
  });

  function setCounts(counts: Record<string, number>, zoom: number): void {
    if (counts[UNMAPPED_STATUS.id] !== undefined && !rows.has(UNMAPPED_STATUS.id)) {
      rows.set(UNMAPPED_STATUS.id, body.insertBefore(buildRow(UNMAPPED_STATUS, true), note));
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

  syncTitle();
  return { element, setCounts, activeStatuses };
}

function bulkButton(which: string, label: string, description: string): HTMLButtonElement {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `gw-lg-bulk gw-lg-${which}`;
  button.textContent = label;
  button.setAttribute("aria-label", description);
  return button;
}

function appendRow(body: HTMLElement, status: StatusClass, on: boolean): HTMLElement {
  const row = buildRow(status, on);
  body.appendChild(row);
  return row;
}

function buildRow(status: StatusClass, on: boolean): HTMLElement {
  const row = document.createElement("label");
  row.className = "gw-lg-row";
  row.dataset["status"] = status.id;
  row.title = status.note;

  const box = document.createElement("input");
  box.type = "checkbox";
  box.checked = on;
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
