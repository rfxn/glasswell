// Shared helpers for the browser gates and the e2e tier — the machinery every DIR-11 pass
// otherwise re-derives in work-output: launch, an instrumented page, the breakpoint ladder,
// screenshots, WCAG contrast sampling and a frame probe.
//
// Import-safe: nothing here touches the filesystem, the network or playwright until a
// function is called, so smoke.mjs can import it before deciding whether to skip.
import { existsSync, mkdirSync, readdirSync, readFileSync } from "node:fs";

export const PLAYWRIGHT_CACHE = "/root/.cache/ms-playwright";

export const KEY_HEADER = "X-Glasswell-Key";
const KEY_RULE =
  "the owner key travels only as the X-Glasswell-Key header, read from GLASSWELL_KEY_FILE " +
  "or GLASSWELL_OWNER_KEY — never a script argument, never any part of a url";

export function baseUrl() {
  // GW_BASE is the retired name, still honoured so an old invocation targets what it names.
  return (process.env.GLASSWELL_BASE_URL ?? process.env.GW_BASE ?? "https://glasswell.lab.rpx.sh")
    .replace(/\/$/, "");
}

/** The one way in: a key file named by GLASSWELL_KEY_FILE, else GLASSWELL_OWNER_KEY. */
export function ownerKey() {
  const file = process.env.GLASSWELL_KEY_FILE;
  const key = (file ? readFileSync(file, "utf8") : (process.env.GLASSWELL_OWNER_KEY ?? "")).trim();
  return key || null;
}

/**
 * Credentials a gate reads out of the page — a minted password shown once, so far — which the
 * journal, the target guard and the argv guard have to treat exactly as they treat the owner
 * key. Registration happens *before* the value is read out of the DOM: a secret registered
 * afterwards is one the journal may already have carried.
 */
const registered = new Set();

export function registerSecret(value) {
  if (typeof value === "string" && value.length >= MIN_SECRET_LENGTH) registered.add(value);
  return value;
}

/** For the unit tier, which asserts on a clean registry between cases. */
export function forgetSecrets() {
  registered.clear();
}

// Short enough to be a word rather than a credential; redacting one would eat ordinary prose.
const MIN_SECRET_LENGTH = 8;

function secrets() {
  const key = ownerKey();
  return key ? [key, ...registered] : [...registered];
}

/** Returns the key after refusing to run with any known secret visible in process.argv. */
export function keyGuard() {
  const key = ownerKey();
  for (const secret of secrets()) {
    if (process.argv.some((argument) => argument.includes(secret)))
      throw new Error(`a credential found in process.argv — ${KEY_RULE}`);
  }
  return key;
}

/** Refuses any navigation target carrying a known secret (case-insensitively). */
export function guardTarget(url) {
  const target = String(url).toLowerCase();
  for (const secret of secrets()) {
    if (target.includes(secret.toLowerCase()))
      throw new Error(`a credential found in a target url — ${KEY_RULE}`);
  }
  return url;
}

export function redact(text) {
  let output = String(text);
  for (const secret of secrets()) {
    const escaped = secret.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    output = output.replace(new RegExp(escaped, "gi"), "REDACTED");
  }
  return output;
}

export function originOf(url) {
  try {
    return new URL(url).origin;
  } catch {
    return null;
  }
}

// Route-scoped rather than extraHTTPHeaders: a direct off-origin request gets no header. A
// same-origin 302 leaving the origin DOES re-attach it on the redirect leg (Chromium follows
// without re-routing); instrumentedPage journals that shape — a detector, not a preventer —
// and the served API issues no redirects at all.
export async function authenticate(context, { origin = new URL(baseUrl()).origin } = {}) {
  const key = keyGuard();
  if (!key) throw new Error("no owner key (set GLASSWELL_KEY_FILE or GLASSWELL_OWNER_KEY)");
  await context.route("**/*", (route) => {
    const request = route.request();
    let sameOrigin = false;
    try {
      sameOrigin = new URL(request.url()).origin === origin;
    } catch {
      // unparseable scheme (about:, data:) is by definition not the target origin
    }
    if (sameOrigin)
      return route.continue({ headers: { ...request.headers(), [KEY_HEADER.toLowerCase()]: key } });
    return route.continue();
  });
}

// The DIR-11 ladder. Gates screenshot at three or more of these.
export const BREAKPOINTS = [
  { width: 1600, height: 1000 },
  { width: 1366, height: 900 },
  { width: 1024, height: 768 },
  { width: 820, height: 1180 },
  { width: 390, height: 844 },
];

export function chromeExecutable() {
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

export async function launch({ executablePath = chromeExecutable(), args = [] } = {}) {
  const { chromium } = await import("playwright-core");
  if (!executablePath) throw new Error("no chromium build found (set GW_CHROME)");
  return chromium.launch({
    executablePath,
    args: ["--no-sandbox", "--enable-unsafe-swiftshader", "--hide-scrollbars", ...args],
  });
}

// A page whose journal answers the questions every gate asks: page errors, console noise,
// non-2xx responses, tile and API traffic, and whether the key ever reached a url.
// `auth: true` (the default) injects the key header on every same-origin request.
export async function instrumentedPage(browser, { viewport, dsf, auth = true, origin, contextOpts } = {}) {
  const context = await browser.newContext({
    viewport: viewport ?? { width: 1600, height: 1000 },
    deviceScaleFactor: dsf ?? 1,
    ...(contextOpts ?? {}),
  });
  if (auth) await authenticate(context, origin ? { origin } : {});
  const page = await context.newPage();
  const key = keyGuard();
  const rawGoto = page.goto.bind(page);
  page.goto = async (url, options) => rawGoto(guardTarget(url), options);
  const targetOrigin = origin ?? originOf(baseUrl());
  const journal = {
    pageerror: [],
    console: [],
    nonok: [],
    tiles: [],
    api: [],
    sentKey: [],
    offOriginRedirects: [],
  };
  page.on("pageerror", (error) => journal.pageerror.push(redact(error.message)));
  page.on("console", (message) => {
    if (message.type() === "error" || message.type() === "warning")
      journal.console.push(`${message.type()}: ${redact(message.text()).slice(0, 300)}`);
  });
  page.on("request", (request) => {
    if (key && request.url().includes(key)) journal.sentKey.push(redact(request.url()));
    const prior = request.redirectedFrom();
    if (prior && originOf(prior.url()) === targetOrigin && originOf(request.url()) !== targetOrigin)
      journal.offOriginRedirects.push(redact(`${prior.url()} -> ${request.url()}`));
  });
  page.on("response", (response) => {
    const url = response.url();
    if (url.includes("/v1/tiles/"))
      journal.tiles.push({ status: response.status(), url: url.replace(/.*\/v1\/tiles\//, "") });
    else if (url.includes("/v1/"))
      journal.api.push({ status: response.status(), url: url.replace(/.*\/v1\//, "").slice(0, 90) });
    if (response.status() >= 400) journal.nonok.push(`${response.status()} ${redact(url)}`);
  });
  return { context, page, journal, redact };
}

export async function mapReady(page, settle = 4000) {
  await page.waitForSelector("#gw-map canvas.maplibregl-canvas", { timeout: 30000 });
  await page.waitForTimeout(settle);
}

export function shooter(directory) {
  mkdirSync(directory, { recursive: true });
  return async (page, name, options = {}) => {
    await page.screenshot({ path: `${directory}/${name}.png`, ...options });
    console.log(`  [shot] ${name}.png`);
  };
}

// The same 3:1 non-text floor, applied to a mark that carries no text: an encoding cell is
// judged on its fill, and a fill may be a background colour, a gradient, or both. Every paint
// the rule contributes is measured against the strip the mark sits on, so a class whose only
// paint is the surface token is caught wherever it is drawn. `host` is a selector for the
// element the probes are appended to, so they are measured in the context that paints them.
export async function markContrast(page, { host, classNames, base }) {
  return page.evaluate(
    ([hostSelector, classes, baseClass]) => {
      const lum = (colour) => {
        const [r, g, b] = colour
          .match(/\d+(\.\d+)?/g)
          .slice(0, 3)
          .map(Number)
          .map((v) => {
            v /= 255;
            return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
          });
        return 0.2126 * r + 0.7152 * g + 0.0722 * b;
      };
      const ratio = (a, b) => {
        const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
        return +((hi + 0.05) / (lo + 0.05)).toFixed(2);
      };
      const opaque = (colour) => Boolean(colour) && colour !== "transparent" && !/,\s*0\)$/.test(colour);
      const backgroundOf = (element) => {
        let node = element;
        while (node) {
          const colour = getComputedStyle(node).backgroundColor;
          if (opaque(colour)) return colour;
          node = node.parentElement;
        }
        return "rgb(11, 16, 20)";
      };
      const container = document.querySelector(hostSelector);
      if (!container) return { missing: hostSelector, theme: document.documentElement.dataset.theme ?? "dark" };
      const background = backgroundOf(container);
      const marks = classes.map((className) => {
        const probe = document.createElement("span");
        probe.className = `${baseClass} ${className}`;
        container.appendChild(probe);
        const style = getComputedStyle(probe);
        const fill = style.backgroundColor;
        const image = style.backgroundImage;
        probe.remove();
        const paints = [
          ...(opaque(fill) ? [fill] : []),
          ...(image === "none" ? [] : image.match(/rgba?\([^)]*\)/g) ?? []).filter(opaque),
        ];
        const ratios = [...new Set(paints)].map((colour) => ({ colour, ratio: ratio(colour, background) }));
        return {
          className,
          paints: ratios,
          best: ratios.length ? Math.max(...ratios.map((entry) => entry.ratio)) : 1,
          signature: `${fill}|${image}`,
        };
      });
      return { theme: document.documentElement.dataset.theme ?? "dark", background, marks };
    },
    [host, classNames, base],
  );
}

export async function shotElement(page, selector, path) {
  const element = page.locator(selector).first();
  if (!(await element.count())) return false;
  await element.screenshot({ path });
  return true;
}

// WCAG 2.x relative-luminance contrast for [label, [selector, ...]] targets, measured in the
// page against the nearest painted ancestor background. SB-05 §7: >=4.5:1 text, >=3:1 chrome.
export async function contrastAudit(page, targets, fallbackBackground = "rgb(11, 16, 20)") {
  return page.evaluate(
    ([pairs, fallback]) => {
      const lum = (colour) => {
        const [r, g, b] = colour
          .match(/\d+(\.\d+)?/g)
          .slice(0, 3)
          .map(Number)
          .map((v) => {
            v /= 255;
            return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
          });
        return 0.2126 * r + 0.7152 * g + 0.0722 * b;
      };
      const ratio = (a, b) => {
        const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
        return +((hi + 0.05) / (lo + 0.05)).toFixed(2);
      };
      const backgroundOf = (element) => {
        let node = element;
        while (node) {
          const colour = getComputedStyle(node).backgroundColor;
          if (colour && colour !== "rgba(0, 0, 0, 0)" && !/, 0\)$/.test(colour)) return colour;
          node = node.parentElement;
        }
        return fallback;
      };
      return pairs.map(([name, selectors]) => {
        const matched = selectors.find((selector) => document.querySelector(selector));
        if (!matched) return { name, missing: true, tried: selectors };
        const element = document.querySelector(matched);
        const style = getComputedStyle(element);
        const background = backgroundOf(element);
        return {
          name,
          matched,
          fg: style.color,
          bg: background,
          size: style.fontSize,
          ratio: ratio(style.color, background),
        };
      });
    },
    [targets, fallbackBackground],
  );
}

// The sampler, as source, so it can also be installed into a document that does not exist yet
// (`addInitScript`) — a measurement that spans a navigation loses any sampler evaluated into
// the page it started from.
export const FRAME_SAMPLER = `() => {
  window.__gwFrames = [];
  window.__gwStop = false;
  let last = performance.now();
  const tick = (t) => {
    window.__gwFrames.push(t - last);
    last = t;
    if (!window.__gwStop) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}`;

/** Stops the sampler and hands back what it collected; [] when a navigation took it. */
export function readFrames(page) {
  return page.evaluate(() => {
    window.__gwStop = true;
    return window.__gwFrames ?? [];
  });
}

// Raw frame lengths in ms while `action` runs plus `ms` of settle; the caller judges them
// against its budget (SB-05 E-3: p95 <= 22 ms, none > 100 ms).
export async function frameProbe(page, action, ms = 3000) {
  await page.evaluate(`(${FRAME_SAMPLER})()`);
  await action();
  await page.waitForTimeout(ms);
  return readFrames(page);
}

export function tally(items, key = "status") {
  return items.reduce((acc, item) => {
    const k = item?.[key] ?? item;
    acc[k] = (acc[k] ?? 0) + 1;
    return acc;
  }, {});
}
