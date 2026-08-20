import { authHeaders } from "../api/client.ts";

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
 * MapLibre's `transformRequest`. The key rides on this app's own tiles and on nothing else —
 * the basemap archive is public and the pmtiles range request must stay header-free to be
 * cacheable.
 */
export function tileRequest(url: string, resourceType?: string): TileRequest {
  if (resourceType === "Tile" && url.includes("/v1/tiles/")) {
    const headers = authHeaders();
    return Object.keys(headers).length > 0 ? { url, headers } : { url };
  }
  return { url };
}
