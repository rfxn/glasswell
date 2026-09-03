// Implementer shots and layout assertions for the well card's second generation, at every
// breakpoint lib.mjs declares. It both asserts and photographs: the rail's whole argument is a
// measurement (the map is beside the card, not under it) and a reviewer judges the rest.
//
//   GW_ROOT=... GW_PORT=8180 python3 tests/support/serve_branch.py
//   GLASSWELL_BASE_URL=http://127.0.0.1:8180 GLASSWELL_KEY_FILE=/tmp/gw-wellcard/owner.key \
//     GW_SHOTS=work-output/wellcard-shots/p1 node tests/e2e/wellcard-shots.mjs
//
// Read-only, against the branch's own bundle and the branch's own API on an ephemeral
// PostGIS, never the deployed instance.
import { mkdirSync } from "node:fs";

import { BREAKPOINTS, baseUrl, chromeExecutable, instrumentedPage, launch, mapReady, shooter } from "./lib.mjs";

const EXPECTED_ORDER = [
  "production",
  "cumulative",
  "identity",
  "completions",
  "neighbours",
  "land",
  "basin",
  "pools",
  "peer",
  "lineage",
];

const BASE = baseUrl();
const OUT = process.env.GW_SHOTS ?? "work-output/wellcard-shots/p1";
const WELL = process.env.GW_WELL ?? "3305310451";
mkdirSync(OUT, { recursive: true });
const shoot = shooter(OUT);

let failures = 0;
const check = (ok, message) => {
  console.log(`  ${ok ? "ok  " : "FAIL"} ${message}`);
  if (!ok) failures += 1;
};

/** Rectangles of the two panels the rail's argument is about, plus the rail's own attribute. */
const geometry = (page) =>
  page.evaluate(() => {
    const box = (selector) => {
      const element = document.querySelector(selector);
      if (!element || element.hidden) return null;
      const { x, width, height } = element.getBoundingClientRect();
      return { x: Math.round(x * 100) / 100, width: Math.round(width * 100) / 100, height: Math.round(height) };
    };
    return {
      map: box("#gw-map"),
      card: box("#gw-card"),
      drawer: box("#gw-drawer"),
      chrome: box("#gw-rail-chrome"),
      locate: (() => {
        const button = document.getElementById("gw-rail-locate");
        return button && !button.hidden ? button.getAttribute("aria-label") : null;
      })(),
      toggle: getComputedStyle(document.getElementById("gw-rail-toggle")).display,
      sections: [...document.querySelectorAll("#gw-card .gw-section")].map((node) => ({
        id: node.dataset.section,
        expanded: node.querySelector(".gw-section-toggle")?.getAttribute("aria-expanded"),
      })),
      absent: document.querySelector(".gw-section-absent-note")?.textContent ?? null,
      focused: document.activeElement?.closest?.(".gw-section")?.dataset?.section ?? null,
      rail: document.getElementById("gw-main")?.getAttribute("data-rail") ?? null,
      snap: document.getElementById("gw-main")?.getAttribute("data-sheet-snap") ?? null,
      hint: !document.querySelector(".gw-hint")?.hidden,
      // The declared offset, not the distance from the viewport: .gw-hint is absolute inside
      // the header's own positioned cluster, so its containing block is not the window.
      hintRight: (() => {
        const hint = document.querySelector(".gw-hint");
        return hint ? getComputedStyle(hint).right : null;
      })(),
    };
  });

/** No pointer anywhere: the teaching hint dismisses itself on the first pointerdown. */
const clickWithoutPointer = (page, selector) =>
  page.evaluate((target) => {
    const element = document.querySelector(target);
    if (!element) return false;
    element.click();
    return true;
  }, selector);

const overlap = (a, b) => a && b && a.x < b.x + b.width && b.x < a.x + a.width;

const browser = await launch({ executablePath: chromeExecutable() });
if (!browser) {
  console.log("no chromium: nothing photographed");
  process.exit(process.env.GLASSWELL_REQUIRE_E2E ? 1 : 0);
}

for (const bp of BREAKPOINTS) {
  const tag = `${bp.width}x${bp.height}`;
  console.log(`\n${tag}`);
  const { page, context } = await instrumentedPage(browser, { viewport: bp });
  try {
    await page.goto(`${BASE}/?well=${WELL}`, { waitUntil: "networkidle" });
    await mapReady(page).catch(() => {});
    await page.waitForTimeout(2500);
    const open = await geometry(page);
    console.log(`  map ${JSON.stringify(open.map)} card ${JSON.stringify(open.card)} rail ${open.rail}`);
    console.log(`  sections ${open.sections.map((each) => `${each.id}:${each.expanded}`).join(" ")}`);
    await shoot(page, `${tag}-card-open`);

    const order = open.sections.map((each) => each.id);
    check(
      order.join(",") === EXPECTED_ORDER.filter((id) => order.includes(id)).join(","),
      `the sections render in the one fixed order (${order.join(", ")})`,
    );
    check(
      open.sections.filter((each) => each.expanded === "true").map((each) => each.id).join(",") ===
        "production,cumulative,identity",
      "three expanded by default and the rest collapsed",
    );

    if (bp.width > 900) {
      check(open.rail === "open", "the rail is a column, not a closed shell");
      check(!overlap(open.map, open.card), `#gw-map and #gw-card do not overlap (map ${open.map?.width}, card at ${open.card?.x})`);
      check(open.map.width > 500, `the map column is over 500 px wide (${open.map.width})`);
      check(open.locate?.startsWith("Centre the map on ") === true, `Locate names the well it centres on (${open.locate})`);
    } else {
      check(open.snap !== null, `the sheet declares a snap point (${open.snap})`);
      check(open.toggle === "none", `the collapse control is not shown where there is no rail to collapse (${open.toggle})`);
      check(open.map.width === bp.width, `the map keeps the full width behind the sheet (${open.map.width})`);
    }

    // Collapsed: the strip, and the teaching hint stepping aside by the strip rather than by
    // a rail that is no longer there.
    if (bp.width > 900) {
      await clickWithoutPointer(page, "#gw-rail-toggle");
      await page.waitForTimeout(700);
      const collapsed = await geometry(page);
      console.log(`  collapsed: map ${JSON.stringify(collapsed.map)} chrome ${JSON.stringify(collapsed.chrome)} hint ${collapsed.hint} at right ${collapsed.hintRight}`);
      await shoot(page, `${tag}-rail-collapsed`);
      check(collapsed.rail === "collapsed", "the rail collapses to its strip");
      check(collapsed.chrome !== null && collapsed.chrome.width <= 41, `the strip is 40 px (${collapsed.chrome?.width})`);
      check(Math.abs(collapsed.map.width - (bp.width - 41)) <= 1, `the map takes the column back to the strip (${collapsed.map.width} of ${bp.width})`);
      check(collapsed.hint, "the teaching hint is still up to be judged beside the strip");
      check(collapsed.hintRight === "56px", `the hint steps aside by the strip and not by a rail that is no longer there (right: ${collapsed.hintRight}, want the 40 px strip plus 16)`);
      check(open.hintRight !== collapsed.hintRight, `the open rail and the strip do not step it aside by the same amount (${open.hintRight} then ${collapsed.hintRight})`);
      await clickWithoutPointer(page, "#gw-rail-toggle");
      await page.waitForTimeout(500);
    }

    // The drawer: its own column at 1600 and above, stacked in the rail below it, and the map
    // does not move when it stacks.
    if (bp.width > 900) {
      const opened = await clickWithoutPointer(page, "#gw-card .gw-handle");
      if (opened) {
        await page.waitForTimeout(1200);
        const withDrawer = await geometry(page);
        console.log(`  drawer open: map ${JSON.stringify(withDrawer.map)} drawer ${JSON.stringify(withDrawer.drawer)}`);
        await shoot(page, `${tag}-drawer-open`);
        check(!overlap(withDrawer.map, withDrawer.drawer), "#gw-map and #gw-drawer do not overlap");
        if (bp.width >= 1600) {
          check(Math.abs(withDrawer.map.width - 578) <= 1, `the map column is 578 px with the drawer open (${withDrawer.map.width})`);
        } else {
          check(Math.abs(withDrawer.map.width - open.map.width) <= 1, `the map does not move when the drawer stacks (${open.map.width} then ${withDrawer.map.width})`);
        }
        await page.keyboard.press("Escape");
        await page.waitForTimeout(600);
      } else {
        check(false, "a lineage handle was reachable in the card");
      }
    }

    // The sheet's three stops, driven from the keyboard the slider role contracts for.
    if (bp.width <= 900) {
      // Spent deliberately before the stops are photographed: the coach mark sits over the
      // sheet at this width, and peek is 160 px of which the reviewer has to judge every one.
      await clickWithoutPointer(page, ".gw-hint-close");
      await page.waitForTimeout(300);
      await page.locator("#gw-rail-grab").focus();
      for (const [key, stop] of [["Home", "peek"], ["ArrowUp", "half"], ["End", "full"]]) {
        await page.keyboard.press(key);
        await page.waitForTimeout(500);
        const snapped = await geometry(page);
        console.log(`  ${stop}: card ${JSON.stringify(snapped.card)} map ${snapped.map.width}`);
        await shoot(page, `${tag}-sheet-${stop}`);
        check(snapped.snap === stop, `${key} reaches the ${stop} stop`);
      }
      const peek = await page.evaluate(() => {
        document.getElementById("gw-rail-grab").focus();
        return null;
      });
      void peek;
    }
  } finally {
    await context.close();
  }
}

// The deep link, the guard, and what an unknown id renders. One width: this is behaviour, and
// the ladder above has already photographed the geometry it happens in.
{
  console.log("\nsections at 1600x1000");
  const { page, journal } = await instrumentedPage(browser, { viewport: BREAKPOINTS[0] });
  await page.goto(`${BASE}/?well=${WELL}&section=neighbours`, { waitUntil: "networkidle" });
  await mapReady(page).catch(() => {});
  await page.waitForTimeout(2500);
  const linked = await geometry(page);
  console.log(`  focused ${linked.focused} · ${linked.sections.map((e) => `${e.id}:${e.expanded}`).join(" ")}`);
  await shoot(page, "1600x1000-section-deeplink");
  check(
    linked.sections.find((each) => each.id === "neighbours")?.expanded === "true",
    "?section= opens the section it names",
  );
  check(linked.focused === "neighbours", `and lands focus inside it (${linked.focused})`);
  check(
    linked.sections.find((each) => each.id === "production")?.expanded === "true",
    "and collapses nothing else on the way",
  );

  // An in-card link pushes, so back returns to the section before it with the card still
  // mounted, its disclosures intact and nothing re-requested.
  // The Lineage section is where the card's own cross-links live, and it builds them when a
  // reader opens it -- it lists what the card is carrying now, not what it carried at mount.
  await page.evaluate(() => {
    document.querySelector("#gw-section-lineage .gw-section-toggle")?.click();
  });
  await page.waitForTimeout(600);
  const before = journal.api.length;
  const wasAt = await page.evaluate(() => window.location.search);
  const mounted = await page.evaluate(() => {
    const card = document.querySelector("#gw-card .gw-card");
    if (card) card.dataset.probe = "mounted";
    const link = document.querySelector("#gw-section-lineage .gw-section-link");
    if (!link) return null;
    link.click();
    return link.getAttribute("href");
  });
  await page.waitForTimeout(800);
  await page.goBack({ waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1200);
  const back = await page.evaluate(() => ({
    probe: document.querySelector("#gw-card .gw-card")?.dataset.probe ?? null,
    search: window.location.search,
  }));
  await shoot(page, "1600x1000-section-back");
  check(mounted !== null, `an in-card section link exists to test the pushed case (${mounted})`);
  check(back.probe === "mounted", "back leaves the very same card node mounted");
  check(
    journal.api.length === before,
    `and re-requests nothing (${journal.api.length - before} new API responses)`,
  );
  // Back to the entry the link pushed from, which the disclosure above had replaced rather
  // than pushed: ten disclosures must not make ten history entries, so what back returns to is
  // the section that was current when the link was pressed.
  check(back.search === wasAt, `and returns to the section it was pushed from (${back.search})`);
  await page.context().close();
}

{
  console.log("\nan id no card has");
  const { page } = await instrumentedPage(browser, { viewport: BREAKPOINTS[0] });
  await page.goto(`${BASE}/?well=${WELL}&section=nonsense`, { waitUntil: "networkidle" });
  await mapReady(page).catch(() => {});
  await page.waitForTimeout(2500);
  const bogus = await geometry(page);
  await shoot(page, "1600x1000-section-unknown");
  console.log(`  absent note: ${bogus.absent}`);
  check(
    bogus.sections.filter((each) => each.expanded === "true").map((each) => each.id).join(",") ===
      "production,cumulative,identity",
    "an unknown id renders the default set",
  );
  check(bogus.absent !== null, "and says so once, rather than showing an empty surface");
  const dropped = await page.evaluate(() => window.location.search);
  check(!dropped.includes("section="), `and drops the id from the URL (${dropped})`);
  await page.context().close();
}

await browser.close();
console.log(`\n${failures === 0 ? "all checks passed" : `${failures} check(s) failed`}`);
process.exit(failures === 0 ? 0 : 1);
