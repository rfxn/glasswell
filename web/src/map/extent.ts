import type { Bbox } from "./counts.ts";

/**
 * The viewport as a named filter node (MAP-ROADMAP M1-2). The predicate lives in the URL —
 * `?extent=0` and nothing else — never in server state, so a shared link reconstructs the
 * population a figure was counted over instead of pointing at a session that no longer exists.
 */
export const EXTENT_PARAM = "extent";

/** What the counts cover when the extent node is off: everything ingested, both basins. */
export const WHOLE_WORLD: Bbox = [-180, -90, 180, 90];

/**
 * Only the exact value `0` switches the node off. Anything else was not asked for, and the
 * safe reading of a value nobody defined is the default — the same strictness as `?legend=0`.
 */
export function extentFilterOn(search: string): boolean {
  return new URLSearchParams(search).get(EXTENT_PARAM) !== "0";
}

/** The box the counts are asked over: the viewport while the node is on, everything when off. */
export function countedBbox(on: boolean, viewport: Bbox): Bbox {
  return on ? viewport : WHOLE_WORLD;
}
