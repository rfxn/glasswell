/**
 * The one place the card builds a query object.
 *
 * Before this the card picked `as_of` out by name and forwarded nothing else, so every control
 * that changes what a figure *is* -- the vintage a restated month is read at, the window a
 * brush leaves behind, the normalisation basis -- had no route from the URL to the request.
 * The bag is named rather than open: `?section=` is app state and must never reach a request,
 * which is what its entry in `KNOWN` buys, and an unrecognised key is not a parameter this
 * API has agreed to answer.
 */
import type { AppState } from "../app/state.ts";

/** Every parameter the card is allowed to carry from the URL into a request, in one list. */
export const FORWARDED = ["as_of", "from", "to", "normalization", "grain"] as const;

export type Forwarded = (typeof FORWARDED)[number];

export function cardQuery(
  state: AppState,
  extra: Record<string, string> = {},
): Record<string, string> {
  const query: Record<string, string> = {};
  for (const key of FORWARDED) {
    const value = state.extra[key]?.[0];
    if (value !== undefined && value !== "") query[key] = value;
  }
  return { ...query, ...extra };
}
