// The frame harness behind web/PERF.md — SB-05 §8.5's shape, pointed at the surfaces P-A
// built. An in-page requestAnimationFrame sampler runs across a scripted, deterministic
// interaction; the intervals are reported as p50/p95/max and a count of frames over 100 ms,
// over N runs, because a single run is an anecdote.
//
//   GLASSWELL_BASE_URL=http://127.0.0.1:8161 GLASSWELL_OWNER_KEY=$(cat /tmp/gw-c11/owner.key) \
//     GW_RUNS=5 node tests/e2e/perf.mjs
//
// Read-only, like smoke.mjs: it navigates, scrolls and clicks; it never writes through the
// API. The key rides the fragment and is redacted out of everything printed.
//
// The numbers this prints are of the instance it was pointed at. Against a seeded harness they
// are harness numbers and web/PERF.md labels them as such — the deployed instance answers a
// different question and has to be asked separately.
import { writeFileSync } from "node:fs";

import {
  BREAKPOINTS,
  FRAME_SAMPLER,
  chromeExecutable,
  frameProbe,
  instrumentedPage,
  launch,
  mapReady,
  readFrames,
  redactor,
} from "./lib.mjs";

const BASE = (process.env.GLASSWELL_BASE_URL ?? process.env.GW_BASE ?? "http://127.0.0.1:8161")
  .replace(/\/$/, "");
const KEY = (process.env.GLASSWELL_OWNER_KEY ?? process.env.GW_KEY ?? "").trim();
const RUNS = Number(process.env.GW_RUNS ?? 5);
const AS_OF = process.env.GW_AS_OF ?? "2026-08-01";
const JSON_OUT = process.env.GW_PERF_JSON ?? "";
const REQUIRE = process.env.GLASSWELL_REQUIRE_E2E === "1";
// SB-05 E-3's pinned budget. This harness reports against it; only the reference client's own
// run may be read as a verdict on it.
const BUDGET = { p95: 22, max: 100 };
const VIEWPORT = BREAKPOINTS[0];
const redact = redactor(KEY);

function unavailable(reason) {
  if (REQUIRE) {
    console.error(`GLASSWELL_REQUIRE_E2E is set but ${reason}`);
    process.exit(1);
  }
  console.log(`perf skipped: ${reason}`);
  process.exit(0);
}

if (!chromeExecutable()) unavailable("no chromium build found (set GW_CHROME)");
if (!KEY) unavailable("no owner key (set GLASSWELL_OWNER_KEY)");

function quantile(sorted, fraction) {
  if (sorted.length === 0) return NaN;
  const position = (sorted.length - 1) * fraction;
  const low = Math.floor(position);
  const high = Math.ceil(position);
  return sorted[low] + (sorted[high] - sorted[low]) * (position - low);
}

// The first interval of a probe is the gap between installing the sampler and the next frame,
// which measures the harness rather than the page.
//
// requestAnimationFrame intervals are quantised to the display's cadence: on a 60 Hz client a
// frame that cost 2 ms of work and one that cost 15 ms both report 16.7 ms. So the interval
// distribution is a dropped-frame detector, not a work meter — which is what E-3's budget is
// asking about, but it means p50 pinned at the vsync period says "nothing was dropped", not
// "the work was free". `busyMs` is the part that is not cadence: the total time the page spent
// beyond the refresh it was locked to, which is the number that moves with row density.
function summarise(frames) {
  const sample = frames.slice(1);
  const sorted = [...sample].sort((a, b) => a - b);
  const vsync = +quantile(sorted, 0.5).toFixed(2);
  return {
    n: sample.length,
    vsync,
    p50: vsync,
    p95: +quantile(sorted, 0.95).toFixed(2),
    max: +(sorted[sorted.length - 1] ?? NaN).toFixed(2),
    dropped: sample.filter((interval) => interval > vsync * 1.5).length,
    busyMs: +sample.reduce((sum, interval) => sum + Math.max(0, interval - vsync), 0).toFixed(1),
    over100: sample.filter((interval) => interval > BUDGET.max).length,
  };
}

const SCENARIOS = [
  {
    id: "explore-entry",
    what: "route entry to a painted wells grid",
    url: () => `${BASE}/?view=explore&ds=wells&as_of=${AS_OF}`,
    // Measured across the mount itself: the navigation happens inside the probe, so the
    // sampler is installed before it and sees every frame the grid costs to build.
    probeAcrossEntry: true,
    act: async (page, url) => {
      await page.goto(url, { waitUntil: "load" });
      await page.waitForSelector(".gw-grid-tr", { timeout: 30000 });
    },
  },
  {
    id: "grid-scroll",
    what: "a scripted scroll down and back up the wells grid",
    url: () => `${BASE}/?view=explore&ds=wells&as_of=${AS_OF}`,
    settle: async (page) => page.waitForSelector(".gw-grid-tr", { timeout: 30000 }),
    act: async (page) => {
      for (const top of [0, 400, 900, 1500, 2200, 3000, 2200, 1500, 900, 400, 0]) {
        await page.evaluate((offset) => {
          document.querySelector(".gw-explore-panel")?.scrollTo({ top: offset });
        }, top);
        await page.waitForTimeout(120);
      }
    },
  },
  {
    id: "grid-scroll-820",
    // §2.5's card posture: the same 60 rows re-laid out to 10,908 px in a 519 px scrollport,
    // which is the deepest scroll any breakpoint asks the reader for.
    what: "the same scroll at 820, where the grid is a card list",
    viewport: BREAKPOINTS[3],
    url: () => `${BASE}/?view=explore&ds=wells&as_of=${AS_OF}`,
    settle: async (page) => page.waitForSelector(".gw-grid-tr", { timeout: 30000 }),
    act: async (page) => {
      for (const top of [0, 1500, 3500, 6000, 8500, 10800, 8500, 6000, 3500, 1500, 0]) {
        await page.evaluate((offset) => {
          document.querySelector(".gw-explore-panel")?.scrollTo({ top: offset });
        }, top);
        await page.waitForTimeout(120);
      }
    },
  },
  {
    id: "explore-entry-390",
    // At 390 the grid refuses (§2.5) and the API pane is the product, so entry is what there
    // is to measure — and it is the breakpoint the C6-era zero-height class hid above.
    what: "route entry at 390, where the grid refuses and the pane is the product",
    viewport: BREAKPOINTS[4],
    url: () => `${BASE}/?view=explore&ds=wells&as_of=${AS_OF}`,
    probeAcrossEntry: true,
    act: async (page, url) => {
      await page.goto(url, { waitUntil: "load" });
      await page.waitForSelector(".gw-grid-narrow", { timeout: 30000 });
    },
  },
  {
    id: "facet-narrow",
    what: "typing an operator into a facet and the grid reflowing to it",
    url: () => `${BASE}/?view=explore&ds=wells&as_of=${AS_OF}`,
    settle: async (page) =>
      page.waitForSelector('input.gw-facet-input[type="text"]', { timeout: 30000 }),
    act: async (page) => {
      const input = page.locator('input.gw-facet-input[type="text"]').first();
      await input.fill("HESS");
      await input.press("Enter");
      await page.waitForTimeout(1200);
    },
  },
  {
    id: "page-next",
    what: "walking to the next page of rows on a cursor",
    url: () => `${BASE}/?view=explore&ds=wells&as_of=${AS_OF}`,
    settle: async (page) => page.waitForSelector(".gw-page-next", { timeout: 30000 }),
    act: async (page) => {
      await page.click(".gw-page-next");
      await page.waitForTimeout(1500);
    },
  },
  {
    id: "row-detail",
    what: "opening a row's detail",
    url: () => `${BASE}/?view=explore&ds=wells&as_of=${AS_OF}`,
    settle: async (page) => page.waitForSelector(".gw-grid-tr", { timeout: 30000 }),
    act: async (page) => {
      await page.locator(".gw-grid-tr").first().click();
      await page.waitForTimeout(1500);
    },
  },
  {
    id: "map-pan-z9",
    what: "SB-05 §8.5's pan/zoom sequence at z=9 over the Williston box",
    url: () => `${BASE}/?view=map&as_of=${AS_OF}&map=9.00/47.80000/-103.35000`,
    settle: async (page) => mapReady(page, 6000),
    act: async (page) => {
      // Deterministic and rotation-free, matching the map's own posture (dragRotate disabled).
      const steps = [
        [0.25, 0], [0.25, 0.15], [0, 0.3], [-0.25, 0.15], [-0.25, 0], [0, -0.3],
      ];
      for (const [dLon, dLat] of steps) {
        await page.mouse.move(800, 500);
        await page.mouse.down();
        await page.mouse.move(800 - dLon * 400, 500 - dLat * 400, { steps: 12 });
        await page.mouse.up();
        await page.waitForTimeout(250);
      }
    },
  },
];

const browser = await launch();
const results = [];

for (const scenario of SCENARIOS) {
  const runs = [];
  for (let run = 0; run < RUNS; run += 1) {
    const { context, page, journal } = await instrumentedPage(browser, {
      viewport: scenario.viewport ?? VIEWPORT,
      key: KEY,
    });
    const url = scenario.url();
    let frames;
    if (scenario.probeAcrossEntry) {
      // Installed before the document exists, so the sampler survives the navigation the
      // measurement is of. The key is planted first, on its own load, because the measured
      // navigation has to be an authenticated one rather than a key panel.
      await page.goto(`${BASE}/?view=map#key=${KEY}`, { waitUntil: "load" });
      await page.waitForTimeout(1500);
      await page.addInitScript({ content: `(${FRAME_SAMPLER})()` });
      await scenario.act(page, url);
      await page.waitForTimeout(1500);
      frames = await readFrames(page);
    } else {
      await page.goto(`${url}#key=${KEY}`, { waitUntil: "load" });
      await scenario.settle(page);
      frames = await frameProbe(page, () => scenario.act(page), 1500);
    }
    runs.push({ ...summarise(frames), pageerror: journal.pageerror.length, nonok: journal.nonok.length });
    await context.close();
  }

  const pooled = {
    vsync: [...runs.map((r) => r.vsync)].sort((a, b) => a - b)[Math.floor(runs.length / 2)],
    p95Worst: Math.max(...runs.map((r) => r.p95)),
    p95Median: [...runs.map((r) => r.p95)].sort((a, b) => a - b)[Math.floor(runs.length / 2)],
    maxWorst: Math.max(...runs.map((r) => r.max)),
    dropped: runs.reduce((sum, r) => sum + r.dropped, 0),
    busyMsWorst: Math.max(...runs.map((r) => r.busyMs)),
    over100: runs.reduce((sum, r) => sum + r.over100, 0),
    frames: runs.reduce((sum, r) => sum + r.n, 0),
    pageerror: runs.reduce((sum, r) => sum + r.pageerror, 0),
  };
  results.push({
    id: scenario.id,
    what: scenario.what,
    viewport: scenario.viewport ?? VIEWPORT,
    runs,
    pooled,
  });

  const size = scenario.viewport ?? VIEWPORT;
  console.log(`\n${scenario.id} — ${scenario.what} [${size.width}x${size.height}]`);
  for (const [index, run] of runs.entries()) {
    console.log(
      `  run ${index + 1}  n=${String(run.n).padStart(4)}  vsync=${String(run.vsync).padStart(5)}  ` +
        `p95=${String(run.p95).padStart(7)}  max=${String(run.max).padStart(8)}  dropped=${String(run.dropped).padStart(3)}  ` +
        `busy=${String(run.busyMs).padStart(7)}ms  >100ms=${run.over100}  pageerror=${run.pageerror}`,
    );
  }
  console.log(
    `  pooled  frames=${pooled.frames}  vsync=${pooled.vsync}  p95(median run)=${pooled.p95Median}  ` +
      `p95(worst run)=${pooled.p95Worst}  max=${pooled.maxWorst}  dropped=${pooled.dropped}  ` +
      `busy(worst run)=${pooled.busyMsWorst}ms  >100ms=${pooled.over100}  ` +
      `verdict=${pooled.p95Worst <= BUDGET.p95 && pooled.maxWorst <= BUDGET.max ? "within E-3" : "outside E-3"}`,
  );
}

await browser.close();

console.log(`\nbase ${redact(BASE)} · runs ${RUNS} · viewport ${VIEWPORT.width}x${VIEWPORT.height}`);
if (JSON_OUT) {
  writeFileSync(JSON_OUT, `${JSON.stringify({ base: redact(BASE), runs: RUNS, viewport: VIEWPORT, budget: BUDGET, results }, null, 2)}\n`);
  console.log(`json ${JSON_OUT}`);
}
