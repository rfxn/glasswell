import "./wells-by.css";

import { ApiError, getEnvelope } from "../../api/client.ts";
import type { Figure, Warning } from "../../api/envelope.ts";
import type { AppState } from "../../app/state.ts";
import { warningPanels } from "../../card/card.ts";
import "../../card/gw-figure.ts";

/** §4.1: the panel rides the URL, so a shared link opens the list the sharer was reading. */
export const WELLS_BY_PREFIX = "wb.";

export const DIMENSIONS = [
  { id: "operator", label: "operator" },
  { id: "county", label: "county" },
  { id: "status", label: "status" },
  { id: "well_type", label: "well type" },
  { id: "completion_year", label: "completion year" },
] as const;

const SORTS = [
  { id: "count", label: "well count" },
  { id: "value", label: "value" },
] as const;

const DEFAULTS = { state: "33", by: "operator", sort: "count", order: "desc", top: "15" };

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
  states: FacetState[];
  rules: string[];
}

export interface WellsByHooks {
  /** Commits panel state to the URL. */
  setPanel(values: Record<string, string | null>): void;
  /** Narrows the grid beside this panel to one bucket, by every filter the bucket's link names. */
  applyFilter(filters: Record<string, string[]>): void;
}

export interface WellsByOptions {
  state: AppState;
  hooks: WellsByHooks;
  signal: AbortSignal;
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

  host.replaceChildren(controls(panel, null, options), loading());
  try {
    const envelope = await getEnvelope<WellFacets>("/v1/wells/facets", query, options.signal);
    if (options.signal.aborted) return;
    const { data } = envelope;
    if (data.states.length > 0) knownStates = data.states;
    host.replaceChildren(
      controls(panel, data, options),
      list(data, envelope.meta.warnings, options),
    );
  } catch (error) {
    if (options.signal.aborted) return;
    // The refusal carries the same state list the success path serves, so the picker survives
    // it and the reader can leave without editing the URL.
    const offered = error instanceof ApiError ? statesOf(error) : [];
    if (offered.length > 0) knownStates = offered;
    host.replaceChildren(controls(panel, null, options), refusal(error));
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
        (value) => options.hooks.setPanel({ by: value, q: null }),
        options.signal,
      ),
    ),
  );

  // The map's layer panel renamed every state row to `Noun (Full state name)`; this is the same
  // convention on the same nouns, so the two surfaces name a state identically.
  const states = (data?.states ?? knownStates).map((entry) => ({
    value: entry.code,
    label: `Wells (${entry.name})${entry.loaded ? "" : " — not loaded"}`,
    disabled: !entry.loaded,
  }));
  line.append(
    pair(
      "in",
      select(
        "state",
        states.length > 0
          ? states
          : [{ value: panel["state"] as string, label: "…", disabled: true }],
        panel["state"] as string,
        (value) => options.hooks.setPanel({ state: value, q: null }),
        options.signal,
      ),
    ),
  );
  bar.append(line);

  const tools = div("gw-wells-by-tools");
  tools.append(
    search(panel, data, options),
    select(
      "sort",
      SORTS.map((entry) => ({ value: entry.id, label: entry.label, disabled: false })),
      panel["sort"] as string,
      (value) => options.hooks.setPanel({ sort: value }),
      options.signal,
    ),
    direction(panel, options),
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
    ? `every ${data.dimension_title.split(",")[0]} in ${data.state_name}`
    : "the whole state, not this page";
  input.setAttribute(
    "aria-label",
    "Search every value in the state, not only the ones listed below",
  );

  let timer: ReturnType<typeof setTimeout> | undefined;
  input.addEventListener(
    "input",
    () => {
      if (timer !== undefined) clearTimeout(timer);
      timer = setTimeout(
        () => options.hooks.setPanel({ q: input.value.trim() || null }),
        SEARCH_DEBOUNCE_MS,
      );
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
  button.textContent = descending ? "highest first" : "lowest first";
  button.setAttribute("aria-label", `Ranking direction: ${button.textContent}. Click to flip.`);
  button.addEventListener(
    "click",
    () => options.hooks.setPanel({ order: descending ? "asc" : "desc" }),
    { signal: options.signal },
  );
  return button;
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
  element.addEventListener("change", () => onChange(element.value), { signal });
  return element;
}

function list(data: WellFacets, warnings: Warning[], options: WellsByOptions): HTMLElement {
  const box = div("gw-wells-by-list");

  const caption = document.createElement("p");
  caption.className = "gw-wells-by-caption";
  caption.textContent = data.caption;
  box.append(caption);

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
  data.buckets.forEach((bucket, index) => {
    rows.append(row(bucket, index + 1, widest, data, options));
  });
  if (data.buckets.length > 0) box.append(rows);

  if (data.remainder) box.append(remainder(data.remainder));
  if (data.absence) box.append(absence(data.absence));
  box.append(total(data));
  // The same panels the well card and the neighbour list render. Under a search the absence
  // bucket is the one figure on screen outside the visible arithmetic, and
  // `search_scopes_the_ranking` is the served sentence that says so.
  box.append(...warningPanels(warnings));
  return box;
}

function row(
  bucket: FacetBucket,
  rank: number,
  widest: number,
  data: WellFacets,
  options: WellsByOptions,
): HTMLElement {
  const item = document.createElement("li");
  item.className = "gw-wells-by-row";
  item.dataset["value"] = bucket.value;

  const filters = filtersOfLink(bucket.links["wells"]);
  const label = filters ? document.createElement("button") : document.createElement("span");
  label.className = "gw-wells-by-value";
  if (label instanceof HTMLButtonElement && filters) {
    label.type = "button";
    label.setAttribute("aria-label", `Narrow the wells below to ${bucket.value} in ${data.state_name}`);
    label.addEventListener("click", () => options.hooks.applyFilter(filters), {
      signal: options.signal,
    });
  } else {
    // A dimension /v1/wells cannot filter on gets no button: a control that looks clickable
    // and narrows nothing is worse than a plain label.
    label.title = "The collection accepts no filter for this dimension, so it cannot be narrowed to one year.";
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

/** The point of the surface: what the list leaves out, counted, never implied by its absence. */
function remainder(value: NonNullable<WellFacets["remainder"]>): HTMLElement {
  const box = div("gw-wells-by-remainder");
  const detail = document.createElement("p");
  detail.className = "gw-wells-by-remainder-detail";
  detail.textContent = value.detail;
  box.append(detail, figure(value.wells, "the remainder"));
  return box;
}

/**
 * Outside the ranking and visually unlike it, because it is not a value. On the current Texas
 * load this bucket holds 70,039 wells — more than any real operator — and a reader who mistook
 * it for one would conclude Texas has a dominant operator that does not exist.
 */
function absence(value: NonNullable<WellFacets["absence"]>): HTMLElement {
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
  return box;
}

function total(data: WellFacets): HTMLElement {
  const box = div("gw-wells-by-total");
  const label = document.createElement("span");
  label.className = "gw-wells-by-total-label";
  const searched = data.q !== null && data.matched_wells !== null;
  label.textContent = searched
    ? `wells matching “${data.q}”`
    : `every current well in ${data.state_name}`;
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
