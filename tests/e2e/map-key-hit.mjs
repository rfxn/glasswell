// Every control in the map key has to be where it looks. The key is anchored to the bottom of
// the map and grows upward as its disclosures open, so a key with more in it than the viewport
// holds used to grow off the map and under the app header: at 390x844 with both dimension
// blocks open its title — which is also its collapse control — sat at y 46 against a header
// bottom of 65, and a tap there landed on the Map/Explore/Status switch, navigating the reader
// off the map (visual-map-wells-by R1).
//
// "Is the title above the header" is the instance, not the property. What is asserted here is
// the property: for every interactive element the key holds that a reader can actually see —
// inside the viewport, and not scrolled out of a scrollport — `elementFromPoint` at its centre
// returns that element or a descendant of it. That holds for a control this branch adds, for
// one added later, and for whatever the clamp does when a third dimension block arrives.
//
// Read-only, and it needs a served instance whose counts populate the dimension blocks: with
// them absent (a static bundle, or an instance predating them) it says so and asserts the
// states it can reach rather than passing quietly on a key it never made grow.
import { baseUrl, chromeExecutable, instrumentedPage, keyGuard, launch, mapReady, redact } from "./lib.mjs";

const BASE = baseUrl();
const REQUIRE = process.env.GLASSWELL_REQUIRE_E2E === "1";
// The two phone heights R1 was measured at, and the desktop one where the same growth reaches
// the header once the vocabulary is open too.
const VIEWPORTS = [
  { width: 1600, height: 1000 },
  { width: 390, height: 844 },
  { width: 390, height: 740 },
];

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
  console.log(`map-key-hit skipped: ${reason}`);
  process.exit(0);
}

try {
  await import("playwright-core");
} catch {
  unavailable("playwright-core is not installed (npm --prefix tests/e2e install)");
}
if (!chromeExecutable()) unavailable("no chromium build found (set GW_CHROME)");
const KEY = keyGuard();

/**
 * Read in the page: the key's geometry against the map and the header, and one hit test per
 * interactive element it holds.
 */
const MEASURE = () => {
  const legend = document.querySelector(".gw-lg");
  const map = document.querySelector("#gw-map");
  const header = document.querySelector("#gw-header");
  if (!legend || !map || !header) return { missing: true };
  const name = (node) =>
    node ? `${node.tagName.toLowerCase()}${node.className ? `.${String(node.className).trim().split(/\s+/)[0]}` : ""}` : "null";

  // The one exemption, and it has to be exactly this narrow: a control scrolled out of one of
  // the key's OWN scrollports is not one the reader is aiming at. Clipped by anything outside
  // the key — the map's own overflow, say — means the key has left its frame, which is the
  // defect rather than an excuse for skipping the control.
  const clippedBy = (node, cx, cy) => {
    for (let parent = node.parentElement; parent; parent = parent.parentElement) {
      const style = getComputedStyle(parent);
      if (style.overflowX === "visible" && style.overflowY === "visible") continue;
      const r = parent.getBoundingClientRect();
      if (cx < r.left || cx > r.right || cy < r.top || cy > r.bottom)
        return { by: name(parent), scrollport: legend.contains(parent) };
    }
    return null;
  };

  const controls = [...legend.querySelectorAll("button, a[href], input, label, [tabindex]:not([tabindex='-1'])")]
    .filter((node) => {
      const style = getComputedStyle(node);
      const r = node.getBoundingClientRect();
      return style.display !== "none" && style.visibility !== "hidden" && r.width > 0 && r.height > 0;
    })
    .map((node) => {
      const r = node.getBoundingClientRect();
      const cx = Math.round(r.left + r.width / 2);
      const cy = Math.round(r.top + r.height / 2);
      const onScreen = cx >= 0 && cy >= 0 && cx <= window.innerWidth && cy <= window.innerHeight;
      const clip = clippedBy(node, cx, cy);
      const hit = onScreen && !clip ? document.elementFromPoint(cx, cy) : null;
      return {
        control: name(node),
        label: (node.getAttribute("aria-label") ?? node.textContent?.trim().slice(0, 24)) || null,
        at: `${cx},${cy}`,
        scrolledAway: Boolean(clip?.scrollport),
        hits: onScreen && !clip && (hit === node || node.contains(hit)),
        // Why it could not be reached, in the words of whatever stopped it.
        hit: clip && !clip.scrollport ? `clipped by ${clip.by}` : onScreen ? name(hit) : "off screen",
      };
    });

  const rect = (node) => {
    const r = node.getBoundingClientRect();
    return { top: Math.round(r.top), bottom: Math.round(r.bottom) };
  };
  const title = legend.querySelector(".gw-lg-title");
  const titleRect = title.getBoundingClientRect();
  const titleHit = document.elementFromPoint(
    Math.round(titleRect.left + titleRect.width / 2),
    Math.round(titleRect.top + titleRect.height / 2),
  );

  return {
    legend: rect(legend),
    map: rect(map),
    header: rect(header),
    title: rect(title),
    titleHit: name(titleHit),
    titleHits: titleHit === title || title.contains(titleHit),
    disclosures: [...legend.querySelectorAll(".gw-lg-dtitle")].filter((n) => n.getAttribute("aria-expanded") === "true").length,
    dimensionBlocks: legend.querySelectorAll(".gw-lg-dim:not([hidden])").length,
    controls,
    // The whole point: a control the reader has not scrolled away that a tap would not reach.
    misTargets: controls.filter((control) => !control.scrolledAway && !control.hits),
  };
};

const browser = await launch();
let noBlocks = false;

for (const viewport of VIEWPORTS) {
  const at = `${viewport.width}x${viewport.height}`;
  const { context, page } = await instrumentedPage(browser, { viewport, auth: Boolean(KEY) });
  await page.goto(`${BASE}/?view=map`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await mapReady(page, 4000);
  // Both reserve bands the key competes for, and both move the moment they are dismissed.
  await page.evaluate(() => {
    document.querySelector(".gw-hint-close")?.click();
    document.querySelector(".gw-banner-x")?.click();
  });
  await page.waitForTimeout(400);
  await page.click(".gw-lg-title");
  await page.waitForTimeout(400);

  // Three states, because the defect is growth: the key as it opens, with the dimension blocks
  // open, and with the vocabulary open on top of them — the closest thing on hand to the next
  // block somebody adds.
  const states = [];
  states.push(["disclosures shut", await page.evaluate(MEASURE)]);
  await page.evaluate(() => {
    for (const title of document.querySelectorAll(".gw-lg-dtitle"))
      if (title.getAttribute("aria-expanded") !== "true") title.click();
  });
  await page.waitForTimeout(400);
  states.push(["both disclosures open", await page.evaluate(MEASURE)]);
  await page.evaluate(() => {
    const vocab = document.querySelector(".gw-lg-vocab-title");
    if (vocab?.getAttribute("aria-expanded") !== "true") vocab?.click();
  });
  await page.waitForTimeout(400);
  states.push(["every block open", await page.evaluate(MEASURE)]);

  for (const [state, seen] of states) {
    if (seen.missing) {
      bad(`${at} ${state} the map key is in the document`, "no .gw-lg / #gw-map / #gw-header");
      continue;
    }
    if (seen.dimensionBlocks === 0) noBlocks = true;
    console.log(
      `  [${at}] ${state}: key top ${seen.legend.top} (map ${seen.map.top}, header bottom ${seen.header.bottom}) · ` +
        `${seen.dimensionBlocks} blocks, ${seen.disclosures} open · ${seen.controls.length} controls, ` +
        `${seen.controls.filter((c) => c.scrolledAway).length} scrolled away`,
    );

    assert(
      seen.legend.top >= seen.map.top - 0.5,
      `${at} ${state} the key stays on the map it annotates`,
      `key top ${seen.legend.top} against a map top of ${seen.map.top}`,
    );
    // The title is the only control that collapses the key and the only one that announces
    // aria-expanded, so it is named as well as swept.
    assert(
      seen.title.top >= seen.header.bottom - 0.5,
      `${at} ${state} the key's own title row clears the app header`,
      `title top ${seen.title.top} against a header bottom of ${seen.header.bottom}`,
    );
    assert(
      seen.titleHits,
      `${at} ${state} a tap on the collapse control reaches the collapse control`,
      `elementFromPoint at the title's centre returned ${seen.titleHit}`,
    );
    assert(
      seen.misTargets.length === 0,
      `${at} ${state} every control the reader has not scrolled away answers its own hit test`,
      seen.misTargets.map((m) => `${m.control} (${m.label}) at ${m.at} -> ${m.hit}`).join("; "),
    );
  }

  await context.close();
}

await browser.close();
if (noBlocks) {
  console.log(
    "  note the key rendered no dimension block — an instance without counts for them cannot " +
      "be made to grow, so the open states above assert less than they do against live counts",
  );
  if (REQUIRE) {
    console.error("GLASSWELL_REQUIRE_E2E is set and the key rendered no dimension block");
    process.exit(1);
  }
}
console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
