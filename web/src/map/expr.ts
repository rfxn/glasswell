import type { ExpressionSpecification } from "maplibre-gl";

/**
 * Typed constructors for the style-spec expressions this app builds. A five-level nested
 * JSON array is unreviewable in a diff and untypeable by `tsc`; the same shape written as
 * calls is both. Only the operators glasswell actually uses are wrapped.
 */
export type Expr = ExpressionSpecification;

export const zoom: Expr = ["zoom"];

export function get(property: string): Expr {
  return ["get", property];
}

export function lower(value: Expr | string): Expr {
  return ["downcase", value];
}

export function coalesce(...values: (Expr | string | number)[]): Expr {
  return ["coalesce", ...values] as Expr;
}

export function match<T>(input: Expr, pairs: [string, T][], fallback: T): Expr {
  return ["match", input, ...pairs.flat(), fallback] as unknown as Expr;
}

export function step<T>(input: Expr, base: T, stops: [number, T][]): Expr {
  return ["step", input, base, ...stops.flat()] as Expr;
}

export function interpolate(input: Expr, stops: [number, number | Expr][]): Expr {
  return ["interpolate", ["linear"], input, ...stops.flat()] as Expr;
}

export function inSet(input: Expr, values: string[]): Expr {
  return ["in", input, ["literal", values]] as Expr;
}

export function when<T>(branches: [Expr | boolean, T][], fallback: T): Expr {
  return ["case", ...branches.flat(), fallback] as unknown as Expr;
}

export function all(...conditions: (Expr | boolean)[]): Expr {
  return ["all", ...conditions] as Expr;
}

export function toNumber(value: Expr): Expr {
  return ["to-number", value] as Expr;
}

export function featureState(key: string): Expr {
  return ["boolean", ["feature-state", key], false];
}
