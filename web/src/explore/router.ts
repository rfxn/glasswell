import type { AppState, ViewMode } from "../app/state.ts";
import type { CatalogueDataset } from "./catalogue.ts";

/** §2.1: a filter is named for the API parameter it becomes, so the URL and the curl agree. */
export const FILTER_PREFIX = "f.";

// Hoisted by the shell rather than declared as facets (C1 MUST-KNOW M9): they narrow no
// dimension, they page and pin the walk.
const HOISTED = ["as_of", "cursor"] as const;

const WELL_FILTER = "q";
const API10 = /^\d{10}$/;

export interface ExploreRequest {
  operationId: string;
  path: string;
  query: Record<string, string[]>;
  /** Path parameters with no value yet: the dataset cannot be browsed until the reader picks one. */
  missing: string[];
}

export function filtersOf(state: AppState): Record<string, string[]> {
  const filters: Record<string, string[]> = {};
  for (const [key, values] of Object.entries(state.extra)) {
    if (key.startsWith(FILTER_PREFIX)) filters[key.slice(FILTER_PREFIX.length)] = values;
  }
  return filters;
}

export function withFilter(state: AppState, name: string, values: string[]): AppState {
  const extra = { ...state.extra };
  if (values.length === 0) delete extra[`${FILTER_PREFIX}${name}`];
  else extra[`${FILTER_PREFIX}${name}`] = [...values];
  return { ...state, extra };
}

export function requestFor(dataset: CatalogueDataset, state: AppState): ExploreRequest {
  const filters = filtersOf(state);
  const query: Record<string, string[]> = {};
  const missing: string[] = [];
  let path = dataset.path;

  for (const [name, values] of Object.entries(filters)) {
    if (!dataset.pathParameters.includes(name)) query[name] = values;
  }
  for (const name of dataset.pathParameters) {
    const value = filters[name]?.[0];
    if (value === undefined) missing.push(name);
    else path = path.replace(`{${name}}`, encodeURIComponent(value));
  }
  for (const name of HOISTED) {
    const values = state.extra[name];
    if (values && values.length > 0) query[name] = values;
  }
  return { operationId: dataset.operationId, path, query, missing };
}

/**
 * §2.6's two invariants: `as_of` always survives the crossing, and a selection crosses as the
 * narrowing that produced it rather than as a card floating over a grid.
 */
export function crossTo(view: ViewMode, state: AppState): AppState {
  if (view === state.view) return state;
  if (view === "explore") {
    if (!state.well) return { ...state, view };
    return withFilter({ ...state, view, well: null, explain: null, ds: state.ds ?? "wells" },
      WELL_FILTER,
      [state.well],
    );
  }
  const carried = filtersOf(state)[WELL_FILTER];
  const api10 = carried?.length === 1 ? carried[0] : undefined;
  if (state.ds !== "wells" || api10 === undefined || !API10.test(api10)) return { ...state, view };
  return withFilter({ ...state, view, well: api10 }, WELL_FILTER, []);
}
