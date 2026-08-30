// The map chrome's geometry, which nothing else in tests/e2e measures. smoke.mjs asserts
// #gw-map, #gw-card and #gw-drawer and no .gw-layers selector at all; ui-modal-qa's
// fold-proof covers the card and the drawer bodies only. So "how much of the layer list is
// above the fold" was a number no gate computed, which is how a reviewer-judged pass graded
// this panel clean while two rows of twelve were reachable without scrolling.
//
// What it measures is a property of the *bundle*, not of the data: the rows come from the
// static registry, so `python3 -m http.server web/dist` is a complete fixture and the numbers
// it yields are identical to a serve_branch run (635/635, 12/12, mean 46.4 at 1600x1000).
// That is what lets this run in CI on every push with no database, no key and no deployed
// instance — see the `map-chrome` job. A key is used when one is present and never required.
//
// Read-only. The key rides the X-Glasswell-Key header (lib.mjs), never a url, and every
// printed line goes through the redactor.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { BREAKPOINTS, baseUrl, chromeExecutable, instrumentedPage, keyGuard, launch, mapReady, redact } from "./lib.mjs";

const BASE = baseUrl();
const REQUIRE = process.env.GLASSWELL_REQUIRE_E2E === "1";
// The roster is read off the registry the panel renders, so a layer added later cannot leave
// this script asserting against a list that has moved.
const REGISTRY = fileURLToPath(new URL("../../web/src/map/registry.ts", import.meta.url));
const BLOCKS = readFileSync(REGISTRY, "utf8").split(/\n {2}\{\n/).slice(1);
const LAYERS = BLOCKS.map((block) => ({
  id: /\bid:\s*"([^"]+)"/.exec(block)?.[1],
  defaultOn: /\bdefaultOn:\s*true/.test(block),
  pending: /\bpendingSource:\s*true/.test(block),
})).filter((layer) => layer.id);
if (LAYERS.length === 0) throw new Error(`no layers parsed from ${REGISTRY}`);
const OPERABLE = LAYERS.filter((layer) => !layer.pending).map((layer) => layer.id);
const DEFAULT_ON = LAYERS.filter((layer) => layer.defaultOn).map((layer) => layer.id);

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

function unavailable(reason) {
  if (REQUIRE) {
    console.error(`GLASSWELL_REQUIRE_E2E is set but ${reason}`);
    process.exit(1);
  }
  console.log(`chrome-fold skipped: ${reason}`);
  process.exit(0);
}

try {
  await import("playwright-core");
} catch {
  unavailable("playwright-core is not installed (npm --prefix tests/e2e install)");
}
if (!chromeExecutable()) unavailable("no chromium build found (set GW_CHROME)");
// Still called with no key: its job is to refuse a key visible in argv, which holds either way.
const KEY = keyGuard();

/** Everything the fold arithmetic needs, read in the page against the painted layout. */
const MEASURE = () => {
  const panel = document.querySelector(".gw-layers");
  const body = document.querySelector(".gw-layers-body");
  const button = document.querySelector(".gw-layers-button");
  if (!panel || !body) return { missing: true };
  const fold = body.getBoundingClientRect().top + body.clientHeight;
  // A row inside a shut group has a zero rect, so it is trivially "above the fold" and it
  // drags the mean row height down. Rendered-ness is carried here and the arithmetic below
  // divides by it, or grouping would have turned both numbers into a pass that measures nothing.
  const rows = [...document.querySelectorAll(".gw-layer-row")].map((row) => ({
    id: row.dataset.layer,
    height: +row.getBoundingClientRect().height.toFixed(1),
    rendered: row.getBoundingClientRect().height > 0,
    collapsed: row.querySelector(".gw-layer-detail")?.hidden !== false,
    aboveFold: row.getBoundingClientRect().bottom <= fold + 0.5,
  }));
  const groups = [...document.querySelectorAll(".gw-layer-group-head")].map((head) => ({
    id: head.closest(".gw-layer-group")?.dataset.group,
    aboveFold: head.getBoundingClientRect().bottom <= fold + 0.5,
  }));
  const a = panel.getBoundingClientRect();
  const b = button?.getBoundingClientRect();
  const span = (lo1, hi1, lo2, hi2) => Math.max(0, Math.min(hi1, hi2) - Math.max(lo1, lo2));
  return {
    disclosed: document.querySelector(".gw-layer-name") !== null,
    keyPanelUp: document.getElementById("gw-key-host")?.hidden === false,
    scrollHeight: body.scrollHeight,
    clientHeight: body.clientHeight,
    rows,
    groups,
    ariaExpanded: button?.getAttribute("aria-expanded") ?? null,
    occlusion: b
      ? +(span(a.left, a.right, b.left, b.right) * span(a.top, a.bottom, b.top, b.bottom)).toFixed(1)
      : null,
  };
};

const browser = await launch();
let skipped = false;

for (const viewport of BREAKPOINTS) {
  const at = `${viewport.width}x${viewport.height}`;
  const { context, page } = await instrumentedPage(browser, { viewport, auth: Boolean(KEY) });
  await page.goto(`${BASE}/?view=map`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await mapReady(page, 3000);
  // The coach mark reserves the control band at <=520 and moves the button the moment it is
  // dismissed, so a click while it is up lands on neither position.
  await page.evaluate(() => document.querySelector(".gw-hint-close")?.click());
  await page.waitForTimeout(400);
  await page.click(".gw-layers-button");
  await page.waitForTimeout(400);

  const seen = await page.evaluate(MEASURE);
  if (seen.missing) {
    bad(`${at} the layer panel opens`, "no .gw-layers / .gw-layers-body in the document");
    await context.close();
    continue;
  }
  if (seen.keyPanelUp) {
    // A keyless run against an instance that demands one measures a panel under a modal
    // overlay. Fail naming the cause rather than reporting whatever that geometry was.
    bad(`${at} the instance is reachable without a key panel`,
      "the app raised its key panel — set GLASSWELL_KEY_FILE, or point at a static bundle");
    await context.close();
    continue;
  }
  if (!seen.disclosed) {
    // Feature detection, not a weakened assertion: an instance built before the per-row
    // disclosure has nothing here to assert against, and says so rather than passing quietly.
    console.log(`  note ${at} instance predates the row disclosure — fold not asserted`);
    skipped = true;
    await context.close();
    continue;
  }

  const rendered = seen.rows.filter((row) => row.rendered);
  const below = rendered.filter((row) => !row.aboveFold).map((row) => row.id);
  const missing = OPERABLE.filter((id) => !seen.rows.some((row) => row.id === id));
  const collapsed = rendered.filter((row) => row.collapsed);
  const mean = collapsed.reduce((sum, row) => sum + row.height, 0) / (collapsed.length || 1);
  const groupsBelow = seen.groups.filter((group) => !group.aboveFold).map((group) => group.id);
  console.log(
    `  [${at}] scrollHeight ${seen.scrollHeight} / clientHeight ${seen.clientHeight} · ` +
      `${rendered.length - below.length}/${rendered.length} rendered rows above the fold · ` +
      `${seen.groups.length} groups · mean collapsed row ${mean.toFixed(1)}px`,
  );

  // The roster is the registry's, so this is what catches a layer that stopped being offered
  // at all — the failure a fold measurement over rendered rows cannot see.
  assert(missing.length === 0, `${at} every operable layer has a row in the panel`,
    `no row for: ${missing.join(", ")}`);
  assert(
    OPERABLE.every((id) => !below.includes(id)),
    `${at} every operable layer the panel renders is above the fold`,
    `below: ${below.join(", ")}`,
  );
  assert(
    DEFAULT_ON.every((id) => !below.includes(id)),
    `${at} both default-on layers are reachable without scrolling`,
    `below: ${DEFAULT_ON.filter((id) => below.includes(id)).join(", ")}`,
  );
  // A row in a shut group is reached through its header, so the header is what has to be
  // reachable. Skipped on an instance that predates grouping, which renders none.
  if (seen.groups.length > 0) {
    assert(groupsBelow.length === 0, `${at} every layer group header is above the fold`,
      `below: ${groupsBelow.join(", ")}`);
  }
  assert(mean <= 60, `${at} a collapsed row stays one line`, `mean ${mean.toFixed(1)}px`);
  assert(seen.occlusion === 0, `${at} the panel does not cover the button that opens it`,
    `${seen.occlusion}px² of overlap`);
  assert(seen.ariaExpanded === "true", `${at} the Layers control reports the panel open`,
    `aria-expanded ${seen.ariaExpanded}`);

  await page.keyboard.press("Escape");
  await page.waitForTimeout(300);
  const dismissed = await page.evaluate(() => ({
    hidden: document.querySelector(".gw-layers")?.hidden,
    focus: document.activeElement?.className ?? "",
  }));
  assert(dismissed.hidden === true, `${at} Escape closes the panel`, "the panel stayed open");
  assert(
    dismissed.focus.includes("gw-layers-button"),
    `${at} focus returns to the control rather than to <body>`,
    `focus landed on "${dismissed.focus}"`,
  );

  await context.close();
}

await browser.close();
if (skipped && REQUIRE) {
  console.error("GLASSWELL_REQUIRE_E2E is set and the instance predates the row disclosure");
  process.exit(1);
}
console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
