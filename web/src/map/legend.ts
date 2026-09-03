import { dispatchExplain, explainHandle, setExplainHandle } from "../chrome/handle.ts";
import { disclosure } from "../chrome/notes.ts";
import { labelElement } from "../glossary/gw-term.ts";
import { teach } from "../glossary/teach.ts";
import type { DimensionCounts, VocabularyLink } from "./counts.ts";
import { PRODUCING_CLASSES, PRODUCING_RULINGS, producingHref, producingNote } from "./producing.ts";
import type { ProducingCounts } from "./producing.ts";
import { PROVENANCE_RULE } from "./provenance.ts";
import { census, loadCensus, measuredWellCount } from "./census.ts";
import { JURISDICTION_LIST } from "./jurisdictions.generated.ts";
import { STATUS_CLASSES, STATUS_VOCAB_RULES, UNMAPPED_STATUS, statusClass } from "./status.ts";
import type { StatusClass } from "./status.ts";
import { statusSwatch } from "./swatch.ts";

const NUMBER = new Intl.NumberFormat("en-US");
/** Not auto-highlighted anywhere: "producing" is an ordinary word on a page full of wells. */
const PRODUCING_CLASS_TERM = "gt_producing_class";
const PENDING_MARK = "…";
const ABSENT_MARK = "—";
const FAULT_COPY = "Counts for this area could not be read.";
const UNMEASURED_COPY = "No jurisdiction has measured wells in this class yet.";
const PARTIAL_NOTE =
  "Status classes recede at low zoom and point tiles are thinned below zoom 8." +
  " The counts above are the data's, not the canvas's.";

/**
 * The other Wells-By scope, named once so the two surfaces read as two scopes of one question
 * rather than as two answers. The map sheet carries the mirror of this line.
 */
const CROSSREF_COPY =
  "These count the map view and move when you pan. Wells by counts a whole state and does not.";

/**
 * A dimension of the same box the status rows count, rendered as a read-out rather than as a
 * filter row. No swatch, for the reason .gw-lg-producing states: the map draws no colour for
 * these classes, and a swatch would promise one it does not.
 */
interface DimensionSpec {
  id: string;
  title: string;
  aria: string;
  /** What the numbers mean, and — because the two blocks do not share one — its zero rule. */
  note: string;
}

const DIMENSIONS: readonly DimensionSpec[] = [
  {
    id: "well_type",
    title: "Well type",
    aria: "Wells by the well type their source reported",
    note:
      "Codes exactly as the source filed them: no decode and no classing. A code the box does" +
      " not hold is absent here, not zero, which is the rule the status rows follow. A well" +
      " whose source filed no type is in no row at all while still counting in the total above.",
  },
  {
    id: "geometry_provenance",
    title: "Geometry provenance",
    aria: "Wells by the provenance of their recorded geometry",
    note:
      `Classed by ${PROVENANCE_RULE}, the class served verbatim. These classes overlap: one` +
      " well can hold a surface hole, a lateral and a survey trace at once, so they do not sum" +
      " to the well count above and no share can be read off them. A registered class the box" +
      " does not hold reads zero rather than absent, which is the producing rows' rule: the" +
      " vocabulary names the class whether or not this box holds one.",
  },
] as const;

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
  /**
   * The producing classes for the same box, or null where the definition is not registered.
   * A read-out with its own handles rather than a canvas filter: repainting needs the style
   * and the map wiring, which this change does not own — see work-output/wells-status.md.
   */
  setProducing(next: ProducingCounts | null): void;
  /** Reported well type codes for the same box; null where it holds no coded well. */
  setWellTypes(next: DimensionCounts | null): void;
  /** Geometry provenance classes for the same box; null where the jurisdiction serves none. */
  setProvenance(next: DimensionCounts | null): void;
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
  title.setAttribute("data-no-glossary", "");
  head.appendChild(title);

  // Hidden while the key is a pill: nine rows are what is being bulk-toggled, and a click
  // whose whole effect is off screen is worse than no affordance.
  const actions = document.createElement("div");
  actions.className = "gw-lg-actions";
  actions.hidden = true;
  actions.setAttribute("role", "group");
  actions.setAttribute("aria-label", "Show or hide every status class");
  actions.setAttribute("data-no-glossary", "");
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
  // The row is the checkbox's label; the scope line below carries the same words as prose.
  extentRow.setAttribute("data-no-glossary", "");

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

  const extentHandle = provenanceHandle("the well count");
  extentRow.appendChild(extentHandle);
  body.appendChild(extentRow);

  // The population statement the off state owes the reader: without it every count on the
  // key silently widens from the canvas to two basins.
  const scope = document.createElement("p");
  scope.className = "gw-lg-scope";
  scope.hidden = extentBox.checked;
  scope.textContent = "Counting every ingested well. The map view is not narrowing these numbers.";
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

  // Producing is asked of the filings, status of the permit, so the classes get their own
  // group rather than more rows in the status list — a well the regulator calls inactive can
  // be producing, and on the 2026-08 load 896 of them are.
  const producing = document.createElement("div");
  producing.className = "gw-lg-producing";
  producing.hidden = true;
  producing.setAttribute("role", "group");
  producing.setAttribute("aria-label", "Wells by whether they are producing");

  const producingTitle = document.createElement("p");
  producingTitle.className = "gw-lg-ptitle";
  producingTitle.appendChild(labelElement("Producing", PRODUCING_CLASS_TERM));
  producing.appendChild(producingTitle);

  const producingRows = new Map<string, HTMLElement>();
  for (const entry of PRODUCING_CLASSES) {
    const row = document.createElement("div");
    row.className = "gw-lg-prow";
    row.dataset["producing"] = entry.id;
    row.title = entry.note;

    const link = document.createElement("a");
    link.className = "gw-lg-label gw-lg-plink";
    link.textContent = entry.label;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.title = `List the ${entry.label.toLowerCase()} wells in this box`;
    row.appendChild(link);

    const cell = document.createElement("span");
    cell.className = "gw-lg-count";
    cell.textContent = ABSENT_MARK;
    row.appendChild(cell);

    row.appendChild(provenanceHandle(`the ${entry.label.toLowerCase()} count`));
    producingRows.set(entry.id, row);
    producing.appendChild(row);
  }

  const producingNoteEl = document.createElement("p");
  producingNoteEl.className = "gw-lg-pnote gw-scope";
  producing.appendChild(producingNoteEl);
  // The two standing rulings, folded: they qualify every producing count on every map and
  // used to cost the key two of its four lines to repeat on each open.
  producing.appendChild(disclosure("How this is judged", PRODUCING_RULINGS));
  body.appendChild(producing);

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

  // The only pointer from this key to the other surface, so nothing it says may depend on a
  // scroll position: outside the body, and outside the region below.
  const crossref = document.createElement("p");
  crossref.className = "gw-lg-crossref";
  crossref.hidden = true;
  crossref.textContent = CROSSREF_COPY;
  element.appendChild(crossref);

  // Under the scroll body rather than inside it, on the vocabulary's precedent below: put in the
  // body these two blocks added 575 px to a 384 px scrollport, so neither was reachable without
  // scrolling at any width (visual-map-wells-by D5). Out here each is a disclosure always in
  // frame, and the two share one scrollport; the key's own clamp is what keeps it on the map.
  const dims = document.createElement("div");
  dims.className = "gw-lg-dims";

  // Rows are data-driven — the codes are the source's, not a roster — so each block rebuilds its
  // rows when the served order changes and patches them in place otherwise, which is what keeps
  // a ⌾ from being torn out from under the pointer between two viewports holding the same classes.
  const dimensionBlocks = new Map<string, DimensionView>();
  for (const spec of DIMENSIONS) {
    const view = buildDimension(spec);
    dimensionBlocks.set(spec.id, view);
    dims.appendChild(view.element);
  }
  element.appendChild(dims);

  // Outside the scroll body (visual-m12/m13): the note's tail sat below the fold at every
  // breakpoint, so the vocabulary gets an always-in-frame disclosure of its own instead.
  const vocab = document.createElement("div");
  vocab.className = "gw-lg-vocab";
  const vocabTitle = document.createElement("button");
  vocabTitle.type = "button";
  vocabTitle.className = "gw-lg-vocab-title";
  vocabTitle.textContent = "Vocabulary";
  vocabTitle.setAttribute("aria-expanded", "false");
  vocabTitle.setAttribute("data-no-glossary", "");
  vocab.appendChild(vocabTitle);
  const note = document.createElement("p");
  note.className = "gw-lg-note";
  note.hidden = true;
  vocab.appendChild(note);
  element.appendChild(vocab);
  vocabTitle.addEventListener("click", () => {
    note.hidden = !note.hidden;
    vocabTitle.setAttribute("aria-expanded", String(!note.hidden));
  });

  // Built before boot resolves the glossary, and its rows are rebuilt per viewport, so the
  // key both waits for the index and re-runs the highlighter after every render.
  const teaching = teach(element);

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
    const scoped = extentBox.checked ? base : `${base} · everywhere`;
    // How many wells this is a key to, on the pill rather than one click inside it. It is the
    // first question asked of a map of dots and the only one that was answered by opening
    // something; the sum moves with the filter, so the pill can never overstate the canvas.
    title.textContent = shownWells() === null ? scoped : `${scoped} · ${shownWells()}`;
  }

  /**
   * The classes left on, summed. Null while the counts are pending or unavailable, and null
   * with every class off — the `0/9` already on the pill says that, and "· 0" beside it reads
   * as a count of the data rather than of what the reader switched off.
   */
  function shownWells(): string | null {
    if (mode !== "ready") return null;
    const rendered = [...rows].filter(([, row]) => row.parentNode === body);
    const on = rendered.filter(([, row]) => checked(row));
    if (on.length === 0) return null;
    // Unfiltered, the honest figure is the population's own — the same one the extent row
    // carries with its handle. Summing the class rows instead would silently drop a well the
    // box holds under no class this key lists.
    if (on.length === rendered.length) {
      const wells = totalCount?.wells;
      return wells === null || wells === undefined ? null : NUMBER.format(wells);
    }
    // Filtered, the sum is over exactly the classes left on. A class the box does not hold has
    // no count to report (see cellText) and contributes nothing rather than blocking the sum —
    // but a selection where none of them has a count at all is unknown, not zero.
    if (on.every(([id]) => counts[id] === undefined)) return null;
    return NUMBER.format(on.reduce((sum, [id]) => sum + (counts[id] ?? 0), 0));
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
    // Every row and every disclosure is a control, not the expand target. `.gw-lg-prow` and
    // `.gw-lg-drow` carry a ⌾, and asking where a number came from used to shut the key over
    // it and throw away the scroll position that reached it (visual-map-wells-by D6).
    if (
      (event.target as HTMLElement).closest(
        ".gw-lg-row, .gw-lg-prow, .gw-lg-extent, .gw-lg-actions, .gw-lg-vocab, .gw-lg-dims",
      )
    ) {
      return;
    }
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
  let producingCounts: ProducingCounts | null = null;
  const dimensionCounts = new Map<string, DimensionCounts | null>();

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
      if (handle) setExplainHandle(handle, derivation ?? null);
      // Owned here rather than set once by the census pass, and only on a measured zero: a
      // class the census carries no row for is unmeasured, and a row hidden for that reason
      // takes its own filter switch off the key with it.
      const measured = measuredWellCount(id);
      const unmeasured = measured === null && census().total !== null;
      row.hidden = measured === 0;
      if (unmeasured) row.setAttribute("data-unmeasured", "true");
      else row.removeAttribute("data-unmeasured");
      const outOfScale = zoomNow < status.minZoom;
      const box = row.querySelector<HTMLInputElement>("input");
      if (box) box.disabled = outOfScale;
      if (outOfScale) {
        row.setAttribute("data-out-of-scale", "true");
        row.title = `Zoom to ${status.minZoom} to see ${status.label.toLowerCase()} wells`;
      } else {
        row.removeAttribute("data-out-of-scale");
        row.title = unmeasured ? `${status.note} ${UNMEASURED_COPY}` : status.note;
      }
    }
    extentCount.textContent = extentCellText();
    const population = mode === "ready" ? (totalCount?.handle ?? null) : null;
    setExplainHandle(extentHandle, population);
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

  function renderProducing(): void {
    producing.hidden = producingCounts === null;
    if (!producingCounts) return;
    producingNoteEl.textContent = producingNote(producingCounts.window);
    for (const [id, row] of producingRows) {
      const count = producingCounts.counts[id];
      const cell = row.querySelector<HTMLElement>(".gw-lg-count");
      if (cell) cell.textContent = producingCellText(count);
      const link = row.querySelector<HTMLAnchorElement>("a");
      if (link) link.href = producingHref(id, producingCounts.bbox);
      const handle = row.querySelector<HTMLButtonElement>(".gw-lg-handle");
      const derivation = mode === "ready" ? producingCounts.handles[id] : undefined;
      if (handle) setExplainHandle(handle, derivation ?? null);
    }
  }

  function producingCellText(count: number | undefined): string {
    if (mode === "pending") return PENDING_MARK;
    if (mode === "unavailable") return ABSENT_MARK;
    // Absent, not zero: a class the box does not hold has no count to report.
    return count === undefined ? ABSENT_MARK : NUMBER.format(count);
  }

  function renderDimensions(): void {
    let anyShown = false;
    for (const [id, view] of dimensionBlocks) {
      const served = dimensionCounts.get(id) ?? null;
      view.element.hidden = served === null;
      if (served === null) continue;
      anyShown = true;
      view.setRows(served.order);
      for (const value of served.order) {
        const row = view.rows.get(value);
        const cell = row?.querySelector<HTMLElement>(".gw-lg-count");
        if (cell) cell.textContent = dimensionCellText(served.counts[value]);
        const handle = row?.querySelector<HTMLButtonElement>(".gw-lg-handle");
        const derivation = mode === "ready" ? served.handles[value] : undefined;
        if (handle) setExplainHandle(handle, derivation ?? null);
      }
    }
    crossref.hidden = !anyShown;
  }

  /** The same three readings the status cells have, so one key never mixes two vocabularies. */
  function dimensionCellText(count: number | undefined): string {
    if (mode === "pending") return PENDING_MARK;
    if (mode === "unavailable") return ABSENT_MARK;
    return count === undefined ? ABSENT_MARK : NUMBER.format(count);
  }

  function render(): void {
    renderRows();
    renderProducing();
    renderDimensions();
    renderPartial();
    teaching.retouch();
    // The pill carries a count now, so it is part of what a new viewport's numbers repaint —
    // without this it kept the sum from the box the reader has already panned away from.
    syncTitle();
  }

  function setVocabulary(vocabulary: VocabularyLink[]): void {
    // The licence pair opens the note, ahead even of the colours preamble (visual-m24 O2):
    // what each basin's wire carries must sit above the note's own fold on open at 390.
    note.replaceChildren(
      document.createTextNode(
        "Every ND feature carries its geometry provenance on the wire: surface, lateral" +
          ` or survey_trace, classed by ${PROVENANCE_RULE}, the class served verbatim.` +
          " TX geometry carries no provenance field: the RRC's coordinate-source attribute" +
          " is licence-gated (RF-1) and is not served until that is answered." +
          " Status colours are data colours, not severity colours. Vocabulary: ",
      ),
    );
    for (const [index, entry] of vocabulary.entries()) {
      if (index > 0) note.appendChild(document.createTextNode(", "));
      note.appendChild(ruleNode(entry));
    }
    note.appendChild(document.createTextNode("."));
    // Registration data, so no state is named here; scoped to the rules this view was classed
    // by and placed above the symbology clauses, because an unscoped tail states one basin's
    // decoding rule over another and does it below the note's own fold.
    const inView = new Set(vocabulary.map((entry) => entry.rule));
    for (const entry of JURISDICTION_LIST) {
      if (!entry.legendNote) continue;
      if (!inView.has(entry.rules["status_vocabulary"] ?? "")) continue;
      note.appendChild(document.createTextNode(` ${entry.legendNote}`));
    }
    note.appendChild(
      document.createTextNode(
        " Laterals are ND DMR and TX RRC GIS bore geometry, not a directional survey trace." +
          " The orchid line is that trace: the bore path ND filed as survey stations." +
          " The teal ring is NDIC's own well_type: disposal and injection wells of any" +
          " injected stream, classed by cr_nd_well_type_disposal_1, the code drawn as filed.",
      ),
    );
    teaching.retouch();
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
    // Among the status rows, not after the producing group: it is one of the classes the
    // canvas paints, and listed below a different vocabulary it lands outside the key's own
    // scrollport — reachable only by scrolling past a block that answers another question.
    if (counts[UNMAPPED_STATUS.id] !== undefined && unmapped && unmapped.parentNode !== body) {
      body.insertBefore(unmapped, producing);
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
  // What the legend may list used to be four undated count maps compiled into the bundle. It
  // is a served measurement now, and the writer measures every registered class rather than
  // only the ones it finds, so a zero here is a jurisdiction that was counted and holds none —
  // a class at zero everywhere has never been drawn, and listing it would promise a colour the
  // canvas cannot produce. A class the census does not carry was not measured (a ledger day
  // written before that writer, which is every day before v0.77) and keeps its row. The census
  // only arrives here; what it means for a row is renderRows's, so no stale `hidden` survives
  // a viewport and no row is hidden by a census that never came.
  void loadCensus().then(render);
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
    // Each of these builds rows the render cycle has already been through, so each retouches:
    // a value the served order introduced is otherwise left unlit until the next viewport.
    setProducing(next) {
      producingCounts = next;
      renderProducing();
      teaching.retouch();
    },
    setWellTypes(next) {
      dimensionCounts.set("well_type", next);
      renderDimensions();
      teaching.retouch();
    },
    setProvenance(next) {
      dimensionCounts.set("geometry_provenance", next);
      renderDimensions();
      teaching.retouch();
    },
  };
}

interface DimensionView {
  element: HTMLElement;
  rows: Map<string, HTMLElement>;
  /** Rebuilds only when the served order changes; otherwise the existing rows are kept. */
  setRows(order: readonly string[]): void;
}

function buildDimension(spec: DimensionSpec): DimensionView {
  const element = document.createElement("div");
  element.className = "gw-lg-dim";
  element.dataset["dimension"] = spec.id;
  element.hidden = true;
  element.setAttribute("role", "group");
  element.setAttribute("aria-label", spec.aria);

  // Shut by default, like the vocabulary: the block's name is what has to be in frame, and its
  // rows and its note together are 240-290 px the key cannot hold open beside the status list.
  const title = document.createElement("button");
  title.type = "button";
  title.className = "gw-lg-dtitle";
  title.textContent = spec.title;
  title.setAttribute("aria-expanded", "false");
  title.setAttribute("data-no-glossary", "");
  element.appendChild(title);

  const opened = document.createElement("div");
  opened.className = "gw-lg-dbody";
  opened.hidden = true;
  element.appendChild(opened);
  title.addEventListener("click", () => {
    opened.hidden = !opened.hidden;
    title.setAttribute("aria-expanded", String(!opened.hidden));
  });

  const list = document.createElement("div");
  list.className = "gw-lg-drows";
  opened.appendChild(list);

  const note = document.createElement("p");
  note.className = "gw-lg-dnote";
  note.textContent = spec.note;
  opened.appendChild(note);

  const rows = new Map<string, HTMLElement>();
  let built: string[] = [];

  return {
    element,
    rows,
    setRows(order) {
      if (built.length === order.length && built.every((value, at) => value === order[at])) return;
      built = [...order];
      rows.clear();
      list.replaceChildren(
        ...order.map((value) => {
          const row = dimensionRow(value);
          rows.set(value, row);
          return row;
        }),
      );
    },
  };
}

/** Value, count, handle — the status row's anatomy without the checkbox and without the swatch. */
function dimensionRow(value: string): HTMLElement {
  const row = document.createElement("div");
  row.className = "gw-lg-drow";
  row.dataset["value"] = value;
  row.title = value;

  const label = document.createElement("span");
  label.className = "gw-lg-label";
  label.textContent = value;
  row.appendChild(label);

  const count = document.createElement("span");
  count.className = "gw-lg-count";
  count.textContent = ABSENT_MARK;
  row.appendChild(count);

  row.appendChild(provenanceHandle(`the ${value} count`));
  return row;
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
  // The whole row toggles its class; the vocabulary note below teaches the same words.
  row.setAttribute("data-no-glossary", "");

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

  row.appendChild(provenanceHandle(`the ${status.label.toLowerCase()} count`));
  return row;
}

/** `label` is the figure's name alone — `explainHandle` supplies the "Lineage for" prefix. */
function provenanceHandle(label: string): HTMLButtonElement {
  const handle = explainHandle({
    className: "gw-lg-handle",
    label,
    activate: (derivation, event) => {
      // Inside a <label>: without this the browser forwards the activation to the checkbox, and
      // asking where a number came from would switch its class off. happy-dom does not implement
      // that forwarding, so legend.test.ts pins the cancellation rather than the toggle.
      event.preventDefault();
      dispatchExplain(handle, derivation);
    },
  });
  return handle;
}
