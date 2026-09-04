// The implementer shots for the Texas allocation track, at the three widths the gate judges.
// Not a gate: it asserts nothing about pixels and fails only when a shot was taken of the
// wrong thing. What a reviewer has to be able to see is that no number on a Texas card can be
// mistaken for a regulator's observation.
//
//   GW_ROOT=... GW_PORT=8137 GW_SEED=/tmp/tx-seed.py \
//     python3 tests/support/serve_branch.py
//   GLASSWELL_BASE_URL=http://127.0.0.1:8137 GLASSWELL_KEY_FILE=/tmp/gw-serve/owner.key \
//     node tests/e2e/tx-allocation-shots.mjs
//
// Read-only, against the branch's own bundle and the branch's own API on an ephemeral
// PostGIS — never the deployed instance.
import { mkdirSync } from "node:fs";

import { BREAKPOINTS, baseUrl, instrumentedPage, launch, shooter } from "./lib.mjs";

const BASE = baseUrl();
const OUT = process.env.GW_SHOTS ?? "work-output/po-review/shots-v080";
const TX_API10 = "4200345818";
// The three widths the visual gate judges. 390 is where the readout has to become two lines
// and where the second band has to still be legible under the first.
const WIDTHS = new Set([1600, 1024, 390]);
const AT = BREAKPOINTS.filter((point) => WIDTHS.has(point.width));

mkdirSync(OUT, { recursive: true });

async function openCard(page) {
  await page.goto(`${BASE}/?well=${TX_API10}`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector(".gw-card", { timeout: 30000 });
  // The chart is a dynamic import behind a request, so the band is the thing to wait on
  // rather than the frame that will hold it.
  await page.waitForSelector(".gw-alloc-row", { timeout: 30000 });
  await page.waitForTimeout(600);
}

async function scrollTo(page, selector) {
  const found = await page.locator(selector).first();
  if (!(await found.count())) return false;
  await found.scrollIntoViewIfNeeded();
  await page.waitForTimeout(250);
  return true;
}

const problems = [];

function require(condition, message) {
  if (!condition) problems.push(message);
}

const browser = await launch();
try {
  for (const point of AT) {
    const label = `${point.width}`;
    const { page, context } = await instrumentedPage(browser, { viewport: point });
    const shot = shooter(OUT);

    await openCard(page);
    require(
      await page.locator(".gw-alloc-row .gw-alloc-mark").count() > 0,
      `${label}: the allocation band drew no marks`,
    );
    require(
      (await page.locator("[data-state='production_pending_allocation']").count()) === 0,
      `${label}: the card still shows the pending-allocation panel over a chart`,
    );
    await scrollTo(page, ".gw-card-chart");
    await shot(page, `flyout-tx-allocated-${label}`);

    // The band and its key on their own, which is what the reviewer judges the encoding on.
    const strip = page.locator(".gw-state-strip").first();
    if (await strip.count()) {
      await strip.screenshot({ path: `${OUT}/chart-allocation-band-${label}.png` });
      console.log(`  [shot] chart-allocation-band-${label}.png`);
    }

    const cumulative = await scrollTo(page, ".gw-cumulative-row");
    require(cumulative, `${label}: the cumulative row did not render for a Texas well`);
    require(
      await page.locator(".gw-alloc-coverage").count() > 0,
      `${label}: the cumulative row carries no allocated-coverage chip`,
    );
    await shot(page, `flyout-tx-cumulative-${label}`);

    await page.goto(`${BASE}/?view=status`, { waitUntil: "domcontentloaded" });
    await page.waitForSelector("#gw-status-page:not([hidden])", { timeout: 30000 });
    await page.waitForSelector(".gw-status-check", { timeout: 30000 });
    const rows = await page.locator(".gw-status-check h4").allTextContents();
    for (const wanted of [
      "Allocation conservation",
      "Crosswalk agreement",
      "Allocation error bounds",
    ]) {
      require(rows.includes(wanted), `${label}: the Status page has no "${wanted}" row`);
    }
    // The three rows, not the first grid: the shot exists to show them together, and the
    // first grid is the serving plane.
    await page.evaluate(() => {
      const row = [...document.querySelectorAll(".gw-status-check")].find((node) =>
        node.textContent?.includes("Allocation conservation"),
      );
      row?.scrollIntoView({ block: "center" });
    });
    await page.waitForTimeout(300);
    await shot(page, `status-tx-validators-${label}`);

    await context.close();
  }
} finally {
  await browser.close();
}

if (problems.length) {
  for (const problem of problems) console.error(`  [wrong thing] ${problem}`);
  process.exitCode = 1;
} else {
  console.log(`\n${AT.length * 4} shots into ${OUT}`);
}
