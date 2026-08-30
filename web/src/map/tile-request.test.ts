// @vitest-environment happy-dom
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { tileUrl } from "../api/client.ts";
import { CACHE_HOSTILE_HEADERS, tileRequest } from "./tile-request.ts";

const TILE = `${tileUrl("nd_laterals").replace("{z}/{x}/{y}", "7/34/45")}`;
const SOURCE = readFileSync("src/map/tile-request.ts", "utf8");

describe("the tile request transform", () => {
  it("attaches no auth header, because the session cookie rides the same-origin fetch", () => {
    expect(tileRequest(TILE).headers).toBeUndefined();
    expect(tileRequest("/basemap/basemap.pmtiles").headers).toBeUndefined();
    expect(SOURCE).not.toMatch(/X-Glasswell-|authHeaders|localStorage/);
  });

  it("leaves the url byte-identical, so a repeat fetch is the same cache entry", () => {
    // Track T's log: 5,903 requests over 1,050 distinct tiles, one z7 tile fetched 109
    // times. That 5.6x only becomes 304s if the url the browser keys on does not move.
    expect(tileRequest(TILE).url).toBe(TILE);
    expect(tileRequest(TILE).url).not.toMatch(/[?&](_|v|t|cb)=/);
  });

  it("sets no header or flag that would opt the tile out of revalidation", () => {
    // Tiles now answer If-None-Match with a 0.7 ms 304 and no body. `cache: "no-store"` or
    // "reload" on the request skips that and pays the full 2 MB every zoom — item 2 of
    // work-output/tileperf-client-handoff.md, which is a verification, not a change.
    const request = tileRequest(TILE) as unknown as Record<string, unknown>;
    expect(request["cache"]).toBeUndefined();
    expect(request["credentials"]).toBeUndefined();
    const headers = (request["headers"] ?? {}) as Record<string, string>;
    for (const name of Object.keys(headers)) {
      expect(CACHE_HOSTILE_HEADERS, `${name} defeats the tile cache`).not.toContain(
        name.toLowerCase(),
      );
    }
  });

  it("names no Accept-Encoding, because the browser's own value is what the proxy reads", () => {
    // Item 3: the proxy asks martin for zstd only when the caller's own Accept-Encoding
    // includes it. An explicit one here would speak for Safari as well as for Chrome.
    const headers = (tileRequest(TILE).headers ?? {}) as Record<string, string>;
    expect(Object.keys(headers).map((name) => name.toLowerCase())).not.toContain("accept-encoding");
  });

  it("keeps the tile same-origin, so the cookie is sent and no tile is preflighted", () => {
    // A cross-origin request carrying credentials is preflighted, and the OPTIONS round trip
    // is paid per tile — which would swamp the 135 ms/tile the server changes returned.
    expect(TILE.startsWith("/")).toBe(true);
    expect(tileRequest(TILE).url.startsWith("/")).toBe(true);
  });
});
