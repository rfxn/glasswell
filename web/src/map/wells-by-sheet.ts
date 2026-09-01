import { parseState } from "../app/state.ts";
import { registerOverlay } from "../chrome/overlays.ts";
import { DIMENSIONS, mountWellsBy, panelState } from "../explore/facets/wells-by.ts";
import type { FacetBucket, WellFacets } from "../explore/facets/wells-by.ts";
import { appliedFilters } from "./facet-pick.ts";
import { facetFilterable } from "./style.ts";

export const WELLS_BY_SHEET_ID = "gw-wells-by";

/** The map's second refusal, beside the collection's own: this dimension is on no tile layer. */
const TILE_UNFILTERABLE =
  "The tiles carry no column for this dimension, so the canvas cannot be narrowed by it here.";

/** The mirror of the legend's cross-reference. Two scopes of one question, not two answers. */
const CROSSREF_COPY = "The map key counts the map view instead, and moves when you pan.";

export interface WellsBySheetOptions {
  /** The query string the panel reads its question and its press out of. */
  search?(): string;
  /** Commits a panel term. The host owns the history mode, because it owns the URL. */
  setPanel(values: Record<string, string | null>, mode: "push" | "replace"): void;
  /** A bucket pressed, or null where the pressed one was pressed again to release it. */
  onPick(value: string | null, bucket: FacetBucket | null): void;
  /** Asked to open. The host shuts the sibling sheet before this one appears. */
  onOpen?(): void;
}

export interface WellsBySheetHandle {
  element: HTMLElement;
  open(): void;
  close(): void;
  toggle(): void;
  /** Re-asks the panel's question, after the URL it reads has moved. */
  refresh(): void;
}

/**
 * The whole-state scope of Wells by, on the map. A sibling of the layer panel rather than a
 * second design: same frame, same column, same open-one-at-a-time rule, and the panel inside it
 * is the explorer's own component with a host's three seams filled in — the map has no grid to
 * narrow, so a press becomes a canvas filter instead of a filter chip.
 */
export function createWellsBySheet(options: WellsBySheetOptions): WellsBySheetHandle {
  const search = options.search ?? (() => window.location.search);

  const element = document.createElement("section");
  element.className = "gw-sheet gw-wells-by-sheet";
  element.id = WELLS_BY_SHEET_ID;
  element.hidden = true;
  element.setAttribute("aria-label", "Wells by");

  const head = document.createElement("header");
  head.className = "gw-sheet-head";
  const heading = document.createElement("h2");
  heading.textContent = "Wells by";
  head.appendChild(heading);

  const close = document.createElement("button");
  close.type = "button";
  close.className = "gw-sheet-close";
  close.textContent = "✕";
  close.setAttribute("aria-label", "Close the Wells by panel");
  close.addEventListener("click", () => handle.close());
  head.appendChild(close);
  element.appendChild(head);

  const crossref = document.createElement("p");
  crossref.className = "gw-sheet-crossref";
  crossref.textContent = CROSSREF_COPY;
  element.appendChild(crossref);

  const body = document.createElement("div");
  body.className = "gw-sheet-body";
  element.appendChild(body);

  const host = document.createElement("div");
  host.className = "gw-wells-by";
  body.appendChild(host);

  // The same contract layer-panel.ts states: the control that opens this is a MapLibre control
  // built by map.ts and never handed here, and main.ts's Escape ladder hides the element rather
  // than calling the handle — so the state it announces is read back off the attribute.
  function syncTrigger(): void {
    for (const trigger of document.querySelectorAll<HTMLElement>(".gw-wells-by-button")) {
      trigger.setAttribute("aria-expanded", String(!element.hidden));
      trigger.setAttribute("aria-controls", element.id);
    }
  }
  new MutationObserver(syncTrigger).observe(element, {
    attributes: true,
    attributeFilter: ["hidden"],
  });
  queueMicrotask(syncTrigger);
  registerOverlay(element);

  let pending: AbortController | null = null;
  /** The rendered buckets, so a press can hand back the figure the panel served for it. */
  let rendered: FacetBucket[] = [];

  function mount(): void {
    pending?.abort();
    pending = new AbortController();
    const where = search();
    void mountWellsBy(host, {
      state: parseState(where),
      applied: appliedFilters(where),
      signal: pending.signal,
      // A dimension no tile layer publishes a column for is a label, not a control: the press
      // would narrow nothing on the canvas, which is what the press is for here.
      bucketAffordance: (dimension) =>
        facetFilterable(dimension) ? { press: true } : { press: false, title: TILE_UNFILTERABLE },
      scopeNote: (data: WellFacets) => {
        rendered = data.buckets;
        return (
          `Counted over every current well in ${data.state_name}.` +
          " This does not move when you pan."
        );
      },
      hooks: {
        setPanel: (values, mode) => options.setPanel(values, mode),
        // The map has no grid, so a bucket's filters become one press rather than a filter set.
        // The un-press path sends the same names with no values, which reads back as null here.
        applyFilter: (filters) => {
          const name = DIMENSIONS.find((entry) => entry.id === dimensionOf(where))?.filter;
          const value = (name ? filters[name]?.[0] : undefined) ?? null;
          options.onPick(
            value,
            value === null ? null : (rendered.find((bucket) => bucket.value === value) ?? null),
          );
        },
      },
    });
  }

  const handle: WellsBySheetHandle = {
    element,
    open() {
      options.onOpen?.();
      element.hidden = false;
      mount();
    },
    close() {
      element.hidden = true;
      pending?.abort();
      pending = null;
    },
    toggle() {
      if (element.hidden) handle.open();
      else handle.close();
    },
    refresh() {
      if (!element.hidden) mount();
    },
  };
  return handle;
}

function dimensionOf(search: string): string {
  return panelState(parseState(search))["by"] as string;
}
