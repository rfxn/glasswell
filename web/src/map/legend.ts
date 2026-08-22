import { EXPLAIN_EVENT } from "../card/gw-figure.ts";
import type { VocabularyLink } from "./counts.ts";
import { PROVENANCE_RULE } from "./provenance.ts";
import { STATUS_CLASSES, STATUS_VOCAB_RULES, UNMAPPED_STATUS, statusClass } from "./status.ts";
import type { StatusClass } from "./status.ts";
import { statusSwatch } from "./swatch.ts";

const NUMBER = new Intl.NumberFormat("en-US");
const PENDING_MARK = "…";
const ABSENT_MARK = "—";
const FAULT_COPY = "Counts for this area could not be read.";
const PARTIAL_NOTE =
  "Status classes recede at low zoom and point tiles are thinned below zoom 8." +
  " The counts above are the data's, not the canvas's.";

/** What the count cells are allowed to say. Never the last viewport's numbers. */
type CountMode = "ready" | "pending" | "unavailable";

export interface LegendOptions {
  /** The classes to open with; absent means every one of them. */
  on?: ReadonlySet<string>;
  onFilter(on: Set<string>): void;
  /** Whether the map-extent node opens on. Absent means on: counts cover the viewport. */
  extentOn?: boolean;
  onExtent?(on: boolean): void;
}

/** The counted population's own figure, kept beside the per-class counts it is the sum over. */
export interface TotalCount {
  wells: number | null;
  handle: string | null;
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
  /** The wells the box holds, from `/v1/wells/status-summary` — not from what was drawn. */
  setCounts(
    counts: Record<string, number>,
    zoom: number,
    handles?: Record<string, string>,
    total?: TotalCount,
  ): void;
  /** A request is out for the current viewport; the previous one's numbers are gone. */
  setPending(zoom: number): void;
  /** No count could be had. Every cell reads absent, and the key says why. */
  setUnavailable(zoom: number): void;
  /** How many features the canvas actually drew, or null when there is no census to make. */
  setDrawn(drawn: number | null): void;
  /** The conformance rules that classed this answer (R8). */
  setVocabulary(rules: VocabularyLink[]): void;
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

  const wanted = (id: string): boolean => options.on?.has(id) ?? true;

  // M1-2: the viewport as a named node in the filter list, above the classes it conjoins
  // with. Ahead of them because it is the outer predicate — the population the class counts
  // are of — and a tree reads root-first.
  const extentRow = document.createElement("label");
  extentRow.className = "gw-lg-extent";

  const extentBox = document.createElement("input");
  extentBox.type = "checkbox";
  extentBox.checked = options.extentOn ?? true;
  // State-aware, not static (gate-m12 F2): the on-state sentence is false while the node is off.
  const syncExtentTitle = (): void => {
    extentRow.title = extentBox.checked
      ? "Counts cover the wells the map view holds. Untick to count everything ingested."
      : "Counts cover everything ingested. Tick to count only the wells the map view holds.";
  };
  syncExtentTitle();
  extentBox.setAttribute("aria-label", "Count only the wells the map view holds");
  extentRow.appendChild(extentBox);

  const extentLabel = document.createElement("span");
  extentLabel.className = "gw-lg-label";
  extentLabel.textContent = "Map view";
  extentRow.appendChild(extentLabel);

  const extentCount = document.createElement("span");
  extentCount.className = "gw-lg-count";
  extentCount.textContent = ABSENT_MARK;
  extentRow.appendChild(extentCount);

  const extentHandle = provenanceHandle("Lineage for the well count");
  extentRow.appendChild(extentHandle);
  body.appendChild(extentRow);

  // The population statement the off state owes the reader: without it every count on the
  // key silently widens from the canvas to two basins.
  const scope = document.createElement("p");
  scope.className = "gw-lg-scope";
  scope.hidden = extentBox.checked;
  scope.textContent = "Counting every ingested well — the map view is not narrowing these numbers.";
  body.appendChild(scope);

  // The joins, visible (M1-2): the extent node is ANDed with the status predicate, and the
  // status rows underneath are one disjunction, not ten conjuncts.
  const join = document.createElement("p");
  join.className = "gw-lg-join";
  join.textContent = "and · any of";
  join.title = "A counted well is inside the map view (while it is on) and carries any status left ticked.";
  body.appendChild(join);

  const rows = new Map<string, HTMLElement>();
  for (const status of STATUS_CLASSES) {
    rows.set(status.id, appendRow(body, status, wanted(status.id)));
  }
  // Built now, listed when the map first draws one. The switch has to exist before the class
  // does — a row conjured out of a count could not be the row that switches the count off.
  rows.set(UNMAPPED_STATUS.id, buildRow(UNMAPPED_STATUS, wanted(UNMAPPED_STATUS.id)));

  // Between the rows and the note: the canvas is a subset of the box at low zoom, and the
  // reader has to be able to see that without reading it as the counts disagreeing.
  const partial = document.createElement("p");
  partial.className = "gw-lg-partial";
  partial.hidden = true;
  partial.title = PARTIAL_NOTE;
  body.appendChild(partial);

  const fault = document.createElement("p");
  fault.className = "gw-lg-fault";
  fault.hidden = true;
  fault.setAttribute("role", "status");
  body.appendChild(fault);

  const note = document.createElement("p");
  note.className = "gw-lg-note";
  body.appendChild(note);

  const checked = (row: HTMLElement): boolean =>
    row.querySelector<HTMLInputElement>("input")?.checked === true;

  /** The rows the reader can see. A row the key has not listed is not part of what it claims. */
  const listed = (): HTMLElement[] => [...rows.values()].filter((row) => row.parentNode === body);

  const activeStatuses = (): Set<string> => {
    const on = new Set<string>();
    for (const [id, row] of rows) if (checked(row)) on.add(id);
    return on;
  };

  /**
   * Collapsed, the key is a pill with no rows on it — and with the filter now surviving a
   * reload, a reader can arrive at a map missing classes with nothing on the canvas saying
   * so. The count is that statement, and it is why the pill is not silent about a filter.
   * The extent node gets the same disclosure: a collapsed key over counts that cover two
   * basins rather than the canvas must say so on the pill.
   */
  function syncTitle(): void {
    const rendered = listed();
    const count = rendered.filter(checked).length;
    const base =
      count === rendered.length ? "Well status" : `Well status · ${count}/${rendered.length}`;
    title.textContent = extentBox.checked ? base : `${base} · everywhere`;
  }

  const report = (): void => {
    syncTitle();
    // The filter moves what is drawn, so the drawn-versus-in-view line has to move with it.
    renderPartial();
    options.onFilter(activeStatuses());
  };

  /**
   * The bulk control owns `checked` and nothing else. `disabled` and the out-of-scale mark
   * belong to setCounts, so "All" cannot promote a class the zoom has withdrawn; and a class
   * the zoom has withdrawn is still cleared by "None", so zooming in does not resurrect what
   * the reader dismissed.
   */
  function setAll(next: boolean): void {
    for (const row of rows.values()) {
      const box = row.querySelector<HTMLInputElement>("input");
      if (box) box.checked = next;
    }
    report();
  }

  all.addEventListener("click", () => setAll(true));
  none.addEventListener("click", () => setAll(false));

  element.addEventListener("click", (event) => {
    // A filter row and the bulk control are controls, not the expand target.
    if ((event.target as HTMLElement).closest(".gw-lg-row, .gw-lg-extent, .gw-lg-actions")) return;
    const open = element.classList.toggle("gw-open");
    title.setAttribute("aria-expanded", String(open));
    actions.hidden = !open;
  });

  element.addEventListener("change", (event) => {
    if (!(event.target as HTMLElement).closest(".gw-lg-row")) return;
    report();
  });

  extentBox.addEventListener("change", () => {
    scope.hidden = extentBox.checked;
    syncExtentTitle();
    syncTitle();
    // The drawn-versus-in-view line compares the canvas with the counted population; with the
    // node off the population is not "in view" and the comparison would be a false sentence.
    renderPartial();
    options.onExtent?.(extentBox.checked);
  });

  let mode: CountMode = "ready";
  let counts: Record<string, number> = {};
  let handles: Record<string, string> = {};
  let totalCount: TotalCount | null = null;
  let drawn: number | null = null;
  let zoomNow = 0;

  function cellText(id: string): string {
    if (mode === "pending") return PENDING_MARK;
    if (mode === "unavailable") return ABSENT_MARK;
    const count = counts[id];
    // Absent, not zero: a class the box does not hold has no count to report.
    return count === undefined ? ABSENT_MARK : NUMBER.format(count);
  }

  function extentCellText(): string {
    if (mode === "pending") return PENDING_MARK;
    if (mode === "unavailable") return ABSENT_MARK;
    const wells = totalCount?.wells;
    return wells === null || wells === undefined ? ABSENT_MARK : NUMBER.format(wells);
  }

  function renderRows(): void {
    element.dataset["counts"] = mode;
    body.setAttribute("aria-busy", String(mode === "pending"));
    for (const [id, row] of rows) {
      const status = statusClass(id);
      const cell = row.querySelector<HTMLElement>(".gw-lg-count");
      // Patched in place: replacing the markup would tear the checkbox out from under
      // the pointer mid-click, and reset the row's focus.
      if (cell) cell.textContent = cellText(id);
      const handle = row.querySelector<HTMLButtonElement>(".gw-lg-handle");
      const derivation = mode === "ready" ? handles[id] : undefined;
      if (handle) {
        handle.hidden = derivation === undefined;
        handle.dataset["handle"] = derivation ?? "";
        handle.title = derivation ? `Show where this count came from: ${derivation}` : "";
      }
      const outOfScale = zoomNow < status.minZoom;
      const box = row.querySelector<HTMLInputElement>("input");
      if (box) box.disabled = outOfScale;
      if (outOfScale) {
        row.setAttribute("data-out-of-scale", "true");
        row.title = `Zoom to ${status.minZoom} to see ${status.label.toLowerCase()} wells`;
      } else {
        row.removeAttribute("data-out-of-scale");
        row.title = status.note;
      }
    }
    extentCount.textContent = extentCellText();
    const population = mode === "ready" ? (totalCount?.handle ?? null) : null;
    extentHandle.hidden = population === null;
    extentHandle.dataset["handle"] = population ?? "";
    extentHandle.title = population ? `Show where this count came from: ${population}` : "";
    fault.hidden = mode !== "unavailable";
    fault.textContent = mode === "unavailable" ? FAULT_COPY : "";
  }

  /**
   * "Showing X of Y" (MAP-ROADMAP M1-1), stated only where it is true: X is a census of the
   * canvas, Y is the box's own count of the classes the reader has left on. Filtering a class
   * off lowers Y with X, so a filter never reads as a shortfall.
   */
  function renderPartial(): void {
    const inView = [...rows]
      .filter(([, row]) => checked(row))
      .reduce((sum, [id]) => sum + (counts[id] ?? 0), 0);
    // With the extent node off, the counts are not "in view" and the comparison with the
    // canvas would be false on its face; the scope line above carries the statement instead.
    if (!extentBox.checked || mode !== "ready" || drawn === null || inView === 0 || drawn >= inView) {
      partial.hidden = true;
      partial.textContent = "";
      return;
    }
    partial.hidden = false;
    partial.textContent = `Showing ${NUMBER.format(drawn)} of ${NUMBER.format(inView)} in view`;
  }

  function render(): void {
    renderRows();
    renderPartial();
  }

  function setVocabulary(vocabulary: VocabularyLink[]): void {
    note.replaceChildren(
      document.createTextNode("Status colours are data colours, not severity colours. Vocabulary: "),
    );
    for (const [index, entry] of vocabulary.entries()) {
      if (index > 0) note.appendChild(document.createTextNode(", "));
      note.appendChild(ruleNode(entry));
    }
    note.appendChild(
      document.createTextNode(
        ". Laterals are ND DMR and TX RRC GIS bore geometry — not a directional survey trace." +
          " The orchid line is that trace: the bore path ND filed as survey stations." +
          " The teal ring is NDIC's own well_type — disposal and injection wells of any" +
          " injected stream, classed by cr_nd_well_type_disposal_1, the code drawn as filed." +
          " Every ND feature carries its geometry provenance on the wire — surface, lateral" +
          ` or survey_trace, classed by ${PROVENANCE_RULE}, the class served verbatim.` +
          " TX geometry carries no provenance field: the RRC's coordinate-source attribute" +
          " is licence-gated (RF-1) and is not served until that is answered.",
      ),
    );
  }

  function setCounts(
    next: Record<string, number>,
    zoom: number,
    derivations?: Record<string, string>,
    total?: TotalCount,
  ): void {
    mode = "ready";
    counts = next;
    handles = derivations ?? {};
    totalCount = total ?? null;
    zoomNow = zoom;
    const unmapped = rows.get(UNMAPPED_STATUS.id);
    if (counts[UNMAPPED_STATUS.id] !== undefined && unmapped && unmapped.parentNode !== body) {
      body.insertBefore(unmapped, partial);
      syncTitle();
    }
    render();
  }

  /** The previous viewport's numbers are dropped, not dimmed: they are no longer an answer. */
  function withdraw(next: CountMode, zoom: number): void {
    mode = next;
    counts = {};
    handles = {};
    totalCount = null;
    zoomNow = zoom;
    render();
  }

  setVocabulary(STATUS_VOCAB_RULES.map((rule) => ({ rule, href: null })));
  syncTitle();
  render();
  return {
    element,
    setCounts,
    setPending: (zoom) => withdraw("pending", zoom),
    setUnavailable: (zoom) => withdraw("unavailable", zoom),
    setDrawn(next) {
      drawn = next;
      renderPartial();
    },
    setVocabulary,
    activeStatuses,
  };
}

/** A rule the response linked is a row a reader can open; one it did not is still named. */
function ruleNode(entry: VocabularyLink): Node {
  if (!entry.href) return document.createTextNode(entry.rule);
  const link = document.createElement("a");
  link.className = "gw-lg-rule";
  link.href = entry.href;
  link.target = "_blank";
  link.rel = "noreferrer";
  link.textContent = entry.rule;
  link.title = `Open ${entry.rule} in the conformance register`;
  return link;
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
  count.textContent = ABSENT_MARK;
  row.appendChild(count);

  row.appendChild(provenanceHandle(`Lineage for the ${status.label} count`));
  return row;
}

/**
 * The count is a served figure, so it carries the app's own provenance affordance and raises
 * the one event main.ts already opens the drawer on.
 */
function provenanceHandle(description: string): HTMLButtonElement {
  const handle = document.createElement("button");
  handle.type = "button";
  handle.className = "gw-handle gw-lg-handle";
  handle.hidden = true;
  handle.textContent = "⌾";
  handle.setAttribute("aria-label", description);
  handle.addEventListener("click", (event) => {
    // Inside a <label>: without this the browser forwards the activation to the checkbox, and
    // asking where a number came from would switch its class off. happy-dom does not implement
    // that forwarding, so legend.test.ts pins the cancellation rather than the toggle.
    event.preventDefault();
    const derivation = handle.dataset["handle"];
    if (derivation) {
      handle.dispatchEvent(
        new CustomEvent(EXPLAIN_EVENT, { detail: { handle: derivation }, bubbles: true }),
      );
    }
  });
  return handle;
}
