/**
 * One invariant, over whatever the app actually hides: an element carrying the `hidden`
 * attribute must compute to `display: none`.
 *
 * `[hidden] { display: none }` is UA-origin, so *any* author-origin `display` beats it whatever
 * its specificity. A class rule that sets `display` therefore renders the element with the
 * attribute still on it — the DOM looks correct, `element.hidden` is `true`, and only the
 * pixels are wrong. That is how `.gw-hover-meta` shipped a reserved empty band under every
 * hover card, and it is the same shape as the sign-out control before it.
 *
 * This lives in the browser tier because it cannot be caught anywhere cheaper: happy-dom
 * applies its own `[hidden]` rule with author-beating weight, so the identical assertion under
 * vitest is green with or without the author-origin reset. A unit test here would be vacuous.
 *
 * The set under test is read off the rendered document rather than from a list, because a
 * hand-maintained class list is exactly what let the five `.gw-hover-meta` elements through.
 */
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize, sep } from "node:path";
import { fileURLToPath } from "node:url";

import { BREAKPOINTS, launch } from "./lib.mjs";

const DIST = fileURLToPath(new URL("../../web/dist/", import.meta.url));
const DIST_ROOT = normalize(DIST).replace(/[\\/]+$/, "");
const REQUIRE = process.env.GLASSWELL_REQUIRE_E2E === "1";
const MIME = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
};

/** The surfaces, and the selector that says each one has finished painting. */
const SURFACES = [
  { name: "map", query: "?base=none", ready: "#gw-map:not([hidden]) .gw-map-chrome" },
  { name: "status", query: "?view=status", ready: "#gw-status-page:not([hidden])" },
  { name: "explore", query: "?view=explore&ds=wells", ready: "#gw-explore:not([hidden])" },
];

function envelope(data) {
  return JSON.stringify({
    data,
    meta: {
      request_id: "req_hidden_display",
      as_of: { requested: "latest", resolved: "2026-08-26" },
      source_freshness: {},
      labels: {},
      next_cursor: null,
      warnings: [],
      deprecations: [],
    },
    links: {},
  });
}

function staticServer() {
  return createServer(async (request, response) => {
    try {
      const pathname = new URL(request.url ?? "/", "http://127.0.0.1").pathname;
      const relative = pathname === "/" ? "index.html" : decodeURIComponent(pathname.slice(1));
      const path = normalize(join(DIST, relative));
      if (path !== DIST_ROOT && !path.startsWith(`${DIST_ROOT}${sep}`)) {
        throw new Error("path escaped dist");
      }
      const body = await readFile(path);
      response.writeHead(200, {
        "content-type": MIME[extname(path)] ?? "application/octet-stream",
        "cache-control": "no-store",
      });
      response.end(body);
    } catch {
      response.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
      response.end("not found");
    }
  });
}

const server = staticServer();
await new Promise((resolve, reject) => {
  server.once("error", reject);
  server.listen(0, "127.0.0.1", resolve);
});
const address = server.address();
if (!address || typeof address === "string") throw new Error("server has no TCP address");
const base = `http://127.0.0.1:${address.port}`;

let passed = 0;
let failed = 0;
let inspected = 0;
const classesSeen = new Set();

function check(name, condition, detail = "") {
  if (condition) {
    passed += 1;
    console.log(`  ok   ${passed + failed} ${name}`);
  } else {
    failed += 1;
    console.log(`  FAIL ${passed + failed} ${name}${detail ? ` — ${detail}` : ""}`);
  }
}

const browser = await launch();
try {
  for (const viewport of BREAKPOINTS) {
    const at = `${viewport.width}x${viewport.height}`;
    const context = await browser.newContext({ viewport });
    const page = await context.newPage();

    const api = async (route) => {
      const path = new URL(route.request().url()).pathname;
      const json = (data) =>
        route.fulfill({ status: 200, contentType: "application/json", body: envelope(data) });
      if (path === "/v1") return json({ published_vintages: [{ vintage_date: "2026-08-26" }] });
      if (path === "/v1/session") return json({ username: null, role: "anonymous", kind: "anonymous", expires_at: null, absolute_expires_at: null });
      if (path === "/v1/glossary/index") return json({ terms: [] });
      if (path === "/v1/glossary") return json([]);
      if (path.startsWith("/v1/tiles/")) return route.fulfill({ status: 204, body: "" });
      return route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
    };
    await page.route("**/v1", api);
    await page.route("**/v1/**", api);

    for (const surface of SURFACES) {
      await page.goto(`${base}/${surface.query}`, {
        waitUntil: "domcontentloaded",
        timeout: 30000,
      });
      try {
        await page.waitForSelector(surface.ready, { timeout: 15000 });
      } catch {
        check(`${at} ${surface.name} painted`, false, "surface never became ready");
        continue;
      }
      // The map builds its chrome asynchronously behind a dynamic import.
      await page.waitForTimeout(surface.name === "map" ? 2500 : 800);

      const report = await page.evaluate(() => {
        const painted = [];
        const seen = [];
        for (const element of document.querySelectorAll("[hidden]")) {
          const display = window.getComputedStyle(element).display;
          const identity =
            `${element.tagName.toLowerCase()}` +
            `${element.id ? `#${element.id}` : ""}` +
            `${element.className && typeof element.className === "string" ? `.${element.className.trim().split(/\s+/).join(".")}` : ""}`;
          seen.push(identity);
          if (display !== "none") painted.push({ identity, display });
        }
        return { painted, seen, total: seen.length };
      });

      inspected += report.total;
      for (const identity of report.seen) {
        for (const name of identity.split(".").slice(1)) classesSeen.add(name);
      }

      check(
        `${at} ${surface.name}: every [hidden] element computes to display:none (${report.total} inspected)`,
        report.painted.length === 0,
        report.painted.map((row) => `${row.identity} is display:${row.display}`).join("; "),
      );
      check(
        `${at} ${surface.name}: found hidden elements, so the assertion is not vacuous`,
        report.total > 0,
        `only ${report.total} hidden elements on this surface`,
      );
    }
    await context.close();
  }
} finally {
  await browser.close();
  server.close();
}

console.log(`\n${inspected} hidden elements inspected across ${BREAKPOINTS.length} breakpoints`);
console.log(`${classesSeen.size} distinct classes carried a hidden element`);
console.log(`\n${passed} passed, ${failed} failed`);

if (failed > 0 && (REQUIRE || true)) process.exitCode = 1;
