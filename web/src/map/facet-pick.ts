import { parseState } from "../app/state.ts";
import { WELLS_BY_PREFIX, panelState } from "../explore/facets/wells-by.ts";
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
