// Shared helpers for the browser gates and the e2e tier — the machinery every DIR-11 pass
// otherwise re-derives in work-output: launch, an instrumented page, the breakpoint ladder,
// screenshots, WCAG contrast sampling and a frame probe.
//
// Import-safe: nothing here touches the filesystem, the network or playwright until a
// function is called, so smoke.mjs can import it before deciding whether to skip.
import { existsSync, mkdirSync, readdirSync } from "node:fs";

export const PLAYWRIGHT_CACHE = "/root/.cache/ms-playwright";

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

export function redactor(key) {
  return (text) => (key ? String(text).replaceAll(key, "REDACTED") : String(text));
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
// non-2xx responses, tile and API traffic, and whether the key ever left the fragment.
export async function instrumentedPage(browser, { viewport, dsf, key = "", contextOpts } = {}) {
  const context = await browser.newContext({
    viewport: viewport ?? { width: 1600, height: 1000 },
    deviceScaleFactor: dsf ?? 1,
    ...(contextOpts ?? {}),
  });
  const page = await context.newPage();
  const redact = redactor(key);
  const journal = { pageerror: [], console: [], nonok: [], tiles: [], api: [], sentKey: [] };
  page.on("pageerror", (error) => journal.pageerror.push(redact(error.message)));
  page.on("console", (message) => {
    if (message.type() === "error" || message.type() === "warning")
      journal.console.push(`${message.type()}: ${redact(message.text()).slice(0, 300)}`);
  });
  page.on("request", (request) => {
    if (key && request.url().includes(key)) journal.sentKey.push(redact(request.url()));
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

// Raw frame lengths in ms while `action` runs plus `ms` of settle; the caller judges them
// against its budget (SB-05 E-3: p95 <= 22 ms, none > 100 ms).
export async function frameProbe(page, action, ms = 3000) {
  await page.evaluate(() => {
    window.__gwFrames = [];
    window.__gwStop = false;
    let last = performance.now();
    const tick = (t) => {
      window.__gwFrames.push(t - last);
      last = t;
      if (!window.__gwStop) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
  await action();
  await page.waitForTimeout(ms);
  return page.evaluate(() => {
    window.__gwStop = true;
    return window.__gwFrames;
  });
}

export function tally(items, key = "status") {
  return items.reduce((acc, item) => {
    const k = item?.[key] ?? item;
    acc[k] = (acc[k] ?? 0) + 1;
    return acc;
  }, {});
}
