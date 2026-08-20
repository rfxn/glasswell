/**
 * Layer visibility survives a reload as `{on, known}` rather than a version number.
 * Storing the key set this build offers is what lets a later boot tell "the user turned
 * this off" apart from "this layer did not exist yet", so a layer added in a release still
 * ships on by default and a retired one disappears without a migration step.
 */
export const LAYER_STORAGE_KEY = "glasswell.layers";
export const BASE_STORAGE_KEY = "glasswell.basemap";

const WRITE_DEBOUNCE_MS = 400;

export interface LayerCapabilitySet {
  on: string[];
  known: string[];
}

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null; // A privacy-mode browser throws on access; visibility is not worth failing boot over.
  }
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

export function readLayerSet(): LayerCapabilitySet | null {
  const raw = storage()?.getItem(LAYER_STORAGE_KEY);
  if (!raw) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null; // Hand-edited or half-written storage is indistinguishable from absent.
  }
  if (typeof parsed !== "object" || parsed === null) return null;
  const { on, known } = parsed as Partial<LayerCapabilitySet>;
  if (!isStringArray(on) || !isStringArray(known)) return null;
  return { on, known };
}

let writeTimer: ReturnType<typeof setTimeout> | undefined;

export function writeLayerSet(
  on: ReadonlySet<string>,
  known: readonly string[],
  delayMs: number = WRITE_DEBOUNCE_MS,
): void {
  const payload = JSON.stringify({ on: known.filter((id) => on.has(id)), known: [...known] });
  clearTimeout(writeTimer);
  const commit = (): void => {
    storage()?.setItem(LAYER_STORAGE_KEY, payload);
  };
  if (delayMs <= 0) commit();
  else writeTimer = setTimeout(commit, delayMs);
}

export function restoreLayerSet(
  stored: LayerCapabilitySet | null,
  known: readonly string[],
  defaultOn: readonly string[],
): Set<string> {
  if (!stored) return new Set(defaultOn);
  const seen = new Set(stored.known);
  const on = new Set(stored.on);
  return new Set(known.filter((id) => (seen.has(id) ? on.has(id) : defaultOn.includes(id))));
}

/** Guarded lookup: a stored id this build no longer offers falls back, it does not break boot. */
export function readGuarded(key: string, allowed: readonly string[]): string | null {
  const value = storage()?.getItem(key);
  return value && allowed.includes(value) ? value : null;
}

export function writeGuarded(key: string, value: string, allowed: readonly string[]): void {
  if (allowed.includes(value)) storage()?.setItem(key, value);
}
