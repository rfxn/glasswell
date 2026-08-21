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
      row.element.hidden = term.length > 0 && !haystack.includes(term);
    }
  });

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
}

function buildRow(layer: LayerDef, options: LayerPanelOptions): LayerRow {
  const element = document.createElement("div");
  element.className = "gw-layer-row";
  element.dataset["layer"] = layer.id;

  const swatch = document.createElement("span");
  swatch.className = "gw-layer-swatch";
  swatch.appendChild(layerSwatch(layer.swatch));
  element.appendChild(swatch);

  const text = document.createElement("div");
  text.className = "gw-layer-text";
  const label = document.createElement("p");
  label.className = "gw-layer-label";
  label.textContent = layer.label;

  const badge = document.createElement("span");
  badge.className = "gw-layer-badge";
  // Every source on a row shares one kind — registry.test.ts refuses a row where they do not.
  const kind = layer.provenance[0]?.kind ?? "pending";
  badge.dataset["kind"] = kind;
  badge.textContent = kind;
  label.appendChild(badge);
  text.appendChild(label);

  const subtitle = document.createElement("p");
  subtitle.className = "gw-layer-sub";
  subtitle.textContent = layer.pendingSource
    ? `${layer.subtitle} — source not ingested`
    : layer.subtitle;
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

  const hint = document.createElement("p");
  hint.className = "gw-layer-hint";
  hint.hidden = true;
  hint.textContent = layer.zoomHint ?? "";
  text.appendChild(hint);

  const derivation = document.createElement("p");
  derivation.className = "gw-layer-derivation";
  derivation.hidden = true;
  text.appendChild(derivation);
  element.appendChild(text);

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
  element.appendChild(opacity);

  return {
    element,
    setOn(on) {
      toggle.setAttribute("aria-pressed", String(on));
      element.dataset["on"] = String(on);
    },
    setZoom(zoom) {
      const outOfScale = layer.minZoom > 0 && zoom < layer.minZoom;
      hint.hidden = !outOfScale;
      if (outOfScale) {
        element.setAttribute("data-out-of-scale", "true");
        element.title = layer.zoomHint ?? `Visible at zoom ${layer.minZoom} and above`;
      } else {
        element.removeAttribute("data-out-of-scale");
        element.title = layer.subtitle;
      }
    },
    setProvenance(derivationId) {
      derivation.hidden = false;
      derivation.textContent = `geometry build ${derivationId}`;
    },
  };
}
