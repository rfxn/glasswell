// Does Chromium actually paint the covered edge of the series table's pinned month column?
//
// Three rounds of `expect(CSS).toMatch(/border-right/)` passed over a mark no reader could see:
// on a `border-collapse: collapse` table the borders are the table's grid and are painted at
// the cell's laid-out position, so a `position: sticky` cell travels and its border does not.
// At max horizontal scroll `10100.000 mcf` read `000 mcf` beside `May 2023` with nothing
// between them. A stylesheet regex cannot see that; only pixels can.
//
// A bundle property, like chrome-fold.mjs: the fixture is the shipped `card/table.css` and
// `style.css` over a table built to `table.ts`'s own shape, so this needs no database, no key
// and no deployed instance. GLASSWELL_REQUIRE_E2E=1 turns "no browser" into a failure.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { chromeExecutable, launch } from "./lib.mjs";

const REQUIRE = process.env.GLASSWELL_REQUIRE_E2E === "1";
const read = (name) => readFileSync(fileURLToPath(new URL(`../../web/${name}`, import.meta.url)), "utf8");

// The 1.4.11 non-text floor: the edge is a boundary, not text.
const NON_TEXT_FLOOR = 3;
// A border runs the height of the column; a cut glyph does not. 0.9 leaves room for the
// hairline rows between cells, which are the one place the column is a different colour.
const RUN = 0.9;
// The frame is narrower than the table on purpose, so `overflow-x: auto` has something to
// scroll. 420 px is the card rail's own body width at 1600.
const FRAME_WIDTH = 420;
const MONTHS = [
  "May 2023", "Jun 2023", "Jul 2023", "Aug 2023", "Sep 2023", "Oct 2023",
  "Nov 2023", "Dec 2023", "Jan 2024", "Feb 2024", "Mar 2024", "Apr 2024",
];

function fixture() {
  const rows = MONTHS.map(
    (month) => `<tr><th scope="row" data-no-glossary>${month}</th>` +
      ["10100.000 mcf", "8250.000 bbl"]
        .map(
          (value) =>
            `<td class="gw-table-value" data-no-glossary>${value}</td>` +
            `<td class="gw-table-state">reported</td>` +
            `<td class="gw-table-handle"><button class="gw-handle">⌾</button></td>`,
        )
        .join("") +
      "</tr>",
  ).join("");
  return `<!doctype html><html><head>
<style>${read("src/style.css")}</style>
<style>${read("src/card/table.css")}</style>
<style>body { margin: 0; background: var(--panel); }
  .frame { width: ${FRAME_WIDTH}px; background: var(--panel); }</style>
</head><body><div class="frame"><div class="gw-series-table"><table>
<caption>Production by month, ${MONTHS.length} months shown.</caption>
<thead>
<tr><th scope="col" rowspan="2" class="gw-table-month">Month</th>
    <th scope="colgroup" colspan="3">Gas (mcf)</th><th scope="colgroup" colspan="3">Oil (bbl)</th></tr>
<tr><th scope="col">Value</th><th scope="col">How it was filed</th><th scope="col">Lineage</th>
    <th scope="col">Value</th><th scope="col">How it was filed</th><th scope="col">Lineage</th></tr>
</thead>
<tbody>${rows}</tbody></table></div></div></body></html>`;
}

function luminance([red, green, blue]) {
  const channel = (value) => {
    const scaled = value / 255;
    return scaled <= 0.04045 ? scaled / 12.92 : ((scaled + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue);
}

function contrast(a, b) {
  const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (high + 0.05) / (low + 0.05);
}

/** Chromium decodes its own screenshot: no image dependency enters this project's lockfile. */
async function pixels(page, clip) {
  const shot = await page.screenshot({ clip });
  return page.evaluate(async (dataUrl) => {
    const image = new Image();
    image.src = dataUrl;
    await image.decode();
    const canvas = document.createElement("canvas");
    canvas.width = image.width;
    canvas.height = image.height;
    const context = canvas.getContext("2d");
    context.drawImage(image, 0, 0);
    const { data } = context.getImageData(0, 0, canvas.width, canvas.height);
    return { width: canvas.width, height: canvas.height, data: [...data] };
  }, `data:image/png;base64,${shot.toString("base64")}`);
}

async function measure(browser, theme) {
  const context = await browser.newContext({ viewport: { width: 1600, height: 1000 } });
  const page = await context.newPage();
  await page.setContent(fixture());
  if (theme === "light") await page.evaluate(() => document.documentElement.dataset.theme = "light");

  const geometry = await page.evaluate(() => {
    const frame = document.querySelector(".gw-series-table");
    frame.scrollLeft = frame.scrollWidth;
    const cell = document.querySelector("tbody tr:first-child th");
    const body = document.querySelector("tbody");
    const value = document.querySelector("tbody tr:first-child .gw-table-value");
    return {
      edge: cell.getBoundingClientRect().right,
      top: body.getBoundingClientRect().top,
      height: body.getBoundingClientRect().height,
      // Proof the fixture is in the state the finding is about: the first value cell starts
      // left of the pinned edge, so its leading digits are covered.
      covered: cell.getBoundingClientRect().right - value.getBoundingClientRect().left,
      panel: getComputedStyle(document.body).backgroundColor,
    };
  });
  if (geometry.covered <= 0) throw new Error(`nothing is covered at max scroll (${geometry.covered} px)`);

  const left = Math.round(geometry.edge) - 8;
  const clip = { x: left, y: Math.round(geometry.top) + 2, width: 16, height: Math.round(geometry.height) - 4 };
  const shot = await pixels(page, clip);
  const panel = geometry.panel.match(/\d+/g).slice(0, 3).map(Number);

  let best = { column: null, run: 0, contrast: 0 };
  for (let column = 0; column < shot.width; column += 1) {
    let hits = 0;
    let worst = Infinity;
    for (let row = 0; row < shot.height; row += 1) {
      const at = (row * shot.width + column) * 4;
      const ratio = contrast(shot.data.slice(at, at + 3), panel);
      if (ratio >= NON_TEXT_FLOOR) {
        hits += 1;
        worst = Math.min(worst, ratio);
      }
    }
    const run = hits / shot.height;
    if (run > best.run) best = { column: left + column, run, contrast: worst === Infinity ? 0 : worst };
  }
  await context.close();
  return { theme, edge: Math.round(geometry.edge), covered: Math.round(geometry.covered), ...best };
}

const executablePath = chromeExecutable();
if (!executablePath) {
  const message = "no chromium build found — set GW_CHROME or install the playwright browser";
  if (REQUIRE) throw new Error(message);
  console.log(`[skip] ${message}`);
  process.exit(0);
}

const browser = await launch({ executablePath });
let failures = 0;
try {
  for (const theme of ["dark", "light"]) {
    const found = await measure(browser, theme);
    const painted = found.run >= RUN && found.contrast >= NON_TEXT_FLOOR;
    // Within a pixel of the pinned cell's own right edge: a mark two columns away is the cut
    // figure's stroke, which is what the earlier 7.05:1 measurement read.
    const placed = found.column !== null && Math.abs(found.column - found.edge) <= 2;
    const verdict = painted && placed ? "ok" : "FAIL";
    if (verdict === "FAIL") failures += 1;
    console.log(
      `[${verdict}] ${theme}: ${found.covered} px of the value cell covered; edge column ` +
        `${found.column} (pinned edge ${found.edge}), ${(found.run * 100).toFixed(0)}% of rows ` +
        `at ${found.contrast.toFixed(2)}:1 (floor ${NON_TEXT_FLOOR}:1 over ${RUN * 100}% of rows)`,
    );
  }
} finally {
  await browser.close();
}

if (failures > 0) {
  console.error(`the covered edge is not painted at max scroll in ${failures} theme(s)`);
  process.exit(1);
}
console.log("the pinned month's covered edge paints at max scroll, both themes");
