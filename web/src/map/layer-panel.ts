import "./layer-panel.css";

import { readState } from "../app/state.ts";
import { explainHandle, setExplainHandle } from "../chrome/handle.ts";
import { registerOverlay } from "../chrome/overlays.ts";
import { applyCrossing, cross, whatsBehindThisLayer } from "../explore/bridge.ts";
import type { Bbox, Crossing } from "../explore/bridge.ts";
import { BASEMAPS } from "./basemap.ts";
import { LAYERS, defaultLayerSet } from "./registry.ts";
import type { LayerDef } from "./registry.ts";
import { layerSwatch } from "./swatch.ts";

export interface LayerPanelOptions {
  on: ReadonlySet<string>;
  basemap: string;
  onToggle(id: string, next: boolean): void;
  onOpacity(id: string, value: number): void;
  onBasemap(id: string): void;
  onReset?(next: Set<string>): void;
}

export interface LayerPanelHandle {
  element: HTMLElement;
  setOn(on: ReadonlySet<string>): void;
  setZoom(zoom: number): void;
  setBasemap(id: string): void;
  setProvenance(id: string, derivationId: string): void;
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
  element.className = "gw-layers";
  element.id = "gw-layers";
  element.hidden = true;
  element.setAttribute("aria-label", "Map layers");

  const head = document.createElement("header");
  head.className = "gw-layers-head";
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
  for (const layer of LAYERS) {
    const row = buildRow(layer, options);
    bodyElement.appendChild(row.element);
    rows.set(layer.id, row);
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
    },
    setZoom(zoom) {
      for (const row of rows.values()) row.setZoom(zoom);
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
      element.hidden = false;
    },
    close() {
      element.hidden = true;
    },
    toggle() {
      element.hidden = !element.hidden;
    },
  };

  handle.setOn(options.on);
  handle.setBasemap(options.basemap);
  return handle;
}

interface LayerRow {
  element: HTMLElement;
  setOn(on: boolean): void;
  setZoom(zoom: number): void;
  setProvenance(derivationId: string): void;
  setCrossing(box: Bbox, resolved: string | null, extentOff: boolean): void;
  setForcedOpen(open: boolean): void;
}

function buildRow(layer: LayerDef, options: LayerPanelOptions): LayerRow {
  const element = document.createElement("div");
  element.className = "gw-layer-row";
  element.dataset["layer"] = layer.id;

  const swatch = document.createElement("span");
  swatch.className = "gw-layer-swatch";
  swatch.appendChild(layerSwatch(layer.swatch));
  element.appendChild(swatch);

  // The disclosure, not a <label>: the row deliberately forwards no activation to the toggle,
  // and this control asks what a layer is made of rather than switching it.
  const name = document.createElement("button");
  name.type = "button";
  name.className = "gw-layer-name";
  const label = document.createElement("span");
  label.className = "gw-layer-label";
  label.textContent = layer.label;
  name.appendChild(label);

  const badge = document.createElement("span");
  badge.className = "gw-layer-badge";
  // Every source on a row shares one kind — registry.test.ts refuses a row where they do not.
  const kind = layer.provenance[0]?.kind ?? "pending";
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
  element.appendChild(name);

  const text = document.createElement("div");
  text.className = "gw-layer-detail";
  text.id = `gw-layer-detail-${layer.id}`;
  text.hidden = true;
  name.setAttribute("aria-controls", text.id);

  const subtitle = document.createElement("p");
  subtitle.className = "gw-layer-sub";
  subtitle.textContent = layer.pendingSource
    ? `${layer.subtitle} — source not ingested`
    : layer.subtitle;
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

  // Only where the row draws more than one. With a single source the subtitle already names
  // it, and the line would say nothing the row has not said; with two, the subtitle can carry
  // what they share and nothing else, so this is where "which file did that line come from"
  // is answered.
  if (layer.provenance.length > 1) {
    for (const source of layer.provenance) {
      const line = document.createElement("p");
      line.className = "gw-layer-source";
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
  behind.textContent = "No served collection carries this layer — it is drawn from tiles only.";
  text.appendChild(behind);

  const hint = document.createElement("p");
  hint.className = "gw-layer-hint";
  hint.hidden = true;
  hint.textContent = layer.zoomHint ?? "";
  text.appendChild(hint);

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "gw-layer-toggle";
  toggle.setAttribute("aria-label", `Show ${layer.label}`);
  toggle.disabled = Boolean(layer.pendingSource);
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
  opacity.disabled = Boolean(layer.pendingSource);
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

  return {
    element,
    setForcedOpen(open) {
      forced = open;
      applyDisclosure();
    },
    setOn(on) {
      toggle.setAttribute("aria-pressed", String(on));
      element.dataset["on"] = String(on);
    },
    setZoom(zoom) {
      const outOfScale = layer.minZoom > 0 && zoom < layer.minZoom;
      hint.hidden = !outOfScale;
      scale.hidden = !outOfScale;
      if (outOfScale) {
        element.setAttribute("data-out-of-scale", "true");
        element.title = layer.zoomHint ?? `Visible at zoom ${layer.minZoom} and above`;
      } else {
        element.removeAttribute("data-out-of-scale");
        element.title = layer.subtitle;
      }
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
