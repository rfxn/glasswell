import "./pane.css";

import { isFigure } from "../../api/envelope.ts";
import type { AppState } from "../../app/state.ts";
import { labelElement } from "../../glossary/gw-term.ts";
import { operationFor } from "../grid/schema.ts";
import { currentCall, onCall } from "./context.ts";
import type { ApiCall } from "./context.ts";
import { DIALECTS, commandFor, requestFrom, walkAllPages } from "./request.ts";
import type { Dialect } from "./request.ts";
import { coverageOf, explain, semanticsFor } from "./semantics.ts";
import type { ParameterSemantics } from "./semantics.ts";

/** §4.1: four sections, and PROBLEMS is P-B (§8.2) — absent here rather than empty here. */
export const SECTIONS = ["request", "operation", "response"] as const;
export type Section = (typeof SECTIONS)[number];

/** Enough of the envelope to read whole; beyond it the reader is told exactly what was cut. */
const BODY_LIMIT = 4000;
/** A body a few lines over the limit renders whole: "3,999 of 4,005 bytes" is noise, not honesty. */
const BODY_SLACK = 400;
const SIDECARS = ["_lineage", "_units", "_basis"] as const;

const ANNOTATIONS: Record<string, string> = {
  data: "the resource. A collection puts its array here, never inside an items wrapper.",
  meta: "request_id, the as_of asked for and what it resolved to, labels, next_cursor, warnings.",
  links: "self, next and explain — the navigation, which is why a row's fields do not list it.",
};

const SIDECAR_NOTE =
  "one handle for the whole series, not one per point: it is rooted here and covers what is under it.";
const FIGURE_NOTE = "a scalar carries its own d, so one number is traceable without a sidecar.";
const UNIT_NOTE =
  "no figure object on this page, so no column here claims a unit. Units arrive with values.";
const SERIES_UNIT_NOTE =
  "the units on this page are read off _units per response, never off the schema (O-1).";
const CACHE_NOTE = "no cache class is declared yet (O-3), so this is the response's own Cache-Control.";
const KEY_NOTE = "Your own key, never this page's — the owner issues them at POST /v1/keys.";

// The reader's choice of dialect is not a property of the link they would share (§2.1), so it
// stays here rather than in the URL.
let dialect: Dialect = "curl";

export interface PaneOptions {
  document: unknown;
  state: AppState;
  /** The section list, written to `api=` by the shell without re-reading the API (C8 N3). */
  onSections(value: string): void;
  signal: AbortSignal;
  call?: ApiCall | null;
}

export function openSections(state: AppState): Section[] {
  const raw = state.extra["api"];
  if (raw === undefined) return [...SECTIONS];
  const named = raw.join(",").split(",");
  return SECTIONS.filter((section) => named.includes(section));
}

/** `none` rather than an empty value: every section closed is a state a link has to be able to carry. */
export function serializeSections(open: readonly Section[]): string {
  const named = SECTIONS.filter((section) => open.includes(section));
  return named.length === 0 ? "none" : named.join(",");
}

export function mountPane(host: HTMLElement, options: PaneOptions): void {
  const open = new Set<Section>(openSections(options.state));
  const draw = (call: ApiCall | null): void => {
    host.replaceChildren(render(call, options, open, draw));
  };
  onCall((call) => draw(call), options.signal);
  draw(options.call ?? currentCall());
}

function render(
  call: ApiCall | null,
  options: PaneOptions,
  open: Set<Section>,
  draw: (call: ApiCall | null) => void,
): HTMLElement {
  const root = element("div", "gw-api");
  root.append(head(call));
  // A call left over from the dataset the reader just navigated away from is not this dataset's
  // call, and rendering it here would be the drift §4.2 exists to prevent.
  if (!call || (options.state.ds !== null && call.dataset.id !== options.state.ds)) {
    root.append(
      note(
        "The call behind whatever the centre column is showing renders here: its URL, its parameters and the envelope it answered with.",
      ),
    );
    return root;
  }

  const operation = operationFor(options.document, call.request.operationId);
  const parameters = semanticsFor(operation);
  const toggle = (section: Section, on: boolean): void => {
    if (on) open.add(section);
    else open.delete(section);
    options.onSections(serializeSections([...open]));
    draw(call);
  };

  root.append(
    section("request", "Request", open, toggle, options.signal, () => requestBody(call, options)),
    section("operation", "Operation", open, toggle, options.signal, () =>
      operationBody(call, operation, parameters, options),
    ),
    section("response", "Response", open, toggle, options.signal, () => responseBody(call)),
  );
  return root;
}

function head(call: ApiCall | null): HTMLElement {
  const header = element("header", "gw-api-head");
  header.append(eyebrow("API"));
  if (!call) return header;

  const route = element("p", "gw-api-route");
  const method = document.createElement("code");
  method.textContent = `GET ${call.request.path}`;
  route.append(method);
  header.append(route, status(call));
  return header;
}

/**
 * §4.4's header line. The timing is the browser's own measurement of this request and says so;
 * the cache class is the response's actual header, because `x-glasswell-cache` is unimplemented
 * (O-3) and a placeholder there would be a claim the API has not made.
 */
function status(call: ApiCall): HTMLElement {
  const line = element("p", "gw-api-status");
  if (call.state === "unissued") {
    line.textContent = "not issued yet";
    return line;
  }
  if (call.state === "pending") {
    line.textContent = "waiting for the response";
    return line;
  }
  const meta = call.meta;
  if (!meta) {
    line.textContent = call.state === "failed" ? "the request did not reach the API" : "answered";
    return line;
  }
  const cache = meta.headers.get("cache-control");
  line.textContent = `${meta.status} · ${Math.round(meta.elapsed_ms)} ms measured in this browser`;
  const cacheMark = element("span", "gw-api-cache");
  cacheMark.textContent = cache ?? "no Cache-Control";
  cacheMark.title = CACHE_NOTE;
  line.append(cacheMark);
  return line;
}

function section(
  id: Section,
  title: string,
  open: Set<Section>,
  toggle: (section: Section, on: boolean) => void,
  signal: AbortSignal,
  body: () => HTMLElement,
): HTMLElement {
  const wrapper = document.createElement("section");
  wrapper.className = "gw-api-section";
  wrapper.dataset["section"] = id;
  const expanded = open.has(id);

  const control = document.createElement("button");
  control.type = "button";
  control.className = "gw-api-toggle";
  control.textContent = title;
  control.setAttribute("aria-expanded", String(expanded));
  control.addEventListener("click", () => toggle(id, !open.has(id)), { signal });

  const heading = document.createElement("h3");
  heading.className = "gw-api-heading";
  heading.append(control);
  wrapper.append(heading);
  if (expanded) wrapper.append(body());
  return wrapper;
}

function requestBody(call: ApiCall, options: PaneOptions): HTMLElement {
  const body = element("div", "gw-api-body");
  if (call.state === "unissued") {
    const missing = call.missing ?? [];
    body.append(
      note(
        `This operation is read one ${missing.join(" and ")} at a time, so no request has been issued to render.`,
      ),
    );
    return body;
  }

  const tabs = element("div", "gw-api-dialects");
  tabs.setAttribute("role", "group");
  tabs.setAttribute("aria-label", "Command dialect");
  for (const name of DIALECTS) {
    const tab = document.createElement("button");
    tab.type = "button";
    tab.className = "gw-api-dialect";
    tab.dataset["dialect"] = name;
    tab.setAttribute("aria-pressed", String(name === dialect));
    tab.textContent = name;
    tab.addEventListener(
      "click",
      () => {
        dialect = name;
        body.replaceWith(requestBody(call, options));
      },
      { signal: options.signal },
    );
    tabs.append(tab);
  }

  const signal = options.signal;
  body.append(tabs, command(commandFor(call.request, dialect), dialect, signal), note(KEY_NOTE));

  const next = nextHref(call);
  const following = next ? requestFrom(call.request.operationId, next) : null;
  if (following) {
    body.append(
      subheading("the next page"),
      note("Each page is its own request: this one carries the cursor the server just minted."),
      command(commandFor(following, dialect), dialect, signal),
      subheading("every page"),
      command(walkAllPages(call.request), "walk", signal),
    );
  }
  return body;
}

function command(text: string, name: string, signal: AbortSignal): HTMLElement {
  const wrapper = element("div", "gw-api-block");
  const block = document.createElement("pre");
  block.className = "gw-api-command";
  block.dataset["dialect"] = name;
  block.textContent = text;

  const copy = document.createElement("button");
  copy.type = "button";
  copy.className = "gw-api-copy";
  copy.textContent = "copy";
  copy.addEventListener(
    "click",
    () => {
      // The text is on the page either way; the clipboard is a permission, not a guarantee.
      void navigator.clipboard?.writeText(text);
      copy.textContent = "copied";
    },
    { signal },
  );
  wrapper.append(copy, block);
  return wrapper;
}

function operationBody(
  call: ApiCall,
  operation: ReturnType<typeof operationFor>,
  parameters: ParameterSemantics[],
  options: PaneOptions,
): HTMLElement {
  const body = element("div", "gw-api-body");
  const id = document.createElement("code");
  id.className = "gw-api-operation-id";
  id.textContent = call.request.operationId;
  id.title = "The join key to the MCP tool set and to the document's own request examples.";
  body.append(id);

  const described = typeof operation?.["description"] === "string" ? operation["description"] : "";
  if (described) body.append(note(described.split("\n\n")[0] as string));

  if (parameters.length === 0) {
    body.append(note("This operation takes no parameters, so there is nothing here to narrow."));
    return body;
  }

  const coverage = coverageOf(parameters);
  const line = element("p", "gw-api-coverage");
  // "annotated" and not "carries a WHY": `cursor` and `limit` carry a SO and no term by
  // design (C5 P1), and a line that promised both would be wrong on two parameters in seven.
  line.textContent =
    coverage.annotated === coverage.total
      ? `Annotated: all ${coverage.total}`
      : `Annotated: ${coverage.annotated}/${coverage.total} (${coverage.percent}%)`;
  // The unannotated ones render WHAT and a muted ? below, which is the statement itself.
  line.title = "The rest render WHAT only, and are counted here rather than hidden.";
  body.append(line);

  const inPlay = new Set([...Object.keys(call.request.query), ...(call.dataset.pathParameters ?? [])]);
  const list = element("div", "gw-api-params");
  for (const parameter of parameters) {
    list.append(parameterBlock(parameter, inPlay.has(parameter.name), options.signal));
  }
  body.append(list);
  return body;
}

/**
 * §4.3's fixed shape. WHAT is always present because SB-04 §7.1 requires a description; WHY and
 * SO are absent exactly when A-8 has not reached this parameter, and the muted `?` is the same
 * mark an unbound column header carries (C7 M2a) so one treatment means one thing.
 */
function parameterBlock(
  parameter: ParameterSemantics,
  expanded: boolean,
  signal: AbortSignal,
): HTMLElement {
  const wrapper = element("div", "gw-api-param");
  wrapper.dataset["param"] = parameter.name;
  wrapper.dataset["annotated"] = String(parameter.annotated);

  const control = document.createElement("button");
  control.type = "button";
  control.className = "gw-api-param-head";
  control.setAttribute("aria-expanded", String(expanded));
  control.append(labelElement(parameter.name, parameter.termId));
  const type = element("span", "gw-api-param-type");
  type.textContent = `${parameter.in} · ${parameter.type}`;
  control.append(type);
  if (!parameter.annotated) control.append(unbound(parameter.name));

  const body = element("div", "gw-api-param-body");
  body.hidden = !expanded;
  control.addEventListener(
    "click",
    () => {
      body.hidden = !body.hidden;
      control.setAttribute("aria-expanded", String(!body.hidden));
      if (!body.hidden) fill(body, parameter);
    },
    { signal },
  );

  wrapper.append(control, body);
  if (expanded) fill(body, parameter);
  return wrapper;
}

function fill(body: HTMLElement, parameter: ParameterSemantics): void {
  if (body.childElementCount > 0) return;
  body.append(field("WHAT", parameter.what));
  if (parameter.so) body.append(field("SO", parameter.so));
  for (const fact of parameter.facts) body.append(factRow(fact.label, fact.reason));
  if (!parameter.termId) {
    body.append(note("No glossary term bound — no WHY to show."));
    return;
  }
  // WHY and SEE come from the term the operation named, and are appended when it answers.
  void explain(parameter.termId).then((explanation) => {
    if (!body.isConnected) return;
    if (explanation.why) body.insertBefore(field("WHY", explanation.why), body.children[1] ?? null);
    if (explanation.see.length > 0) body.append(field("SEE", explanation.see.join(" · ")));
  });
}

function field(label: string, text: string): HTMLElement {
  const row = element("div", "gw-api-field");
  row.dataset["field"] = label;
  const name = element("span", "gw-api-field-label");
  name.textContent = label;
  const value = element("span", "gw-api-field-value");
  value.textContent = text;
  row.append(name, value);
  return row;
}

function factRow(label: string, reason: string | null): HTMLElement {
  const fact = element("p", "gw-api-fact");
  fact.textContent = label;
  if (reason) fact.title = reason;
  return fact;
}

function responseBody(call: ApiCall): HTMLElement {
  const body = element("div", "gw-api-body");
  if (call.state === "pending" || call.state === "unissued") {
    body.append(note("Nothing has answered yet, so there is no envelope to label."));
    return body;
  }
  if (!call.envelope) {
    body.append(note(`The API refused this request: ${problemOf(call.error)}`));
    return body;
  }

  const envelope = call.envelope as unknown as Record<string, unknown>;
  for (const name of ["data", "meta", "links"] as const) {
    if (!(name in envelope)) continue;
    const row = element("div", "gw-api-annotation");
    row.dataset["member"] = name;
    const key = document.createElement("code");
    key.textContent = name;
    const text = element("span", "gw-api-annotation-text");
    text.textContent = ANNOTATIONS[name] as string;
    row.append(key, text);
    body.append(row);
  }

  // A collection can root a sidecar on every row, and a hundred pointers is a wall rather than
  // a callout: the first few are named and the rest are counted.
  const sidecars = sidecarsIn(envelope["data"]);
  if (sidecars.length > 0) {
    const rest = sidecars.length - SIDECARS.length;
    const named = sidecars.slice(0, SIDECARS.length).join(", ");
    const listed = rest > 0 ? `${named} and ${rest} more` : named;
    body.append(callout(`${listed}: ${SIDECAR_NOTE}`, "sidecar"));
  }
  if (hasFigure(envelope["data"])) body.append(callout(FIGURE_NOTE, "figure"));
  else if (sidecars.some((pointer) => pointer.endsWith("/_units"))) {
    body.append(callout(SERIES_UNIT_NOTE, "unit"));
  } else body.append(callout(UNIT_NOTE, "unit"));

  const json = JSON.stringify(call.envelope, null, 2);
  const whole = bytesOf(json);
  // Cut at a line, not mid-token: a JSON body that stops inside a handle reads as a corrupt one.
  const cut = json.length > BODY_LIMIT + BODY_SLACK ? json.lastIndexOf("\n", BODY_LIMIT) : -1;
  const shown = cut > 0 ? json.slice(0, cut) : json;
  const block = document.createElement("pre");
  block.className = "gw-api-envelope";
  block.textContent = shown;
  body.append(block);

  const count = element("p", "gw-api-bytes");
  count.textContent =
    shown === json
      ? `${format(whole)} bytes · whole`
      : `${format(bytesOf(shown))} of ${format(whole)} bytes · rest on the wire`;
  body.append(count);
  return body;
}

function callout(text: string, kind: string): HTMLElement {
  const line = element("p", "gw-api-callout");
  line.dataset["callout"] = kind;
  line.textContent = text;
  return line;
}

function problemOf(error: unknown): string {
  if (typeof error === "object" && error !== null && "problem" in error) {
    const problem = (error as { problem: { title?: string; status?: number } }).problem;
    return `${problem.title ?? "no title"} (${problem.status ?? "no status"})`;
  }
  return String(error);
}

/** The pointers the three sidecars sit at, so §4.4 can point at them rather than describe them. */
function sidecarsIn(node: unknown, pointer = "", depth = 0): string[] {
  if (depth > 4 || typeof node !== "object" || node === null) return [];
  if (Array.isArray(node)) {
    return node.flatMap((item, index) => sidecarsIn(item, `${pointer}/${index}`, depth + 1));
  }
  const record = node as Record<string, unknown>;
  const found = SIDECARS.filter((key) => key in record).map((key) => `${pointer}/${key}`);
  return [
    ...found,
    ...Object.entries(record)
      .filter(([key]) => !(SIDECARS as readonly string[]).includes(key))
      .flatMap(([key, value]) => sidecarsIn(value, `${pointer}/${key}`, depth + 1)),
  ];
}

/** m12: a figure is recognised in the response, never in the schema — units arrive with values. */
function hasFigure(node: unknown, depth = 0): boolean {
  if (isFigure(node)) return true;
  if (depth > 4 || typeof node !== "object" || node === null) return false;
  return Object.values(node as Record<string, unknown>).some((value) => hasFigure(value, depth + 1));
}

function nextHref(call: ApiCall): string | null {
  const next = call.envelope?.links?.["next"];
  return typeof next === "string" && next !== "" ? next : null;
}

function bytesOf(text: string): number {
  return new TextEncoder().encode(text).length;
}

function format(count: number): string {
  return String(count).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

function unbound(name: string): HTMLElement {
  const marker = element("span", "gw-col-unbound");
  marker.textContent = "?";
  marker.title = `${name}: no semantics are published for this parameter yet.`;
  marker.setAttribute("aria-label", `${name} has no published semantics yet`);
  return marker;
}

function subheading(text: string): HTMLElement {
  const heading = element("p", "gw-api-subheading");
  heading.textContent = text;
  return heading;
}

function eyebrow(text: string): HTMLElement {
  const line = element("p", "gw-api-eyebrow");
  line.textContent = text;
  return line;
}

function note(text: string): HTMLElement {
  const line = element("p", "gw-api-note");
  line.textContent = text;
  return line;
}

function element(tag: string, className: string): HTMLElement {
  const created = document.createElement(tag);
  created.className = className;
  return created;
}
