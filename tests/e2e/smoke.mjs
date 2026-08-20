// DR-62: the browser half of the regression net. scripts/smoke.sh proves the API's claims;
// this proves the ones only a browser can — that the app boots, that a deep link resolves to
// a card, that a figure's handle reaches a checksummed regulator file on screen, and that a
// hostile query string cannot make the page ask for something outside the tile allowlist.
//
// Read-only. It navigates and reads; it never writes through the API.
// The key rides the fragment, is never logged, and is redacted out of every url printed.
import { existsSync, mkdirSync, readdirSync } from "node:fs";

const BASE = (process.env.GW_BASE ?? "http://127.0.0.1:8000").replace(/\/$/, "");
const KEY = (process.env.GLASSWELL_OWNER_KEY ?? process.env.GW_KEY ?? "").trim();
const WELL = process.env.GW_WELL ?? "3305310451";
const SHOTS = process.env.GW_SHOTS ?? "";
const REQUIRE = process.env.GLASSWELL_REQUIRE_E2E === "1";
const PLAYWRIGHT_CACHE = "/root/.cache/ms-playwright";
const ALLOWED_TILE_LAYERS = ["nd_wells", "nd_laterals", "nd_spacing_units"];
// The build host renders through swiftshader. A shader that will not compile there says
// nothing about the app, and the map still draws — every other page error is real.
const SOFTWARE_GL = /shader|webgl|swiftshader|GPU stall/i;

const redact = (text) => String(text).replace(/key=[0-9a-fA-F]{8,}/g, "key=REDACTED");
const sameOrigin = (url) =>
  url.startsWith(BASE) || url.startsWith("blob:") || url.startsWith("data:") || url === "about:blank";

let passed = 0;
let failed = 0;
const ok = (label) => {
  passed += 1;
  console.log(`  ok   ${String(passed + failed).padStart(2)} ${label}`);
};
const bad = (label, detail) => {
  failed += 1;
  console.log(`  FAIL ${String(passed + failed).padStart(2)} ${label} — ${redact(detail)}`);
};
const assert = (condition, label, detail) => (condition ? ok(label) : bad(label, detail));

/** No browser is a skip when a human runs it and a failure when CI does. */
function unavailable(reason) {
  if (REQUIRE) {
    console.error(`GLASSWELL_REQUIRE_E2E is set but ${reason}`);
    process.exit(1);
  }
  console.log(`e2e skipped: ${reason}`);
  process.exit(0);
}

function chromeExecutable() {
  if (process.env.GW_CHROME) return process.env.GW_CHROME;
  if (!existsSync(PLAYWRIGHT_CACHE)) return null;
  const builds = readdirSync(PLAYWRIGHT_CACHE)
    .filter((entry) => entry.startsWith("chromium-"))
    .sort((a, b) => Number(b.split("-")[1]) - Number(a.split("-")[1]));
  for (const build of builds) {
    const path = `${PLAYWRIGHT_CACHE}/${build}/chrome-linux64/chrome`;
    if (existsSync(path)) return path;
  }
  return null;
}

let chromium;
try {
  ({ chromium } = await import("playwright-core"));
} catch {
  unavailable("playwright-core is not installed (npm --prefix tests/e2e install)");
}
const executablePath = chromeExecutable();
if (!executablePath) unavailable("no chromium build found (set GW_CHROME)");
if (!KEY) unavailable("no owner key (set GLASSWELL_OWNER_KEY)");

if (SHOTS) mkdirSync(SHOTS, { recursive: true });

const browser = await chromium.launch({
  executablePath,
  args: ["--no-sandbox", "--enable-unsafe-swiftshader", "--hide-scrollbars"],
});
const context = await browser.newContext({ viewport: { width: 1600, height: 1000 } });
const page = await context.newPage();

const journal = { errors: [], requests: [], responses: [] };
page.on("pageerror", (error) => {
  if (!SOFTWARE_GL.test(error.message)) journal.errors.push(error.message);
});
page.on("request", (request) => journal.requests.push(request.url()));
page.on("response", (response) => journal.responses.push([response.status(), response.url()]));

async function visit(query, { key = false, settle = 6000 } = {}) {
  journal.errors = [];
  journal.requests = [];
  journal.responses = [];
  await page.goto(`${BASE}/${query}${key ? `#key=${KEY}` : ""}`, {
    waitUntil: "load",
    timeout: 60000,
  });
  await page.waitForTimeout(settle);
}

async function shoot(name) {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png` });
}

const tilePath = (url) => url.replace(BASE, "");
const tileRequests = () => journal.requests.filter((url) => tilePath(url).startsWith("/v1/tiles/"));
const tileResponses = () =>
  journal.responses.filter(([, url]) => tilePath(url).startsWith("/v1/tiles/"));
const offOrigin = () => journal.requests.filter((url) => !sameOrigin(url));

console.log(`e2e: ${BASE} (well ${WELL})`);

// 1-3 — the app boots, draws, and asks nobody but this origin. The key is adopted here, from
// the fragment, exactly as SMOKE.md 2 tells the owner to do it.
await visit("", { key: true, settle: 8000 });
assert(
  (await page.locator("#gw-map canvas.maplibregl-canvas").count()) > 0,
  "the map canvas is on the page",
  "MapLibre rendered no canvas",
);
assert(journal.errors.length === 0, "the first load raises no page error", journal.errors.join(" | "));
assert(offOrigin().length === 0, "no request leaves this origin", offOrigin().slice(0, 3).join(" | "));
await shoot("e2e-01-boot");

// 4-6 — a deep link is a shareable state: viewport, selection, and a card that resolves.
await visit(`?map=12.00/47.71074/-102.74821&well=${WELL}`, { settle: 8000 });
await page.waitForSelector("#gw-card", { state: "visible", timeout: 30000 }).catch(() => {});
const card = page.locator("#gw-card");
assert((await card.count()) > 0, "a deep link opens the well card", "#gw-card never appeared");
const cardText = (await card.count()) ? await card.innerText() : "";
assert(cardText.includes(WELL), "the card is the well the link named", `card text lacks ${WELL}`);
const refused = tileResponses().filter(([status]) => status >= 400);
assert(
  tileRequests().length > 0 && refused.length === 0,
  "every tile the map asks for is answered",
  `${tileRequests().length} requests, ${refused.length} of them 4xx/5xx`,
);
await shoot("e2e-02-card");

// 7-8 — the thesis, in the browser: a figure's handle to a checksum and a regulator url.
const handle = page.locator("#gw-card button.gw-handle, #gw-card [data-gw-explain]").first();
if (await handle.count()) {
  await handle.click();
  await page.waitForSelector("#gw-drawer", { state: "visible", timeout: 30000 }).catch(() => {});
  // The drawer is visible ~250 ms before /v1/explain has answered, so reading innerText on
  // `visible` reads the header alone. Wait for the content, not for the element.
  await page
    .waitForFunction(
      () => (document.querySelector("#gw-drawer")?.innerText ?? "").length > 300,
      null,
      { timeout: 30000 },
    )
    .catch(() => {});
  const drawer = page.locator("#gw-drawer");
  const body = (await drawer.count()) ? await drawer.innerText() : "";
  assert(/[0-9a-f]{64}/.test(body), "the drawer shows a 64-hex checksum", "no sha256 on screen");
  assert(/dmr\.nd\.gov/.test(body), "the drawer names the regulator file", "no dmr.nd.gov url");
  await shoot("e2e-03-drawer");
} else {
  bad("the drawer shows a 64-hex checksum", "the card offered no derivation handle");
  bad("the drawer names the regulator file", "the card offered no derivation handle");
}

// 9-12 — N-5: a hostile query string must not put the page outside the tile allowlist, off
// this origin, or into an unhandled exception — and whatever it does ask for must be refused.
const hostile = "..%2F..%2Fetc%2Fpasswd";
await visit(
  `?wells=${hostile}&laterals=${hostile}&base=%22%3E%3Cscript%3E&map=1e309/999/999`,
  { settle: 7000 },
);
// Every .pbf the page asked for, not just the ones that stayed inside /v1/tiles/: with
// `?wells=..%2F..%2Fetc%2Fpasswd` the browser normalises the path and asks for
// `/etc/passwd/{z}/{x}/{y}.pbf`, which carries no tiles prefix at all. Filtering on that
// prefix made this assertion vacuous for exactly the case it exists to catch (Gate-O M-2).
const pbfResponses = journal.responses.filter(([, url]) => /\.pbf(\?|$)/.test(url));
const escaped = pbfResponses.filter(
  ([status, url]) =>
    status < 400 &&
    !ALLOWED_TILE_LAYERS.some((layer) => tilePath(url).startsWith(`/v1/tiles/${layer}/`)) &&
    !tilePath(url).startsWith("/basemap/"),
);
assert(
  escaped.length === 0,
  "no .pbf outside the allowlist is served",
  escaped.slice(0, 2).map(([status, url]) => `${status} ${tilePath(url)}`).join(" | "),
);
const offAllowlist = pbfResponses.filter(
  ([, url]) =>
    !ALLOWED_TILE_LAYERS.some((layer) => tilePath(url).startsWith(`/v1/tiles/${layer}/`)) &&
    !tilePath(url).startsWith("/basemap/"),
);
console.log(`  note   escaped .pbf requests observed: ${offAllowlist.length}`);
assert(
  offAllowlist.every(([status]) => status === 404),
  "an escaped tile request is refused 404",
  offAllowlist.map(([status, url]) => `${status} ${tilePath(url)}`).slice(0, 2).join(" | ") ||
    "(the page asked for none — the client guard may have landed)",
);
assert(
  offOrigin().length === 0,
  "a hostile parameter cannot send a request off-origin",
  offOrigin().slice(0, 3).join(" | "),
);
assert(journal.errors.length === 0, "a hostile parameter does not break the page",
  journal.errors.join(" | "));
await shoot("e2e-04-hostile");

// 13 — no key at all, in a context that never had one: refuse honestly, do not look empty.
const anonymous = await browser.newContext({ viewport: { width: 1600, height: 1000 } });
const anonymousPage = await anonymous.newPage();
await anonymousPage.goto(`${BASE}/?well=${WELL}`, { waitUntil: "load", timeout: 60000 });
await anonymousPage.waitForTimeout(5000);
const anonymousBody = await anonymousPage.locator("body").innerText();
assert(/key/i.test(anonymousBody), "without a key the app says so", "the page named no key requirement");
if (SHOTS) await anonymousPage.screenshot({ path: `${SHOTS}/e2e-05-no-key.png` });
await anonymous.close();

await browser.close();
console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
