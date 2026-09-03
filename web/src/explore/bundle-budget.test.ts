import { gzipSync } from "node:zlib";
import { mkdtempSync, readFileSync, readdirSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

// The budgets web/PERF.md records, enforced. They were set from a measurement on this tree
// (`Record what the explorer's shell actually costs`), not chosen ahead of one, and each
// carries about 5% of headroom over what was measured — enough that a refactor does not trip
// it and little enough that a dependency arriving on the entry path does.
// Re-measured when the chart moved off the entry path: the entry fell 46,330 → 21,340 B
// because uPlot had been riding it for every reader, and the explorer route rose
// 65,100 → 68,149 B because the plot this branch adds is one an explorer reader really does
// download. Tightening the entry is the point of re-measuring — a budget carrying 25 kB of
// slack has stopped being a ratchet.
// Re-measured again for the "Wells by ..." panel: the explorer route rose 68,149 → 71,511 B.
// It is on the route rather than split behind a dynamic import on purpose — it renders on the
// wells dataset, which is the dataset the explorer opens on, so splitting it would buy a
// second round trip for almost every reader rather than saving one a download.
// Re-measured when the well card came off the entry path: the entry fell 21,340 → 12,750 B,
// because the card and its tail — figures, formatting, the completion and neighbour panels —
// had been riding it for every reader, including one who never opens a well. Re-tightened for
// the same reason the chart's move was: leaving 9 kB of slack in place would stop it ratcheting.
// Re-measured for the allocation band: the explorer route rose 71,511 → 75,958 B, because the
// chart chunk gained a second band with its own six-class vocabulary, its own key, and the
// per-month class, divisor and completeness arrays behind them. It is on the route rather than
// split because it renders inside the plot itself — a chart that had to fetch a second chunk
// before it could say whether a point was observed or allocated would draw the number first
// and the label after it, which is the one ordering this band exists to prevent.
const BUDGET_BYTES = {
  entryGzip: 14_000,
  explorerRouteGzip: 79_700,
  mapChunkGzip: 330_000,
};

// vite's own size report gzips at zlib's default level, so these numbers are the ones
// `npm run build` prints and can be reconciled against its log line by line.
const GZIP_LEVEL = 6;

const WEB = fileURLToPath(new URL("../..", import.meta.url));

let dist: string;
let assets: string[];

/**
 * Built here rather than read from `web/dist`, because CI runs vitest before the build step:
 * a budget that reads an artifact which may not exist is a budget that skips, and a budget
 * that skips is not a budget. The real config is used so the measured bytes are the shipped
 * bytes — the version stamp it injects is part of what the reader downloads.
 */
beforeAll(async () => {
  dist = mkdtempSync(join(tmpdir(), "gw-budget-"));
  const { build } = await import("vite");
  await build({
    root: WEB,
    configFile: join(WEB, "vite.config.ts"),
    logLevel: "silent",
    build: { outDir: dist, emptyOutDir: true },
  });
  assets = readdirSync(join(dist, "assets"));
}, 180_000);

afterAll(() => {
  rmSync(dist, { recursive: true, force: true });
});

const bytes = (name: string): number => statSync(join(dist, "assets", name)).size;
const gzip = (name: string): number =>
  gzipSync(readFileSync(join(dist, "assets", name)), { level: GZIP_LEVEL }).length;
const named = (prefix: string): string => {
  const match = assets.filter((name) => new RegExp(`^${prefix}-[A-Za-z0-9_-]+\\.js$`).test(name));
  expect(match, `expected exactly one ${prefix} chunk, saw ${match.join(", ")}`).toHaveLength(1);
  return match[0]!;
};

/** Static and dynamic edges are the same literal in an emitted chunk, so one pattern finds both. */
const edges = (name: string): string[] =>
  [...readFileSync(join(dist, "assets", name), "utf8").matchAll(/["'`]\.\/([\w.-]+\.js)["'`]/g)].map(
    (match) => match[1]!,
  );

function reach(roots: string[], cut: (name: string) => boolean = () => false): string[] {
  const seen = new Set<string>();
  const queue = [...roots];
  while (queue.length > 0) {
    const name = queue.pop()!;
    if (seen.has(name) || !assets.includes(name) || cut(name)) continue;
    seen.add(name);
    queue.push(...edges(name));
  }
  return [...seen].sort();
}

const entryChunks = (): string[] =>
  [...readFileSync(join(dist, "index.html"), "utf8").matchAll(/assets\/([\w.-]+\.js)/g)].map(
    (match) => match[1]!,
  );

describe("what the explorer's shell costs the reader", () => {
  it("keeps the entry chunk inside its budget", () => {
    const measured = entryChunks().reduce((sum, name) => sum + gzip(name), 0);
    expect(measured, `entry chunk ${measured} B gzipped`).toBeLessThanOrEqual(BUDGET_BYTES.entryGzip);
  });

  it("keeps the explorer route, other surfaces excluded, inside its budget", () => {
    // What a reader who lands on ?view=explore actually downloads: the entry chunk, the shell
    // chunk it imports, and nothing either sibling surface's dynamic branch pulls in. The
    // entry chunk names every import, so the graph walker must cut both branches explicitly.
    const map = named("map");
    const status = named("surface");
    const neighbors = named("neighbors");
    // The status chip is the same class of cost as the neighbour panel: a well card only ever
    // renders on the map surface, so its lazy branches are cut here and asserted off the route
    // below. Cutting it also cuts the map status vocabulary and the swatch it reaches through.
    const statusChip = named("status-chip");
    // The card itself joined its own lazy branches when it came off the entry path. Until then
    // it rode inside the entry chunk, so an explorer reader was measured — and charged — for a
    // panel that only ever renders over the map. Cutting it is the same ruling as its children.
    const card = named("card");
    const route = reach(
      [...entryChunks(), named("shell")],
      (name) =>
        name === map ||
        name === status ||
        name === neighbors ||
        name === statusChip ||
        name === card,
    );
    const measured = route.reduce((sum, name) => sum + gzip(name), 0);

    expect(route, "the map chunk is not on the explorer route").not.toContain(map);
    expect(route, "the Status chunk is not on the explorer route").not.toContain(status);
    expect(route, "the well card is not on the explorer route").not.toContain(card);
    expect(route, "the well-card neighbour chunk is not on the explorer route").not.toContain(
      neighbors,
    );
    expect(route, "the well-card status chip is not on the explorer route").not.toContain(
      statusChip,
    );
    expect(measured, `explorer route ${measured} B gzipped over ${route.join(", ")}`).toBeLessThanOrEqual(
      BUDGET_BYTES.explorerRouteGzip,
    );
  });

  it("keeps the map chunk inside its budget", () => {
    const map = named("map");
    const route = reach([...entryChunks(), named("shell")], (name) => name === map);
    const mapOnly = reach([map]).filter((name) => !route.includes(name));
    const measured = mapOnly.reduce((sum, name) => sum + gzip(name), 0);

    expect(measured, `map chunk ${measured} B gzipped over ${mapOnly.join(", ")}`).toBeLessThanOrEqual(
      BUDGET_BYTES.mapChunkGzip,
    );
  });

  it("keeps maplibre out of the entry chunk entirely", () => {
    // The structural half of the budget, and the one a byte count would let drift back in
    // slowly: C0 moved the map behind a dynamic import, and a single static import from a
    // module the entry reaches would undo it in one commit.
    for (const name of entryChunks()) {
      const source = readFileSync(join(dist, "assets", name), "utf8");
      expect(source, `${name} carries maplibre`).not.toMatch(/maplibregl|maplibre-gl/);
    }
  });

  it("still splits the map into its own chunk rather than inlining it", () => {
    expect(bytes(named("map"))).toBeGreaterThan(500_000);
    expect(bytes(named("shell"))).toBeGreaterThan(1_000);
  });

  it("names the measurement the budgets were set from", () => {
    // A budget with no recorded measurement behind it is a number somebody liked. PERF.md is
    // where the measurement lives; this asserts the file exists and carries the same figures.
    const perf = readFileSync(join(WEB, "PERF.md"), "utf8");
    for (const budget of Object.values(BUDGET_BYTES)) {
      expect(perf, `PERF.md does not record the ${budget} B budget`).toContain(
        budget.toLocaleString("en-US"),
      );
    }
  });
});
