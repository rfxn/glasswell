import "./wells-by.css";

import { ApiError, getEnvelope } from "../../api/client.ts";
import type { Figure, Warning } from "../../api/envelope.ts";
import type { AppState } from "../../app/state.ts";
import { warningNotes } from "../../chrome/notes.ts";
import { DEFAULT_JURISDICTION } from "../../map/jurisdictions.generated.ts";
import "../../card/gw-figure.ts";

/** §4.1: the panel rides the URL, so a shared link opens the list the sharer was reading. */
export const WELLS_BY_PREFIX = "wb.";

/**
 * The dimensions the panel offers, each with the `/v1/wells` parameter its buckets narrow the
 * collection by — `facets.py`'s `DIMENSIONS[...]["filter"]`, which wells-by.test.ts parses and
 * holds equal to this. `null` where the collection accepts no such filter at all.
 */
export const DIMENSIONS = [
  { id: "operator", label: "operator", filter: "operator" },
  { id: "county", label: "county", filter: "county" },
  { id: "status", label: "status", filter: "status" },
  { id: "well_type", label: "well type", filter: "well_type" },
  { id: "completion_year", label: "completion year", filter: null },
] as const;

const SORTS = [
  { id: "count", label: "well count" },
  { id: "value", label: "value" },
] as const;

/** Every size the operation accepts a cut at: `ge=1, le=50` on the server, 15 by default. */
const TOPS = ["10", "15", "20", "25", "50"] as const;

// Which jurisdiction the explorer opens on is a registry row now: exactly one registration
// carries `explorer_default`, and its rationale is the reason — the only jurisdiction serving
// well-grain production history end to end. Nothing here decides it.
const DEFAULT_STATE = DEFAULT_JURISDICTION.prefix;

/** The scope sentinel `/v1/wells/facets` and `/v1/wells` both read: every registered
 *  jurisdiction, resolved server-side, so this file never carries a list of them. */
export const ALL_JURISDICTIONS = "all";
const DEFAULTS = { state: DEFAULT_STATE, by: "operator", sort: "count", order: "desc", top: "15" };

/** Exported so the suite asserts against the shipped defaults rather than a copy of them. */
export const DEFAULTS_FOR_TEST = DEFAULTS;
const SEARCH_DEBOUNCE_MS = 250;

export interface FacetState {
  code: string;
  name: string;
  loaded: boolean;
}

export interface FacetBucket {
  value: string;
  wells: Figure;
  links: Record<string, string>;
}

/** One jurisdiction the counts were taken over, and what it does with the dimension. */
export interface FacetJurisdiction {
  code: string;
  name: string;
  wells: Figure | null;
  dimension: "carried" | "absent_by_rule" | "absent_unregistered" | "no_wells_in_scope";
  rule_id: string | null;
}

export interface WellFacets {
  state: string;
  state_name: string;
  dimension: string;
  dimension_title: string;
  sort: string;
  order: string;
  q: string | null;
  top: number;
  distinct_values: number;
  caption: string;
  buckets: FacetBucket[];
  remainder: { values: number; wells: Figure; detail: string } | null;
  absence: {
    label: string;
    detail: string;
    rule_id: string | null;
    wells: Figure;
    links: Record<string, string>;
  } | null;
  wells: Figure | null;
  matched_wells: Figure | null;
  jurisdictions: FacetJurisdiction[];
  states: FacetState[];
  rules: string[];
}

export interface WellsByHooks {
  /** Commits panel state to the URL. Search churn replaces rather than pushes. */
  setPanel(values: Record<string, string | null>, mode: "push" | "replace"): void;
  /**
   * Narrows the grid beside this panel to one bucket, by every filter the bucket's link names.
   * A name mapped to an empty list clears that filter — the un-press path removes exactly the
   * terms the press added.
   */
  applyFilter(filters: Record<string, string[]>): void;
}

/** Whether a bucket is a control on this surface, and — where it is not — why not. */
export interface BucketAffordance {
  press: boolean;
  title?: string;
}

export interface WellsByOptions {
  state: AppState;
  hooks: WellsByHooks;
  signal: AbortSignal;
  /**
   * The filters the surface beside this panel already carries, which is what makes a bucket a
   * pressed control. Handed in rather than read off `state.extra` here: the map surface has no
   * grid and no `f.` prefix, and a panel that reached into the explorer's URL vocabulary could
   * not be the one component both surfaces render.
   */
  applied: Record<string, string[]>;
  /** The host's own press rule. Absent, the link-presence rule below stands. */
  bucketAffordance?(dimension: string, bucket: FacetBucket): BucketAffordance;
  /**
   * One line above the ranking naming the population these counts were taken over. A function
   * where the sentence needs the served state name: the map sheet says "every current well in
   * North Dakota", and the name is the server's rather than a second copy of the code table.
   */
  scopeNote?: string | ((data: WellFacets) => string);
}

/** What the server calls the bucket for wells with no value; `facets.py` ABSENCE_LABEL. */
const ABSENCE_LABEL = "not reported";

/** The collection's own refusal: a dimension /v1/wells accepts no filter for. */
const COLLECTION_UNFILTERABLE =
  "The collection accepts no filter for this dimension, so it cannot be narrowed to one year.";

/** What the panel did before it served two surfaces: a bucket is pressable where the server
 *  published a link for it, and a plain label where it did not. */
function linkAffordance(_dimension: string, bucket: FacetBucket): BucketAffordance {
  return filtersOfLink(bucket.links["wells"]) === null
    ? { press: false, title: COLLECTION_UNFILTERABLE }
    : { press: true };
}

export function panelState(state: AppState): Record<string, string> {
  const read = (key: string): string | undefined =>
    state.extra[`${WELLS_BY_PREFIX}${key}`]?.[0];
  return {
    state: read("state") ?? DEFAULTS.state,
    by: read("by") ?? DEFAULTS.by,
    sort: read("sort") ?? DEFAULTS.sort,
    order: read("order") ?? DEFAULTS.order,
    top: read("top") ?? DEFAULTS.top,
    q: read("q") ?? "",
  };
}

/**
 * The filters a bucket narrows the collection by, read out of the link the server published for
 * it rather than rebuilt from the dimension here. The `state` term is why: a county-003 bucket
 * counted in Texas narrows to Texas county 003, and a filter assembled from the dimension alone
 * returns North Dakota's county 003 beside it. A bucket the collection cannot reproduce carries
 * no link, and gets no filter rather than one that narrows to something else.
 */
function filtersOfLink(link: string | undefined): Record<string, string[]> | null {
  const mark = link?.indexOf("?") ?? -1;
  if (link === undefined || mark < 0) return null;
  const filters: Record<string, string[]> = {};
  for (const [name, value] of new URLSearchParams(link.slice(mark + 1))) {
    (filters[name] ??= []).push(value);
  }
  return Object.keys(filters).length > 0 ? filters : null;
}

/**
 * The last state list the server served. A refusal is a problem document and carries none, so
 * without this the picker collapses to a disabled placeholder at exactly the moment the reader
 * needs it — the empty state would be a dead end they could only leave by editing the URL.
 * The list changes only when an ingest runs, so a cached one is never stale within a session.
 */
let knownStates: FacetState[] = [];

const SEARCH_SELECTOR = ".gw-wells-by-search-input";

/**
 * What the reader has typed, and where their caret is, when a commit tears the panel down. Every
 * commit rebuilds the explorer — the shell replaces its own children before this module replaces
 * the host's — so a focused search input is destroyed mid-word. The value travels with the caret
 * because the rebuilt input is filled from the URL, which lags the keyboard by a debounce plus a
 * round trip: restoring the caret alone put the reader back in a box that had un-typed them.
 */
let searchDraft: { value: string; start: number; end: number } | null = null;

/**
 * Armed by the search box's own commit, spent by the rebuild that commit causes. Every control on
 * this panel rebuilds it, and a `blur` cannot tell the two apart — Chromium fires one as it
 * removes a focused element, and reports the element still connected while it does. So the
 * rebuild the reader's typing caused is marked at the commit rather than inferred at the teardown.
 */
let searchCommitted = false;

/**
 * Re-reads where the reader is. A box they have left owns no draft; a detached box is not a
 * departure but the teardown this whole mechanism exists to survive, and says nothing either way.
 */
function rememberDraft(input: HTMLInputElement | null): void {
  if (!input?.isConnected) return;
  if (document.activeElement !== input) {
    searchDraft = null;
    return;
  }
  searchDraft = {
    value: input.value,
    start: input.selectionStart ?? input.value.length,
    end: input.selectionEnd ?? input.value.length,
  };
}

/** The one place the panel's children are swapped, so nothing can rebuild it and forget this. */
function swap(host: HTMLElement, ...children: HTMLElement[]): void {
  const outgoing = host.querySelector<HTMLInputElement>(SEARCH_SELECTOR);
  // Whose rebuild this is: the box's own commit, or a reader still typing in the box being torn
  // down. A sort, a bucket press or anything else carries nothing into the panel it rebuilds.
  const carried = searchCommitted || (outgoing !== null && document.activeElement === outgoing);
  searchCommitted = false;
  rememberDraft(outgoing);
  const draft = carried ? searchDraft : null;
  // Taken, not read: a draft outliving the swap that consumed it is one a later mount would
  // type into a box the reader never touched.
  searchDraft = null;
  host.replaceChildren(...children);
  const input = host.querySelector<HTMLInputElement>(SEARCH_SELECTOR);
  // Only a draft carried in from a commit the reader's own typing caused: a first mount must
  // not take focus off whatever they were using.
  if (!draft || !input) return;
  input.value = draft.value;
  input.focus();
  const end = Math.min(draft.end, input.value.length);
  input.setSelectionRange(Math.min(draft.start, end), end);
}

export async function mountWellsBy(host: HTMLElement, options: WellsByOptions): Promise<void> {
  const panel = panelState(options.state);
  const query: Record<string, string> = {
    state: panel["state"] as string,
    by: panel["by"] as string,
    sort: panel["sort"] as string,
    order: panel["order"] as string,
    top: panel["top"] as string,
  };
  if (panel["q"]) query["q"] = panel["q"];

  swap(host, controls(panel, null, options), loading());
  try {
    const envelope = await getEnvelope<WellFacets>("/v1/wells/facets", query, options.signal);
    if (options.signal.aborted) return;
    const { data } = envelope;
    if (data.states.length > 0) knownStates = data.states;
    swap(host, controls(panel, data, options), list(data, envelope.meta.warnings, options));
  } catch (error) {
    if (options.signal.aborted) return;
    // The refusal carries the same state list the success path serves, so the picker survives
    // it and the reader can leave without editing the URL.
    const offered = error instanceof ApiError ? statesOf(error) : [];
    if (offered.length > 0) knownStates = offered;
    swap(host, controls(panel, null, options), refusal(error));
  }
}

/**
 * The refusal is the surface, not an error banner over an empty one. A state whose ingest has
 * not run answers 422 with a sentence naming which states did load, and that sentence is more
 * use to a reader than a zero would be — which is the whole reason the endpoint refuses
 * rather than serving an empty list.
 */
function refusal(error: unknown): HTMLElement {
  const box = div("gw-wells-by-empty");
  const heading = document.createElement("p");
  heading.className = "gw-wells-by-empty-title";
  heading.textContent =
    error instanceof ApiError ? "Nothing to count here" : "The facet list is unavailable";
  const detail = document.createElement("p");
  detail.className = "gw-wells-by-empty-detail";
  detail.textContent =
    error instanceof ApiError
      ? (error.problem?.detail ?? error.message)
      : "The request did not complete, so no count is shown rather than a stale one.";
  box.append(heading, detail);
  return box;
}

/** RFC 9457 extension member: the refusal names what the caller could have asked for. */
function statesOf(error: ApiError): FacetState[] {
  const offered = (error.problem as { states?: unknown } | undefined)?.states;
  if (!Array.isArray(offered)) return [];
  return offered.filter(
    (entry): entry is FacetState =>
      typeof entry === "object" &&
      entry !== null &&
      typeof (entry as FacetState).code === "string" &&
      typeof (entry as FacetState).name === "string",
  );
}

function loading(): HTMLElement {
  const box = div("gw-wells-by-loading");
  box.setAttribute("role", "status");
  box.textContent = "Counting wells…";
  return box;
}

function controls(
  panel: Record<string, string>,
  data: WellFacets | null,
  options: WellsByOptions,
): HTMLElement {
  const bar = div("gw-wells-by-controls");

  const line = div("gw-wells-by-line");
  line.append(
    pair(
      "Wells by",
      select(
        "dimension",
        DIMENSIONS.map((entry) => ({ value: entry.id, label: entry.label, disabled: false })),
        panel["by"] as string,
        (value) => options.hooks.setPanel({ by: value, q: null }, "push"),
        options.signal,
      ),
    ),
  );

  line.append(pair("in", scope(panel, data, options)));
  bar.append(line);

  const tools = div("gw-wells-by-tools");
  tools.append(
    search(panel, data, options),
    select(
      "sort",
      SORTS.map((entry) => ({ value: entry.id, label: entry.label, disabled: false })),
      panel["sort"] as string,
      (value) => options.hooks.setPanel({ sort: value }, "push"),
      options.signal,
    ),
    direction(panel, options),
    select(
      "top",
      cuts(panel["top"] as string).map((size) => ({
        value: size,
        label: `top ${size}`,
        disabled: false,
      })),
      panel["top"] as string,
      (value) => options.hooks.setPanel({ top: value }, "push"),
      options.signal,
    ),
  );
  bar.append(tools);
  return bar;
}

/**
 * The search asks the server, always. Searching the fifteen rows on screen would answer "no
 * such operator" for 9,354 of the 9,369 Texas carries, which is a wrong answer delivered
 * instantly rather than a right one delivered in a round trip.
 */
function search(
  panel: Record<string, string>,
  data: WellFacets | null,
  options: WellsByOptions,
): HTMLElement {
  const wrapper = document.createElement("label");
  wrapper.className = "gw-wells-by-search";
  const name = document.createElement("span");
  name.className = "gw-wells-by-search-label";
  name.textContent = "Search";
  const input = document.createElement("input");
  input.type = "search";
  input.className = "gw-wells-by-search-input";
  input.value = panel["q"] as string;
  input.placeholder = data
    ? `every ${data.dimension_title.split(",")[0]} ${population(data)}`
    : "the whole scope, not this page";
  input.setAttribute(
    "aria-label",
    "Search every value in the state, not only the ones listed below",
  );

  let timer: ReturnType<typeof setTimeout> | undefined;
  input.addEventListener(
    "input",
    () => {
      // On the keystroke, not only in the timer: by the time the timer runs a rebuild may
      // already have detached this element, and a detached input is never activeElement.
      rememberDraft(input);
      if (timer !== undefined) clearTimeout(timer);
      // `replace`, on the convention web/src/app/state.ts states for viewport churn: "the back
      // button is not forty pan events". A seven-character search is seven commits.
      timer = setTimeout(() => {
        // The box on screen, which a rebuild mid-debounce makes a different element from the one
        // this closure holds: re-reading it is what arms the restore for the commit below.
        rememberDraft(document.querySelector<HTMLInputElement>(SEARCH_SELECTOR) ?? input);
        // The reader's own text, and this detached element's only when they have left the box.
        const typed = searchDraft?.value ?? input.value;
        searchCommitted = true;
        options.hooks.setPanel({ q: typed.trim() || null }, "replace");
      }, SEARCH_DEBOUNCE_MS);
    },
    { signal: options.signal },
  );
  // A pending keystroke must not commit after the panel is gone, or it re-renders a surface
  // the reader has already navigated away from.
  options.signal.addEventListener("abort", () => {
    if (timer !== undefined) clearTimeout(timer);
  });
  wrapper.append(name, input);
  return wrapper;
}

function direction(panel: Record<string, string>, options: WellsByOptions): HTMLElement {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "gw-wells-by-order";
  const descending = panel["order"] === "desc";
  button.textContent = directionLabel(panel["sort"] as string, descending);
  button.setAttribute("aria-label", `Ranking direction: ${button.textContent}. Click to flip.`);
  button.addEventListener(
    "click",
    () => options.hooks.setPanel({ order: descending ? "asc" : "desc" }, "push"),
    { signal: options.signal },
  );
  return button;
}

/**
 * The words the caption uses for the same parameter (`facets.py` `_caption`). Count words on an
 * alphabetical ranking described the wrong thing twice: `order=asc` on `sort=value` is A to Z,
 * not the lowest anything.
 */
function directionLabel(sort: string, descending: boolean): string {
  if (sort === "value") return descending ? "Z to A" : "A to Z";
  return descending ? "highest first" : "lowest first";
}

/** The offered cuts, plus whatever the URL asked for: the control names the list it produced. */
function cuts(current: string): string[] {
  return [...new Set([...TOPS, current])].sort((a, b) => Number(a) - Number(b));
}

/** Label and control wrap as one unit: at 320 a bare `in` was left stranded on the line above. */
function pair(label: string, control: HTMLElement): HTMLElement {
  const wrapper = div("gw-wells-by-pair");
  const lead = document.createElement("span");
  lead.className = "gw-wells-by-lead";
  lead.textContent = label;
  wrapper.append(lead, control);
  return wrapper;
}

/**
 * The jurisdictions the counts are taken over. A list box rather than a dropdown because the
 * scope is a set: a plain click still picks exactly one, which is the question most readers
 * open with, and the same control takes several without a second one beside it.
 *
 * `All jurisdictions` leads it because it is the widest answer and the one a reader scanning a
 * basin across a state line wants first. It is the sentinel, not an expansion of the codes: the
 * registry resolves it at request time, so a jurisdiction that registers tomorrow is in it.
 */
function scope(
  panel: Record<string, string>,
  data: WellFacets | null,
  options: WellsByOptions,
): HTMLElement {
  const asked = panel["state"] as string;
  // The map's layer panel renamed every state row to `Noun (Full state name)`; this is the same
  // convention on the same nouns, so the two surfaces name a state identically.
  const known = (data?.states ?? knownStates).map((entry) => ({
    value: entry.code,
    label: `Wells (${entry.name})${entry.loaded ? "" : " · not loaded"}`,
    disabled: !entry.loaded,
  }));
  const offered = [
    { value: ALL_JURISDICTIONS, label: "All jurisdictions", disabled: false },
    ...(known.length > 0 ? known : [{ value: asked, label: "…", disabled: true }]),
  ];
  const element = document.createElement("select");
  element.className = "gw-wells-by-select gw-wells-by-state";
  element.multiple = true;
  element.size = Math.min(offered.length, 5);
  element.setAttribute("aria-label", "state");
  const picked = new Set(asked === ALL_JURISDICTIONS ? [ALL_JURISDICTIONS] : asked.split(","));
  for (const option of offered) {
    const node = document.createElement("option");
    node.value = option.value;
    node.textContent = option.label;
    node.disabled = option.disabled;
    node.selected = picked.has(option.value);
    element.append(node);
  }
  element.addEventListener(
    "change",
    () => {
      const chosen = [...element.selectedOptions].map((option) => option.value);
      // Codes win over the sentinel: a reader who adds a code to `all` is narrowing, and a
      // selection cleared to nothing is no narrowing at all rather than an empty scope the
      // server would refuse.
      const codes = chosen.filter((value) => value !== ALL_JURISDICTIONS);
      const value = codes.length > 0 ? codes.join(",") : ALL_JURISDICTIONS;
      options.hooks.setPanel({ state: value, q: null }, "push");
    },
    { signal: options.signal },
  );
  return element;
}

function select(
  name: string,
  options_: { value: string; label: string; disabled: boolean }[],
  current: string,
  onChange: (value: string) => void,
  signal: AbortSignal,
): HTMLElement {
  const element = document.createElement("select");
  element.className = `gw-wells-by-select gw-wells-by-${name}`;
  element.setAttribute("aria-label", name);
  for (const option of options_) {
    const node = document.createElement("option");
    node.value = option.value;
    node.textContent = option.label;
    node.disabled = option.disabled;
    node.selected = option.value === current;
    element.append(node);
  }
  // Assigned after insertion as well: inserting an option resets the select, which drops a
  // selectedness set before it, and a picker showing a value the request did not use is a
  // control that lies about the list beside it.
  if (options_.some((option) => option.value === current)) element.value = current;
  element.addEventListener("change", () => onChange(element.value), { signal });
  return element;
}

function list(data: WellFacets, warnings: Warning[], options: WellsByOptions): HTMLElement {
  const box = div("gw-wells-by-list");
  // The counts change under a control that keeps focus, so nothing else would announce them.
  box.setAttribute("aria-live", "polite");

  const caption = document.createElement("p");
  caption.className = "gw-wells-by-caption";
  caption.textContent = data.caption;
  box.append(caption);

  // Above the ranking, never under it: a population stated after the numbers is a correction.
  // A set names itself even where the host asked for no note: a combined count with nothing
  // saying which jurisdictions are in it is a number a reader cannot place.
  const scopeNote =
    typeof options.scopeNote === "function"
      ? options.scopeNote(data)
      : (options.scopeNote ??
        (data.jurisdictions.length > 1
          ? `Counted over every current well ${population(data)}.`
          : undefined));
  if (scopeNote) {
    const scope = document.createElement("p");
    scope.className = "gw-wells-by-scope";
    scope.textContent = scopeNote;
    box.append(scope);
  }

  // A press needs both: a host willing to take one, and a link naming the filters it would
  // apply. Resolved once per bucket here so the sentence below and the rows agree on it.
  const affordanceOf = options.bucketAffordance ?? linkAffordance;
  const refusals = data.buckets.map((bucket) => {
    const affordance = affordanceOf(data.dimension, bucket);
    return affordance.press && filtersOfLink(bucket.links["wells"]) !== null
      ? null
      : (affordance.title ?? COLLECTION_UNFILTERABLE);
  });

  // On screen, not only in a `title`: a span renders identically to a button at rest, and on a
  // touch surface there is no cursor and no hover, so a reader taps a count, nothing happens and
  // nothing anywhere says why (visual-map-wells-by D8). Said once for the dimension rather than
  // per row, and only where it holds for the whole ranking — it is a fact about the column.
  const refused = refusals.length > 0 && refusals.every(Boolean) ? refusals[0] : null;
  if (refused) {
    const note = document.createElement("p");
    note.className = "gw-wells-by-refusal";
    note.textContent = refused;
    box.append(note);
  }

  if (data.buckets.length === 0) {
    const none = div("gw-wells-by-empty");
    const title = document.createElement("p");
    title.className = "gw-wells-by-empty-title";
    title.textContent = data.q ? "No value matches that search" : "No values to rank";
    const detail = document.createElement("p");
    detail.className = "gw-wells-by-empty-detail";
    detail.textContent = data.q
      ? `The search ran over every ${data.dimension.replace("_", " ")} in ${data.state_name}, not over a page of them, so this is the whole answer.`
      : `The spine holds wells in ${data.state_name} but none of them carries this dimension.`;
    none.append(title, detail);
    box.append(none);
    // Falls through: absence and the total still belong under an empty ranking, and are the
    // only two things on screen that explain why it is empty.
  }

  const widest = data.buckets.reduce(
    (top, bucket) => Math.max(top, Number(bucket.wells.value) || 0),
    0,
  );
  const rows = document.createElement("ol");
  rows.className = "gw-wells-by-rows";
  const applied = options.applied;
  data.buckets.forEach((bucket, index) => {
    rows.append(row(bucket, index + 1, widest, data, applied, options, refusals[index] ?? null));
  });
  if (data.buckets.length > 0) box.append(rows);

  // A warning is rendered against what it points at: `absence_unregistered` restated the absence
  // block's own paragraph 39 px below it with the total wedged between the two.
  const aboutAbsence = data.absence ? warnings.filter((warning) => warning.pointer === "/absence") : [];
  const rest = warnings.filter((warning) => !aboutAbsence.includes(warning));

  if (data.remainder) box.append(remainder(data.remainder));
  if (data.absence) box.append(absence(data.absence, aboutAbsence));
  box.append(...absentByRule(data));
  box.append(total(data));
  // The same panels the well card and the neighbour list render. Under a search the absence
  // bucket is the one figure on screen outside the visible arithmetic, and
  // `search_scopes_the_ranking` is the served sentence that says so.
  box.append(...warningNotes(rest));
  return box;
}

/** Mirrors the enum chips: a bucket whose filter the grid already carries is a pressed control. */
function narrowedBy(
  filters: Record<string, string[]>,
  applied: Record<string, string[]>,
): boolean {
  return Object.entries(filters).every(([name, values]) =>
    values.every((value) => applied[name]?.includes(value)),
  );
}

/**
 * The same filter names with no values, which `withFilter` deletes. The `state` term goes with
 * the dimension term rather than persisting: the press put it there, and a filter left behind
 * by an un-press is one no control below 520 can clear.
 */
function released(filters: Record<string, string[]>): Record<string, string[]> {
  return Object.fromEntries(Object.keys(filters).map((name) => [name, []]));
}

function row(
  bucket: FacetBucket,
  rank: number,
  widest: number,
  data: WellFacets,
  applied: Record<string, string[]>,
  options: WellsByOptions,
  /** Why this bucket is not a control, or null where it is one. */
  refusal: string | null,
): HTMLElement {
  const item = document.createElement("li");
  item.className = "gw-wells-by-row";
  item.dataset["value"] = bucket.value;

  const filters = filtersOfLink(bucket.links["wells"]);
  // A control that looks clickable and narrows nothing is worse than no control.
  const label = refusal === null ? document.createElement("button") : document.createElement("span");
  label.className = "gw-wells-by-value";
  if (label instanceof HTMLButtonElement && filters) {
    const pressed = narrowedBy(filters, applied);
    label.type = "button";
    label.setAttribute("aria-label", `Narrow the wells below to ${bucket.value} in ${data.state_name}`);
    label.setAttribute("aria-pressed", String(pressed));
    // A toggle button un-presses. At <=520 the grid's clear-filters line is display:none, so a
    // press with no un-press is the only way back out of an unfiltered list — and there is none.
    label.addEventListener(
      "click",
      () => options.hooks.applyFilter(pressed ? released(filters) : filters),
      { signal: options.signal },
    );
  } else {
    // Kept beside the line above the ranking: the pointer still gets the reason on the row it
    // is over, and the reader without one has already been told.
    label.title = refusal ?? COLLECTION_UNFILTERABLE;
  }

  const position = document.createElement("span");
  position.className = "gw-wells-by-rank";
  position.textContent = String(rank);
  position.setAttribute("aria-hidden", "true");

  const name = document.createElement("span");
  name.className = "gw-wells-by-name";
  name.textContent = bucket.value;
  label.append(name);

  const bar = div("gw-wells-by-bar");
  const fill = div("gw-wells-by-fill");
  const share = widest > 0 ? (Number(bucket.wells.value) || 0) / widest : 0;
  fill.style.setProperty("--gw-share", `${(share * 100).toFixed(2)}%`);
  bar.append(fill);
  bar.setAttribute("aria-hidden", "true");

  item.append(position, label, bar, figure(bucket.wells, bucket.value));
  return item;
}

/**
 * The population, in the server's own words. `state_name` is the served list for a set, so the
 * only thing composed here is the preposition — one jurisdiction reads exactly as it always did.
 */
function population(data: WellFacets): string {
  return `${data.jurisdictions.length > 1 ? "across" : "in"} ${data.state_name}`;
}

/**
 * A jurisdiction that reports nothing at all for this dimension, said in the panel's own words.
 * Its wells are outside the `not reported` bucket by design — a registered absence and an
 * unexplained one summed together are a number with two meanings — so the count has to be on
 * screen somewhere, and the rule that took it out has to be beside it.
 */
function absentByRule(data: WellFacets): HTMLElement[] {
  const noun = data.dimension.replace("_", " ");
  return data.jurisdictions
    .filter((entry) => entry.dimension === "absent_by_rule")
    .map((entry) => {
      const box = div("gw-wells-by-by-rule");
      const head = div("gw-wells-by-by-rule-head");
      const label = document.createElement("span");
      label.className = "gw-wells-by-by-rule-label";
      label.textContent = entry.name;
      head.append(label);
      if (entry.wells) head.append(figure(entry.wells, entry.name));
      const detail = document.createElement("p");
      detail.className = "gw-wells-by-by-rule-detail";
      detail.textContent =
        `${entry.name} reports no ${noun} for any well, so these are counted here rather` +
        ` than in “${ABSENCE_LABEL}” beside jurisdictions that do report one.`;
      box.append(head, detail);
      if (entry.rule_id) {
        const link = document.createElement("a");
        link.className = "gw-wells-by-rule";
        link.href = `/v1/conformance/${entry.rule_id}`;
        link.textContent = entry.rule_id;
        const line = document.createElement("p");
        line.className = "gw-wells-by-rule-line";
        line.append(document.createTextNode("Registered as "), link);
        box.append(line);
      }
      return box;
    });
}

function figure(value: Figure, label: string): HTMLElement {
  const element = document.createElement("gw-figure");
  element.className = "gw-wells-by-count";
  element.setAttribute("value", value.value);
  element.setAttribute("unit", value.unit);
  element.setAttribute("handle", value.d);
  element.setAttribute("label", label);
  element.setAttribute("label-hidden", "");
  return element;
}

/**
 * The point of the surface: what the list leaves out, counted, never implied by its absence.
 * A label and a count, in the same shape as the rows above it — the sentence the server
 * composes says the same thing at four times the width and stays reachable as the row's title.
 */
function remainder(value: NonNullable<WellFacets["remainder"]>): HTMLElement {
  const box = div("gw-wells-by-remainder");
  box.title = value.detail;
  const detail = document.createElement("p");
  detail.className = "gw-wells-by-remainder-detail";
  detail.textContent = `${value.values.toLocaleString()} more values`;
  box.append(detail, figure(value.wells, "the remainder"));
  return box;
}

/**
 * Outside the ranking and visually unlike it, because it is not a value. On the current Texas
 * load this bucket holds 70,039 wells — more than any real operator — and a reader who mistook
 * it for one would conclude Texas has a dominant operator that does not exist.
 */
function absence(value: NonNullable<WellFacets["absence"]>, warnings: Warning[]): HTMLElement {
  const box = div("gw-wells-by-absence");
  const head = div("gw-wells-by-absence-head");
  const label = document.createElement("span");
  label.className = "gw-wells-by-absence-label";
  label.textContent = value.label;
  head.append(label, figure(value.wells, value.label));
  const detail = document.createElement("p");
  detail.className = "gw-wells-by-absence-detail";
  detail.textContent = value.detail;
  box.append(head, detail);

  if (value.rule_id && value.links["rule"]) {
    const link = document.createElement("a");
    link.className = "gw-wells-by-rule";
    link.href = value.links["rule"];
    link.textContent = value.rule_id;
    const line = document.createElement("p");
    line.className = "gw-wells-by-rule-line";
    line.append(document.createTextNode("Registered as "), link);
    box.append(line);
  }
  box.append(...warningNotes(warnings));
  return box;
}

function total(data: WellFacets): HTMLElement {
  const box = div("gw-wells-by-total");
  const label = document.createElement("span");
  label.className = "gw-wells-by-total-label";
  const searched = data.q !== null && data.matched_wells !== null;
  label.textContent = searched
    ? `wells matching “${data.q}”`
    : `every current well ${population(data)}`;
  const value = searched ? data.matched_wells : data.wells;
  box.append(label);
  if (value) box.append(figure(value, label.textContent ?? "total"));
  return box;
}

function div(className: string): HTMLElement {
  const element = document.createElement("div");
  element.className = className;
  return element;
}
