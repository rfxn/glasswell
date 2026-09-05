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
// The fourth budget closes a gap the other three left open: the resolver below reads `.js`
// out of `dist/index.html` and nothing has ever measured the stylesheet beside it, so a
// 30 kB CSS addition passed all three. Set once at 7,420 B — the 6,520 B measured on the
// v0.77 tree plus the 900 B the well card's rail is allowed to spend — and ratcheted at the
// end of the v0.81 card group. The rail spent 860 of its 900 B, so measured + 5 % is 7,735
// and would be a 315 B raise: the ratchet takes the unspent ceiling back instead, to 7,400,
// which is the 7,367 measured on this head plus 33 B — two and a half times the 13 B, the
// largest stylesheet jitter §3 records. Spending the ceiling was deliberate; raising it is a
// failed exit.
// Re-measured on the MERGED tree at the v0.81 card merge, which is the first walk that carries
// both trains: the Texas allocation band (which raised the route from 74,838 to 76,412 on its
// own head) and the card's six cuts. The route measured 76,103 B there, so the budget stays at
// the 79,700 B the Texas train set and the merge raises nothing. Neither branch's own number
// describes the tree they land in. Re-walked at the card group's last phase, with P5's chart
// controls and P6's three sections landed: 78,971 B, which is 729 B of headroom rather than
// 3,597. The chart, table, peer, pools and export modules all ride cut chunks; what grew on
// the route is the card's request layer and the shell that reaches it.
const BUDGET_BYTES = {
  entryGzip: 14_000,
  entryCssGzip: 7_400,
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

/** The same resolution one extension along, because the stylesheet ships on the same document. */
const entryStyles = (): string[] =>
  [...readFileSync(join(dist, "index.html"), "utf8").matchAll(/assets\/([\w.-]+\.css)/g)].map(
    (match) => match[1]!,
  );

// The explorer route is one cut, enforced and quoted from the same walk: everything the entry
// and the shell reach until the chunks a reader downloads only by landing on them.
function explorerRouteChunks(): string[] {
  const stops = new Set(
    ["map", "surface", "neighbors", "status-chip", "card", "drawer", "sheet", "table"].map(named),
  );
  return reach([...entryChunks(), named("shell")], (name) => stops.has(name));
}

describe("what the explorer's shell costs the reader", () => {
  it("keeps the entry chunk inside its budget", () => {
    const measured = entryChunks().reduce((sum, name) => sum + gzip(name), 0);
    expect(measured, `entry chunk ${measured} B gzipped`).toBeLessThanOrEqual(BUDGET_BYTES.entryGzip);
  });

  it("keeps the entry stylesheet inside its budget", () => {
    const styles = entryStyles();
    expect(styles, "index.html names no stylesheet").not.toHaveLength(0);
    const measured = styles.reduce((sum, name) => sum + gzip(name), 0);
    expect(measured, `entry stylesheet ${measured} B gzipped`).toBeLessThanOrEqual(
      BUDGET_BYTES.entryCssGzip,
    );
  });

  it("keeps the lineage drawer out of the entry chunk", () => {
    // The same structural shape as the maplibre assertion below: the drawer opens on a click
    // that most readers never make, and a static import from any module the entry reaches
    // would put its 7.9 kB of source back on every first paint. Counted with a global match
    // rather than `grep -c`, which counts lines and answers 1 for a minified chunk.
    for (const name of entryChunks()) {
      const source = readFileSync(join(dist, "assets", name), "utf8");
      const occurrences = source.match(/gw-chain/g)?.length ?? 0;
      expect(occurrences, `${name} carries the lineage drawer`).toBe(0);
    }
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
    // The lineage drawer is the sixth, and it is cut on the sentence above rather than on the
    // map-only one: it renders over both surfaces, and it is downloaded over neither until the
    // reader clicks a handle. `openExplain` runs at boot only behind `state.view === "map"`
    // (main.ts's `start`), and `followHistory` takes its else-branch on every other view, so no
    // reader reaches it by landing. Cutting it is what keeps this number meaning first paint:
    // moving a module out of the entry chunk always raises the walked total, because a 4 kB
    // chunk gzips worse alone than inside a 40 kB one, while the bytes the reader downloads on
    // landing fall. That is the trap the card's own cut was added for in v0.73.
    const drawer = named("drawer");
    // The bottom sheet's gesture is cut on the map-only ruling, not the drawer's: the card
    // never renders over Explore, so the branch that sizes it never runs here.
    const sheet = named("sheet");
    // The chart's table alternative, cut on the drawer's own ruling: it is fetched when a
    // reader presses `Table` and by nobody who lands. Left uncut the walked total rises by the
    // table chunk's own weight, which is the split artifact the paragraph above describes, and
    // it is the difference between this route passing and failing: PERF.md §6 records both
    // walks against the head each was measured at, and the cut stands on the owner's ruling
    // recorded there, not on this file's. No byte count is quoted here on purpose: the chunk
    // statically imports the stamped entry chunk, so its own gzip moves with every commit and
    // a figure in a source file read at a later head is a figure that disagrees with the tree.
    const table = named("table");
    const route = explorerRouteChunks();
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
    expect(route, "the lineage drawer is not on the explorer route").not.toContain(drawer);
    expect(route, "the well card's bottom sheet is not on the explorer route").not.toContain(sheet);
    expect(route, "the table view is not on the explorer route").not.toContain(table);
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

  /**
   * The budget table states headroom "over" a measured figure, and that figure went stale
   * without anything noticing: at v0.81 the map row still read "+5.2% over 313,823" when the
   * chunk measured 325,660, so the stated headroom was +1.3% and §6's own trend row had
   * recorded the larger number three days earlier. A budget whose recorded measurement is
   * fiction reports headroom the tree does not have.
   *
   * 3% rather than the byte: this catches a figure a train has left behind (the map row was
   * 3.6% out) without reddening on the single-digit build jitter §3 documents.
   */
  it("keeps the measurement PERF.md quotes beside each budget within 3% of the tree", () => {
    const map = named("map");
    const routeCut = reach([...entryChunks(), named("shell")], (name) => name === map);
    const measured = {
      "entry chunk": entryChunks().reduce((sum, name) => sum + gzip(name), 0),
      "explorer route, map excluded": explorerRouteChunks().reduce((sum, name) => sum + gzip(name), 0),
      "map chunk": reach([map])
        .filter((name) => !routeCut.includes(name))
        .reduce((sum, name) => sum + gzip(name), 0),
    };
    const perf = readFileSync(join(WEB, "PERF.md"), "utf8");

    for (const [row, actual] of Object.entries(measured)) {
      const stated = new RegExp(`^\\| ${row} \\|[^|]*\\|[^|]*over ([\\d,]+)`, "m").exec(perf);
      expect(stated, `PERF.md's budget table has no "over" figure for ${row}`).not.toBeNull();
      const recorded = Number((stated as RegExpExecArray)[1]!.split(",").join(""));
      const drift = Math.abs(recorded - actual) / actual;

      expect(
        drift,
        `PERF.md records ${row} at ${recorded} B; it measures ${actual} B here` +
          " -- re-measure the row and append to \u00a76's trend rather than leaving the budget" +
          " stating headroom over a figure that no longer exists",
      ).toBeLessThan(0.03);
    }
  });
});
