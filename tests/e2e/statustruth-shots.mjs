// The implementer shots for the v0.81 status-truth track, at the three widths the visual gate
// judges. Not a gate: it asserts nothing about pixels and fails only when a shot was taken of
// the wrong thing, which it says in the filename and on stdout so a caption cannot outlive it.
//
//   GW_ROOT=... GW_PORT=8137 GW_SEED=tests/support/serve_seed_statustruth.py \
//     python3 tests/support/serve_branch.py
//   GLASSWELL_BASE_URL=http://127.0.0.1:8137 GLASSWELL_KEY_FILE=/tmp/gw-serve-st/owner.key \
//     node tests/e2e/statustruth-shots.mjs
//
// Read-only, against the branch's own bundle and the branch's own API on an ephemeral
// PostGIS -- never the deployed instance.
import { mkdirSync, writeFileSync } from "node:fs";
import { baseUrl, chromeExecutable, instrumentedPage, launch, mapReady } from "./lib.mjs";

const BASE = baseUrl();
const OUT = process.env.GW_SHOTS ?? "work-output/statustruth-shots/p4";
// The three the brief names, and no others: a shot at a width nobody judges is a file to read.
const WIDTHS = [
  { width: 1600, height: 1000 },
  { width: 1024, height: 768 },
  { width: 390, height: 844 },
];
// A Texas well the RRC filed no status for -- the absence class on its plainest reading -- and
// a New Mexico well whose class resolves at read time from its own filed letter.
const TX_ABSENT = "4238399803";
const NM_RESOLVED = "3001599801";
// One disposal well per jurisdiction that publishes an injection codebook, and one from a
// jurisdiction that does not: the hover has to name its own regulator or draw no ring at all.
// api10, and the viewport that puts it under the pointer: `?map=z/lat/lon` is the app's own
// viewport parameter, so the shot names the frame rather than hoping a selection flies to it.
const DISPOSAL = {
  ND: { api10: "3305399804", map: "13/47.74000/-103.40000" },
  TX: { api10: "4238399802", map: "13/31.86000/-102.24000" },
  NM: { api10: "3001599803", map: "13/32.28000/-104.18000" },
  MT: { api10: "2508399804", map: "13/47.58000/-104.70000" },
};
mkdirSync(OUT, { recursive: true });

const stampOf = (page) =>
  page.evaluate(() => document.querySelector(".gw-build-hash")?.textContent ?? "no-stamp");

async function dismissToasts(page) {
  for (const selector of ["button[aria-label='Dismiss']", ".gw-toast button"]) {
    const buttons = page.locator(selector);
    for (let i = (await buttons.count()) - 1; i >= 0; i -= 1) {
      await buttons.nth(i).click({ timeout: 1500 }).catch(() => {});
    }
  }
  await page.waitForTimeout(250);
}

const frames = [];
let failures = 0;
const browser = await launch({ executablePath: chromeExecutable() });
for (const bp of WIDTHS) {
  const { page, context } = await instrumentedPage(browser, {
    viewport: { width: bp.width, height: bp.height },
  });
  const shot = async (name, note = "") => {
    const path = `${OUT}/${name}-${bp.width}.png`;
    await page.screenshot({ path });
    frames.push({ file: path.split("/").pop(), width: bp.width, stamp: await stampOf(page), note });
  };
  try {
    await page.goto(`${BASE}/?view=map`, { waitUntil: "networkidle" });
    await mapReady(page).catch(() => {});
    await page.waitForTimeout(2500);
    await dismissToasts(page);

    // Surface 3: the layer panel's Wells rows, which the registration's presentation facts
    // now reach both by generation and on the wire.
    let panel = true;
    try {
      await page.locator("button:has-text('Layers')").first().click({ timeout: 5000 });
      await page.waitForTimeout(800);
      await page.locator(".gw-layer-family-head button[aria-expanded]").first()
        .click({ timeout: 4000 });
      await page.waitForTimeout(600);
    } catch (error) {
      panel = false;
      console.log(`  WARN ${bp.width}: layer panel did not open -- ${String(error).split("\n")[0]}`);
    }
    await shot(`layer-panel-wells${panel ? "" : "-PANEL-SHUT"}`, "surface 3");
    if (!panel) failures += 1;
    await page.keyboard.press("Escape");
    await page.waitForTimeout(400);

    // Surfaces 1 and 2: the status block, twelve rows in the domain's own order with the
    // absence row among them, and the same block at 390 inside its scrollport.
    let legend = true;
    let rows = [];
    try {
      await page.locator(".gw-lg-title").first().click({ timeout: 5000 });
      await page.waitForTimeout(600);
      rows = await page.evaluate(() =>
        [...document.querySelectorAll(".gw-lg-row")].map((row) => row.dataset.status),
      );
      if (rows.length < 12 || !rows.includes("unmapped")) {
        legend = false;
        console.log(`  WARN ${bp.width}: the status block lists ${rows.length} rows: ${rows}`);
      }
    } catch (error) {
      legend = false;
      console.log(`  WARN ${bp.width}: legend did not open -- ${String(error).split("\n")[0]}`);
    }
    await shot(`legend-status${legend ? "" : "-SHUT"}`, `surface 1/2 · rows ${rows.join(",")}`);
    if (!legend) failures += 1;

    // The vocabulary note, which now names every registered provenance rule and says which
    // registrations publish none.
    let note = true;
    try {
      await page.locator(".gw-lg-vocab-title").first().click({ timeout: 5000 });
      await page.waitForTimeout(700);
      const text = await page.locator(".gw-lg-note").first().textContent();
      if (!text || !text.includes("each regulator filed it")) {
        note = false;
        console.log(`  WARN ${bp.width}: the vocabulary note does not read per regulator`);
      }
    } catch (error) {
      note = false;
      console.log(`  WARN ${bp.width}: the note did not open -- ${String(error).split("\n")[0]}`);
    }
    await shot(`legend-vocabulary${note ? "" : "-SHUT"}`, "surface 1");
    if (!note) failures += 1;
    await dismissToasts(page);

    // Surface 4: the hover card, one disposal well per jurisdiction. Selecting a well centres
    // the map on it, so the pointer is moved to the centre of the canvas and the sentence the
    // card renders is read back rather than assumed: three jurisdictions, three sentences, and
    // the one that publishes no injection codebook must render none.
    for (const [code, target] of Object.entries(DISPOSAL)) {
      const { api10, map } = target;
      await page.goto(`${BASE}/?view=map&map=${map}`, { waitUntil: "networkidle" });
      await mapReady(page).catch(() => {});
      await page.waitForTimeout(3000);
      await dismissToasts(page);
      // The centre of the map container, not of the viewport: selecting a well centres it in
      // `#gw-map`, and the card takes the right half of the window, so the two differ by more
      // than the hit radius. Aiming at the viewport centre photographed empty cards over a
      // canvas that was drawing the well perfectly well.
      const box = await page.evaluate(() => {
        const map = document.querySelector("#gw-map");
        if (!map) return null;
        const rect = map.getBoundingClientRect();
        return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
      });
      const cx = Math.round(box ? box.x + box.width / 2 : bp.width / 2);
      const cy = Math.round(box ? box.y + box.height / 2 : bp.height / 2);
      let sentence = "";
      const spiral = [[0, 0]];
      for (const r of [4, 8, 12, 18, 26]) {
        for (const [dx, dy] of [[r, 0], [0, r], [-r, 0], [0, -r], [r, r], [-r, -r], [r, -r],
                                [-r, r]]) {
          spiral.push([dx, dy]);
        }
      }
      for (const [dx, dy] of spiral) {
        await page.mouse.move(cx + dx, cy + dy);
        await page.waitForTimeout(160);
        sentence = await page
          .evaluate(() => {
            const card = document.querySelector(".gw-hover");
            return card && !card.hidden ? (card.textContent ?? "") : "";
          })
          .catch(() => "");
        if (sentence.includes(api10)) break;
        sentence = "";
      }
      const named = sentence.includes(`as ${code} filed it`);
      if (!named) {
        // A branch instance serves the API and the bundle and no tile server, so the wells
        // layers load nothing and there is no point on the canvas to hover: the frame carries
        // the toast that says so. The sentence itself is asserted in hover-card.test.ts; the
        // photograph is the visual gate's, against a deployed instance where martin serves.
        console.log(
          `  NOTE ${bp.width}: ${code} ${api10} is not on this canvas` +
            ` (hover reads ${JSON.stringify(sentence)})`,
        );
      }
      await shot(
        `hover-disposal-${code.toLowerCase()}${named ? "" : "-NOT-HOVERED"}`,
        `surface 4 · ${api10} · ${sentence.slice(0, 120) || "no point on the canvas"}`,
      );
    }

    // The blocker's own reproduction, which is the frame that says whether the tile agrees with
    // the two figures beside it: Wells By, status, Texas, press the absence class. The pill,
    // the legend row and the drawn-versus-in-view line have to agree, and they did not while
    // seven of the nine mart projections served a null class the press could not match.
    await page.goto(`${BASE}/?view=map&map=10/31.92000/-102.24000`, { waitUntil: "networkidle" });
    await mapReady(page).catch(() => {});
    await page.waitForTimeout(3000);
    await dismissToasts(page);
    let pressed = "";
    try {
      await page.locator(".gw-wells-by-button").first().click({ timeout: 5000 });
      await page.waitForTimeout(1200);
      const selects = page.locator(".gw-wells-by-controls select");
      await selects.nth(0).selectOption("status");
      await page.waitForTimeout(1200);
      // The scope, explicitly: the panel opens on the default jurisdiction, and the absence
      // class this frame is about is Texas's.
      await selects.nth(1).selectOption({ label: "Wells (Texas)" });
      await page.waitForTimeout(2000);
      await page.locator("[data-value='unmapped']").first().click({ timeout: 5000 });
      await page.waitForTimeout(2000);
      pressed = await page.evaluate(() => {
        const pill = document.querySelector(".gw-facet-pill");
        const partial = document.querySelector(".gw-lg-partial");
        const row = document.querySelector(".gw-lg-row[data-status='unmapped'] .gw-lg-count");
        return [pill?.textContent ?? "", row?.textContent ?? "", partial?.textContent ?? ""]
          .join(" | ");
      });
    } catch (error) {
      console.log(`  WARN ${bp.width}: the Wells-By press did not take -- ${String(error).split("\n")[0]}`);
    }
    await shot(
      `wellsby-press-unmapped-tx${pressed ? "" : "-NOT-PRESSED"}`,
      `the blocker's frame · ${pressed || "not pressed"}`,
    );

    // Surface 5: the well card's status chip. A Texas well the source filed nothing for, and a
    // New Mexico well whose class resolves at read time from the letter beside it.
    for (const [label, api10] of [["tx-absent", TX_ABSENT], ["nm-resolved", NM_RESOLVED]]) {
      await page.goto(`${BASE}/?view=map&well=${api10}`, { waitUntil: "networkidle" });
      await page.waitForTimeout(3200);
      const chip = await page.locator(".gw-card-status").first().textContent().catch(() => null);
      const drew = chip !== null && chip.trim().length > 0;
      if (!drew) {
        console.log(`  WARN ${bp.width}: ${api10} shows no status chip`);
        failures += 1;
      }
      await shot(`card-chip-${label}${drew ? "" : "-NO-CHIP"}`, `surface 5 · chip ${chip ?? "-"}`);
    }

    // Surface 6: the status page, where the resolver check and the schema head are read.
    await page.goto(`${BASE}/?view=status`, { waitUntil: "networkidle" });
    await page.waitForTimeout(2200);
    await dismissToasts(page);
    await shot("status-page", "surface 6");
  } finally {
    await context.close();
  }
}
await browser.close();

writeFileSync(`${OUT}/frames.json`, `${JSON.stringify(frames, null, 2)}\n`, "utf8");
for (const frame of frames) {
  console.log(`${frame.file}  stamp=${frame.stamp}  ${frame.note}`);
}
console.log(failures === 0 ? "every shot took what it was aimed at" : `${failures} shot(s) warned`);
process.exit(0);
