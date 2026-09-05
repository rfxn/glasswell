export interface AsOf {
  requested: string;
  resolved: string | null;
}

export interface Warning {
  code: string;
  detail?: string;
  pointer?: string;
  /** Where the decision behind the warning is a registered rule, its id travels beside it. */
  rule_id?: string;
}

export interface Meta {
  request_id: string;
  as_of: AsOf;
  source_freshness: Record<string, unknown>;
  labels: Record<string, string>;
  next_cursor: string | null;
  warnings: Warning[];
  deprecations: unknown[];
}

export interface Links {
  self?: string | null;
  next?: string | null;
  explain?: string | null;
  [key: string]: string | null | undefined;
}

export interface Envelope<T> {
  data: T;
  meta: Meta;
  links: Links;
}

export interface Figure {
  value: string;
  unit: string;
  d: string;
  basis?: string | null;
  granularity?: string | null;
  report_vintage?: string | null;
}

const SIDECAR_KEYS = ["_lineage", "_units", "_basis"] as const;

export function unwrap<T>(envelope: Envelope<T>): T {
  return envelope.data;
}

export function asOf<T>(envelope: Envelope<T>): AsOf {
  return envelope.meta.as_of;
}

export function labelFor<T>(envelope: Envelope<T>, pointer: string): string | null {
  return envelope.meta.labels[pointer] ?? null;
}

export function isFigure(value: unknown): value is Figure {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as Figure).value === "string" &&
    "unit" in value &&
    "d" in value
  );
}

export function valueAt(data: unknown, pointer: string): unknown {
  let node = data;
  for (const token of pointerTokens(pointer)) {
    if (Array.isArray(node)) {
      node = node[Number(token)];
    } else if (typeof node === "object" && node !== null) {
      node = (node as Record<string, unknown>)[token];
    } else {
      return undefined;
    }
    if (node === undefined) return undefined;
  }
  return node;
}

export function figureAt(data: unknown, pointer: string): Figure | null {
  const found = valueAt(data, pointer);
  return isFigure(found) ? found : null;
}

/** SB-07 §9.1: a figure's own `d`, else the nearest ancestor `_lineage` sidecar (B11). */
export function derivationFor(data: unknown, pointer: string): string | null {
  const figure = figureAt(data, pointer);
  if (figure) return figure.d;

  let best: { prefix: string; handle: string } | null = null;
  for (const [prefix, handle] of sidecarEntries(data, "")) {
    if (pointer === prefix || pointer.startsWith(prefix + "/")) {
      if (best === null || prefix.length > best.prefix.length) best = { prefix, handle };
    }
  }
  return best?.handle ?? null;
}

/** The dotted `_units` / `_basis` sidecars, resolved the same way as `_lineage`. */
export function sidecarFor(
  data: unknown,
  pointer: string,
  key: "_units" | "_basis",
): string | null {
  let best: { prefix: string; value: string } | null = null;
  for (const [prefix, value] of sidecarEntries(data, "", key)) {
    if (pointer === prefix || pointer.startsWith(prefix + "/")) {
      if (best === null || prefix.length > best.prefix.length) best = { prefix, value };
    }
  }
  return best?.value ?? null;
}

function* sidecarEntries(
  node: unknown,
  pointer: string,
  key: (typeof SIDECAR_KEYS)[number] = "_lineage",
): Generator<[string, string]> {
  if (Array.isArray(node)) {
    for (const [index, value] of node.entries()) {
      yield* sidecarEntries(value, `${pointer}/${index}`, key);
    }
    return;
  }
  if (typeof node !== "object" || node === null) return;
  const record = node as Record<string, unknown>;
  const sidecar = record[key];
  if (typeof sidecar === "object" && sidecar !== null) {
    for (const [dotted, handle] of Object.entries(sidecar as Record<string, unknown>)) {
      if (typeof handle === "string") {
        yield [`${pointer}/${dotted.split(".").join("/")}`, handle];
      }
    }
  }
  for (const [childKey, value] of Object.entries(record)) {
    if ((SIDECAR_KEYS as readonly string[]).includes(childKey)) continue;
    yield* sidecarEntries(value, `${pointer}/${childKey}`, key);
  }
}

function pointerTokens(pointer: string): string[] {
  if (pointer === "" || pointer === "/") return [];
  return pointer
    .replace(/^\//, "")
    .split("/")
    .map((token) => token.replace(/~1/g, "/").replace(/~0/g, "~"));
}
