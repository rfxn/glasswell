// The implementer shots for the seam-hardening track, at every breakpoint lib.mjs declares.
// Not a gate: it asserts nothing and fails nothing. It photographs the three surfaces this
// track changed so a reviewer judges them at the train rather than reading a diff and
// imagining them — the map layer panel, whose wells rows are generated from the registry now,
// and two well cards, one of which is a jurisdiction the neighbour mart's measured domain does
// not reach and whose basin registers no length rule.
//
//   GW_ROOT=... GW_PORT=8141 GW_SEED=<a seed planting the excluded registration> \
//     python3 tests/support/serve_branch.py
//   GLASSWELL_BASE_URL=http://127.0.0.1:8141 GLASSWELL_KEY_FILE=/tmp/gw-serve/owner.key \
//     node tests/e2e/seam-shots.mjs
//
// Read-only, against the branch's own bundle and the branch's own API on an ephemeral
// PostGIS — never the deployed instance.
import { mkdirSync } from "node:fs";
import { BREAKPOINTS, baseUrl, chromeExecutable, instrumentedPage, launch, mapReady } from "./lib.mjs";

const BASE = baseUrl();
const OUT = process.env.GW_SHOTS ?? "work-output/seam-shots";
const CO = "0512300001";
const ND = "3305310451";
mkdirSync(OUT, { recursive: true });

/** The tile and hint toasts sit over the map chrome at narrow widths. Dismissed rather than
 *  waited out: they have no timeout and a shot taken behind one photographs the toast. */
async function dismissToasts(page) {
  for (const selector of ["button[aria-label='Dismiss']", ".gw-toast button", "button:has-text('×')"]) {
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
  const { page, context } = await instrumentedPage(browser, { viewport: { width: bp.width, height: bp.height } });
  try {
    await page.goto(`${BASE}/?view=map`, { waitUntil: "networkidle" });
    await mapReady(page).catch(() => {});
    await page.waitForTimeout(2500);
    // The panel open: the wells rows, their order and their first-paint defaults are what
    // the generated roster now decides, so that is what a reviewer has to be able to see.
    //
    // Loudly. At 390 the tile toast overlays the Layers button, Playwright's actionability
    // check timed out, a bare `.catch(() => {})` discarded it, and the shot was taken with the
    // panel shut — a file that looks like evidence and is not. The toast is dismissed first
    // and a failure names itself in the filename and on stdout.
    await dismissToasts(page);
    let opened = true;
    try {
      await page.locator("button:has-text('Layers')").first().click({ timeout: 5000 });
      await page.waitForTimeout(800);
    } catch (error) {
      opened = false;
      console.log(`  WARN ${bp.width}: layer panel did not open — ${String(error).split("\n")[0]}`);
    }
    const suffix = opened ? "" : "-PANEL-SHUT";
    await page.screenshot({ path: `${OUT}/map-layers-${bp.width}${suffix}.png`, fullPage: false });
    if (!opened) failures += 1;

    // The four child rows are the generated ones, and their subtitles are where the served
    // count lands. Closed, the family shows one parent and says nothing about them.
    if (opened) {
      // The family head, by its own class: `:has-text("Wells")` matched the survey-traces row,
      // whose subtitle says "525 of 43,817 wells", and photographed that instead.
      const disclosure = page.locator(".gw-layer-family-head button[aria-expanded]").first();
      await disclosure.click({ timeout: 4000 }).catch(() => {});
      await page.waitForTimeout(600);
      await page.screenshot({ path: `${OUT}/map-wells-family-${bp.width}.png`, fullPage: false });
    }

    await page.goto(`${BASE}/?view=map&well=${CO}`, { waitUntil: "networkidle" });
    await page.waitForTimeout(3000);
    await page.screenshot({ path: `${OUT}/card-neighbours-refused-${bp.width}.png`, fullPage: false });

    await page.goto(`${BASE}/?view=map&well=${ND}`, { waitUntil: "networkidle" });
    await page.waitForTimeout(3000);
    await page.screenshot({ path: `${OUT}/card-north-dakota-${bp.width}.png`, fullPage: false });
    console.log(`shot ${bp.width}x${bp.height} ok`);
  } finally {
    await context.close();
  }
}
await browser.close();
if (failures > 0) {
  console.error(`${failures} shot(s) were taken with the panel shut; they are named -PANEL-SHUT`);
  process.exit(1);
}
