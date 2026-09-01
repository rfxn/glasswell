import { parseState } from "../app/state.ts";
import { DIMENSIONS, WELLS_BY_PREFIX, panelState } from "../explore/facets/wells-by.ts";
import type { FacetSelection } from "./style.ts";

/**
 * The bucket a reader pressed, in the URL and nowhere else.
 *
 * It rides the `wb.` prefix the Explore panel already uses, so a reader who set `wb.state`,
 * `wb.by` and `wb.top` there and crossed to the map arrives at the same panel rather than at
 * its defaults. `wb.pick` is the one term the map adds: which bucket the canvas is narrowed to.
 */
export const PICK_PARAM = `${WELLS_BY_PREFIX}pick`;

/**
 * The press a query string carries, or null for none. The dimension is `panelState`'s, not a
 * second copy of the default — `?wb.pick=HESS` with no `wb.by` is an operator press because
 * `operator` is what the panel opens on, and two files disagreeing about that would put the
 * pill's dimension and the canvas's on different columns.
 */
export function facetFromSearch(search: string): FacetSelection | null {
  const value = new URLSearchParams(search).get(PICK_PARAM);
  if (value === null || value === "") return null;
  return { dimension: panelState(parseState(search))["by"] as string, value };
}

/**
 * Everything the URL says about the Wells-By panel, as one comparable string. The map follows
 * `popstate` so a back press undoes a press, and this is how a history move it has no stake in —
 * a well card, a lineage drawer — costs neither a filter rewrite nor a re-mount of the sheet.
 */
export function wellsByTerms(search: string): string {
  return [...new URLSearchParams(search)]
    .filter(([key]) => key.startsWith(WELLS_BY_PREFIX))
    .map(([key, value]) => `${key}=${value}`)
    .sort()
    .join("&");
}

/**
 * The press in the shape `narrowedBy` compares against: the `/v1/wells` filter the pressed
 * dimension becomes, and the state it was counted in — which is exactly what `_bucket_link`
 * publishes, so the pressed bucket matches its own link and no other. Empty where nothing is
 * pressed, or where the dimension is one the collection accepts no filter for.
 */
export function appliedFilters(search: string): Record<string, string[]> {
  const facet = facetFromSearch(search);
  if (!facet) return {};
  const name = DIMENSIONS.find((entry) => entry.id === facet.dimension)?.filter;
  if (!name) return {};
  return { [name]: [facet.value], state: [panelState(parseState(search))["state"] as string] };
}
