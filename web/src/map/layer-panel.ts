import "./layer-panel.css";

import { readState } from "../app/state.ts";
import { explainHandle, setExplainHandle } from "../chrome/handle.ts";
import { registerOverlay } from "../chrome/overlays.ts";
import { applyCrossing, cross, whatsBehindThisLayer } from "../explore/bridge.ts";
import type { Bbox, Crossing } from "../explore/bridge.ts";
import { teach } from "../glossary/teach.ts";
import { ABBREVIATION } from "./jurisdictions.generated.ts";
import { BASEMAPS } from "./basemap.ts";
import { loadCensus, measuredJurisdiction } from "./census.ts";
import type { LayerFamily } from "./groups.ts";
import { COUNT_SLOT, LAYERS, defaultLayerSet, familyState, groupEntries } from "./registry.ts";
import type { GroupEntry, LayerDef } from "./registry.ts";
import { layerSwatch } from "./swatch.ts";

const NUMBER = new Intl.NumberFormat("en-US");
/** The legend's mark for a count that has not arrived. Never a literal that has drifted. */
const PENDING_MARK = "…";

/** The subtitle as one string, with whatever the registry has served in the count slot. */
function subtitleText(layer: LayerDef): string {
  const measured = layer.jurisdiction ? measuredJurisdiction(layer.jurisdiction) : null;
  return layer.subtitle.replace(
    COUNT_SLOT,
    measured === null ? PENDING_MARK : NUMBER.format(measured.wells),
  );
}

export interface LayerPanelOptions {
  on: ReadonlySet<string>;
  basemap: string;
  onToggle(id: string, next: boolean): void;
  onOpacity(id: string, value: number): void;
  onBasemap(id: string): void;
  onReset?(next: Set<string>): void;
  /** Asked to open. The host shuts the sibling sheet before this one appears. */
  onOpen?(): void;
}

export interface LayerPanelHandle {
  element: HTMLElement;
  setOn(on: ReadonlySet<string>): void;
  setZoom(zoom: number): void;
  setBasemap(id: string): void;
  setProvenance(id: string, derivationId: string): void;
  /**
   * The ids that are on, in scale, and drew nothing here. A statement about the canvas: a
   * layer whose tiles failed lands in this set too, and the wording never claims the ground.
   */
  setCoverage(empty: ReadonlySet<string>): void;
  /** §2.6: the crossing is rebuilt per viewport, because the box it narrows by moved. */
  setCrossing(box: Bbox, resolved: string | null, extentOff?: boolean): void;
  open(): void;
  close(): void;
  toggle(): void;
}

/**
 * The picker: what exists, what it is made of, and how much of it to show. Rows are built
 * once and patched thereafter — a full re-render on every toggle destroys focus mid-list
 * and cannot survive holding an input.
 */
export function createLayerPanel(options: LayerPanelOptions): LayerPanelHandle {
  const element = document.createElement("section");
  element.className = "gw-sheet gw-layers";
  element.id = "gw-layers";
  element.hidden = true;
  element.setAttribute("aria-label", "Map layers");

  const head = document.createElement("header");
  head.className = "gw-layers-head";
  head.setAttribute("data-no-glossary", "");
  const heading = document.createElement("h2");
  heading.textContent = "Layers";
  head.appendChild(heading);

  const reset = document.createElement("button");
  reset.type = "button";
  reset.className = "gw-layer-reset";
  reset.textContent = "Reset";
  reset.title = "Return every layer to its default visibility";
  reset.addEventListener("click", () => options.onReset?.(new Set(defaultLayerSet())));
  head.appendChild(reset);

  const close = document.createElement("button");
  close.type = "button";
  close.className = "gw-layers-close";
  close.textContent = "✕";
  close.setAttribute("aria-label", "Close the layer panel");
  close.addEventListener("click", () => handle.close());
  head.appendChild(close);
  element.appendChild(head);

  const search = document.createElement("input");
  search.type = "search";
  search.className = "gw-layer-search";
  search.placeholder = "Filter layers";
  search.setAttribute("aria-label", "Filter layers");
  search.setAttribute("data-no-glossary", "");
  element.appendChild(search);

  const bodyElement = document.createElement("div");
  bodyElement.className = "gw-layers-body";
  element.appendChild(bodyElement);

  const baseGroup = document.createElement("div");
  baseGroup.className = "gw-base-group";
  const baseHeading = document.createElement("h3");
  baseHeading.textContent = "Basemap";
  baseGroup.appendChild(baseHeading);

  const segmented = document.createElement("div");
  segmented.className = "gw-base-switcher";
  segmented.setAttribute("role", "group");
  segmented.setAttribute("aria-label", "Basemap");
  segmented.setAttribute("data-no-glossary", "");
  const baseButtons = new Map<string, HTMLButtonElement>();
  for (const base of BASEMAPS) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "gw-base-option";
    button.dataset["base"] = base.id;
    button.textContent = base.label;
    button.title = base.attribution.replace(/<[^>]*>/g, "");
    button.addEventListener("click", () => options.onBasemap(base.id));
    segmented.appendChild(button);
    baseButtons.set(base.id, button);
  }
  baseGroup.appendChild(segmented);
  bodyElement.appendChild(baseGroup);

  const rows = new Map<string, LayerRow>();
  const sections: LayerGroupSection[] = [];
  for (const { group, entries } of groupEntries()) {
    const section = buildGroup(group.id, group.label, entries, options);
    for (const [id, row] of section.rows) rows.set(id, row);
    bodyElement.appendChild(section.element);
    sections.push(section);
  }

  search.addEventListener("input", () => {
    const term = search.value.trim().toLowerCase();
    for (const [id, row] of rows) {
      const layer = LAYERS.find((candidate) => candidate.id === id);
      // The sources too: "Laterals (TX)" was a label a reader could search for, and combining
      // the rows would otherwise have made "tx" find nothing on a row that draws Texas.
      const sources = (layer?.provenance ?? []).map((source) => `${source.label} ${source.source}`);
      const haystack = `${layer?.label} ${layer?.subtitle} ${sources.join(" ")}`.toLowerCase();
      const matched = term.length === 0 || haystack.includes(term);
      row.element.hidden = !matched;
      // The strings the filter matches on live inside the disclosure now, so a hit that stays
      // collapsed is a hit the reader cannot see.
      row.setForcedOpen(term.length > 0 && matched);
    }
    // A hit inside a group the reader had shut is a hit they cannot see either, and a group
    // with no hits left is a header standing over nothing.
    for (const section of sections) section.setFiltered(term.length > 0);
  });

  // The MapLibre control that opens this panel is built by map.ts and never handed here, and
  // main.ts's Escape ladder closes the element rather than calling the handle — so the state
  // it announces is read back off the attribute rather than pushed at every open site.
  function syncTrigger(): void {
    for (const trigger of document.querySelectorAll<HTMLElement>(".gw-layers-button")) {
      trigger.setAttribute("aria-expanded", String(!element.hidden));
      trigger.setAttribute("aria-controls", element.id);
    }
  }
  new MutationObserver(syncTrigger).observe(element, {
    attributes: true,
    attributeFilter: ["hidden"],
  });
  // Deferred once: map.ts adds the control after this call returns, in the same task.
  queueMicrotask(syncTrigger);
  registerOverlay(element);

  const handle: LayerPanelHandle = {
    element,
    setOn(on) {
      for (const [id, row] of rows) row.setOn(on.has(id));
      for (const section of sections) section.setOn(on);
    },
    setZoom(zoom) {
      for (const row of rows.values()) row.setZoom(zoom);
      for (const section of sections) section.refreshFamilies();
    },
    setCoverage(empty) {
      for (const [id, row] of rows) row.setEmpty(empty.has(id));
      for (const section of sections) section.refreshFamilies();
    },
    setBasemap(id) {
      for (const [base, button] of baseButtons) {
        button.setAttribute("aria-pressed", String(base === id));
      }
    },
    setProvenance(id, derivationId) {
      rows.get(id)?.setProvenance(derivationId);
    },
    setCrossing(box, resolved, extentOff) {
      for (const row of rows.values()) row.setCrossing(box, resolved, extentOff ?? false);
    },
    open() {
      options.onOpen?.();
      element.hidden = false;
    },
    // Through the pair rather than flipping the attribute, so the open path is one path and
    // the sibling sheet is shut whichever control was used.
    toggle() {
      if (element.hidden) handle.open();
      else handle.close();
    },
    close() {
      element.hidden = true;
    },
  };

  handle.setOn(options.on);
  handle.setBasemap(options.basemap);
  // Rows are built once and patched, so one pass plus the ready subscription covers the panel.
  teach(element);
  return handle;
}

interface LayerRow {
  element: HTMLElement;
  setOn(on: boolean): void;
  setZoom(zoom: number): void;
  setEmpty(empty: boolean): void;
  setProvenance(derivationId: string): void;
  setCrossing(box: Bbox, resolved: string | null, extentOff: boolean): void;
  setForcedOpen(open: boolean): void;
  /** What the parent aggregates over: drawn here, and drawing nothing here. */
  isOn(): boolean;
  isEmpty(): boolean;
}

interface LayerFamilySection {
  element: HTMLElement;
  rows: Map<string, LayerRow>;
  setOn(on: ReadonlySet<string>): void;
  /** Re-reads the members after anything that can move their marks: zoom, coverage, a toggle. */
  refresh(): void;
  setFiltered(filtering: boolean): void;
}

interface LayerGroupSection {
  element: HTMLElement;
  rows: Map<string, LayerRow>;
  setOn(on: ReadonlySet<string>): void;
  refreshFamilies(): void;
  setFiltered(filtering: boolean): void;
}

/**
 * A group opens if the reader is already drawing something inside it. Twelve rows and a
 * basemap switcher overflow the sheet on a phone, and the groups nobody has switched on are
 * the ones worth costing a click rather than a scroll.
 */
function buildGroup(
  id: string,
  label: string,
  entries: readonly GroupEntry[],
  options: LayerPanelOptions,
): LayerGroupSection {
  const element = document.createElement("div");
  element.className = "gw-layer-group";
  element.dataset["group"] = id;

  const head = document.createElement("button");
  head.type = "button";
  head.className = "gw-layer-group-head";
  head.setAttribute("data-no-glossary", "");
  const heading = document.createElement("span");
  heading.className = "gw-layer-group-label";
  heading.textContent = label;
  head.appendChild(heading);

  const count = document.createElement("span");
  count.className = "gw-layer-group-count";
  count.hidden = true;
  head.appendChild(count);
  element.appendChild(head);

  const body = document.createElement("div");
  body.className = "gw-layer-group-body";
  body.id = `gw-layer-group-${id}`;
  head.setAttribute("aria-controls", body.id);

  const rows = new Map<string, LayerRow>();
  const families: LayerFamilySection[] = [];
  const layers: LayerDef[] = [];
  for (const entry of entries) {
    if (entry.kind === "layer") {
      const row = buildRow(entry.layer, options);
      body.appendChild(row.element);
      rows.set(entry.layer.id, row);
      layers.push(entry.layer);
      continue;
    }
    const family = buildFamily(entry.family, entry.layers, options);
    for (const [memberId, row] of family.rows) rows.set(memberId, row);
    body.appendChild(family.element);
    families.push(family);
    layers.push(...entry.layers);
  }
  element.appendChild(body);

  let chosen = layers.some((layer) => options.on.has(layer.id));
  let forced = false;
  function applyDisclosure(): void {
    const open = chosen || forced;
    body.hidden = !open;
    head.setAttribute("aria-expanded", String(open));
  }
  head.addEventListener("click", () => {
    chosen = !chosen;
    forced = false;
    applyDisclosure();
  });
  applyDisclosure();

  return {
    element,
    rows,
    setOn(on) {
      for (const family of families) family.setOn(on);
      const drawn = layers.filter((layer) => on.has(layer.id)).length;
      count.hidden = drawn === 0;
      // Switches in this panel, not a figure about the ground: no derivation resolves it.
      // Members are counted one by one, so a shut family cannot hide four switches behind one.
      count.textContent = `${drawn} on`;
    },
    refreshFamilies() {
      for (const family of families) family.refresh();
    },
    setFiltered(filtering) {
      for (const family of families) family.setFiltered(filtering);
      const matched = [...rows.values()].filter((row) => !row.element.hidden).length;
      element.hidden = filtering && matched === 0;
      forced = filtering && matched > 0;
      applyDisclosure();
    },
  };
}

/**
 * The parent, and the members it governs. North Dakota was the unmarked default here only
 * because it was ingested first; the parent is what replaces that accident with a structure —
 * one switch for all states, one row each beneath it.
 *
 * It is derived, never stored: `familyState()` reads the members on every render, so a
 * capability set written before this existed restores untouched (persist.test.ts).
 */
function buildFamily(
  family: LayerFamily,
  layers: readonly LayerDef[],
  options: LayerPanelOptions,
): LayerFamilySection {
  const element = document.createElement("div");
  element.className = "gw-layer-family";
  element.dataset["family"] = family.id;

  // `.gw-layer-row` as well as its own class: the row grid aligns the parent with its siblings,
  // and tests/e2e/chrome-fold.mjs measures this element against the fold like any other row.
  const head = document.createElement("div");
  head.className = "gw-layer-row gw-layer-family-head";
  head.setAttribute("data-no-glossary", "");

  // No swatch of its own. Four regulators draw four colours, and one mark here would predict a
  // canvas three of them contradict — the spacer keeps the parent's label on the siblings' rule.
  const spacer = document.createElement("span");
  spacer.className = "gw-layer-swatch gw-layer-swatch-none";
  head.appendChild(spacer);

  const name = document.createElement("button");
  name.type = "button";
  name.className = "gw-layer-name gw-layer-family-name";
  const label = document.createElement("span");
  label.className = "gw-layer-label";
  label.textContent = family.label;
  name.appendChild(label);

  // Only while the parent is mixed. All-on and all-off are already on the switch, and a count
  // standing beside a switch that says the same thing is a second reading of one fact.
  const count = document.createElement("span");
  count.className = "gw-layer-family-count";
  count.hidden = true;
  name.appendChild(count);

  const empty = document.createElement("span");
  empty.className = "gw-layer-empty";
  empty.hidden = true;
  empty.textContent = "none here";
  name.appendChild(empty);
  head.appendChild(name);

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "gw-layer-toggle gw-layer-family-toggle";
  // A <button> with aria-pressed="mixed", not a checkbox with .indeterminate: it is the only
  // tri-state the panel's own switch idiom already renders, it serialises into the DOM so a
  // gate can read it, and Enter and Space operate it with no key handler of this module's own.
  toggle.setAttribute("aria-label", `Show every ${family.childAxis}'s ${family.label.toLowerCase()}`);
  head.appendChild(toggle);
  element.appendChild(head);

  const body = document.createElement("div");
  body.className = "gw-layer-family-body";
  body.id = `gw-layer-family-${family.id}`;
  name.setAttribute("aria-controls", body.id);

  const rows = new Map<string, LayerRow>();
  for (const layer of layers) {
    const row = buildRow(layer, options, family);
    body.appendChild(row.element);
    rows.set(layer.id, row);
  }
  element.appendChild(body);

  // Shut on first paint whatever the members say, unlike a group. Every member is on by
  // default, so "open when something inside is on" would never shut it, and the four rows it
  // would cost are the four the parent exists to spare a reader who does not care which state.
  let chosen = false;
  let forced = false;
  function applyDisclosure(): void {
    const open = chosen || forced;
    body.hidden = !open;
    name.setAttribute("aria-expanded", String(open));
  }
  name.addEventListener("click", () => {
    chosen = !chosen;
    forced = false;
    applyDisclosure();
  });
  applyDisclosure();

  let state: boolean | "mixed" = false;
  // Mixed resolves upward, then all-on falls to all-off: the parent is a two-step cycle whose
  // third value is a report and never a destination. Filling up first is the additive move and
  // it is the one a further click undoes.
  toggle.addEventListener("click", () => {
    const next = state !== true;
    for (const layer of layers) options.onToggle(layer.id, next);
  });

  function refresh(): void {
    const drawn = [...rows.values()].filter((row) => row.isOn());
    // True of the parent only where it is true of every member drawing: a family with one
    // member painting is not empty, and the reader opens it to see which one.
    const blank = drawn.length > 0 && drawn.every((row) => row.isEmpty());
    empty.hidden = !blank;
    if (blank) head.setAttribute("data-empty", "true");
    else head.removeAttribute("data-empty");
  }

  return {
    element,
    rows,
    setOn(on) {
      state = familyState(family.id, on);
      toggle.setAttribute("aria-pressed", state === "mixed" ? "mixed" : String(state));
      head.dataset["on"] = String(state);
      const drawn = layers.filter((layer) => on.has(layer.id)).length;
      count.hidden = state !== "mixed";
      count.textContent = `${drawn} of ${layers.length}`;
      refresh();
    },
    refresh,
    setFiltered(filtering) {
      const matched = [...rows.values()].filter((row) => !row.element.hidden).length;
      // The parent's own row goes with its members: a header standing over nothing is worse
      // than no header, and a hit inside a shut family is a hit the reader cannot see.
      element.hidden = filtering && matched === 0;
      forced = filtering && matched > 0;
      applyDisclosure();
    },
  };
}

// Full name → registered code, generated from the registry. A fifth jurisdiction tags its own
// rows without an edit here, and the panel cannot spell one differently from the map.
const STATE_ABBREVIATION: Readonly<Record<string, string>> = ABBREVIATION;

/** `Survey traces (North Dakota)` → the noun and the jurisdiction that scopes it, separately. */
export function splitScope(label: string): { name: string; scope: string | null } {
  const match = /^(.*?)\s*\(([^()]+)\)\s*$/.exec(label);
  if (!match?.[1] || !match[2]) return { name: label, scope: null };
  return { name: match[1], scope: match[2] };
}

function buildRow(layer: LayerDef, options: LayerPanelOptions, family?: LayerFamily): LayerRow {
  const element = document.createElement("div");
  element.className = family ? "gw-layer-row gw-layer-row-child" : "gw-layer-row";
  element.dataset["layer"] = layer.id;
  // Under a parent the row reads by the axis it divides on; the parent above already carries
  // the noun, and repeating it would put "Wells" four times under a row that says "Wells".
  const rowLabel = family ? (layer.familyLabel ?? layer.label) : layer.label;

  const swatch = document.createElement("span");
  swatch.className = "gw-layer-swatch";
  swatch.appendChild(layerSwatch(layer.swatch));
  element.appendChild(swatch);

  // The disclosure, not a <label>: the row deliberately forwards no activation to the toggle,
  // and this control asks what a layer is made of rather than switching it.
  const name = document.createElement("button");
  name.type = "button";
  name.className = "gw-layer-name";
  // The name is the disclosure control; the subtitle inside it is where the words are taught.
  name.setAttribute("data-no-glossary", "");
  const named = splitScope(rowLabel);
  const label = document.createElement("span");
  label.className = "gw-layer-label";
  label.textContent = named.name;
  label.title = rowLabel;
  name.appendChild(label);
  // "Survey traces (North Dakota)" wrapped to two lines and made its row 10 px taller than
  // the one above it. The jurisdiction is a scope, not part of the noun, so it reads as one.
  if (named.scope) {
    const scopeTag = document.createElement("span");
    scopeTag.className = "gw-layer-jurisdiction";
    scopeTag.title = named.scope;
    scopeTag.textContent = STATE_ABBREVIATION[named.scope] ?? named.scope;
    name.appendChild(scopeTag);
  }

  const badge = document.createElement("span");
  badge.className = "gw-layer-badge";
  // Every source on a row shares one kind — registry.test.ts refuses a row where they do not,
  // and refuses a row with no source at all.
  const kind = layer.provenance[0]?.kind ?? "official";
  badge.dataset["kind"] = kind;
  badge.textContent = kind;
  name.appendChild(badge);

  // The out-of-scale *state* stays in the collapsed row; the sentence explaining it goes in
  // the disclosure with the rest of the prose. Six of twelve rows are out of scale at the
  // opening zoom, and their two-line hints were 43 px of row each.
  const scale = document.createElement("span");
  scale.className = "gw-layer-scale";
  scale.hidden = true;
  scale.textContent = `zoom ${layer.minZoom}+`;
  name.appendChild(scale);

  // Present, switched on, in scale, and painting nothing. Hiding the row would be a claim the
  // layer does not exist; letting it look drawn would be a claim the ground is empty.
  const empty = document.createElement("span");
  empty.className = "gw-layer-empty";
  empty.hidden = true;
  empty.textContent = "none here";
  name.appendChild(empty);
  element.appendChild(name);

  const text = document.createElement("div");
  text.className = "gw-layer-detail";
  text.id = `gw-layer-detail-${layer.id}`;
  text.hidden = true;
  name.setAttribute("aria-controls", text.id);

  const subtitle = document.createElement("p");
  subtitle.className = "gw-layer-sub";
  // Split rather than interpolated, so the served count keeps its own node and its own handle:
  // the number is patched in when the registry answers, and the prose around it never moves.
  const [opening, ...rest] = layer.subtitle.split(COUNT_SLOT);
  const count = document.createElement("span");
  count.className = "gw-layer-count";
  const countHandle = explainHandle({
    className: "gw-layer-count-handle",
    label: `the ${layer.label.toLowerCase()} count`,
  });
  subtitle.append(opening ?? layer.subtitle);
  if (rest.length > 0) subtitle.append(count, rest.join(COUNT_SLOT), countHandle);
  if (layer.snapshot) {
    subtitle.appendChild(
      explainHandle({
        className: "gw-layer-snapshot",
        label: `the ${layer.label.toLowerCase()} counts`,
        handle: layer.snapshot,
      }),
    );
  }
  text.appendChild(subtitle);

  /** The served count, or the pending mark: a row states no number it cannot resolve. */
  function paintCount(): void {
    if (rest.length === 0) return;
    const measured = layer.jurisdiction ? measuredJurisdiction(layer.jurisdiction) : null;
    count.textContent = measured === null ? PENDING_MARK : NUMBER.format(measured.wells);
    count.title = measured?.measuredOn
      ? `Measured ${measured.measuredOn}, from the jurisdiction registry`
      : "No well count has been measured for this jurisdiction yet.";
    setExplainHandle(countHandle, measured?.handle ?? null);
    if (!element.hasAttribute("data-out-of-scale")) element.title = subtitleText(layer);
  }
  paintCount();
  // The panel is built before the map has asked the registry anything, so the row paints what
  // is resident and repaints when the answer lands. It never paints a compiled-in count.
  void loadCensus().then(paintCount);

  // Only where the row draws more than one. With a single source the subtitle already names
  // it, and the line would say nothing the row has not said; with two, the subtitle can carry
  // what they share and nothing else, so this is where "which file did that line come from"
  // is answered.
  if (layer.provenance.length > 1) {
    for (const source of layer.provenance) {
      const line = document.createElement("p");
      line.className = "gw-layer-source";
      // A file name and a row count, on notes.ts's precedent: machine detail, not vocabulary.
      line.setAttribute("data-no-glossary", "");
      line.textContent = source.label ? `${source.label} · ${source.source}` : source.source;
      text.appendChild(line);
    }
  }

  // The same handle the legend and the thematic key resolve in one click, on the surface a
  // reader reaches a layer's provenance from.
  const derivation = explainHandle({
    className: "gw-layer-derivation",
    label: `the ${layer.label.toLowerCase()} geometry`,
  });
  derivation.setAttribute("data-no-glossary", "");
  text.appendChild(derivation);

  // §2.6's fourth row. `ⓘ` is in none of the three faces this product ships, so the affordance
  // is the sentence rather than a glyph that would render as tofu (guardrails.test.ts F5).
  let landing: Crossing | null = null;
  const crossing = document.createElement("a");
  crossing.className = "gw-layer-crossing";
  crossing.hidden = true;
  crossing.addEventListener("click", (event) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    if (landing) cross(landing);
  });
  text.appendChild(crossing);

  const behind = document.createElement("p");
  behind.className = "gw-layer-nocollection";
  behind.hidden = layer.collection !== null;
  behind.textContent = "No served collection carries this layer. It is drawn from tiles only.";
  text.appendChild(behind);

  const hint = document.createElement("p");
  hint.className = "gw-layer-hint";
  hint.hidden = true;
  hint.textContent = layer.zoomHint ?? "";
  text.appendChild(hint);

  const emptyReason = document.createElement("p");
  emptyReason.className = "gw-layer-empty-reason";
  emptyReason.hidden = true;
  emptyReason.textContent =
    "Nothing from this layer is drawn in this view. Pan or zoom to where it publishes.";
  text.appendChild(emptyReason);

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "gw-layer-toggle";
  toggle.setAttribute("aria-label", `Show ${layer.label}`);
  toggle.setAttribute("data-no-glossary", "");
  toggle.addEventListener("click", () => {
    options.onToggle(layer.id, toggle.getAttribute("aria-pressed") !== "true");
  });
  element.appendChild(toggle);

  const opacity = document.createElement("input");
  opacity.type = "range";
  opacity.className = "gw-layer-opacity";
  opacity.min = "10";
  opacity.max = "100";
  opacity.step = "5";
  opacity.value = String(Math.round(layer.opacity * 100));
  opacity.setAttribute("aria-label", `${layer.label} opacity`);
  opacity.addEventListener("input", () => {
    options.onOpacity(layer.id, Number(opacity.value) / 100);
  });
  text.appendChild(opacity);
  element.appendChild(text);

  // Two independent reasons a row can be open, so the filter closing again cannot shut a row
  // the reader opened themselves.
  let chosen = false;
  let forced = false;
  function applyDisclosure(): void {
    const open = chosen || forced;
    text.hidden = !open;
    name.setAttribute("aria-expanded", String(open));
  }
  name.addEventListener("click", () => {
    chosen = !chosen;
    applyDisclosure();
  });
  applyDisclosure();

  let drawn = false;
  let blank = false;
  function setEmptyState(next: boolean): void {
    blank = next;
    empty.hidden = !next;
    emptyReason.hidden = !next;
    if (next) element.setAttribute("data-empty", "true");
    else element.removeAttribute("data-empty");
  }

  return {
    element,
    isOn: () => drawn,
    isEmpty: () => blank,
    setForcedOpen(open) {
      forced = open;
      applyDisclosure();
    },
    setOn(on) {
      drawn = on;
      toggle.setAttribute("aria-pressed", String(on));
      element.dataset["on"] = String(on);
      // A row nobody is drawing cannot be empty; the mark would outlive the reason for it.
      if (!on) setEmptyState(false);
    },
    setZoom(zoom) {
      const outOfScale = layer.minZoom > 0 && zoom < layer.minZoom;
      hint.hidden = !outOfScale;
      scale.hidden = !outOfScale;
      if (outOfScale) {
        element.setAttribute("data-out-of-scale", "true");
        element.title = layer.zoomHint ?? `Visible at zoom ${layer.minZoom} and above`;
        // Out of scale already explains the blank canvas; two marks would be two reasons.
        setEmptyState(false);
      } else {
        element.removeAttribute("data-out-of-scale");
        element.title = subtitleText(layer);
      }
    },
    setEmpty(next) {
      setEmptyState(next && !element.hasAttribute("data-out-of-scale"));
    },
    setProvenance(derivationId) {
      setExplainHandle(derivation, derivationId);
      // The row spells the affordance out rather than wearing the bare glyph (map.css).
      derivation.textContent = `⌾ geometry build ${derivationId}`;
    },
    setCrossing(box, resolved, extentOff) {
      // Rebuilt rather than patched: the box is half the destination, so a stale href would be
      // a link to the viewport the reader left. The row is a <label>-free container, so the
      // anchor keeps its own click and never reaches the toggle beside it.
      landing = whatsBehindThisLayer(layer.collection, box, { state: readState(), resolved }, extentOff);
      crossing.hidden = landing === null;
      if (!landing) return;
      applyCrossing(crossing, landing);
    },
  };
}
