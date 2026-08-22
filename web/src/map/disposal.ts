import { get, inSet } from "./expr.ts";
import type { Expr } from "./expr.ts";

/**
 * NDIC's injection class, codes verbatim — a well_type fact from the regulator, not an
 * interpretation. The membership is `cr_nd_well_type_disposal_1`'s: 1,989 of 43,824 wells
 * on the measured vintage, SWD 1,059 and WI 848 carrying nearly all of it. No per-code
 * English decode is asserted anywhere the codes appear.
 */
export const DISPOSAL_WELL_TYPES = [
  "SWD",
  "WI",
  "CO2I",
  "AI",
  "GI",
  "SFI",
  "MWUI",
  "INJP",
] as const;

/** The conformance row that classes these codes; every surface naming the class cites it. */
export const DISPOSAL_RULE = "cr_nd_well_type_disposal_1";

/**
 * Not the water stream blue, twice over: the drilling status already spends #3D8BD4, and
 * the class holds gas, CO2 and air injectors beside SWD/WI, so a stream colour would be a
 * claim the membership does not support. Teal is in neither the status palette, the trace
 * orchid nor the selection cyan; 6.5:1 on the dark substrate.
 */
export const DISPOSAL_COLOUR = "#2AA79B";

export function disposalFilter(): Expr {
  return inSet(get("well_type_reported"), [...DISPOSAL_WELL_TYPES]);
}

/** The verbatim code when the feature is in the class; null otherwise, absent included. */
export function disposalType(properties: Record<string, unknown>): string | null {
  const value = properties["well_type_reported"];
  if (typeof value !== "string") return null;
  return (DISPOSAL_WELL_TYPES as readonly string[]).includes(value) ? value : null;
}
