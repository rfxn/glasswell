# PERF — what the frontend costs, measured

Two budgets live here, and neither is a number anyone chose in advance.

- **Shell bytes.** What a reader downloads to reach a surface. Set from the measurement below
  and enforced by `web/src/explore/bundle-budget.test.ts`, which rebuilds and asserts on every
  `npm --prefix web run test`.
- **Frame time.** SB-05 errata **E-3**'s pinned form of blueprint §2.4's S2: *20,000 laterals
  in view at z=9 with model-driven styling, a scripted pan-and-zoom on the reference client,
  p95 frame time ≤ 22 ms, no frame > 100 ms.* The explorer surfaces are measured against it
  below. **The map's S2 number is not in this file and is not C11's to produce** — see
  §5.

Every figure here says which instance produced it. A number measured against a seeded harness
is a harness number; it is not a claim about the deployed instance, and the two are labelled
apart throughout.

---

## 1. Reference client

The measurements in §3 and §4 were taken on this client. SB-05 §2.4 names the reference client
as "the owner's primary workstation"; this is that workstation, but driving a **headless**
browser on a **software rasteriser**, which is the part that matters for §4.

| | |
|---|---|
| host | `freedom` — AMD Ryzen 9 5900X, 6 cores visible to the container, 11 GiB RAM |
| kernel | Linux 6.14.5-100.fc40.x86_64 |
| browser | Google Chrome for Testing 149.0.7827.55 (playwright-core, headless) |
| flags | `--no-sandbox --enable-unsafe-swiftshader --hide-scrollbars` |
| GL renderer | `ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero)), SwiftShader driver)` |
| display cadence | 60 Hz — rAF intervals quantise to **16.7 ms** |
| device pixel ratio | 1 |
| node | v20.19.1 |

**There is no GPU in this client.** Every pixel is rasterised by SwiftShader on the CPU. That
is fine for the explorer, which draws DOM, and it is disqualifying for the map, which draws
WebGL — §5 says so rather than reporting a number that reads as a verdict.

---

## 2. How to reproduce

```bash
# The instance: this branch's bundle and source, ND-scale density (20,000 wells + laterals)
GW_PORT=8161 GW_SEED=work-output/explorer-c11-seed.py python3 tests/support/serve_branch.py

# Shell bytes
npm --prefix web run build                     # vite prints its own gzip column
npm --prefix web run test -- src/explore/bundle-budget.test.ts

# Frame time
GLASSWELL_BASE_URL=http://127.0.0.1:8161 GLASSWELL_OWNER_KEY=$(cat /tmp/gw-c11/owner.key) \
  GW_RUNS=5 node tests/e2e/perf.mjs
```

`tests/e2e/perf.mjs` installs a `requestAnimationFrame` sampler, runs a scripted deterministic
interaction, and reports the interval distribution — SB-05 §8.5's harness, pointed at the
surfaces P-A built.

**Harness change (e2e-key-hardening):** the harness now authenticates by injecting the
`X-Glasswell-Key` header through a Playwright route on every same-origin request, which adds
~0.95 ms per intercepted request (~38 ms across a 41-request load). Invisible in the
vsync-pinned frame distributions, but present in the scenarios that probe across a navigation
(`explore-entry`, `explore-entry-390`) and in tile-heavy probe windows (`map-pan-z9`). Every
number recorded before that commit was taken without route interception — do not compare
across it silently.

---

## 3. Shell bytes — measured, then budgeted

Measured on `npm --prefix web run build`, commit `explorer-c11-integration`, 2026-08-21.
Gzip is zlib's default level, which is what vite's own size column reports, so every row here
reconciles against the build log line by line.

| what | raw B | gzip B | chunks |
|---|---:|---:|---|
| entry chunk | 113,349 | 44,192 | `index-*.js` |
| entry chunk + its CSS | 137,625 | 49,821 | `index-*.js` + `index-*.css` |
| **explorer route, map excluded** | **170,756** | **62,817** | `index-*.js` + `shell-*.js` |
| map chunk, map-only | 1,153,568 | 313,823 | `map-*.js` + the shared inflate chunk |
| all JS | 1,324,324 | 376,640 | |

**These numbers jitter by single-digit bytes between builds of the same source.** Two causes,
both real and both in what the reader downloads: the content-hash in each chunk's filename
appears inside the chunks that import it, and the build stamp vite inlines carries a `+` when
the working tree is dirty. Gzipped totals were seen to move by up to 7 B across rebuilds of an
identical tree. Every budget below carries about 5% of headroom, which is three orders of
magnitude more than that.

**Against the baseline.** Before P-A split the bundle the entry chunk was **1,229,038 B /
341,517 B gzipped** on `ff9a0ae` — one chunk, every byte of maplibre on the first paint of
every surface. A reader who lands on `?view=explore` now downloads **62,817 B gzipped**, which
is **18.4%** of that, and never fetches the map chunk at all. The *total* across all chunks is
larger than the baseline (376,640 vs 341,517 gzipped) because the explorer is new code; the
split is the win, not the total, and stating only the total would hide that in either
direction.

**The entry chunk grew, and where.** C0 measured it at 97,900 B / 38,498 B gzipped. It is now
113,349 / 44,192 — **+15,449 B raw, +5,694 B gzipped**. The C10 gate predicted ≈113 kB once the
owed card mounts landed, and that is what it measures: `bridge.ts` is now reached from
`card/card.ts`, which the entry chunk carries, so the crossing machinery folded out of the
explorer's shell chunk and into the entry. Verified rather than inferred — `gw-crossing`
(`explore/bridge.ts:306`) appears in `index-*.js` and not in `shell-*.js`.

### The budgets

| budget | B gzipped | headroom over measured |
|---|---:|---|
| entry chunk | 46,500 | +5.2% over 44,192 |
| explorer route, map excluded | 66,000 | +5.1% over 62,817 |
| map chunk | 330,000 | +5.2% over 313,823 |

Plus one structural budget that a byte count would let drift back slowly: **maplibre must not
appear in the entry chunk at all.** C0 bought that with a dynamic import, and a single static
import from any module the entry reaches would undo it in one commit.

`web/src/explore/bundle-budget.test.ts` enforces all four. It builds into a temporary
directory rather than reading `web/dist`, because CI runs vitest *before* the build step: a
budget that reads an artifact which may not exist is a budget that skips, and a budget that
skips is not a budget. The build costs about 4 s.

---

## 4. Frame time — the explorer surfaces

Harness instance, ND-scale density: **20,000 seeded wells and 20,000 seeded laterals** over the
Williston core, plus the contract fixture's 8 wells. Five runs per scenario, 1600×1000 unless
the row says otherwise, `as_of=2026-08-01`.

`p95` is the worst of the five runs. `dropped` counts intervals longer than 1.5 vsync across
all five. `busy` is the worst run's total time beyond the display cadence — the part of the
distribution that is work rather than refresh rate.

| scenario | frames | p95 ms | max ms | >100 ms | dropped | busy ms | E-3 |
|---|---:|---:|---:|---:|---:|---:|---|
| route entry to a painted wells grid | 488 | 16.8 | 33.3 | 0 | 2 | 16.9 | within |
| scroll the wells grid, down and back | 856 | 16.8 | 16.8 | 0 | 0 | 1.0 | within |
| the same scroll at 820, as a card list | 858 | 16.8 | 16.8 | 0 | 0 | 1.0 | within |
| route entry at 390, where the grid refuses | 490 | 16.8 | 16.8 | 0 | 0 | 0.7 | within |
| narrow by an operator facet | 820 | 16.8 | 16.8 | 0 | 0 | 1.0 | within |
| walk to the next page on a cursor | 917 | 16.8 | 16.8 | 0 | 0 | 1.4 | within |
| open a row's detail | 917 | 16.8 | 16.8 | 0 | 0 | 1.2 | within |

**Read this correctly.** rAF intervals are quantised to the display's cadence: on a 60 Hz
client a frame costing 2 ms of work and one costing 15 ms both report 16.7 ms. So p95 pinned at
one vsync means *nothing was dropped* — it does not mean the work was free. The honest
statement of these rows is: **across 5,346 sampled frames on seven explorer interactions, two
frames were dropped and none exceeded 100 ms**, and the total time spent beyond the refresh
cadence was under 17 ms in the worst run of any scenario — both dropped frames landing in the
same run of route entry, which is the one scenario that also parses and executes the bundle.

**What ND density does and does not exercise here.** `/v1/wells` pages at 100 rows and the grid
windows 60 of them, so the grid's per-frame cost is bounded by the page size, not by the
corpus. Seeding 20,000 wells therefore proves the *query and paging* path at ND scale — the
cursor walk in the table above is over a 20,008-row corpus — and does **not** raise the
explorer's render cost, because the explorer never renders more than a page. A future surface
that renders unbounded rows would need this measured again; today's does not.

**Zero page errors** across all 40 runs, which is the second thing this harness watches.

---

## 5. What is not measured here, and whose it is

**S2 — 20k laterals at z=9 — is not in this file.** `work-output/CADENCE.md` §T assigns
`ui/PERF.md` and the S2 measurement to the tile-simplification track (DR-54 + DR-55), which
owns `marts/tiles.py` and `infra/martin/config.yaml`. C11 owns the *shell* budget
(`PLAN-EXPLORER-PA.md` §C11 item 11.3). This file records the explorer's numbers and states the
map's blockers; it does not claim S2.

The blockers are measured, not assumed:

1. **No tile server.** `tests/support/serve_branch.py` stands up PostGIS and uvicorn, not
   martin. `GET /v1/tiles/nd_laterals/9/93/181.pbf` on the harness returns **502** — the tile
   proxy has no upstream. Zero laterals reach the canvas, so a pan at z=9 draws the graticule
   fallback over an empty map.
2. **No GPU.** The reference client above rasterises through SwiftShader. Even with the map
   empty, the scripted pan at z=9 measures **p95 33.3 ms, max 33.4 ms, 207 dropped frames of
   1,982, and no frame over 100 ms** across five runs. An empty map already misses E-3's
   p95 ≤ 22 ms on this client, which is a fact about the client, not about the map.

Recorded so the number exists and cannot be mistaken for S2:

| scenario | frames | p95 ms | max ms | >100 ms | dropped | busy ms | laterals drawn |
|---|---:|---:|---:|---:|---:|---:|---:|
| pan/zoom at z=9 over the Williston box | 1,982 | 33.3 | 33.4 | 0 | 207 | 866.4 | **0** |

### The checklist S2 needs, exactly

Whoever picks up DR-55 needs all six; the first three are why this file cannot answer it.

1. A martin instance over the same database, with `marts.nd_laterals` installed, so tiles
   return 200 rather than 502.
2. 20,000 laterals **in one z=9 viewport** with model-driven styling active — the seed in
   `work-output/explorer-c11-seed.py` lays exactly that geometry down, so the data half is
   solved and only the serving half is missing.
3. A client with real GPU rasterisation. SwiftShader cannot answer a budget written for
   interactive frame rates.
4. The scripted sequence from SB-05 §8.5, which `tests/e2e/perf.mjs`'s `map-pan-z9` scenario
   already implements — re-point it, do not rewrite it.
5. The secondary floor SB-05 names: a 2020-class laptop with integrated graphics at
   p95 ≤ 33 ms, reported but not gating.
6. Tile bytes transferred, tile count and time-to-first-paint of L5 alongside the frame
   distribution, which §8.5 asks for and this harness cannot produce without item 1.

### Deferred to the deployed instance

The numbers above are the harness's. VM 111 differs in ways that move them, and each needs
measuring there rather than extrapolating:

- **Real ND row counts and value distributions**, not a lattice seed — column widths, prose
  cell heights and the grid's reflow all depend on the actual strings.
- **martin in front of real tile marts**, which is the only place items 1 and 2 above are both
  true at once.
- **The network.** Every figure here was measured over loopback. Transfer time for the 62,817 B
  explorer route and the 313,823 B map chunk is a deployed-instance question.
- **A real display.** 16.7 ms is this client's vsync; a 120 Hz display quantises to 8.3 ms and
  would resolve work these rows cannot separate.

---

## 6. Trend

SB-05 §8.5 asks that results be appended at every phase exit, so S2 has a trend rather than a
single green check. Append; do not overwrite.

| date | commit | entry gzip B | explorer route gzip B | map chunk gzip B | note |
|---|---|---:|---:|---:|---|
| 2026-08-21 | `ff9a0ae` | 341,517 | — | — | one chunk; no split, no explorer |
| 2026-08-21 | C0 | 38,498 | — | 302,369 | map moved behind a dynamic import |
| 2026-08-21 | C11 | 44,192 | 62,817 | 313,823 | first measurement of the explorer route |
| 2026-08-22 | M1-7 | 44,245 | 62,867 | 315,287 | disposal layer: +538 gz on the map chunk (base cda2e51 measured 314,749); entry unchanged |
