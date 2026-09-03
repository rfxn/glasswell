import { get, inSet } from "./expr.ts";
import { BY_PREFIX, JURISDICTION_LIST } from "./jurisdictions.generated.ts";
import type { Expr } from "./expr.ts";

/**
 * The published injection codebooks, one per registration that has one, codes verbatim — a
 * well_type fact from the regulator, not an interpretation. No per-code English decode is
 * asserted anywhere the codes appear.
 *
 * Keyed by registration rather than applied to every feature: the list below is NDIC's, and
 * before this it classed a Texas, a New Mexico and a Montana well as disposal on North Dakota's
 * codebook and hovered North Dakota's rule beside it. A registration with no entry draws no
 * ring, which is what the legend says.
 *
 * Keyed in the client and not read from the registry, because the registry has no well_type
 * decision to read: `cr_nd_well_type_disposal_1` and New Mexico's `cr_nm_wellhistory_well_type_1`
 * are published conformance rules under no decision, and a `well_type_vocabulary` key is the
 * open registry-vocabulary question rather than one this train answers.
 */
interface DisposalCodebook {
  readonly codes: readonly string[];
  /** The conformance row that classes these codes; every surface naming the class cites it. */
  readonly rule: string;
}

const CODEBOOKS: Readonly<Record<string, DisposalCodebook>> = {
  // 1,989 of 43,824 wells on the measured vintage, SWD 1,059 and WI 848 carrying nearly all.
  ND: {
    codes: ["SWD", "WI", "CO2I", "AI", "GI", "SFI", "MWUI", "INJP"],
    rule: "cr_nd_well_type_disposal_1",
  },
};

/** Every code any registered codebook classes, for the style filter that draws the ring. */
export const DISPOSAL_WELL_TYPES: readonly string[] = [
  ...new Set(Object.values(CODEBOOKS).flatMap((book) => book.codes)),
];

/** The codebook the feature's own registration publishes, or null where it publishes none. */
export function disposalCodebook(api10: string | null | undefined): DisposalCodebook | null {
  const registration = BY_PREFIX[String(api10 ?? "").slice(0, 2)];
  return registration ? (CODEBOOKS[registration.code] ?? null) : null;
}

/** The registrations that publish one, named where the legend says whose ring this is. */
export function disposalRegistrations(): readonly string[] {
  return JURISDICTION_LIST.filter((row) => CODEBOOKS[row.code]).map((row) => row.code);
}

/** The rules those codebooks cite, so the legend names a decision rather than a colour. */
export function disposalRules(): readonly string[] {
  return disposalRegistrations().map((code) => CODEBOOKS[code]!.rule);
}

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

/**
 * The verbatim code when the feature is in its own registration's class; null otherwise, a
 * feature whose registration publishes no codebook included.
 */
export function disposalType(properties: Record<string, unknown>): string | null {
  const value = properties["well_type_reported"];
  if (typeof value !== "string") return null;
  const book = disposalCodebook(String(properties["api10"] ?? ""));
  return book !== null && book.codes.includes(value) ? value : null;
}
