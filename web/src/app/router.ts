import type { AppState, ViewMode } from "./state.ts";
import { filtersOf, withFilter } from "../explore/router.ts";

const WELL_FILTER = "q";
const API10 = /^\d{10}$/;

/**
 * Cross-surface state has one deliberate bridge: Map and Explore translate an API-10
 * selection into the equivalent wells filter. Status preserves route context but never
 * interprets it, so an Explorer query cannot become a map selection by passing through it.
 */
export function crossTo(view: ViewMode, state: AppState): AppState {
  if (view === state.view) return state;
  if (view === "status" || state.view === "status") {
    return { ...state, view, well: null, explain: null };
  }
  if (view === "explore") {
    if (!state.well) return { ...state, view };
    return withFilter(
      { ...state, view, well: null, explain: null, ds: state.ds ?? "wells" },
      WELL_FILTER,
      [state.well],
    );
  }
  const carried = filtersOf(state)[WELL_FILTER];
  const api10 = carried?.length === 1 ? carried[0] : undefined;
  if (state.ds !== "wells" || api10 === undefined || !API10.test(api10)) return { ...state, view };
  return withFilter({ ...state, view, well: api10 }, WELL_FILTER, []);
}
