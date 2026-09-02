// The implementer shots for the Colorado track, at every breakpoint lib.mjs declares.
// Not a gate: it asserts nothing about pixels and fails only when a shot was taken of the
// wrong thing. It photographs the surfaces a fifth jurisdiction arrives on, so a reviewer
// judges them at the train rather than reading a diff and imagining them.
//
//   GW_ROOT=... GW_PORT=8142 GW_SEED=tests/support/serve_seed_colorado.py \
//     python3 tests/support/serve_branch.py
//   GLASSWELL_BASE_URL=http://127.0.0.1:8142 GLASSWELL_KEY_FILE=/tmp/gw-serve/owner.key \
//     node tests/e2e/colorado-shots.mjs
//
// Read-only, against the branch's own bundle and the branch's own API on an ephemeral
// PostGIS — never the deployed instance.
import { mkdirSync } from "node:fs";
import { BREAKPOINTS, baseUrl, chromeExecutable, instrumentedPage, launch, mapReady } from "./lib.mjs";

const BASE = baseUrl();
const OUT = process.env.GW_SHOTS ?? "work-output/colorado-shots";
// The producing well, and the one whose status ECMC documents with no equivalent class.
const PRODUCER = "0512324638";
const SUSPENDED = "0512324700";
mkdirSync(OUT, { recursive: true });

async function dismissToasts(page) {
  for (const selector of ["button[aria-label='Dismiss']", ".gw-toast button"]) {
    const buttons = page.locator(selector);
    for (let i = (await buttons.count()) - 1; i >= 0; i -= 1) {
      await buttons.nth(i).click({ timeout: 1500 }).catch(() => {});
    }
  }
  await page.waitForTimeout(300);
}

let failures = 0;
const browser = await launch({ executablePath: chromeExecutable() });
for (const bp of BREAKPOINTS) {
  const { page, context } = await instrumentedPage(browser, {
    viewport: { width: bp.width, height: bp.height },
  });
  try {
    await page.goto(`${BASE}/?view=map`, { waitUntil: "networkidle" });
    await mapReady(page).catch(() => {});
    await page.waitForTimeout(2500);
    await dismissToasts(page);

    // The layer row, inside the Wells family. A shot taken with the panel shut looks like
    // evidence and is not, so the failure names itself in the filename and on stdout.
    let opened = true;
    try {
      await page.locator("button:has-text('Layers')").first().click({ timeout: 5000 });
      await page.waitForTimeout(800);
      const disclosure = page.locator(".gw-layer-family-head button[aria-expanded]").first();
      await disclosure.click({ timeout: 4000 });
      await page.waitForTimeout(600);
    } catch (error) {
      opened = false;
      console.log(`  WARN ${bp.width}: layer panel did not open — ${String(error).split("\n")[0]}`);
    }
    const suffix = opened ? "" : "-PANEL-SHUT";
    await page.screenshot({ path: `${OUT}/co-layer-row-${bp.width}${suffix}.png` });
    if (!opened) failures += 1;

    // The panel closed first. At 390 it is a full-height sheet over the map, and the legend
    // is an overlay pinned to the map's bottom-left, so a click aimed at the key lands on the
    // sheet: the shot at that width failed for exactly this and nowhere else.
    await page.keyboard.press("Escape");
    await page.waitForTimeout(500);

    // The legend, where the registration's own note is rendered and the census counts it.
    // Two clicks, not one: the key opens on `.gw-lg-title` and the note this track added
    // lives behind `.gw-lg-vocab-title`, so a shot of the key alone would photograph
    // everything except the sentence it was taken for.
    let legend = true;
    try {
      await page.locator(".gw-lg-title").first().click({ timeout: 5000 });
      await page.waitForTimeout(500);
      await page.locator(".gw-lg-vocab-title").first().click({ timeout: 5000 });
      await page.waitForTimeout(700);
      const note = await page.locator(".gw-lg-note").first().textContent();
      if (!note || !note.includes("vacated permit")) {
        legend = false;
        console.log(`  WARN ${bp.width}: the registration's legend note is not on the page`);
      }
    } catch (error) {
      legend = false;
      console.log(`  WARN ${bp.width}: legend did not open — ${String(error).split("\n")[0]}`);
    }
    await page.screenshot({ path: `${OUT}/co-legend-${bp.width}${legend ? "" : "-SHUT"}.png` });
    if (!legend) failures += 1;

    // The producing well: status with its filed code, the chart the dual write makes render,
    // and the cumulative frame with the span sentence beside its totals.
    await page.goto(`${BASE}/?view=map&well=${PRODUCER}`, { waitUntil: "networkidle" });
    await page.waitForTimeout(3200);
    await page.screenshot({ path: `${OUT}/co-flyout-producing-${bp.width}.png` });

    // The cumulative frame, scrolled to rather than hoped for: it sits below the chart, so a
    // viewport shot of the card top photographs everything except the totals and the sentence
    // that says what they are over.
    let cumulative = true;
    try {
      const frame = page.locator(".gw-well-cumulatives").first();
      await frame.scrollIntoViewIfNeeded({ timeout: 5000 });
      await page.waitForTimeout(700);
      const text = await frame.textContent();
      if (!text || !text.includes("months filed")) {
        cumulative = false;
        console.log(`  WARN ${bp.width}: the cumulative frame states no span`);
      }
    } catch (error) {
      cumulative = false;
      console.log(`  WARN ${bp.width}: no cumulative frame — ${String(error).split("\n")[0]}`);
    }
    await page.screenshot({
      path: `${OUT}/co-cumulative-${bp.width}${cumulative ? "" : "-ABSENT"}.png`,
    });
    if (!cumulative) failures += 1;

    // The documented-with-no-class well, which is the case a reader is most likely to
    // misread: the regulator did say something, and the card has to show what.
    await page.goto(`${BASE}/?view=map&well=${SUSPENDED}`, { waitUntil: "networkidle" });
    await page.waitForTimeout(3200);
    await page.screenshot({ path: `${OUT}/co-flyout-documented-${bp.width}.png` });

    // Explore, on the facet domain the registry serves rather than a client table.
    await page.goto(`${BASE}/?view=explore&wb.state=05`, { waitUntil: "networkidle" });
    await page.waitForTimeout(2600);
    await page.screenshot({ path: `${OUT}/co-explore-${bp.width}.png` });
    console.log(`shot ${bp.width}x${bp.height} ok`);
  } finally {
    await context.close();
  }
}
await browser.close();
if (failures > 0) {
  console.error(`${failures} shot(s) were taken of a shut surface; they are named in the file`);
  process.exit(1);
}
