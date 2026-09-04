// The two measurements a reviewer makes with a screenshot and no unit test can make at all:
// whether every allocation-band fill is visible against the strip it is drawn on, in both
// themes, and whether the allocated-share chip is one bordered box or two.
//
//   GW_ROOT=... GW_PORT=8141 GW_SEED=.../seed.py python tests/support/serve_branch.py
//   GLASSWELL_BASE_URL=http://127.0.0.1:8141 GLASSWELL_KEY_FILE=/tmp/gw-serve-txgate/owner.key \
//     node tests/e2e/tx-allocation-audit.mjs
//
// Read-only, against the branch's own bundle and the branch's own API on an ephemeral
// PostGIS -- never the deployed instance.
import { baseUrl, instrumentedPage, launch, markContrast } from "./lib.mjs";

const BASE = baseUrl();
const TX_API10 = process.env.GW_TX_API10 ?? "4200300002";
// SB-05 §7: a graphic that carries no text still has to be visible, and 3:1 is the floor.
const FLOOR = 3;
// The two bands, each in its own vocabulary and its own prefix: what the filing said, and
// how this well's number was arrived at from it.
const BANDS = [
  {
    label: "allocation",
    host: ".gw-alloc-cells",
    base: "gw-alloc-mark",
    // The six the allocation vocabulary serves, in ALLOCATION_CLASSES order.
    classNames: [
      "gw-alloc-observed-gas-well",
      "gw-alloc-observed-single-well",
      "gw-alloc-equal-share",
      "gw-alloc-after-status-change",
      "gw-alloc-excluded-after-plug",
      "gw-alloc-unallocated",
    ],
  },
  {
    label: "state",
    host: ".gw-state-cells",
    base: "gw-state-mark",
    // The four a well-grain jurisdiction emits, plus the lease's own filing.
    classNames: [
      "gw-state-reported",
      "gw-state-reported-zero",
      "gw-state-withheld",
      "gw-state-no-report",
      "gw-state-lease-reported",
    ],
  },
];
// The theme toggle ships behind VITE_GW_THEME_TOGGLE, so the attribute the stylesheet keys
// on is set directly: what is being measured is the shipped rule, not the control.
const THEMES = ["dark", "light"];

const problems = [];
let checks = 0;

function require(condition, message) {
  checks += 1;
  if (!condition) problems.push(message);
}

async function openCard(page) {
  await page.goto(`${BASE}/?well=${TX_API10}`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector(".gw-card", { timeout: 30000 });
  await page.waitForSelector(".gw-alloc-row", { timeout: 30000 });
  await page.waitForTimeout(600);
}

const browser = await launch();
try {
  const { page, context } = await instrumentedPage(browser, {
    viewport: { width: 1600, height: 1000 },
  });
  await openCard(page);

  for (const theme of THEMES) {
    await page.evaluate((value) => {
      document.documentElement.dataset["theme"] = value;
    }, theme);
    await page.waitForTimeout(200);
    for (const band of BANDS) {
      const measured = await markContrast(page, {
        host: band.host,
        classNames: band.classNames,
        base: band.base,
      });
      require(!measured.missing, `${theme}: no ${band.label} band to measure (${measured.missing})`);
      if (measured.missing) continue;
      for (const mark of measured.marks) {
        // Every opaque paint, not the best one: a hatch whose visible stripe carries it while
        // its other stripe is the strip passes on luck, and luck is not an encoding.
        const worst = mark.paints.length ? Math.min(...mark.paints.map((entry) => entry.ratio)) : 1;
        require(
          worst >= FLOOR,
          `${theme}: ${mark.className} paints ${worst}:1 on ${measured.background},` +
            ` under the ${FLOOR}:1 floor (${mark.paints.map((p) => p.colour).join(", ") || "no paint"})`,
        );
        console.log(
          `  [${theme}] ${mark.className.padEnd(32)} ${String(worst).padStart(6)}:1` +
            `  ${mark.paints.map((p) => `${p.colour} ${p.ratio}:1`).join(" / ") || "no paint"}`,
        );
      }
      const signatures = new Set(measured.marks.map((mark) => mark.signature));
      require(
        signatures.size === band.classNames.length,
        `${theme}: the ${band.label} band's ${band.classNames.length} classes share` +
          ` ${signatures.size} encodings; two classes a reader cannot tell apart are one class`,
      );
    }
  }

  await page.evaluate(() => {
    document.documentElement.dataset["theme"] = "dark";
  });

  // M4: `display: inline` paints the chip's border once per line box, so a chip that wraps
  // reads as two boxes -- one of them a bordered `100%` with nothing to say what of.
  for (const width of [1600, 1366]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.waitForTimeout(400);
    await page.locator(".gw-cumulative-row").first().scrollIntoViewIfNeeded();
    const boxes = await page.evaluate(() =>
      [...document.querySelectorAll(".gw-alloc-share")].map((node) => ({
        text: node.textContent,
        rects: node.getClientRects().length,
      })),
    );
    require(boxes.length > 0, `${width}: no allocated-share chip on the cumulative row`);
    for (const box of boxes) {
      require(
        box.rects === 1,
        `${width}: the "${box.text}" chip paints ${box.rects} bordered boxes`,
      );
      console.log(`  [${width}] ${JSON.stringify(box.text)} ${box.rects} box(es)`);
    }
  }

  await context.close();
} finally {
  await browser.close();
}

if (problems.length) {
  for (const problem of problems) console.error(`  [fails] ${problem}`);
  console.error(`\n${problems.length} of ${checks} checks failed`);
  process.exitCode = 1;
} else {
  console.log(`\n${checks} checks passed`);
}
