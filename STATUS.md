# Current status

Reconciled on **2026-09-01** against the v0.73 release line, the checked-in OpenAPI
snapshot, current `main` history, and a read-only census of the deployed database taken
2026-08-31. This is the
short current-state ledger;
[`ROADMAP.md`](ROADMAP.md) owns phase scope and exit criteria, while
[`blueprint.md`](blueprint.md) remains the committed v0.5 contract and
[`blueprint-v0.6-draft.md`](blueprint-v0.6-draft.md) is the rc5 amendment set.

**`main` is level with `origin/main`.** The unpushed backlog described here on 2026-08-31
was pushed on 2026-09-01 when PR #44 merged at `bc2dba5`, so hosted CI has now run against
all of it. **v0.72 is deployed** (`v0.72+1e78194`, verify 194/194, smoke 26/26), and the
deployed schema head is `070` — `068`, `069` and `070` were applied on the host at
2026-08-31 21:41–21:42Z, after the census this file was reconciled against, which is why
the previous revision recorded them as absent. Repository, database and deployed code are
level for the first time this week; figures below still carry where they were measured.

## Shipped baseline

- **Release line:** 54 tagged releases, v0.20 through v0.73, cut 2026-08-21 through
  2026-09-01.
- **North Dakota:** ingest, bitemporal promotion, quarantine, conformance, wells,
  geometry, monthly production, lineage, explain, glossary, API, tiles, and map are built.
- **Production history:** the 125-workbook back-load is complete. `nd_mpr_xlsx` holds 131
  distinct months from 2015-05-01 and 7,223,544 rows; the P3 entry gate is met. Montana's
  two grains have since been promoted into the same table — see below — so
  `canonical.production_monthly` is no longer a single-state table and its resident total is
  **unverified** from this checkout.
- **P3 source readiness:** FracFocus disclosure-header ingest captures terms evidence and
  hashes every archive member, promotes append-only hydraulic-fracturing job-end anchors,
  and never falls back to spud or first production. The resident load carries 18,665 valid
  events across 17,563 ND API-10s; all 43,817 current ND wells carry `basin=williston`, while
  the 26,254 wells without a source anchor remain null. All 40 current MPR pool labels have
  reviewed, knowledge-vintaged formation aliases.
- **Texas:** Permian-district GIS wells, wellbore identity, operators, and bore geometry
  are on the map, and the same EWA load populates `canonical.well_lease_links`, the
  append-only well-to-lease crosswalk SB-01 §2.9 makes Validator A; `link_role` records which
  crosswalk each row came from so no promotion can average two of them. 359,421 Texas wells
  are resident, of which 70,039 carry no operator name — 39,390 filed by `tx_wellbore_ewa_csv`
  with an empty operator field and 30,649 from `tx_gis_wells_county` with no EWA wellbore
  record at all. Neither is regulator withholding, and `cr_tx_operator_absence_1` is the row
  that says so; `cr_tx_ewa_measures_1` remains the only Texas withholding rule and covers
  `TOTAL_DEPTH` and `COMPLETION_DATE` only. Lease production is
  **not** a registered source: `tx_pdq_dsv` has a poll-cadence policy row
  (`050_durable_fetch_attempts.sql`, which carries no foreign key to `lineage.sources`) and a
  test fixture, and no seeded `lineage.sources` entry, no conformance rules and no ingest module.
  Allocation and the validators that would check it against the links are not built. Texas also
  carries no geometry-provenance rule of its own, so its `geometry_provenance` figure cites North
  Dakota's classing rule — a pre-existing residual, now stated rather than inherited silently.
- **New Mexico:** the header spine is built and the gate is not open. `ingest/nm_wells.py`
  promotes the OCD FTP header table into `canonical.wells` and a surface point into
  `canonical.well_spatial`, keyed by `cr_nm_wellhistory_api10_1`; the coordinate policy is a
  pair rule with a stated nil-before-zero precedence, because four records in 321,510 carry a
  good latitude and a longitude of exactly zero. `marts.nm_wells_tile` publishes the points and
  the serving path resolves New Mexico's own status vocabulary, geometry provenance, liquids
  basis and pool-grain rules rather than North Dakota's. **Distinguish the production database
  from the deployed host, and the built path from the run one.** The Tier 2 path merged at
  `7dfafc0` — two console scripts, [`docs/runbook-nm-tier2.md`](docs/runbook-nm-tier2.md), and
  an end-to-end test that promotes, reads a real API-10, rolls back to 404 and promotes again —
  but it has not run to completion. The first genuinely least-privileged `--stage-only` run
  against `glasswell` staged eight of the nine OCD tables and failed after 33 minutes on the
  ninth: `staging.stg_nm_ocd_wcproduction__partitions` is upserted and migration 028 granted the
  registry only select and insert. `068_partition_registry_update_grant.sql` is the fix. Step 3
  then failed on the real 321,510-record header artifact, because `_staged_frames` passed column
  names without dtypes and polars typed an all-null inference window as `Null`; `1ec4882` pins
  the declaration. **No `state_code = '30'` row exists in `canonical.wells`** — confirmed by the
  2026-08-31 read-only census, not assumed. `lineage.operator_aliases` holds zero rows on the
  deployed instance, and because `canonical.wells` is append-only and
  `operator_name_reported` is not among the attributes `_HEADER_DIVERGENCE` compares,
  promoting headers before those aliases exist would leave every New Mexico well permanently
  unattributed with no error and every reconciliation closing. That ordering is the live
  hazard, not a hypothetical. On the same host, a scratch database `glasswell_d1` holds a fully
  promoted 17,597,960-row NM production spine and 763,473 completion rows from the August build.
  The Tier 1 promotion that moves those into `glasswell` is owner-gated and documented in
  [`docs/runbook-nm-promotion.md`](docs/runbook-nm-promotion.md); New Mexico
  reports production at the well-completion-pool grain and glasswell rolls none of it up to the
  well, so an NM well's well-level series is absent rather than zero and says so.
- **Montana:** built, promoted and on the map. It is a Williston extension rather than a phase;
  ROADMAP's N3 owns its exit criteria. Montana arrived as 46 conformance rows before it arrived
  as data, because MBOGC publishes two grains and each states its own liquids basis, null
  semantics and grain uniqueness. Both grains reach canonical; the PRU lease grain carries a
  lease `entity_key` and **no api10**, which is why every state predicate over it is written on
  `source_id`. 40,626 Montana headers are resident in `canonical.wells`, against 42,026 points
  published to `marts.mt_wells_tile` — the 1,400 difference is the `unknown_status` rejects that
  `mt_gis` had been counting and dropping without a quarantine row, now quarantined under reason
  codes that already existed. 4,172 well paths publish off by default at the laterals' zoom,
  each carrying `geometry_class = map_stick` and `vertex_count` as tile properties so a client
  that reads no documentation cannot mistake a two-vertex stick for a directional survey.
  Montana serves **no basin** deliberately — it is 4.6% Bakken and tagging the state would
  corrupt the type-curve peer ladder (`cr_mt_basin_scope_1`) — and because it is the first state
  with lateral geometry and no basin, lateral length is withheld under
  `cr_mt_paths_length_scope_1` rather than served under North Dakota's rule. Production covers
  20,021 wells, not the 42,027 the feasibility claim assumed.
  `066_neighbors_multistate.sql` parameterises the neighbour mart's state scope: ND wells within
  five miles of the Montana border went from a mean of 142.36 neighbours to 174.79, +22.8% over
  586 wells and +19,006 edges, and the mart is byte-identical beyond five miles. Loading is
  documented in [`docs/runbook-mt-load.md`](docs/runbook-mt-load.md). Montana's resident
  production row counts are **unverified** here; the runbook's expected staged figures are
  5,809,608 at the well grain and 1,603,216 at the lease grain, within ±2%.
- **Serving surface:** the frozen snapshot contains 49 operations, 48 under `/v1`, covering
  health, operational status, wells and their facets, ND production, source-observed completion
  context, current ND physical neighbours, canonical formations with alias counts, lineage,
  manifests, derivations, vintages, conformance, quarantine, glossary, error codes, keys,
  sessions, accounts, and tiles. Every well also carries a producing
  class, and `/v1/wells?producing=` scopes the collection to one, defined by
  `cr_producing_window_1`, `cr_producing_streams_1` and `cr_producing_evidence_1` rather than
  by a predicate in the serving path. `/v1/wells` also gained an exact-match `state` parameter,
  additively and inside the cursor fingerprint, so a cursor minted before it is refused.
  Forecast, valuation, scenario, agent, and inventory
  operations are not served. The pinned `tcv1.0` type-curve control now is:
  `/v1/modeling/publications` and its detail serve the accepted P3 receipt with its acceptance
  gates and its peer-ladder support distribution; `/v1/wells/{api10}/type-curve` serves one
  held-out test subject's P10/P50/P90 monthly and cumulative curves under both normalisation
  arms, with `control_unavailable` served as a stated outcome on a required field rather than
  as an absent figure; and `/v1/type-curves` browses the control population by rung. Every
  figure carries a handle that resolves to the pinned `typecurve.build` derivation and the
  split set it was built on, and the resolver refuses to read any artifact an accepted
  publication does not name. Training, calibration, the model registry, the analog index and
  benchmark scoring remain built but unserved.
- **Counted buckets:** `/v1/wells/facets` serves wells by one of five dimensions — operator,
  county, status, well type and completion year — over a **required** single state, which is an
  R8 constraint rather than a UX one: operator names arrive per source and
  `lineage.operator_aliases` is empty, so a cross-state sum would be an unmade aliasing
  decision. Each response states what its count leaves out three ways. An absence bucket named
  `not reported` carries the count, the reason and the rule that decided it, and is never
  ranked and never narrowed by the search — on the Texas load it would outrank all 9,369 real
  operator values. A remainder states how many values fell below the cut and how many wells they
  hold, and is absent rather than zero when the list is complete. The scope is named in the
  caption. `sum(buckets) + remainder + absence == wells` without a search and
  `sum(buckets) + remainder == matched_wells` under one, both asserted. ND carries exactly two
  vintage rows per API-10, so the dedup is the same `row_number()` rank `/v1/wells` uses; without
  it every North Dakota operator would have read at exactly 2×. `070_well_facets.sql` adds
  `wells_facet_dimensions_idx`, whose INCLUDE list is the five dimensions plus `derivation_id` —
  the last is not optional, because leaving it out demotes the plan to a heap visit per row.
  There is no `marts.well_facets`; the counts are computed per request.
- **Frontend:** URL-backed Map, Explore, and Status surfaces; a well
  card with independent completion-event, pool-to-formation and current physical-neighbour
  sections, production chart, lineage drawer, glossary, explorer, satellite/hybrid modes, and
  searchable layer panel ship. The neighbour card explicitly separates proximity from analogs.
  The production chart is built for the 131 months on record: it discloses the window it draws,
  reads the month under the pointer out as DOM with its own handle, and bins nothing. The map
  legend carries per-class producing counts with their own handles and the window beneath them,
  and the explorer draws the crossed-to series from the response the grid already fetched. The
  layer panel holds 15 rows in four groups — Well spine, Land and legal framework, Derived
  surfaces, Geology framework. Four state well layers (`wells`, `tx-wells`, `nm-wells`,
  `mt-wells`) nest under one tri-state `Wells` parent that is derived at render time, owns no
  layer id, declares no style layer and is never persisted; `mt-paths`, `survey-traces`,
  `lateral-bores` and `disposal-wells` stay siblings because the family divides by state and
  those divide by something else. `WELL_POINT_LAYERS` now names all four, so the legend's
  showing-N-of-M census no longer understates a canvas by every New Mexico well on it.
  Montana and New Mexico draw nothing today and say `none here` beside a live switch rather
  than vanishing. The Status surface was reworked to report what the deployment **is, runs and
  holds** — a deployment block, an architecture section grouped by tier naming the systemd unit
  or mount each component was observed through, per-timer armed state reported separately from
  last-run outcome, a `lineage.conformance_rules` inventory, open quarantine per reason code,
  distinct months per state, and a `staging_inventory` disclosure that states staging is
  uncounted. Visible standing prose fell from 276 words to 77; the method statements moved into
  collapsed disclosures rather than being deleted. The explorer gained a "Wells by …" panel
  under a `wb.` URL prefix whose bucket clicks write ordinary `f.<param>` filters.
- **Not on the map:** `basins` and `plays` are registered tile layers over `marts.tile_basins`
  and `marts.tile_plays`, and neither has a row in the layer registry. `marts.basin_boundaries_tile`
  is empty on the deployed host, so both answer 204; the load is documented in
  [`docs/runbook-basin-load.md`](docs/runbook-basin-load.md) and has not been run. The two rows
  the Geology framework group does carry — `play-outline` and `geology-au` — are
  `pendingSource` placeholders that declare no style layer, name EIA and USGS as un-ingested,
  and draw nothing by construction.

## Phase ledger

Montana is deliberately absent from this table: ROADMAP treats it as a Williston extension
rather than a phase, and its exit criteria are N3's.

| Phase | Status | Remaining boundary |
|-------|--------|--------------------|
| **P0** Scaffold and contracts | Met | `/v1/audit` is not served, but is not a P0 exit requirement |
| **P1** ND spine | Met with named deferrals | PDF-era production and FracFocus chemistry remain absent; the disclosure-header anchor path is built |
| **P2** Serving and map | Substantially met | Completion context, promoted completion design, formations and current ND physical neighbours are served and visible on eligible well cards without treating proximity as an analog. Per-well cumulative oil, gas and water are served at `/v1/wells/{api10}/cumulatives` from `marts.well_cumulatives`, each figure carrying the mart snapshot vintage and the month counts that reconcile to its span, so a filed zero, an absent report and a withheld month stay three distinct served facts. Vintage cohorts are served at `/v1/wells/vintage-cohorts`, keyed on the spud year under `cr_nd_vintage_cohort_1`, with the no-spud-date cohort explicit. FracFocus base water volume is promoted to `canonical.well_completion_design` under `cr_ff_base_water_units_1` and `cr_ff_design_promote_1`, so `design_availability` reads `promoted` and fluid intensity per lateral foot is served under `cr_ff_fluid_intensity_1`, null with a named reason wherever the divisor or the disclosure is missing. Neighbours use current lateral geometry, strict earlier-completion cutoffs and exact query lineage; retrospective geometry remains explicitly unavailable. The mart was rebuilt on this deploy to 7,958,550 edge rows over 22,263 subject rows at `snapshot_vintage` 2026-08-29, under derivation `drv_ft3xiv7yoyt7baopmnqq`, and `066_neighbors_multistate.sql` has since parameterised its state scope so the ND–Montana border is no longer a truncation. Land and spacing units are built and served as tiles, not as JSON: `land_townships`, `land_sections`, their two metric layers and `nd_spacing_units` are published tile layers over `marts.land_units_tile`, `marts.land_metrics_tile` and `marts.nd_spacing_units_tile`, and each is reachable from the map layer panel; SB-04 §4.7's `/v1/spacingunits` is class B and is not served. Permits, GOR and water-cut remain |
| **P3** Forecasting and benchmark | Pinned control gate accepted; modeling remains | Immutable `fv1.0`, semantic-major `fv2.0`, `mdv1.4`, and control-major `tcv1.0` remain separate identities. The accepted 2026-08-28 publication `p3pub_8b434525d8c621762e31b06ca660bfcd` pins `v0.59+b0be225`, environment `env_59334df47ed960e6`, and split set `sset_c7bbb9a6932db76b`; two complete builds reproduced all eight artifacts and all eight split files byte-identically. Unavailability is 230 / 21,300 (1.0798%), below the 5% ceiling, with 222 missing-lateral and eight insufficient-peer mentions and no TEST missing-formation mention. Matrix-wide coverage is 17,075 resolved, 486 missing and two conflicts across 17,563 subjects. Models, calibration, the model-registry writer, analog index, benchmark scoring and harness remain; the content-addressed benchmark artifact contract is built but has no caller outside its own unit test |
| **P4** Dollars and scenarios | Not started | Entire phase |
| **P5** Intelligence, agents and alerts | Not started | Entire phase |
| **P6** Hardening and glass-box proof | Partial | The deployed instance persists source-poll outcomes independently, registers 26 source-specific cadence policies (22 from `050`, four Montana sources from `064`), validates all current selector-bearing figures against nine fail-closed output contracts, separates conformance publication and valid time, caps viewport provenance writes per principal, and runs sandboxed nightly lineage retention. The v0.62 deployment applied schema 53 and 54, which register publication evidence for `cr_tx_ewa_measures_1` and the three superseding API-10 identity rules, found the lineage-retention timer enabled, active and last-result clean, and serves a bundle stamped 0.62 with a changelog page naming it. Host checks read 109 passed / 18 failed immediately after that deploy, every failure in the Postgres tuning block, and 127 passed / 0 failed once the shipped drop-in was applied; 20 API smoke checks passed. All 22 settings in that drop-in are now live: `shared_buffers` 2GB→4GB, `effective_cache_size` 6GB→12GB, `work_mem` 32MB→64MB, `max_connections` 60→80, `autovacuum_work_mem` -1→256MB, `max_wal_size` 1GB→4GB. The 4 GiB `/swapfile` SB-06 §2.3 asked for and provisioning never created now exists, with one `/etc/fstab` entry, on a host that reported `Swap: 0`. The guest reports 12,179 MB resident rather than the 16 GiB ceiling the drop-in was sized against, so `shared_buffers` is about a third of resident memory rather than the intended quarter. Fetch-attempt history begins at the v0.61 deployment that created the table. The latest recurring restore proof still covers the 1,493,244,558-byte schema-47 dump: it matched 197 manifests, 403,238 latest wells, 7,223,544 production rows and 43,817 ND tile rows, passed six reads, removed scratch state and persisted a `root:glasswell` `0640` receipt — a proof now three states and eleven schema versions behind the tree. A restore at the current head, remote-copy evidence, full VM/raw-zone recovery, tunnel/Access, outsider guest exercise, broader API rate policy, determinism and tool-equivalence gates remain |
| **P7** Permian | Started, unpromoted/incomplete | New Mexico's Tier 2 path is built and merged but has not run to completion: the staging grant and the staged-frame dtype defects it surfaced are both fixed and neither fix is deployed, and no NM row is canonical. Tier 1 production promotion stays owner-gated. TX lease-production ingest, allocation, and the validators over allocated production remain — the Validator A well-to-lease crosswalk they would be checked against is already built |
| **P8** Living systems | Not started | Entire phase |

## Public access — live as of 2026-08-31

The deployment is reachable at **`https://glasswell.rpx.sh`** through a Cloudflare Tunnel, and
is **closed by default**: `/healthz`, the SPA shell and assets, `/basemap/*` and the two login
routes answer anonymously; every other operation refuses before any database work. `/healthz`
and the SPA shell were re-probed through the edge during this reconciliation and answer 200.
Measured through the edge at cutover: `/healthz`, `/` and `/v1/session` return 200 while
`/v1/wells/{api10}`, `/v1/conformance` and `/docs` return 403, with
`strict-transport-security: max-age=31536000; includeSubDomains` emitted at the edge.

Authentication is the application's own session login with two roles, `owner` and `viewer`.
**Cloudflare Access is not used** and is not enabled on the account — the app's login is the
authorization layer, and Access would have been a second, redundant one. `SB-06` §5 and
`SB-04` carry the amendment; the blueprints previously said glasswell never grows a user
table, and that contract was changed deliberately rather than worked around.

The API-key path is retained but demoted: the static owner key is refused at the tunnel edge,
so it is a LAN and deploy-gate credential only, and `/v1/keys*` plus the `agent` scope are
marked `deprecated: true` in the served document with removal stated for the next major.

Rollback is three independent levels, all exercised or trivially available: delete the proxied
CNAME (seconds), `systemctl stop cloudflared` (host-side, no dashboard), or revert and redeploy.
The tunnel is `3b2d209f-7671-4497-ae4f-740dcbc34788`; connector credentials are host state at
`/etc/cloudflared/` and are not in this repository.

## Immediate gaps

1. Implement the three-stream quantile-model writer, split-conformal calibration and model
   registry contract against the accepted `fv2.0` / `mdv1.4` split set; publish per-slice
   empirical coverage rather than serving a candidate early. **Note `fv2.0` is a one-feature
   set** — `features.feature_specs` holds two rows, both `geology.formation_group`, with five
   of six declared families empty; expanding it moves `feature_set_hash` and cascades the
   publication identity.
2. Build the persisted analog index and benchmark runner, enforce the identical split against
   accepted `tcv1.0`, and measure the control bracket and determinism gates end to end.
   `ANALOG_IQR_RATIO_MAX` is unset in SB-02 and is not executable as written.
3. Re-run NM Tier 2. The deploy blocker is cleared — the host has carried `068`, `069` and
   `070` since 2026-08-31 21:41Z, so the ninth OCD staging table is now writable and the two
   failures that stopped the last two attempts are fixed on the host rather than only in the
   repository. What remains is the run itself. Write `lineage.operator_aliases` before any
   header promotion, or accept the permanent absence in writing — `canonical.wells` is
   append-only and there is no after.
4. Run the boundary load, or drop the two pending Geology rows. `basins` and `plays` are
   published tile layers with an empty mart behind them and no layer-panel row in front of
   them, and the panel's two geology rows draw nothing by construction. The surface currently
   promises geology in three places and delivers it in none.
5. Exercise a credential from a genuinely off-LAN vantage. The tunnel is live and the edge
   enforces the ruled scopes, but every probe so far originated on this network, so public
   *reachability* is proven and a foreign source address is not.
6. Prove remote-copy recency and full replacement-VM/raw-zone recovery, and take a restore proof
   at a current schema. The last recurring proof is schema 47 against a 403,238-well database;
   the tree is at 070 and the deployed database holds 809,191 well rows across four states.
   The offsite push is instrumented but its far side is `rrsync -wo`, so byte-level read-back
   is impossible and the recovery drill is mechanised but has **never been executed**.
7. Resolve the owner-gated v0.6 §11 capability-matrix/IP review separately from the already
   public source repository.
8. Route two residuals that two tracks each declined. Facet member ordering inside the `Wells`
   family is draw order, which is ingest order, and will read as broken at eight states; and
   the collector's `canonical.well_completions` arm still uses the `left(api10, 2)` filtered
   aggregate that `069` removed from the production arm.
9. Merge the N2 re-land. `feat/n2-reland` carries the N2 schema, the cumulative marts,
   vintage cohorts, the FracFocus base-fluid-intensity promotion and
   `/v1/wells/{api10}/cumulatives`, cherry-picked from `feat/n2-enrich-views` onto current
   main with the migration renumbered `055_n2_enrich_views.sql` to
   `071_n2_enrich_views.sql`. `PLAN-HORIZON.md` records track T2 as shipped in v0.67; v0.67
   shipped a tunnel-assertion fix, and nothing on main imports the N2 surface. Merge the
   re-land rather than the stale branch, and correct the plan's release column in the same
   train.

## Verification state

- The full locked Python suite passes **4,191 tests with 55 skips**, including the
  Docker-backed integration and contract tiers; Ruff passes. That run predates the two fix
  merges at `a45e559` and `55a6ad9`, which add tests rather than change behaviour.
- The web suite passes **1,439 tests across 92 files**; typecheck passes. Both were run
  against this checkout during this reconciliation.
- The browser gates last read **45 Map assertions** (`tests/e2e/chrome-fold.mjs`), **124 Status
  assertions** (`tests/e2e/status-surface.mjs`) and **30 hidden-display assertions**, all zero
  failed, plus **16** browserless `e2e-guards`. The Status count grew from 88 to 124 with the
  Status rework. These figures come from the facets and layers tracks' own runs against their
  built bundles, and have **not** been re-run against merged `main`.
- The dependency lock matches the installed environment and the generated OpenAPI snapshot
  reports current. `openapi_diff` across the session's releases reports **additive changes
  only** — the `/v1` freeze holds.
- **The pull-request pattern stopped after #41** (merged 2026-08-30). Every merge since has
  gone straight to `main`, so the six hosted CI jobs — `python`, `web`, `e2e-guards`, `shell`,
  `collateral`, `map-chrome` — now run after the fact rather than before it. The last pushed
  commit, `1ec4882`, is **red**: its Python job failed on the login-ordering test racing the
  limiter's minute boundary, which `2d2027a` fixes one commit later and which has not been
  pushed. The 25 unpushed commits above it have **no hosted CI verdict at all**.
- **The deployed code version is unverified.** This ledger previously carried two contradictory
  values in one file — `v0.62+204bebb` and `v0.67` — and neither can be confirmed from this
  checkout; `/v1/status` reports it but requires a session. The deployed schema head was
  reported at **067** by a read-only probe on 2026-08-31 and is not re-confirmed here; on that
  reading the host lags the repository by three migrations.
- **`infra/verify.sh` and `scripts/smoke.sh` have not been run since the v0.67 deploy**, and no
  track this session ran either. The last recorded figures are 172 host checks and 24 API smoke
  checks, both exit 0, and they describe a host three states of data and eleven schema versions
  behind the tree. Treat them as historical, not current.
- Measured against the deployed database after the v0.71 deploy, read-only: `canonical.wells`
  holds **809,191 rows** over **585,864 distinct API-10s** — Texas 359,421, New Mexico 321,510,
  North Dakota 87,634 vintage rows, Montana 40,626, with 321,234 New Mexico rows in
  `canonical.well_spatial`. North Dakota carries no well with an absent operator and 1,590
  distinct operators. An earlier figure of 487,681 over 443,864 circulated in this file and
  called New Mexico zero: it was the correct total for the three states resident *before* the
  New Mexico promotion, quoted rather than measured, and 809,191 - 321,510 = 487,681 is how it
  survived review. Derive this line from the database or mark it unverified; do not carry it
  forward.
- **v0.66 refused its own deploy** at `verify.sh` (170 passed, 2 failed) and the refusal was
  correct both times: no owner account existed, and an assertion added by that release
  demanded a tunnel listener exist on a host that has none, reporting "8080 is bound
  off-loopback" about a host with nothing bound to 8080. v0.67 fixed the assertion
  conditionally and the count rose to 172 — the repair *added* checks rather than deleting
  the failing one.
- **The four edge probes in `verify.sh` reported `000` after the cutover, and the cause is
  lab DNS rather than the tunnel.** VM 111's resolver returns NXDOMAIN for `glasswell.rpx.sh`
  while `1.1.1.1` and `8.8.8.8` both return the Cloudflare edge addresses, so `curl` on the
  host cannot reach the public hostname at all. Measured off-host against the edge, the same
  surface answers correctly: `/healthz`, `/` and `/v1/session` 200; `/v1/wells/{api10}`,
  `/v1/conformance` and `/docs` 403; HSTS present. Public reachability and edge enforcement
  are therefore proven; the host-run assertions are blocked on split-horizon resolution.
  Either give the host a resolver that sees the public record, or have those four probes pin
  the edge address explicitly. Whether the split horizon has since been repaired is unverified.
- **Scale figures are not production figures.** The status-collector rewrite's 17.4× result —
  60,571 ms to 3,474 ms over 29,580,309 rows, whole-table sort and 1.88 GB of temp spill
  replaced by three index-only scans with zero heap fetches — was measured on a purpose-built
  local container with synthetic rows, at 2 GB `shared_buffers` against the host's 4 GB. The
  before/after ratio and the query plans are the argument; the absolute times are not
  comparable to the deployed host, and the thirty-state projection is a projection. The
  continuity check that would confirm the old and new jurisdiction definitions agree on the
  resident ND load **could not be run** — the deployed database is not reachable from the
  workstation on 5432 — so series continuity across `cr_nd_inventory_jurisdiction_1` and its
  three siblings is **unverified**.
