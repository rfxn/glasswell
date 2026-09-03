# Roadmap

Nine phases, each exiting on a stated criterion rather than on a feeling. The cut
order under compression is decided in advance, and some things are never cut.

<p align="center"><img src="assets/roadmap.svg" alt="Build phases P0 through P8 with exit criteria, the pre-committed cut order, and the never-cut list" width="1000"></p>

The phase model here is the nine-phase P0–P8 set in
[`blueprint-v0.6-draft.md`](blueprint-v0.6-draft.md) §7. [`blueprint.md`](blueprint.md)
is still the committed contract at v0.5 and still carries the earlier eight-phase
numbering; its §10 governs when that changes.

## Where it stands

59 tagged releases, v0.20 through v0.78, cut from 2026-08-21 through 2026-09-03, run
a **four-state** deployment on one VM (`git tag | grep -c '^v'`): North Dakota end to end,
Texas and Montana on the map, and New Mexico's headers, surface geometry and Tier 1
production resident. The concise evidence ledger is [`STATUS.md`](STATUS.md), which owns
every count and dates each one; status here is per phase and stated against the exit
criteria below, not against a feeling of progress:

| Phase | Where it stands |
|-------|-----------------|
| **P0** Scaffold and contracts | **Met.** Envelope and error model frozen and contract-tested; OpenAPI snapshot committed with a diff test; naked-number and glossary-coverage checks blocking; `lineage.audit_events` append-only as enforced, by grant and by trigger; registry and glossary seeded with evidence and served. No `/v1/audit` read endpoint yet, which P0's exit does not ask for |
| **P1** ND spine | **Met with named deferrals.** Ingest, promotion with conformance references and bitemporal vintages, and a live quarantine with a measured share, across the monthly production report, DMR GIS layers and PLSS grid. The 125-workbook XLSX back-load is complete: canonical holds 131 distinct months from 2015-05-01 and 7,223,544 rows. The PDF era remains deferred by design. FracFocus disclosure-header ingest now supplies P3 completion anchors; chemistry remains unparsed |
| **P2** Serving and map | **Substantially met.** Fifty-six snapshot-pinned operations across 51 paths, fifty-five under `/v1` (counted from `tests/contract/openapi_snapshot.json`, 2026-09-01); tiles from PostGIS with the layer allowlist asserted in CI; URL-backed Map, Explore, and Status surfaces; well card, lineage drawer and glossary tooltip shipped; the frame-rate budget codified in the perf harness. Source-observed completion events, pool-to-formation mappings and current ND physical neighbours are separate API/card sections. Neighbours use current lateral geometry, strict earlier-completion cutoffs, exact query lineage and an explicit non-analog warning; retrospective geometry is unavailable rather than inferred. Completion-design measurements are promoted as of v0.75 under `cr_ff_design_promote_1`, and `design_availability` reads `promoted` on the served completion record. Permits, land units, spacing units, GOR and water-cut remain |
| **P3** Forecasting and benchmark | **Pinned control accepted; modeling remains.** Publication `p3pub_8b434525d8c621762e31b06ca660bfcd` advances the evaluation vintage to 2026-08-28 without changing `fv2.0`, `mdv1.4`, `tcv1.0`, or split set `sset_c7bbb9a6932db76b`. Two full builds reproduce all eight artifacts and all eight split files byte-identically; an independent read rehashes every file against the receipt. Control unavailability is 1.0798% (230 / 21,300), below the 5% ceiling, with source-absent laterals retained rather than inferred. No model, calibration, persisted analog index or benchmark runner exists, and the model registry remains DDL with no writer |
| **P4** Dollars and scenarios | **Not started.** No deck, DCF, breakeven, payout or scenario loop. `econ.value` and `econ.sensitivity` exist in the derivation-kind vocabulary and nothing emits them |
| **P5** Intelligence, agents and alerts | **Not started.** No agent gateway and no curated tool surface; no league table, AOIs or digests; `lineage.forecast_grades` is DDL with no writer |
| **P6** Hardening and glass-box proof | **Partial.** Six CI jobs are branch-protection-required — `python`, `web`, `e2e-guards`, `shell`, `collateral`, `map-chrome` — with the tile allowlist asserted and conformance exercised end to end. The deployment is **`v0.73+9796501` at schema head 070**, measured on the host 2026-09-01, and carries independently committed source-poll outcomes aligned to actual recurring timers, nine fail-closed selector-output contracts, two-clock conformance, a bounded viewport rate window, a sandboxed nightly retention unit, session auth with rate limits, backup, an offsite push receipt and the public tunnel. `infra/verify.sh` and `scripts/smoke.sh` last read 194/194 and 26/26 at the v0.72 deploy and have not been re-run for v0.73. The recurring logical restore still passes only against the schema-47 backup — carried from the previous revision of `STATUS.md` and not re-verified today — so the proof sits twenty-three schema versions behind the deployment. Full VM/raw-zone recovery remains open, as do broader rate policy, remote-copy evidence, the outsider guest exercise, and broader determinism and tool-equivalence gates; Cloudflare Access is ruled out rather than deferred |
| **P7** Permian — NM first, then TX, with Montana resident alongside | **NM resident; the Texas half unbuilt.** New Mexico's spine landed: `ingest/nm_wells.py` promotes OCD headers into `canonical.wells` and a surface point into `canonical.well_spatial`, and Tier 1 production is promoted. Measured on the deployed database 2026-09-01: 321,510 NM header rows over 142,000 API-10s, 141,778 carrying a surface point, and **17,597,960 production rows at the completion-pool grain**. `ingest/nm_c115b.py` still stops at staging by design, because the C-115B service publishes a rolling window and a month that rolls out of it cannot be re-fetched. NM's promoted `status_canonical` stays null by design — the table is append-only and a re-promotion would have to invent a valid time the OCD never filed — and as of v0.74 the class is resolved at read time from `cr_nm_wellhistory_status_vocab_2`'s registered codebook through one shared resolver every serving path reads. Ten of fourteen OCD codes carry canonical classes; the four that do not are served as `documented_unmapped`. **Montana** is resident alongside this phase rather than inside it — both production grains, tiles and paths — under N3 below. TX carries wells, wellbore identity and bore geometry on the map and **no production at all**: `tx_pdq_dsv` is not a registered source, so TX lease production, allocation v0 and its two validators remain unbuilt P7b scope |
| **P8** Living systems | **Not started.** |

## Phases

| Phase | Contents | Exit criteria |
|-------|----------|---------------|
| **P0** Scaffold and contracts | Repo layout with the staging / canonical / marts split; derivation capture written before the first transform, not retrofitted after it; DDL for manifests, fetch log, quarantine, derivations, recipes, audit events, `conformance_rules`, `crs_registry`, `glossary_terms` and `land_units`; registry seeded from evidence already in hand — datum and CRS transforms, per-basin compute CRS, the liquids policy of oil plus condensate, API-number formatting, unit policy; API skeleton with the envelope, error model, pagination, `as_of` and an auth stub | Audit stream live and append-only as enforced — grants revoked, trigger behind them, one writing role; first conformance and glossary rows committed with evidence URLs; envelope and error model frozen; a trivial endpoint passes the naked-number and glossary-coverage checks; one recipe replays byte-identical |
| **P1** ND spine | The identity question first — whether the free monthly production report keys on API-10 or only on the state file number, and the crosswalk built before anything else if it does not; fetchers on the free NDIC and DMR GIS paths, with no subscription on the critical path; XLSX, shapefile and file-geodatabase parsers; staging load with quarantine live; promotion to canonical with conformance references and bitemporal vintages; PostGIS load of well points, laterals, PLSS sections and townships, spacing units and pre-spud permits; FracFocus completion design. The PDF era, 2003-01 → 2015-04, is deferred inside this phase | Every ND production row explains to a manifest and cites the rules that shaped it; the identity decision is a committed conformance rule with its evidence; the quarantine path is exercised by an injected fixture and its share is measured, whatever it turns out to be — exiting on a non-zero share would reward manufacturing rejects; re-fetching an unchanged file is a logged no-op; a synthetic restatement produces a new vintage without touching prior rows |
| **P2** Serving and map | API v1 over wells, production, completions, neighbours, permits, land units, spacing units, formations, manifests, conformance, quarantine and glossary; geometry tiles from PostGIS behind the tile proxy, with attribute bundles joined client-side; map application, well card with GOR and water-cut charts, the lineage drawer, and the glossary tooltip component | 20k+ laterals at interactive frame rates; the glass box demonstrated on a served production number; glossary coverage for the surfaces that exist; the tile-layer allowlist checked in, with CI asserting the served source list equals it; every UI figure has a reproducing endpoint |
| **P3** Forecasting and benchmark | Entry is the production back-load, without which not one rolling origin is reachable. The v0.6-rc4 amendment resolves the old arithmetic: 2015-05 → 2025-09 is 125 monthly workbooks and 336.6 MB measured; all 125 landed, leaving 131 distinct canonical months from 2015-05-01 and meeting the entry gate. Feature builder with declared availability dates; type-curve baseline; three-stream gradient-boosted quantile models; split-conformal calibration; model registry; persisted analog index; benchmark harness | Entry gate: ≥ 120 distinct production months in canonical with the earliest at or before 2016-01. Then calibration green and the analog check measured against its bracket rather than asserted — an inconclusive interval blocks exit exactly as a failure does; the pinned type-curve control on the identical split; per-slice empirical coverage published with its interval; the determinism check green; every forecast citing a registered artifact, and no number served from an unregistered one |
| **P4** Dollars and scenarios | Decks and assumptions with water opex and per-state tax defaults; DCF, breakeven and payout; sensitivities and tornado; the scenario loop; type-curve builder in the UI; analog panel on the scenario card | A scenario returns forecast plus NPV in under three seconds; the type-curve builder is live; the tornado is hand-checked directionally; every valuation reports P10, P50 and P90 together |
| **P5** Intelligence, agents and alerts | Activity surfaces and the DUC proxy; operator league table on the residual metric, with operator aliasing and a stated rollup mode; areas of interest and weekly digests; well sets and rollups; agent gateway over curated tools; the forecast ledger starts writing | The ten-question suite passes through the public tools; the tool-equivalence report is clean; an AOI digest is correct against a manual diff, with its freshness window stated |
| **P6** Hardening and glass-box proof | Naked-number, glossary-coverage, tile-allowlist, conformance, contract, tool-equivalence and determinism checks all wired and blocking; determinism pinning across the artifact path; tunnel and Access with all three scopes and a non-interactive guest-key class; the two-user database split landed before the first guest key; rate limits; backup and a live restore drill; observability and the weekly self-report; non-functional budgets converted to tests | A stranger with a guest key reproduces every number in the UI; the restore drill completed from backup to a working system; the glass-box, performance, scenario, agent, conformance, glossary and as-of criteria all green |
| **P7** Permian — NM first, then TX; Montana is resident alongside it as a Williston extension, not as phase scope | **NM first.** OCD fetch with address re-resolution; XML full-table parsers; production, well and completion history, spacing units and the well-completion crosswalk; change detection; a well-level Permian spine, which is the allocation variable removed — and the well headers and geometry that spine is made of, since `canonical.wells` and `canonical.well_spatial` are the unbuilt half and no promoted NM figure reaches the map or the well card without them. **Then TX.** RRC identifier resolution with rotation monitoring; lease production and the in-dump well-to-lease crosswalk; the wellbore master; completion feed and permits, incremental; county GIS layers with the NAD27 transform recorded as a derivation; allocation v0 with both validators; abstracts loaded as land units. TX directional survey stations stay out — see the two reasons under **Out of scope** | Allocation error bounds published from both validators; the quality scorecard published; the Texas user stories passing on TX data; quarantine rate reported by basin against the per-basin trigger; the oil-lease share of allocation measured and published; a Permian benchmark artifact, sliced, against the type-curve control on the identical split; no NM figure served before a well header and geometry exist for the rows behind it; the NM-before-TX ordering validated — the well-level spine de-confounded the allocation error measurement, or it is documented why it did not |
| **P8** Living systems | One graded forecast-ledger cycle, bounded by elapsed time; inventory v0, ND-scoped — geometrically admissible undrilled locations at an assumed spacing, each carrying a training-support score, and never reserves; basin transfer as a stretch; capability matrix with attribution checked; the notebook write-up and the fluency outcomes; publish decision against IP-carve-out status | One graded cycle complete, the capability matrix published, and the township inventory demo recorded (conditional); every honest gap tagged `data-unreachable` or `effort-unreachable`; the publish decision recorded either way |

Epics E1–E16 and user stories U1–U15 are defined in blueprint v0.4 §5 and §6; the
v0.5 amendments, E17 (inventory) and U16–U21 are in [`blueprint.md`](blueprint.md)
§5 and §6; E18 (glossary-as-data) and U22 are new in
[`blueprint-v0.6-draft.md`](blueprint-v0.6-draft.md) §5 and §6.

## Next work

A capability review at the mature end of the market, held internally under the
[`blueprint.md`](blueprint.md) §8.2 carve-out, found the analytics surface already built
and sold: filtered rate-versus-time with normalisation and grouping, basin rollups,
machine-learned rock-quality tiers over locations that do not exist, breakeven
economics, decline parameters as a download. It also found no lineage affordance
anywhere on it — no derivation handle, no per-figure source, no vintage stamp, no
spacing or support disclosure — one artifact carrying two different totals for the same
quantity with nothing on the page to reconcile them, and drilled wells stacked with
modelled locations behind a single measure a reader can forget to filter. The
conclusion is not to copy that surface. It is that the same class of figure, served
with the handle attached and the 4D statements mandatory, is the product — and R8,
the naked-number rule and Protocol 4D are already built, which is the expensive part.

Three priorities, owner-approved 2026-08-29. Each sits inside an existing phase rather
than alongside one; none renumbers the P0–P8 set:

| Priority | Contents | Exit criteria |
|----------|----------|---------------|
| **N1** Serve the computed modeling layer *(P3 → P2 serving)* — **done, v0.68** | *As scoped, before v0.68:* `src/glasswell/modeling/` is 5,211 lines and no router imports it — `grep -rn "from glasswell.modeling" src/glasswell/api/` returns nothing. It holds formation type curves at P10/P50/P90 on the closed `formation_area_length → formation_area → formation_basin` peer ladder, under both normalisation arms (`NORMALIZATIONS = ("typecurve_per_kft", "typecurve_absolute")`), with the control pinned `tcv1.0` and the accepted publication `p3pub_8b434525d8c621762e31b06ca660bfcd`; 12- and 24-month cumulatives and producing-month-indexed curves (`HORIZONS = (12, 24)` in `modeling/model_dataset.py`); feature matrices and model-ready splits. All persisted to Parquet, none served. The work is routers over pinned artifacts, not new modelling | Met. Every served type-curve and cumulative figure carries an `api.respond` handle whose chain names the pinned `typecurve.build` derivation, its `split_set_id` partition and its artifact sha256, at the default explain depth; `control_unavailable` is a 200 with `outcome` as a required field, its reasons named and the figure slots present and null with resolvable handles; the naked-number, not-a-figure and glossary-coverage gates cover the four new operations, which the walker picks up from the served document; and no figure reads an artifact the resolver has not put through four independent agreements — an accepted publication receipt, a registered derivation, receipt/locator/digest agreement, and a contained non-symlink path whose digest matches, re-stat-checked after the read. Served at `/v1/modeling/publications`, `/v1/modeling/publications/{publication_id}`, `/v1/wells/{api10}/type-curve` and `/v1/type-curves`. Feature matrices are **not** served: `fv2.0` is one categorical column and `feature_specs` holds two rows, so a `/v1/features` surface would overstate what a caller can be shown; the feature version, set hash and derivation are served as identity on the publication detail instead |
| **N2** Enrich the served views from data already in hand *(P2)* — **re-landed in v0.75** | Per-well cumulative oil, gas and water — the `prod` CTE in `marts/land_metrics.py` `_MEMBERSHIP` already computes it `group by api10` on every refresh and discards it into the PLSS rollup. Spacing statistics over `marts.nd_neighbor_edges`, which already holds directed distances with a pair-local UTM zone recorded per edge. Parent/child labelling, since `/v1/wells/{api10}/neighbors` already returns only earlier-completion same-formation neighbours — the relation is live; the label, the child-side inversion and the aggregates are not. Vintage cohorts from `spud_year`, already a tile column. Fluid intensity per lateral foot, one promotion away — `total_base_water_volume` was staged only, and the card reported `design_availability=not_promoted`; v0.75 promoted it and the card renders it. Lateral length, the producing class and land-unit rollups are already served and are out of scope; `marts.nd_well_card` is empty on purpose, as `013_lateral_length_precision.sql` states and `tests/integration/test_marts_nd.py` asserts, so filling it is a decision to reverse rather than a gap to close | Each new figure carries a derivation handle and states its null semantics, keeping `no_report`, `reported_zero` and `withheld` distinct; the cohort key — spud year or completion anchor year — is a committed conformance rule with its rationale, not a choice made in a query; the fluid-intensity promotion moves the card off `not_promoted`; any figure whose inputs are state-truncated says so on the figure |
| **N3** State expansion — the NM gate, then Montana *(P7, then a Williston extension)* — **done — NM v0.70, MT v0.70/v0.71** | *As scoped, before v0.70:* NM's remaining half is the spine: well headers into `canonical.wells` and **surface** geometry into `canonical.well_spatial`. NM lateral geometry is tagged `data-unreachable` and the evidence is two measurements, not an absence of effort: the OCD FTP header table ships a surface point, one datum and no path over all 321,510 records, and the OCD public wells layer is `esriGeometryPoint` and describes itself as the surface drilling location. 43,409 horizontal and 3,265 directional wells are named in the header table with no path filed for any of them, and `cr_nm_wellhistory_geometry_scope_1` is the row that records it so no consumer reads a horizontal well's presence as a lateral. Then Montana — MBOGC publishes bulk well-level *and* lease/unit-level monthly production, the complete well list, surface points and well paths, from one regulator; the `^33` neighbour constraints become state-parameterised; the BLM PLSS scope rule extends | NM: no figure served before a well header and geometry exist for the rows behind it — the gate opens on the spine, not on the row count, and a surface point satisfies it. MT: ND wells at the Montana line carry complete neighbour sets, with the count that changed reported rather than asserted; MT well-level and lease-level volumes reconciled and the residual published as a measured allocation control before TX allocation v0 is written; MT quarantine share measured against the per-basin trigger |

N1 and N2 do not depend on each other, and neither depends on N3. Two of N2's figures do
depend on N3: spacing distributions and parent/child aggregates read
`marts.nd_neighbor_edges`, whose DDL constrains the subject key and both endpoints to
`^33[0-9]{8}$` (`045_nd_neighbors.sql:5` and `:55`), so ND wells at the Montana line have
truncated neighbour sets today. Serving those two before Montana lands means restating
them after it. N1 is the only one of the three that unlocks a built artifact rather than
building one, so it goes first under compression.

### State expansion

**Montana follows the NM gate and precedes TX allocation v0.** It is not a phase and
renumbers nothing; it extends P1's ND spine into a second Williston state. It is not one
of the additional basins deferred until after P8, because it is the same Williston Bakken
already trained on. Colorado and Wyoming open the Rockies rather than extending the
Williston; §2.3's deferral is amended for them at v0.77, with the argument recorded there.

Four reasons for that position. It extends the trained basin rather than opening a new
one, so formation aliases and the peer ladder in `modeling/type_curve.py` reach across
the state line instead of needing new analogues. It repairs a live defect rather than only
adding coverage: `045_nd_neighbors.sql` constrains `nd_neighbor_subjects.api10` and both
sides of `nd_neighbor_edges` to `^33[0-9]{8}$`, and `marts/land_metrics.py` pins
`GRID_STATE_API_PREFIXES = ("33",)`, so ND wells near the border have truncated neighbour
sets and every spacing or parent/child figure built on them inherits the truncation. It is
the only candidate publishing both production grains from one regulator, which makes the
well-level file a control for the lease-level file — the TX allocation problem rehearsed
against ground truth before allocation v0 is written, which is the same argument P7's exit
criterion already makes for NM-before-TX, at a fraction of NM's cost. And the land grid is
free: the BLM CadNSDI service that `ingest/blm_plss.py` already fetches covers Montana,
with the ND scope held as a conformance row (`cr_blm_plss_scope_1`), so land units, land
metrics, spacing-unit tiles and the Protocol 4D inventory story port on a scope change
rather than a new component.

It goes after the NM gate and not before it because NM's cost is already sunk — roughly
200 KB across `ingest/nm_ocd.py`, `ingest/nm_dims.py`, `ingest/nm_c115b.py` and
`seed/conformance_nm.py` — and its gate is a build decision about the spine, not a new
source. Montana is net-new build. Estimated S–M, about two weekends at the rate below; it
sits outside the phase budget table because it is not a phase.

**Oklahoma is tagged `data-unreachable` on production.** Headers, permits and completions
are bulk and good. Production is not: the Corporation Commission does not publish it, the
Tax Commission is the recordkeeper, and its history is lease-grain on the production-unit
number, served through a per-record web lookup and a mailed request form. No bulk
production file exists, so this carries the same tag as open question 7 and the TX survey
filings, for the same reason. Header-and-permit coverage alone would ship a state whose
wells could never carry a production number, which is worse than absence. The completions
master does carry the tax production-unit number, so the identity half of a lease
crosswalk is largely pre-solved if a bulk feed ever appears.

## Horizon

Two elevations frame every release after v0.73. They are the product-owner direction of
2026-09-01; the plan of record that carries them is untracked at
`work-output/po-review/PRODUCT-REVIEW.md`.

**Elevation A — states as registrations, not projects.** A new state should be one source
row, one jurisdiction row, its R8 rule set — status vocabulary, geometry provenance,
liquids basis, production grain, unmapped action — and an ingest module that writes
staging. The layer panel, the `Wells` family, the facets `state` domain, the status
collector, the neighbour scope, the tile layer list and the legend census all read the
registry rather than an API-10 prefix. The proof is state #5 landing through the seam with
no edit to `routers/wells.py`.

**Elevation B — status truth on every surface.** One canonical class vocabulary; every
jurisdiction maps into it by rule rows with published evidence; documented-but-unmappable
codes are a distinct served class, never null; resolution happens in the mart layer so
tiles, flyout and legend cannot disagree on screen; and "active" is labelled for what the
regulator means by it, with the producing class carried beside it.

P3–P5 stay inside the phase model above and are sequenced after both, because the direction
is UX first and scale second, and because a model built over four hand-wired states would be
rebuilt once the registry lands.

| Horizon | Releases | Theme | Contents |
|---------|----------|-------|----------|
| **H1** | v0.74–v0.76 | Truth, retained work, foundations | v0.74 **shipped** — NM read-time status resolution, the Map→Explore crossing, and Basins and Plays drawn as real layer rows; v0.75 the N2 re-land and glossary coverage on the three densest surfaces; v0.76 the jurisdiction registry and an owner-only Accounts surface — **merged on `release/v0.76` as of 2026-09-02, neither tagged nor deployed**: migration 073 registers the four jurisdictions with their two clocks and serves them at `GET /v1/jurisdictions`, migration 074 carries the session client label behind `GET`/`DELETE /v1/sessions`, and the per-state dicts the elevation names are rows |
| **H2** | v0.77–v0.80 | Prove the seam, fill the biggest hole | v0.77 state #5 lands as a registration · Colorado through the registry, one parameterised wells mart replacing the four per-state copies, the martin catalogue asserted against `TILE_LAYERS` in CI, the neighbour envelope and length-source defaults widened by rule, the glossary page cap removed, and the cadence-driven scheduler (C26) so NM and MT are scheduled; v0.78 Texas lease production, allocation v0 and both validators — P7b, the largest resident state finally carrying numbers; v0.79 status truth for N states: the legend and status vocabulary served from `/v1/jurisdictions`, `canonical.status_resolution` generalised past one jurisdiction, a jurisdiction row and regulator deep-link on the flyout, hover and provenance notes that name the well's own regulator; v0.80 glossary full coverage with an em-dash lint, Explore usable at 390 px (a media arm below 520 px), DOM-count budgets in PERF.md for the layer panel, legend and Status table |
| **H3** | v0.81+ | The blueprint phases, on a registry | P3 modeling (quantile models, calibration, registry writer), P4 economics, P5 agents; Canada as a jurisdiction with a UWI identity scheme rather than a special case; PA/OH/WV as the first non-PLSS land question. The `/v1/wells` spine query is rewritten ahead of P3 modeling, not after |

State #5 is chosen on reachability first: bulk headers, bulk well-grain production, surface
coordinates, a published status codebook, stated terms. The per-release track tables —
worktrees, branches, migration numbers and exit criteria for v0.74, v0.75 and v0.76 — are
working files under `work-output/`, which is git-excluded and reaches no clone. The table
above is the tracked form, and it is the one every other document should cite.

## Timebox

Rough, and deliberately stated in weekends rather than sprints, at 12–16 productive
hours per weekend, solo:

| Phase | Weekends | Note |
|-------|----------|------|
| P0 Scaffold and contracts | 2 | Higher than instinct: derivation capture and the envelope are contracts, and contracts frozen late are the most reliable source of rework |
| P1 ND spine | 4 | Six source families, three file formats, bitemporal promotion, quarantine |
| P2 Serving and map | 4 | Tiles, attribute bundles, card, drawer and the whole glossary system, plus the tuning loop against the frame-rate budget |
| P3 Forecasting and benchmark | 4 | Features, three streams, conformal calibration, registry, harness, determinism |
| P4 Dollars and scenarios | 3 | |
| P5 Intelligence, agents and alerts | 3 | The agent suite is the long pole, not the league table |
| P6 Hardening and glass-box proof | 3 | Seven checks, three scopes, a real restore drill |
| P7 Permian (NM 2, TX 4) | 6 | TX carries the heaviest parse work in the project |
| P8 Living systems | 3 + elapsed | The graded cycle is bounded by calendar time, not effort |
| **Total** | **~32 weekends** | About seven to eight months of weekends |

Montana is deliberately absent: it is a Williston extension rather than a phase, and its
estimate sits with it under **Next work**.

The earlier estimate — roughly 17 to 19 weekends — did not survive inspection. The
same span had to carry ND ingest across six source families, promotion, PostGIS,
tiles and a map UI, three-stream models with conformal calibration, a benchmark
harness, analogs, economics, scenarios, a builder UI, alerting, the ledger write
path and an agent gateway, plus hardening. The increase is not scope creep: it is
the cost of what the earlier figure assumed rather than budgeted — capture written
first, bitemporal ingest, determinism pinning, seven checks, an auth model, a
restore drill, and the honest parse cost of delimited, XML, fixed-width and
text-layer formats. It is better for the number to be bigger and true.

## Traceability

Every success criterion maps to at least one epic and to the phase that proves it:

| Criterion | Epics | Proven in |
|-----------|-------|-----------|
| S1 stranger reproduces every number | E9, E10 | P6 |
| S2 20k+ laterals at frame rate | E7 | P2, re-verified P6 |
| S3 scenario under three seconds | E6 | P4 |
| S4 benchmark artifact per basin | E4 | P3 (ND), P7 (Permian) |
| S5 agent ten-question suite | E9 | P5, re-verified P6 |
| S6 allocation with both validators | E12 | P7, Texas half — unbuilt; Montana, resident on both production grains, is the rehearsal control for it |
| S7 ledger with a graded cycle | E13 | P8 |
| S8 quality scorecard published | E11 | P7 |
| S9 glass box holds | E10 | P2 first proof, P6 full |
| S10 capability matrix | E16 | P8 |
| S11 conformance registry served | E11 | P6 |
| S12 inventory demo *(conditional)* | E17 | P8 |
| S13 glossary coverage | E18 | P2 partial, P6 full |
| S14 as-of reproducibility | E1, E10 | P6 |
| F1–F11 fluency | E15 | Continuous, written up in P8 |

## Cut order under compression

First cut on the left:

**E14 transfer → inventory (E17) → alerts and league table → activity (E8) →
map-UI polish (E7) → field-notes UI**

The memos still get written when the last one goes; only the reader is cut.
Deciding this in advance is what stops a schedule slip from quietly eating the
load-bearing work.

### Never cut

- **E1** and **E2** — the ingest and canonical spine. There is no product without it.
- **E4** — the benchmark. It is the control group; without it every accuracy claim is marketing.
- **E5** — economics. Without dollars there is no loop.
- **E10** and **E11** — glass-box lineage and quality. They are the thesis.
- **E12 validators** — the allocation error bounds. Allocation without measured error is a guess with a decimal point.
- **Derivation capture** — retrofitting lineage is not a thing that happens.
- **The conformance registry** — cheap, and load-bearing. Without it, no cross-source number can cite the rules that shaped it.
- **E18's glossary** — cheap, load-bearing for coverage, and the only thing that makes the teaching claim concrete rather than aspirational.

Cutting E17 forfeits the inventory demo, which is already conditional. Nothing else
in the cut order costs a success criterion.

## Deferred until after P8

Canada · NGL three-stream economics beyond simple gas pricing · fault-aware
geology · additional basins beyond the Rockies sequence named under Horizon H2 · TX
inventory geometry · a public hosted demo and capability
matrix (IP-gated, see [`blueprint.md`](blueprint.md) §8.2). The source repository is public;
its proprietary license and data-redistribution limits are unchanged.

## Out of scope

Not deferred — out, until the blueprint changes:

Mineral ownership and title · daily production · multi-tenant SaaS auth
(single-tenant key auth is in) · distributed infrastructure · mobile · lineage
ontology platform · rig and frac-crew tracking (a documented moat item) ·
interpreted maturity mapping (moat item) · news and research layer.

**TX directional survey station data** is out for two different reasons, and they
are not one reason: filings before 2021-01-01 are `data-unreachable` — scanned
images with no free machine-readable index over them — and filings from that date
are `effort-unreachable` — reachable nightly, but behind per-well vendor-format PDF
parsing. Anything ever built on them states its coverage start.

## Open questions

Carried forward, to be resolved with evidence rather than preference:

1. **Headline target horizon** — cum12, cum24, or an EUR-style extrapolation? Start with cum12 oil: data-supported for recent vintages, and a short feedback loop for the ledger. EUR stays out of the target set.
2. **Feature-set boundary** — how much geology against design and location alone? Bulk ND tops are paywalled while TX formation data ships free, so the honest start is design-plus-location with geology as an ablation.
3. **Bulk formation tops behind the paid ND tier** — owner-parked, and worth buying only if that ablation shows geology carries real lift. Bounded to a one-time bulk pull if it ever happens.
4. **Type-curve peer-group definition** — geography, formation, vintage window, operator, or a learned neighbourhood? Start with an explicit filter set the user controls, which is also the builder UI. This governs the product builder only: the benchmark control's peer group is pinned, because a control that moves between runs is not a control.
5. **Parent-child depletion encoding** — offset count within a radius, time-weighted cumulative production, or a distance-decayed pressure proxy? All three are computable; the choice needs an ablation, and it is likely the highest-value feature family in the Bakken.
6. **Extrapolation form** — an interpretable decline form that imposes assumptions, or direct multi-horizon models that make fewer but extrapolate worse? Currently the former; revisit with ledger evidence.
7. **Price deck source and default** — no free, redistributable forward strip is in hand. Currently a flat default deck with its provenance stated. This one is an honest gap, and it belongs in the capability matrix tagged `data-unreachable`.
8. **Confidential and tight-hole handling** — exclude, censor, or impute? Currently censored, but the confidential period systematically hides new wells, which is exactly the population inventory and scenarios care about.
9. **Analog distance metric** — plain Euclidean on standardised features, or learned? Start Euclidean; compare once forecasting is stable.
10. **Inventory spacing assumption** — a single user input, or per-operator inferred from recent development? Start with user input; inferred spacing is a P8 experiment.
11. **TX inventory geometry** — with no PLSS, what is the unit: the operator's unit polygon, the lease, the abstract, or a synthetic grid? The land-unit abstraction keeps this a design question rather than a migration. It is also not a Texas question. Pennsylvania, West Virginia and Ohio are metes-and-bounds with no PLSS either, so `ingest/blm_plss.py`, `marts/land_units.py`, `marts/land_metrics.py`, the spacing-unit tiles and the whole Protocol 4D township-inventory story do not port to Appalachia at all. Whatever answers this answers those, and until it does, Appalachia inherits an open design question rather than an ingest job.
12. **Attribute-bundle size ceiling** — the client-side join is measured at ND scale and the Permian is an order of magnitude larger. The declared feature cap turns this into an instrument that fires on real traffic rather than a measurement someone must remember to take.
13. **Rule-change re-promotion cost** — at what rule-change frequency does re-vintaging become the dominant compute cost, and does a rule change ever justify a rebuild instead?
14. **Vintage cohort key** — spud year or completion anchor year? **Closed 2026-09-01** ·
    `cr_nd_vintage_cohort_1` pins `spud_year` with its measured rationale
    (`seed/conformance_vintage.py:26`), shipped in v0.75. Both inputs are already held: `spud_year` is a tile column, and `modeling/model_dataset.py` already bins subjects by anchor year. The two disagree for any well spudded in one year and completed in the next, which is most of them, so this is a conformance row with a rationale rather than a query-level choice.
15. **Whether a shorter horizon earns its keep** — a six-month cumulative is cheap to compute and expensive to land: `HORIZONS = (12, 24)` is part of the pinned `mdv1.4` identity and the accepted publication references it, so adding one changes an immutable and forces a reproducibility re-run. Only worth it against measured evidence that cum12 is too long a feedback loop for the ledger.

Two further questions — league-table normalisation, and whether upstream bandwidth
would carry a public demo — are closed, and are kept on the record in
[`blueprint-v0.6-draft.md`](blueprint-v0.6-draft.md) §8.3 rather than deleted, so
their resolution stays traceable.

## Known risks

| Risk | Mitigation |
|------|------------|
| **IP carve-out** (top item, time-sensitive) | The source repository became public on 2026-08-28 under its existing proprietary license. That does not publish the hosted app, regulator artifacts, capability matrix or vendor-comparison corpus; those remain separately gated before a public URL or matrix row |
| **Source redistribution rights** — a different legal question from competitor IP, and easy to conflate with it | Per-source licence status tracked with evidence URLs, and the absence of an affirmative grant recorded honestly rather than assumed; a per-source re-read gates any public artifact. The exposure is live, not theoretical: one RRC field, the coordinate-source provenance, is already withheld pending an open licence question while the rest of the TX stack is served. It is a review item over that stack, and it is not the reason any particular dataset is unbuilt |
| **Solo-builder bandwidth** — ~32 weekends is a long single-threaded run | The cut order is pre-decided, so compression is a lookup rather than a negotiation; phases are ordered so each ends with something demonstrable |
| **Source access drift** — identifiers rotate without notice, page structure changes | Identifier resolution is a monitored step; every poll writes an independently committed attempt before network access and finalizes as new, unchanged or failed only after manifest visibility. Status applies the registered source cadence, and one failed/open source key cannot be hidden by another key's success |
| **Conformance registry rot** — rules drift from code and the registry becomes decoration | Three rule kinds plus coverage, execution and binding checks; the documented share is itself a tracked scorecard metric |
| **Datum mishandling** — silent ~100 m position errors corrupt spacing and inventory | Datum rules per file vintage; the CRS service is the only transform path; a fixed set of TX wells with published positions asserted in CI |
| **Public-data quality bias** — withheld wells, trade-secret fields, missing quantities | Withheld is a distinct state, never collapsed to missing; the share is a scorecard metric and its own censoring class in the model |
| **Allocation error too large to be useful** | Measure early on the Texas half and report the oil-lease share; if the bounds are wide, ship them wide and say so — a labelled bad number is content, an unlabelled one is a defect |
| **Single VM, irreplaceable raw zone** | Nightly and weekly off-box copies, and a live restore drill as a P6 exit item |
| **Glass-box tax collapses velocity** | Capture is a decorator and a context manager, not a per-call-site chore, and it is built in P0 so the cost is paid once. If it does slow the build, that measurement is itself an answer worth writing up |
| **Harvest scope creep** — small features quietly become medium ones | Each harvested feature is capped at its stated acceptance; anything beyond it is a new blueprint version |
| **State assumptions hardened into DDL** — a check constraint is the expensive half of a single-state assumption, because it is a migration rather than an argument | `marts/neighbors.py` parameterises `state_code`, but `045_nd_neighbors.sql` constrains `nd_neighbor_subjects.api10` and both sides of `nd_neighbor_edges` to `^33[0-9]{8}$` and `marts/land_metrics.py` pinned `GRID_STATE_API_PREFIXES = ("33",)` until v0.76 made it `grid_state_prefixes()`, a read of the registry's own `land_grid_state` column. ND wells at the Montana line are the worked example that this is a correctness gap, not a coverage gap. Every new state audits the DDL and the mart module constants for hardcoded prefixes before its first row lands. Four states are now resident against 465 hardcoded state references across 59 files (measured in `work-output/po-review/code-audit.md`, 2026-09-01), so the audit is no longer sufficient on its own: the **jurisdiction registry is merged on `release/v0.76`** (2026-09-01, not yet tagged), after which the promotion, inventory and serving paths read a registry row rather than an API-10 prefix. `tests/unit/test_add_a_state.py` is that gate and it is keyword-free — any two-digit literal in the serving trees, jurisdiction name in the web bundle, or prefix in a migration written after 071 is a refusal unless it carries a named exemption. The DDL half stands: `045_nd_neighbors.sql` is applied history and still constrains its API-10 columns to `^33[0-9]{8}$` |
| **Built-but-unserved work accumulates** — 5,211 lines of modeling no router imports is capital earning nothing while it rots against the serving contracts | N1 makes serving the exit condition rather than a follow-on. The artifact identities are pinned — `tcv1.0`, `mdv1.4`, the accepted publication — so the serving layer reads a fixed input and the cost is a router, not a rebuild. The same test applies to anything else built ahead of its consumer: name the endpoint that will read it, or do not build it yet |
| **Inventory misuse** — slot counts read as reserves | The 4D statements are mandatory in every rollup, response and export |

---

> Copyright (C) 2026 Ryan MacDonald &lt;ryan@rfxn.com&gt; &#183; All rights reserved
