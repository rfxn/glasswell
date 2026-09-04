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
| support floor | Chrome 105, Safari 15.4, Firefox 121: the `:has()` floor the stylesheets already require (`web/package.json` `browserslist`); the row above is the measurement browser, not the floor |
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

**That paragraph stopped being true when the card was split and is corrected here.** `bridge.ts`
is reached from `card/card.ts` and from nowhere the entry chunk carries, so it left the entry
with the card. Re-measured on `7ff303c`: `gw-crossing` occurs **0** times in the chunk
`dist/index.html` names and lives in `bridge-*.js`. Counted with `grep -o ... | wc -l` over the
resolved chunk, because `grep -c` counts matching *lines* and a minified chunk is two of them.
The conclusion the paragraph drew survives for a different reason — the card reaches `bridge.ts`
through its own chunk — but the entry-path claim itself is stale and no budget decision should
rest on it.

### The budgets

| budget | B gzipped | headroom over measured |
|---|---:|---|
| entry chunk | 14,000 | +7.5% over 13,026 (v0.80 P0, drawer split; was +0.4% over 13,950 at v0.78 and +0.5% over 13,928 at v0.76) |
| **entry stylesheet** | **7,400** | the ratcheted value: 7,367 measured at the card group's last phase plus 33 B. Was 7,420 — the 6,520 measured on the v0.77 tree plus the 900 B ceiling the rail was allowed to spend |
| explorer route, map excluded | 79,700 | +0.9% over **78,971**, re-walked at the card group's last phase. The same build on the merge commit measures 76,110 (76,103 at the merge itself; the 7 B is the jitter above), so P5 and P6 spent **2,861 B**. Texas measured 76,412 on its own head and set 79,700; the card measured 74,544 on its own; neither number described the tree both landed in |
| map chunk | 330,000 | +5.2% over 313,823 |

**The fourth budget, and why it is the only one carrying deliberate slack.** The other three
were set at about 5% over a measurement and ratchet downwards. `entryCssGzip` was set at
**7,420 B**: the **6,520 B** measured on the v0.77 tree plus the **900 B** the well card's rail
is allowed to spend on the grid, the collapse strip, three sheet snap points, ten section headers
and the touch rules the card's own controls need. That ceiling is spent on purpose in this
release and recovered at the end of it. **A budget carrying unspent slack has stopped being a
ratchet, so the slack has an expiry.** The gap it closes is real: `bundle-budget.test.ts`
resolves `assets/([\w.-]+\.js)` out of `dist/index.html` and matched no stylesheet at all, so a
30 kB CSS addition passed every budget in the file.

**The ratchet, and why it is not "measured + 5%".** The rule the card spec wrote was *ratchet to
the measured value plus 5%*, which assumes the rail leaves most of its ceiling unspent. It did
not: the stylesheet measures **7,367 B** at the card group's last phase, so the rail spent
**860 of its 900 B** on the grid, the strip, the snap points, the section headers, the chart's
own controls and three new sections. Measured + 5% is **7,735 B**, which is **315 B above the
budget it was meant to tighten** — applying the formula would raise a budget §0 P-6 and §11's
fourteenth non-goal both forbid raising. The ratchet takes back what is actually unspent
instead: **7,420 → 7,400**, which is the measurement plus **33 B**, two and a half times the
13 B that is the largest stylesheet jitter this section records (6,520 → 6,507 on an unchanged
sheet; the 7 B figure above is the route's, a different artifact), and 20 B of ceiling returned. The number a formula produces is not
the number when the formula produces a raise; what the tree measures decides, and it is written
down here rather than resolved silently.

The v0.77 tree measured 6,520 B and this one measures 6,507; the stylesheet did not change
between them and the 13 bytes are the jitter the paragraph above describes. The budget is the
ruled 7,420 either way.

**The explorer route's recorded number was two trains stale, and that mattered.** This table
carried 71,511 B from the "Wells by ..." panel onward. Re-walked on `7ff303c` the same route
measures **74,838 B**, so the headroom was **162 B** rather than 3,489. The v0.78 seam and the
all-jurisdictions facet panel each spent some of it and neither re-recorded the total. It is
re-measured here because a budget nobody re-walks is a number, not an instrument, and because
P0's own change is the size that would have silently broken it.

**Why the lineage drawer is cut from that route, and why cutting it is not a way of passing.**
The number this budget protects is what a reader who lands on `?view=explore` downloads. Every
chunk left on the route is fetched on landing; the five cuts are branches a reader reaches only
by acting. The drawer became the sixth when it moved behind a dynamic import: `openExplain`
runs at boot only behind `state.view === "map"` and `followHistory` takes its else-branch on
every other view, so no Explore reader fetches it by landing, and one who clicks a handle
fetches 1,376 B on the click rather than carrying 938 B of it in the entry chunk from the
start. **Left uncut the walked total reads 75,284 B and the budget fails** — not because the
reader downloads more, but because a 4 kB module gzips worse alone than inside a 40 kB chunk.
That artifact is exactly what the card's own cut was added for in v0.73: a split always raises
the walked total and always lowers what lands. Cut, the route measures **73,925 B**, which is
**913 B less than the same walk on the base tree**, and it is the number a reader would
recognise.

The entry was re-measured again when the well card moved to a dynamic import. `card/card.ts`
and everything only it reaches — `gw-figure`, `card/format.ts`, the completion and neighbour
panels, the status chip — had been in the entry chunk since C0, so every reader paid for a
panel that renders only after a well is clicked, and a reader who opens the explorer never
clicks one. The card became its own 4.5 kB chunk and the entry fell 21,340 → 12,750 B. The
explorer route is measured with the card cut, on the same ruling its neighbour and status-chip
branches were already cut under: it only ever renders over the map.

**Re-measured at v0.80's own head** (`feat/tx-lease-production`, the Texas fix round), because
the figure the raise was argued from was not this tree's. The v0.79 note cited 71,511 B
as the route before the band; the well-card track's P0 measured the same route at **74,838 B**
at its own base and **76,438 B** uncut, so 71,511 was a stale before-figure and the 4,447 B the
note attributes to the band is not the band's cost. What the route measures on this branch,
by the test's own walk over `bridge`, `chart`, `gw-count`, `index`, `jurisdictions.generated`,
`load`, `notes`, `series`, `shell` and `wells-by`, with the map, Status, card, neighbour and
status-chip branches cut:

| tree | explorer route, gzipped |
|---|---:|
| v0.79 note's cited before-figure (stale) | 71,511 |
| `feat/well-card-2` P0, same walk at its base | 74,838 (76,438 uncut) |
| **`feat/tx-lease-production` @ this head** | **76,412** |

The budget stays at **79,700**, which is this measurement plus 4.3%. It is not re-derived
upward to 76,412 + 4.9% = 80,156: a ratchet moves as far as a measurement forces it and no
further, and the number above already fits with headroom in the band the other two budgets
carry. `BUDGET_BYTES` will conflict with `feat/well-card-2` at the v0.81 train; the arithmetic
here is what the integrator resolves it against.

**Why the band is on the route at all**, which is the part of the v0.79 note that still
stands: the chart chunk carries a second state band with its own six-class vocabulary, its own
key, and the per-month class, divisor and completeness arrays behind them, and it sits on the
route rather than behind a second dynamic import on purpose — it renders inside the plot, so a
chart that had to fetch another chunk before it could say whether a point was observed or
allocated would draw the number first and the label after it. That ordering is the one thing
the band exists to prevent.

*(The v0.79 note's figures — "71,511 → 75,958 B" and "measured + 4.9%" — are superseded by the
table above and have been removed rather than left below their own correction: a reader who
scrolled here first got the number the block above exists to retire.)*

The budget was set from 12,750 B, measured before the review round that followed it. The
stale-selection guard, the rejection handler and the per-detail warning grouping put the
entry shipped in v0.73 at **13,482 B** — 3.8% of headroom rather than the ~5% the other two
budgets carry. That is tight enough to fire on the next addition to the entry path, which is
the instrument working: the next thing to reach for is another dynamic import, not another
notch on the budget.

Re-measured across the v0.76 train, which put two tracks on the entry path at once, and again
after each of its three fix rounds. The Accounts surface took it to 13,680 B, the jurisdiction
registry to 13,842 B, the sentinel round to 13,871 B, the visual round to 13,931 B, and the
chrome round that followed it to **13,928 B** — **72 B under the budget**, where v0.73 had 518.

The registry's generated module is not the reason that train's entry grew: the jurisdiction
rows the client reads (names, identity prefixes, tile-layer ids) resolve into a lazy branch,
and no state name appears in the entry chunk at all. What landed there is chrome and wiring,
a little at a time.

Re-measured across the v0.78 seam-hardening train, which is where the budget did the work it
exists for. The mart engine, the served length and neighbour refusals and the narrowed
add-a-state gate cost the entry **2 B**; the glossary paging loop then cost **79**, which is
more headroom than there was. It was split rather than paid for: `loadGlossary` is a boot-only
round trip and now lives in `glossary/load.ts`, imported when it runs rather than in every
reader's first paint, and the store keeps only its state. Net **13,950 B — 50 B under the
budget**, and the loop that reads the vocabulary to its end is off the entry path entirely.

Re-measured across the assembled v0.78 train — the seam, the cadence scheduler, Colorado and
wells-by across every jurisdiction — at four points, because the gzip figure moves under you:

| Tree | raw | gzipped | headroom |
|---|---:|---:|---:|
| seam + scheduler | 40,254 | 13,947 | 53 |
| `2081795` (four tracks merged) | 40,254 | 13,949 | 51 |
| `40bfd4f` (measured by the whole-train gate) | 40,254 | 13,946 | 54 |
| `a74a5d3` (the sentinel fix round) | 40,254 | 13,950 | 50 |

**The raw column is the claim; the gzip column is weather.** `__GW_BUILD__` carries `git describe`,
so the distance from the tag rewrites a few bytes inside the chunk on every commit, and four
measurements of unchanged code differ by 4 B. The raw count does not move: **40,254 B before
Colorado and the facet work and 40,254 B after**. A fifth jurisdiction that arrives as registry rows
costs the reader's first paint zero bytes, which is the property the seam track was built to
produce, and this is the measurement of it.

Compare raw when you want to know whether code moved. Compare gzip against the budget only with
the tree named beside it, which is why every row above carries one.

Headroom is about 50 B — under a page of source. The next track on the entry path splits rather
than widens; the budget does not move.

**Every figure here includes the build stamp.** `vite.config.ts` defines `__GW_BUILD__` from
`git describe`, so the entry chunk carries the tag, the distance and the short SHA of whatever
tree it was built from: a clean tag measures a few bytes under a dirty working tree, and the
same commit measures differently once its distance from the tag grows a digit. The 13,950 B
above was measured on this branch at `755535b`; a clean-tree measurement of the same code came
back 13,932 B, and the 18 bytes are the stamp. Re-measure before moving the budget, and say
which tree the number came from — this is the fourth train running where somebody has had to
re-derive that the delta was the stamp.

The budget is not raised. 72 B is the instrument doing exactly what the paragraph above says it
should, and it is now tight enough that the next addition to the entry path fires it — which
means the next thing to reach for is a dynamic import, not another notch. **Re-measure before
adding anything to `main.ts`, `chrome/` or `style.css`, and treat a failure as the answer
rather than as an obstacle.**

The first two were re-measured when the production chart moved to a dynamic import. uPlot had
been riding the entry chunk, which every reader downloads whether or not they open a card, and
by then the entry had reached 46,330 B against its 46,500 B budget — 170 B of headroom, so the
instrument was about to fire on any addition at all rather than on a bad one. Splitting the
chart out took the entry to 21,340 B and moved those bytes onto the explorer route, which is
honest: a reader landing on a production dataset draws the plot. The entry budget is tightened
in the same act, because a budget carrying 25 kB of slack has stopped being a ratchet.

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
| 2026-09-02 | v0.80 P0 (`7ff303c` + the split) | **13,026** | **73,925** | 318,073 | The lineage drawer moved behind a dynamic import, which is what funds the well card's second generation. Measured on the same tree before and after: entry **13,947 → 13,026 gzip**, **921 B returned** (raw 40,254 → 36,539), against 53 B of headroom before it and 974 B after. `gw-chain` occurs **3** times in the entry chunk before and **0** after, counted with `grep -o` piped to `wc -l` over the chunk `dist/index.html` names, because `grep -c` counts lines and a minified chunk is two of them. The drawer is now `drawer-*.js`, 4,060 B raw / **1,376 B gzip**, fetched on the first handle a reader opens and by no reader who opens none. The explorer route is re-walked in the same act: **74,838 B** on the base tree against the 71,511 this file recorded, and **73,925 B** here with the drawer cut on the rule the paragraph above states. The entry stylesheet is unchanged at 6,507 B and gains the fourth budget in the same commit, at the ruled 7,420 B |
| 2026-09-04 | v0.81 card fix round 3 (`38cf446`, both gates' fixes) | **13,667** | **79,460** | 325,643 | The P5–P7 sentinel's and visual gate's fixes, measured on the tree they land in: entry 13,666 → 13,667 (jitter class), explorer route **78,971 → 79,460** (+489: the reloaded-window bar and its widening control, the BigInt sum, the capture band's key and single control, the per-lateral-foot refusal note and the table's pinned-column class — all in `chart/*`, `card/format.ts` and `card/table.ts`, which ride the route), entry stylesheet unmoved at **7,367** against the ratcheted 7,400 (every new rule rides `chart/chart.css`), map chunk 325,643 → 325,643. **The route is inside its budget on one cut, and this row says so** (sentinel H-5). P5 added the chart's table alternative to the walk's cut list in `explore/bundle-budget.test.ts`, a file P5 does not own, on the file's own ruling for `drawer` and `sheet`: a chunk fetched on a press is not downloaded by a reader who lands. Re-walked both ways on this tree: **79,460 B with `table` cut, 80,234 B without it** — the table chunk is 791 B gzipped, and without the cut the route is **534 B over 79,700**. P5's commit stated the difference as "about 500 B"; it is 773 B on the P7 head and 774 B here. The route cannot be made to fit by the card's own means without changing what Explore's series drawer offers: the only card-owned bytes on the route are `chart/*`, `card/format.ts` and `card/table.ts`, and moving the card-only controls (brush, running total, the capture band, table, normalisation) behind options the card supplies would remove them from Explore too, which is not the card's to decide. **The cut therefore stands on the owner's ruling, not on this file's precedent**: either an Owns amendment ratifying it as the seventh cut on the rule the file already states for the sixth, or a ruling that the card-only controls come off Explore's drawer, after which the inversion above takes about 10 kB off this route. Until that ruling the budget is unchanged at 79,700 and unraised, with 240 B of headroom on the cut |
| 2026-09-04 | v0.81 card P7 (`0d68f51`) | **13,666** | **78,971** | 325,643 | The card's second generation, measured at the group's last phase on a clean head and against the same build on the merge commit `7324027`, which is the only base that attributes anything: entry **13,576 → 13,666** (+90), explorer route **76,110 → 78,971** (+2,861), entry stylesheet **7,396 → 7,367** (-29), map chunk **325,642 → 325,643** (+1, the jitter class, and none of it this branch's). P5's chart controls and P6's peer, pools and export sections ride cut chunks (`chart`, `table`, `card`, `drawer`, `sheet`); what the route gained is the card's request layer and the shell that reaches them. The stylesheet **fell** across a group that added three sections, because the drawer's chrome moved to `lineage/drawer.css` while the rail's own rules stayed on the entry sheet. **The budget ratchets 7,420 → 7,400**, the measurement plus 33 B: measured + 5% is 7,735 and would be a 315 B raise, so the ratchet takes back what is unspent instead. Against the row below, the entry is +640 and the route +5,046 — most of that the Texas train's, which this row does not claim |
| 2026-08-21 | `ff9a0ae` | 341,517 | — | — | one chunk; no split, no explorer |
| 2026-08-21 | C0 | 38,498 | — | 302,369 | map moved behind a dynamic import |
| 2026-08-21 | C11 | 44,192 | 62,817 | 313,823 | first measurement of the explorer route |
| 2026-08-22 | M1-7 | 44,245 | 62,867 | 315,287 | disposal layer: +538 gz on the map chunk (base cda2e51 measured 314,749); entry unchanged |
| 2026-08-22 | M1-3 | 44,014 | 62,615 | 314,293 | provenance wire field + snapshot coverage: +383 gz on the map chunk (base 88105aa measured 313,910 on this toolchain); entry +10, jitter class |
| 2026-09-02 | facets-all-jurisdictions | 13,930 | 73,634 | 325,700 | scope becomes a set: +473 gz on the explorer route, +4 on the entry (jitter class — the panel is not on the entry path) and +15 on the map chunk, against a v0.76 baseline re-measured on this toolchain at 13,927 / 73,167 / 325,217. Re-measured after merging v0.77, which is the row shown; the pre-merge measurement was 13,931 / 73,640 / 325,232. The map chunk figure is not comparable with the 313,823 two rows below: the v0.74–v0.76 layers moved it, and nothing here did |
| 2026-08-31 | facets | 21,340 | 71,511 | 313,823 | "Wells by ..." panel: +3,362 gz on the explorer route, entry and map chunk unchanged. Not split behind a dynamic import — it renders on the `wells` dataset, the one the explorer opens on, so a split buys a second round trip for nearly every reader |

---

## 7. API cost — the counted-facet query

The one measurement in this file that is not about bytes or frames. `/v1/wells/facets`
scopes to a set of jurisdictions as of v0.78, and `all` asks the spine one question over
every promoted well rather than over one state's share of them, so what it costs is a
number this track owed rather than an estimate it could offer.

**Instance:** the deployed database, VM 111, 2026-09-02, **809,191 spine rows over 585,864
distinct API-10** in four jurisdictions. Read-only, `explain (analyze, buffers)` over the
exact statement `facets.py` emits, `top=15`, `sort=count:desc`, no `q`, no `as_of`. Warm
cache, three consecutive runs, the range reported. This is the deployed instance, not a
harness: the numbers are claims about production.

| dimension | `state=all` | `state=42` (Texas) | `state=33` (North Dakota) | buffers, `all` |
|---|---:|---:|---:|---:|
| operator | 611–613 ms | 320–334 ms | 53–54 ms | 12,787 |
| county | 493–501 ms | 262–282 ms | 44–45 ms | 12,778 |
| **status** | **1,561–1,647 ms** | 397–418 ms | 85–86 ms | **296,767** |
| well_type | 490–497 ms | 256–257 ms | 45–46 ms | 12,778 |
| completion_year | 557–573 ms | 317–319 ms | 47–49 ms | 12,778 |

Four of the five are answered index-only off `wells_facet_dimensions_idx` with **0 heap
fetches**, which is what deduping per `(state_code, api10)` buys: the api10-only partition
the operation shipped with cannot use that index over a set at all, and the same `all`
operator facet measured **279,288 buffers and 1,031 ms** in that shape against 12,780 and
592 ms in this one.

**`status` was the exception, and the fix is an index and a keyed relation rather than a
cache.** The paragraphs below are the diagnosis as measured on the deployed database *before*
the migration this track added; the section that follows them is the before/after on a fixture
of the same size, and what it predicts for the host.

**`status` is the exception and it is not a cache's problem.** It is the one dimension that
joins — New Mexico's class is resolved at read time (`cr_nm_wellhistory_status_vocab_2`) —
and the join costs it the index-only scan: 296,767 buffers against 12,778, all of it heap.
Two things are wrong with the plan and both are addressable:

1. `w.status_reported` is not in the covering index's `INCLUDE` list, so the outer side of
   the join has to visit the heap for every one of 809,191 rows. Adding it restores the
   index-only scan. Measured share: the single-state ND status facet reads 89,111 buffers
   for 87,634 rows, which scales to the 296,762 the four-state one reads.
2. The planner merges on `state_code` alone and applies `status = status_reported` as a
   join filter, so **4,179,636 rows are removed by the filter** — every well compared
   against all fourteen New Mexico map rows. A `canonical.status_resolution` the planner can
   merge on both keys (a materialisation keyed `(for_state_code, for_status_reported)`, or
   an index on the underlying map that supports it) is the other half.

Forcing a hash join instead (`enable_mergejoin = off`, session-local, measured) drops the
buffers to 20,791 and makes it **worse** — 2,248 ms — because the hash destroys the index
order the `distinct on` needs and the sort of 809,191 rows costs more than the heap did. The
index change is the fix; the plan hint is not.

### What the migration changes, measured before and after

Both faults are addressed by the migration this track carries: `status_reported` joins the
covering index's `INCLUDE`, and `canonical.status_resolution` is backed by a keyed relation the
planner can look up instead of a view it can only scan.

**The deployed database cannot answer a before/after read-only** — the comparison needs an index
that does not exist there yet — so it was measured on an ephemeral PostGIS loaded to the
deployed row count: **809,191 spine rows over four states, ND/TX/NM/MT in their deployed
proportions, New Mexico's `status_canonical` null so the resolver join is live.** Same statement,
`vacuum (analyze)` before each measurement, three runs, the last reported.

| | buffers | time | spine scan | resolver |
|---|---:|---:|---|---|
| before (v0.76 index, view resolver) | 32,598 | 1,285 ms | `Index Scan` — a heap visit per row | scanned |
| **after** (this migration) | **12,484** | **818 ms** | `Index Only Scan`, **Heap Fetches 0** | `Index Scan using status_resolution_resolved_pkey` |

**−62% buffers and −36% time on the fixture.** The index rebuild itself takes **1.25 s** at that
size and grows the index from **95 MB to 98 MB**.

**What that predicts for the host, stated as a prediction.** The fixture's heap is 160 MB and the
deployed one is larger — which is exactly why the same `Index Scan` reads 296,767 buffers there
against 32,598 here. The change does not make the heap visit cheaper; it removes it, so the
deployed status facet should read the same order of buffers as the other four dimensions
(~12,800, a ~23× fall) and its 4,179,636 join-filter comparisons should become one index probe
per New Mexico row. On that basis it should land near the 490–613 ms band rather than at
1,561–1,647 ms. **This is not a measurement of the deployed database and must be re-measured
there after the deploy** — `web/PERF.md` gets the real number then, and this paragraph is what it
will be checked against.

One caveat that is not about the deploy: an index-only scan reads the visibility map, so the
gain is realised only on a vacuumed table. On the same fixture the rebuilt index recorded
809,191 heap fetches before a vacuum and 0 after. The deployed table is autovacuumed; a freshly
restored one is not, until it is.

No cache is shipped, and the facet rate limit is unchanged at 60 requests per principal per
UTC minute. A cached facet is a figure whose derivation handle no longer describes when it
was computed, and `all` was under two seconds warm even before this.

**On the fixture** (contract tier, 36 wells over three jurisdictions, whole request including
the `api.respond` derivation write): 11–16 ms per dimension. It measures the code path, not
the data — the deployed table above is the number that means anything.
