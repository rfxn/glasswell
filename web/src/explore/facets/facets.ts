import "./facets.css";

import type { CatalogueDataset } from "../catalogue.ts";
import { controlsFor } from "./schema.ts";
import type { Control } from "./schema.ts";
import { operationFor } from "../grid/schema.ts";

export interface FacetHooks {
  setFilter(name: string, values: string[]): void;
  setHoisted(name: string, values: string[]): void;
  clearFilters(): void;
}

export interface FacetOptions {
  dataset: CatalogueDataset;
  document: unknown;
  datasets: readonly CatalogueDataset[];
  filters: Record<string, string[]>;
  hoisted: Record<string, string[]>;
  hooks: FacetHooks;
  signal: AbortSignal;
}

const BBOX_NOTE = "minx,miny,maxx,maxy · WGS84 · capped at 4°";

export function renderFacets(host: HTMLElement, options: FacetOptions): void {
  const operation = operationFor(options.document, options.dataset.operationId);
  const siblings = options.datasets
    .filter((candidate) => candidate.id !== options.dataset.id)
    .map((candidate) => operationFor(options.document, candidate.operationId))
    .filter((candidate): candidate is NonNullable<typeof candidate> => candidate !== null);
  const bar = controlsFor(operation ?? {}, options.dataset.facets, siblings);

  const global = bar.controls.filter((control) => control.hoisted && control.name === "as_of");
  const local = bar.controls.filter((control) => !control.hoisted);
  const children: HTMLElement[] = [];

  if (global.length > 0) children.push(globalStrip(global, options));
  const row = document.createElement("div");
  row.className = "gw-facet-row";
  for (const control of local) row.append(field(control, options));
  children.push(row);

  if (bar.unsupported.length > 0) children.push(unsupported(bar.unsupported));
  if (Object.keys(options.filters).length > 0) children.push(clearAll(options));
  host.replaceChildren(...children);
}

/**
 * §3.1: `as_of` is global rather than per-dataset, so it is lifted out of the facet row into
 * its own strip. SB-08 hoists it into the page header; `chrome/header.ts` is C6's file and this
 * chunk edits none of it, so the strip sits at the top of the facet host and says it is global.
 */
function globalStrip(controls: Control[], options: FacetOptions): HTMLElement {
  const strip = document.createElement("div");
  strip.className = "gw-facet-global";
  const label = document.createElement("span");
  label.className = "gw-facet-global-label";
  label.textContent = "knowledge time";
  strip.append(label);
  for (const control of controls) strip.append(field(control, options, true));
  const note = document.createElement("span");
  note.className = "gw-facet-note";
  note.textContent = "every dataset · travels with the link";
  strip.append(note);
  return strip;
}

function field(control: Control, options: FacetOptions, isGlobal = false): HTMLElement {
  const values = isGlobal
    ? (options.hoisted[control.name] ?? [])
    : (options.filters[control.name] ?? []);
  const set = (next: string[]): void => {
    if (isGlobal) options.hooks.setHoisted(control.name, next);
    else options.hooks.setFilter(control.name, next);
  };

  const wrapper = document.createElement("label");
  wrapper.className = `gw-facet gw-facet-${control.kind}`;
  wrapper.dataset["facet"] = control.name;
  const name = document.createElement("span");
  name.className = "gw-facet-name";
  name.textContent = control.name;
  if (control.description) name.title = control.description;
  wrapper.append(name, body(control, values, set, options.signal));
  if (control.kind === "stepper" && control.maximum !== undefined) {
    wrapper.append(hint(`${control.minimum ?? 1}–${control.maximum}; the server's cap, not ours`));
  }
  if (control.kind === "bbox") wrapper.append(hint(BBOX_NOTE));
  return wrapper;
}

function body(
  control: Control,
  values: readonly string[],
  set: (next: string[]) => void,
  signal: AbortSignal,
): HTMLElement {
  if (control.kind === "chips") return chips(control, values, set, signal);
  if (control.kind === "toggle") {
    const toggle = document.createElement("input");
    toggle.type = "checkbox";
    toggle.className = "gw-facet-toggle";
    toggle.checked = values[0] === "true";
    toggle.addEventListener("change", () => set(toggle.checked ? ["true"] : []), { signal });
    return toggle;
  }

  const input = document.createElement("input");
  input.className = "gw-facet-input";
  input.value = values[0] ?? "";
  if (control.description) input.placeholder = control.description;
  if (control.kind === "date") input.type = "date";
  else if (control.kind === "month") {
    input.type = "month";
    // The same pattern the server declares, so an invalid month never becomes a 422.
    if (control.pattern) input.pattern = control.pattern;
  } else if (control.kind === "stepper") {
    input.type = "number";
    if (control.minimum !== undefined) input.min = String(control.minimum);
    if (control.maximum !== undefined) input.max = String(control.maximum);
    if (control.fallback) input.placeholder = control.fallback;
  } else {
    input.type = "text";
  }
  input.addEventListener("change", () => set(input.value === "" ? [] : [input.value]), { signal });
  return input;
}

/** The enum is the vocabulary, so the chips *are* the closed list — no free text beside them. */
function chips(
  control: Control,
  values: readonly string[],
  set: (next: string[]) => void,
  signal: AbortSignal,
): HTMLElement {
  const group = document.createElement("span");
  group.className = "gw-facet-chips";
  group.setAttribute("role", control.multiple ? "group" : "radiogroup");
  for (const option of control.options ?? []) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "gw-facet-chip";
    chip.textContent = option;
    const chosen = values.includes(option);
    chip.setAttribute("aria-pressed", String(chosen));
    chip.addEventListener(
      "click",
      () => {
        if (!control.multiple) set(chosen ? [] : [option]);
        else set(chosen ? values.filter((value) => value !== option) : [...values, option]);
      },
      { signal },
    );
    group.append(chip);
  }
  return group;
}

/** §3.1 rule 3: an absence a reader can act on beats an absence they cannot see. */
function unsupported(names: readonly string[]): HTMLElement {
  const note = document.createElement("p");
  note.className = "gw-facet-unsupported";
  note.textContent = `This collection cannot be narrowed by ${names.join(", ")} — the operation declares no such parameter, so neither the grid nor curl can ask for it.`;
  return note;
}

function clearAll(options: FacetOptions): HTMLElement {
  const wrapper = document.createElement("p");
  wrapper.className = "gw-facet-clear-line";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "gw-facet-clear";
  button.textContent = "clear filters";
  // One commit, not one per filter: a loop of commits re-renders under its own feet.
  button.addEventListener("click", () => options.hooks.clearFilters(), { signal: options.signal });
  wrapper.append(button);
  return wrapper;
}

function hint(text: string): HTMLElement {
  const element = document.createElement("span");
  element.className = "gw-facet-hint";
  element.textContent = text;
  return element;
}
