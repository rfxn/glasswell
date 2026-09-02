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

const browser = await launch({ executablePath: chromeExecutable() });
for (const bp of BREAKPOINTS) {
  const { page, context } = await instrumentedPage(browser, { viewport: { width: bp.width, height: bp.height } });
  try {
    await page.goto(`${BASE}/?view=map`, { waitUntil: "networkidle" });
    await mapReady(page).catch(() => {});
    await page.waitForTimeout(2500);
    // The panel open: the wells rows, their order and their first-paint defaults are what
    // the generated roster now decides, so that is what a reviewer has to be able to see.
    const layers = page.locator("button:has-text('Layers')").first();
    if (await layers.count()) {
      await layers.click().catch(() => {});
      await page.waitForTimeout(800);
    }
    await page.screenshot({ path: `${OUT}/map-layers-${bp.width}.png`, fullPage: false });

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
