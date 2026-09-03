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
// The words the legend shot exists for: Colorado's own legend_note, served from the
// registration. The shot is judged on this sentence being readable, not on the note existing.
const SENTENCE = "vacated permit";
mkdirSync(OUT, { recursive: true });

// A shot is judged by what is in the frame, so the harness measures frames. `within` is the
// containment a disclosure owes its panel; `inViewport` is what the screenshot will actually
// hold. One pixel of slack on each edge: sub-pixel layout rounds, and a rounding is not a
// defect.
const box = (b) => `${Math.round(b.y)}..${Math.round(b.y + b.height)}`;
const within = (inner, outer) =>
  inner.y >= outer.y - 1 && inner.y + inner.height <= outer.y + outer.height + 1;
const inViewport = (b, bp) => b.y >= -1 && b.y + b.height <= bp.height + 1;

/**
 * Scroll a phrase to the top of the scrollport that holds it, and hand back its rect.
 *
 * `.gw-lg-note` is its own scrollport — max-height 192 px over 310 px of content — so the
 * element is fully in view while the sentence the shot exists for is not, and every
 * element-level check passes over a clipped sentence. This measures the words.
 */
async function phraseRect(page, selector, phrase) {
  return page.evaluate(
    ([selector, phrase]) => {
      const host = document.querySelector(selector);
      if (!host) return null;
      const walker = document.createTreeWalker(host, NodeFilter.SHOW_TEXT);
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        const at = node.textContent.indexOf(phrase);
        if (at < 0) continue;
        const range = document.createRange();
        range.setStart(node, at);
        range.setEnd(node, at + phrase.length);
        const hostTop = host.getBoundingClientRect().top;
        host.scrollTop += range.getBoundingClientRect().top - hostTop - 8;
        const rect = range.getBoundingClientRect();
        return { y: rect.y, height: rect.height, host: host.getBoundingClientRect().toJSON() };
      }
      return null;
    },
    [selector, phrase],
  );
}

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
    //
    // And the note has to be IN FRAME, which is a different question from being in the DOM.
    // A textContent check passes on a node scrolled out of sight, which is how five shots of
    // a cut-off note were taken and reported as successes. So it is scrolled to and then
    // measured: inside the legend panel's own box, and inside the viewport the shot captures.
    let legend = true;
    try {
      await page.locator(".gw-lg-title").first().click({ timeout: 5000 });
      await page.waitForTimeout(500);
      await page.locator(".gw-lg-vocab-title").first().click({ timeout: 5000 });
      await page.waitForTimeout(700);
      const noteEl = page.locator(".gw-lg-note").first();
      const note = await noteEl.textContent();
      if (!note || !note.includes(SENTENCE)) {
        legend = false;
        console.log(`  WARN ${bp.width}: the registration's legend note is not on the page`);
      }
      const sentence = await phraseRect(page, ".gw-lg-note", SENTENCE);
      await page.waitForTimeout(400);
      const panelBox = await page.locator(".gw-lg").first().boundingBox();
      if (!sentence || !panelBox) {
        legend = false;
        console.log(`  WARN ${bp.width}: Colorado's sentence has no box, so it is not rendered`);
      } else if (!within(sentence, sentence.host) || !within(sentence, panelBox)
                 || !inViewport(sentence, bp)) {
        legend = false;
        console.log(
          `  WARN ${bp.width}: Colorado's sentence is not in frame` +
            ` (sentence ${box(sentence)}, note ${box(sentence.host)},` +
            ` panel ${box(panelBox)}, viewport 0..${bp.height})`,
        );
      }
      await dismissToasts(page);
    } catch (error) {
      legend = false;
      console.log(`  WARN ${bp.width}: legend did not open — ${String(error).split("\n")[0]}`);
    }
    await page.screenshot({ path: `${OUT}/co-legend-${bp.width}${legend ? "" : "-SHUT"}.png` });
    if (!legend) failures += 1;

    // The producing well: the chart the dual write makes render, the cumulative frame with its
    // span sentence, and whichever status the card can serve.
    //
    // Which is none, on this branch. card.ts builds the status chip only where
    // `status_canonical` is set, and Colorado's class resolves at read time through a resolver
    // that merges after this track — so every Colorado card here carries no chip and no filed
    // code, and the shot is named for that rather than captioned as if it showed one. The
    // first cut of these shots was taken while this migration still wrote its own resolver arm
    // and did show `Active · filed PR`; the arm was removed under the facets ruling and the
    // shots were not retaken, which is how a caption outlived the thing it described.
    await page.goto(`${BASE}/?view=map&well=${PRODUCER}`, { waitUntil: "networkidle" });
    await page.waitForTimeout(3200);
    const chip = await page
      .locator(".gw-card-status")
      .first()
      .isVisible()
      .catch(() => false);
    if (!chip) {
      console.log(
        `  NOTE ${bp.width}: the card serves no status chip — status_canonical is null until` +
          " the registry-driven resolver merges, and the filed code rides on the chip",
      );
    }
    const chipSuffix = chip ? "" : "-NO-STATUS-CHIP";
    await page.screenshot({ path: `${OUT}/co-flyout-producing-${bp.width}${chipSuffix}.png` });

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

    // The documented-with-no-class well, which is the case a reader is most likely to misread:
    // the regulator did say something. What the card shows for it is the same question as
    // above, so the same assertion names the answer on the file.
    await page.goto(`${BASE}/?view=map&well=${SUSPENDED}`, { waitUntil: "networkidle" });
    await page.waitForTimeout(3200);
    const documentedChip = await page
      .locator(".gw-card-status")
      .first()
      .isVisible()
      .catch(() => false);
    await page.screenshot({
      path: `${OUT}/co-flyout-documented-${bp.width}${documentedChip ? "" : "-NO-STATUS-CHIP"}.png`,
    });

    // Explore, on the facet domain the registry serves rather than a client table. The
    // dataset is named: `?view=explore` with no `ds` is the "Pick a dataset" landing page,
    // which is what the first run of this harness photographed five times over — a shot with
    // no Colorado in it, taken with no assertion to say so.
    //
    // Below 520 px the app refuses to draw the grid at all — §2.5's deliberate inversion, where
    // the API guide is the product on a phone. That refusal is a served answer, not a missing
    // one, so the shot is named for it and is not a failure; what would be a failure is rows
    // that never arrived, which is a different assertion and is made at every width.
    let explore = true;
    let narrow = false;
    try {
      await page.goto(`${BASE}/?view=explore&ds=wells&f.state=05&wb.state=05`, {
        waitUntil: "networkidle",
      });
      const firstRow = page.locator(".gw-grid-tr").first();
      await firstRow.waitFor({ state: "attached", timeout: 15000 });
      const rows = await page.locator(".gw-grid-tr").count();
      const filter = await page
        .locator("[data-facet='state']")
        .first()
        .locator("input, select")
        .first()
        .inputValue();
      // The Wells-by scope is the registry's own domain, so a state it does not carry cannot
      // be selected here at all; this is the half the shot is cited for.
      const scoped = await page.locator(".gw-wells-by").first().innerText();
      if (rows < 1 || filter !== "05" || !scoped.includes("in Colorado")) {
        explore = false;
        console.log(
          `  WARN ${bp.width}: explore served ${rows} row(s) under state=${filter},` +
            ` and the Wells-by scope ${scoped.includes("in Colorado") ? "is" : "is not"} Colorado`,
        );
      } else {
        narrow = await page.locator(".gw-grid-narrow").first().isVisible().catch(() => false);
        const subject = narrow ? page.locator(".gw-grid-narrow").first() : firstRow;
        await subject.scrollIntoViewIfNeeded({ timeout: 5000 });
        await page.waitForTimeout(600);
        const subjectBox = await subject.boundingBox();
        if (!subjectBox || !inViewport(subjectBox, bp)) {
          explore = false;
          console.log(`  WARN ${bp.width}: what the shot is for is outside the frame it takes`);
        }
      }
    } catch (error) {
      explore = false;
      console.log(`  WARN ${bp.width}: explore did not load — ${String(error).split("\n")[0]}`);
    }
    await page.waitForTimeout(400);
    const exploreSuffix = explore ? (narrow ? "-NARROW-REFUSAL" : "") : "-ABSENT";
    await page.screenshot({ path: `${OUT}/co-explore-${bp.width}${exploreSuffix}.png` });
    if (!explore) failures += 1;
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
