import { explainHandle, setExplainHandle } from "../chrome/handle.ts";
import type { Figure } from "../api/envelope.ts";
import { DIMENSIONS } from "../explore/facets/wells-by.ts";
import { LAYERS } from "./registry.ts";
import { TILE_THIN_MAX_ZOOM, TILE_THIN_PIXELS, facetUnfilteredLayers } from "./style.ts";

const NUMBER = new Intl.NumberFormat("en-US");

/** The bucket the canvas is narrowed to, with the panel's own figure for it — never a census. */
export interface AppliedBucket {
  dimension: string;
  value: string;
  /**
   * What the Wells-By panel served for this bucket. Null where the panel has not answered —
   * a shared link restores the press before the sheet is ever opened — and the pill then shows
   * the press with no number rather than counting the canvas to fill the space. The canvas is a
   * sample below zoom 8 and a viewport above it, so a number off it would move with the map.
   */
  wells: Figure | null;
}

export interface FacetPillOptions {
  onClear(): void;
  onOpen(): void;
}

export interface FacetPillHandle {
  element: HTMLElement;
  set(applied: AppliedBucket | null): void;
  setZoom(zoom: number): void;
}

/**
 * What the canvas is narrowed to, said on the canvas. The sheet can be shut — on a phone it
 * covers the map — so the press has to be visible and releasable without opening it, and the
 * two conditions that make the filtered canvas less than it looks have to travel with it.
 */
export function createFacetPill(options: FacetPillOptions): FacetPillHandle {
  const element = document.createElement("div");
  element.className = "gw-facet-pill";
  element.hidden = true;
  element.setAttribute("role", "status");

  const head = document.createElement("div");
  head.className = "gw-facet-pill-head";
  element.appendChild(head);

  const open = document.createElement("button");
  open.type = "button";
  open.className = "gw-facet-pill-open";
  open.addEventListener("click", () => options.onOpen());
  head.appendChild(open);

  const label = document.createElement("span");
  label.className = "gw-facet-pill-label";
  open.appendChild(label);

  const count = document.createElement("span");
  count.className = "gw-facet-pill-count";
  open.appendChild(count);

  const handle = explainHandle({ className: "gw-facet-pill-handle", label: "this bucket's count" });
  head.appendChild(handle);

  const clear = document.createElement("button");
  clear.type = "button";
  clear.className = "gw-facet-pill-x";
  clear.textContent = "✕";
  clear.setAttribute("aria-label", "Stop narrowing the map to this value");
  clear.addEventListener("click", () => options.onClear());
  head.appendChild(clear);

  const partial = document.createElement("p");
  partial.className = "gw-facet-pill-partial";
  partial.hidden = true;
  element.appendChild(partial);

  const thin = document.createElement("p");
  thin.className = "gw-facet-pill-thin";
  thin.hidden = true;
  thin.textContent = thinNote();
  element.appendChild(thin);

  let applied: AppliedBucket | null = null;
  let zoomNow = Number.POSITIVE_INFINITY;

  function render(): void {
    element.hidden = applied === null;
    // Below the thinning ceiling the tiles are a sample whatever is pressed, so the line is
    // about the zoom rather than about the press — but it is only worth saying beside one.
    thin.hidden = applied === null || zoomNow > TILE_THIN_MAX_ZOOM;
    if (!applied) return;
    label.textContent = `${dimensionLabel(applied.dimension)} · ${applied.value}`;
    open.title = `Open Wells by, on ${applied.value}`;
    count.textContent = applied.wells ? NUMBER.format(Number(applied.wells.value)) : "";
    setExplainHandle(handle, applied.wells?.d ?? null);
    const unfiltered = unfilteredNote(applied.dimension);
    partial.hidden = unfiltered === null;
    partial.textContent = unfiltered ?? "";
  }

  render();
  return {
    element,
    set(next) {
      applied = next;
      render();
    },
    setZoom(next) {
      zoomNow = next;
      render();
    },
  };
}

function dimensionLabel(id: string): string {
  return DIMENSIONS.find((entry) => entry.id === id)?.label ?? id;
}

/**
 * The layers this press does not reach, named. `well_type_reported` is on no line layer and
 * `county_code` is on neither North Dakota's nor Montana's, so a press on either narrows some of
 * the canvas and leaves the rest whole — a difference the reader would otherwise have to notice.
 */
function unfilteredNote(dimension: string): string | null {
  const rows = facetUnfilteredLayers(dimension)
    .map((id) => LAYERS.find((layer) => layer.styleLayers.includes(id))?.label)
    .filter((label): label is string => typeof label === "string");
  const named = [...new Set(rows)];
  if (named.length === 0) return null;
  return `${sentenceList(named)} ${named.length === 1 ? "is" : "are"} not filtered: this dimension is not on those tile layers.`;
}

/** `THIN_PIXELS` as English. 0.5 is the only value the gate approved, and it says "half". */
function thinNote(): string {
  const share = TILE_THIN_PIXELS === 0.5 ? "half pixel" : `${TILE_THIN_PIXELS} of a pixel`;
  return `The map is a sample below zoom ${TILE_THIN_MAX_ZOOM + 1}: the tiles keep one well per ${share}, so what is drawn is a sample of what is filtered.`;
}

function sentenceList(items: string[]): string {
  if (items.length <= 1) return items[0] ?? "";
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}
