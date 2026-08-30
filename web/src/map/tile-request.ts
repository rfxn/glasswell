export interface TileRequest {
  url: string;
  headers?: Record<string, string>;
}

/**
 * Request headers that would opt a tile out of the HTTP cache. Named so the test can hold
 * the transform to them: tiles carry an ETag and answer If-None-Match with a 0.7 ms 304 and
 * no body, and that only pays if this request participates in the cache at all.
 */
export const CACHE_HOSTILE_HEADERS: readonly string[] = [
  "cache-control",
  "pragma",
  "if-modified-since",
  "if-none-match",
  "accept-encoding",
];

/**
 * MapLibre's `transformRequest`. It attaches nothing: the session cookie rides the
 * same-origin fetch on its own, and a custom header would preflight every tile.
 */
export function tileRequest(url: string): TileRequest {
  return { url };
}
