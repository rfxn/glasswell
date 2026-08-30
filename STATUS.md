# Current status

Reconciled on **2026-08-30** against the v0.69 release line, the checked-in OpenAPI
snapshot, current `main` history, and deployed `v0.62+204bebb` at schema head 54. This is the
short current-state ledger;
[`ROADMAP.md`](ROADMAP.md) owns phase scope and exit criteria, while
[`blueprint.md`](blueprint.md) remains the committed v0.5 contract and
[`blueprint-v0.6-draft.md`](blueprint-v0.6-draft.md) is the rc5 amendment set.

## Shipped baseline

- **Release line:** 50 tagged releases, v0.20 through v0.69, cut 2026-08-21 through
  2026-08-30.
- **North Dakota:** ingest, bitemporal promotion, quarantine, conformance, wells,
  geometry, monthly production, lineage, explain, glossary, API, tiles, and map are built.
- **Production history:** the 125-workbook back-load is complete. Canonical holds 131
  distinct months from 2015-05-01 and 7,223,544 rows; the P3 entry gate is met.
- **P3 source readiness:** FracFocus disclosure-header ingest captures terms evidence and
  hashes every archive member, promotes append-only hydraulic-fracturing job-end anchors,
  and never falls back to spud or first production. The resident load carries 18,665 valid
  events across 17,563 ND API-10s; all 43,817 current ND wells carry `basin=williston`, while
  the 26,254 wells without a source anchor remain null. All 40 current MPR pool labels have
  reviewed, knowledge-vintaged formation aliases.
- **Texas:** Permian-district GIS wells, wellbore identity, operators, and bore geometry
  are on the map, and the same EWA load populates `canonical.well_lease_links`, the
  append-only well-to-lease crosswalk SB-01 §2.9 makes Validator A; `link_role` records which
  crosswalk each row came from so no promotion can average two of them. Lease production is
  **not** a registered source: `tx_pdq_dsv` has a poll-cadence policy row
  (`050_durable_fetch_attempts.sql`, which carries no foreign key to `lineage.sources`) and a
  test fixture, and no seeded `lineage.sources` entry, no conformance rules and no ingest module.
  Allocation and the validators that would check it against the links are not built. Texas also
  carries no geometry-provenance rule of its own, so its `geometry_provenance` figure cites North
  Dakota's classing rule — a pre-existing residual, now stated rather than inherited silently.
- **New Mexico:** the header spine is built. `ingest/nm_wells.py` promotes the OCD FTP header
  table into `canonical.wells` and a surface point into `canonical.well_spatial`, keyed by
  `cr_nm_wellhistory_api10_1`; the coordinate policy is a pair rule with a stated nil-before-zero
  precedence, because four records in 321,510 carry a good latitude and a longitude of exactly
  zero. `marts.nm_wells_tile` publishes the points and the serving path resolves New Mexico's own
  status vocabulary, geometry provenance, liquids basis and pool-grain rules rather than North
  Dakota's. **Distinguish the production database from the deployed host.** In `glasswell`, the
  nine OCD staging tables are unpopulated and no canonical NM row is resident; what *is* resident
  is `staging.nm_c115b_upstream` at 71,447 rows, 10 NM sources and 79 NM conformance rules. On the
  same host, a scratch database `glasswell_d1` holds a fully promoted 17,597,960-row NM production
  spine and 763,473 completion rows from the August build. The Tier 1 promotion that moves those
  into `glasswell` is owner-gated and documented in `docs/runbook-nm-promotion.md`; New Mexico
  reports production at the well-completion-pool grain and glasswell rolls none of it up to the
  well, so an NM well's well-level series is absent rather than zero and says so.
- **Serving surface:** the frozen snapshot contains 34 operations, 33 under `/v1`, covering
  health, operational status, wells, ND production, source-observed completion context,
  current ND physical neighbours, canonical formations with alias counts, lineage, manifests,
  conformance, quarantine, glossary, keys, and tiles. Every well also carries a producing
  class, and `/v1/wells?producing=` scopes the collection to one, defined by
  `cr_producing_window_1`, `cr_producing_streams_1` and `cr_producing_evidence_1` rather than
  by a predicate in the serving path. Forecast, valuation, scenario, agent, and inventory
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
- **Frontend:** URL-backed Map, Explore, and Status surfaces; MapLibre ND/TX layers; a well
  card with independent completion-event, pool-to-formation and current physical-neighbour
  sections, production chart, lineage drawer, glossary, explorer, satellite/hybrid modes, and
  searchable layer panel ship. The neighbour card explicitly separates proximity from analogs.
  The production chart is built for the 131 months on record: it discloses the window it draws,
  reads the month under the pointer out as DOM with its own handle, and bins nothing. The map
  legend carries per-class producing counts with their own handles and the window beneath them,
  and the explorer draws the crossed-to series from the response the grid already fetched.

## Phase ledger

| Phase | Status | Remaining boundary |
|-------|--------|--------------------|
| **P0** Scaffold and contracts | Met | `/v1/audit` is not served, but is not a P0 exit requirement |
| **P1** ND spine | Met with named deferrals | PDF-era production and FracFocus chemistry remain absent; the disclosure-header anchor path is built |
| **P2** Serving and map | Substantially met | Completion context, formations and current ND physical neighbours are served and visible on eligible well cards without promoting staging-only design measurements or treating proximity as an analog. Neighbours use current lateral geometry, strict earlier-completion cutoffs and exact query lineage; retrospective geometry remains explicitly unavailable. The mart was rebuilt on this deploy to 7,958,550 edge rows over 22,263 subject rows at `snapshot_vintage` 2026-08-29, under derivation `drv_ft3xiv7yoyt7baopmnqq`. Land and spacing units are built and served as tiles, not as JSON: `land_townships`, `land_sections`, their two metric layers and `nd_spacing_units` are published tile layers over `marts.land_units_tile`, `marts.land_metrics_tile` and `marts.nd_spacing_units_tile`, and each is reachable from the map layer panel; SB-04 §4.7's `/v1/spacingunits` is class B and is not served. Permits, GOR and water-cut remain |
| **P3** Forecasting and benchmark | Pinned control gate accepted; modeling remains | Immutable `fv1.0`, semantic-major `fv2.0`, `mdv1.4`, and control-major `tcv1.0` remain separate identities. The accepted 2026-08-28 publication `p3pub_8b434525d8c621762e31b06ca660bfcd` pins `v0.59+b0be225`, environment `env_59334df47ed960e6`, and split set `sset_c7bbb9a6932db76b`; two complete builds reproduced all eight artifacts and all eight split files byte-identically. Unavailability is 230 / 21,300 (1.0798%), below the 5% ceiling, with 222 missing-lateral and eight insufficient-peer mentions and no TEST missing-formation mention. Matrix-wide coverage is 17,075 resolved, 486 missing and two conflicts across 17,563 subjects. Models, calibration, the model-registry writer, analog index, benchmark scoring and harness remain; the content-addressed benchmark artifact contract is built but has no caller outside its own unit test |
| **P4** Dollars and scenarios | Not started | Entire phase |
| **P5** Intelligence, agents and alerts | Not started | Entire phase |
| **P6** Hardening and glass-box proof | Partial | The deployed instance persists source-poll outcomes independently, registers 22 source-specific cadence policies, validates all current selector-bearing figures against nine fail-closed output contracts, separates conformance publication and valid time, caps viewport provenance writes per principal, and runs sandboxed nightly lineage retention. The v0.62 deployment applied schema 53 and 54, which register publication evidence for `cr_tx_ewa_measures_1` and the three superseding API-10 identity rules, found the lineage-retention timer enabled, active and last-result clean, and serves a bundle stamped 0.62 with a changelog page naming it. Host checks read 109 passed / 18 failed immediately after the deploy, every failure in the Postgres tuning block, and 127 passed / 0 failed once the shipped drop-in was applied; 20 API smoke checks pass. All 22 settings in that drop-in are now live: `shared_buffers` 2GB→4GB, `effective_cache_size` 6GB→12GB, `work_mem` 32MB→64MB, `max_connections` 60→80, `autovacuum_work_mem` -1→256MB, `max_wal_size` 1GB→4GB. The 4 GiB `/swapfile` SB-06 §2.3 asked for and provisioning never created now exists, with one `/etc/fstab` entry, on a host that reported `Swap: 0`. The guest reports 12,179 MB resident rather than the 16 GiB ceiling the drop-in was sized against, so `shared_buffers` is about a third of resident memory rather than the intended quarter. Fetch-attempt history begins at the v0.61 deployment that created the table and remains empty until a source next polls. The latest recurring restore proof still covers the 1,493,244,558-byte schema-47 dump: it matched 197 manifests, 403,238 latest wells, 7,223,544 production rows and 43,817 ND tile rows, passed six reads, removed scratch state and persisted a `root:glasswell` `0640` receipt. A schema-54 restore, remote-copy evidence, full VM/raw-zone recovery, tunnel/Access, outsider guest exercise, broader API rate policy, determinism and tool-equivalence gates remain |
| **P7** Permian | Started, unpromoted/incomplete | NM promotion and deployment; TX lease-production ingest, allocation, and the validators over allocated production — the Validator A well-to-lease crosswalk it would be checked against is already built |
| **P8** Living systems | Not started | Entire phase |

## Public access — live as of 2026-08-30

The deployment is reachable at **`https://glasswell.rpx.sh`** through a Cloudflare Tunnel, and
is **closed by default**: `/healthz`, the SPA shell and assets, `/basemap/*` and the two login
routes answer anonymously; every other operation refuses before any database work. Measured
through the edge at cutover: `/healthz`, `/` and `/v1/session` return 200 while
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
3. Promote New Mexico. The spine work is **built and reviewed** on `feat/n3-nm-gate` but not
   merged; the production promotion is deliberately deferred to a supervised ops window,
   because `glasswell-status.timer` runs every fifteen minutes and would publish NM rows
   labelled "North Dakota" into an append-only table before a fix could land.
4. Exercise a credential from a genuinely off-LAN vantage. The tunnel is live and the edge
   enforces the ruled scopes, but every probe so far originated on this network, so public
   *reachability* is proven and a foreign source address is not.
5. Prove remote-copy recency and full replacement-VM/raw-zone recovery. The schema-54 restore
   drill **passed** (receipt `schema_match: true`, 197 manifests, 7,223,544 production rows);
   the offsite push is instrumented but its far side is `rrsync -wo`, so byte-level read-back
   is impossible and the recovery drill is mechanised but has **never been executed**.
6. Resolve the owner-gated v0.6 §11 capability-matrix/IP review separately from the already
   public source repository.

## Verification state

- The full locked Python suite passes **3,484 tests with 56 skips**, including the
  Docker-backed integration and contract tiers; Ruff passes.
- The web suite passes **1,325 tests across 88 files**; typecheck and production build pass.
- Browserless E2E guards, shell checks, collateral checks, changelog lint and the
  headless-Chromium gates pass: **35 Map assertions and 88 Status assertions**.
- The dependency lock matches the installed environment and the generated OpenAPI snapshot
  reports current. `openapi_diff` across the session's releases reports **additive changes
  only** — the `/v1` freeze holds.
- Every release from v0.64 to v0.67 passed all six hosted CI jobs before merge. The deployed
  **`v0.67`** instance at schema head 55 passes **172 host checks and 24 API smoke checks**,
  both exit 0.
- **v0.66 refused its own deploy** at `verify.sh` (170 passed, 2 failed) and the refusal was
  correct both times: no owner account existed, and an assertion added by that release
  demanded a tunnel listener exist on a host that has none, reporting "8080 is bound
  off-loopback" about a host with nothing bound to 8080. v0.67 fixed the assertion
  conditionally and the count rose to 172 — the repair *added* checks rather than deleting
  the failing one.
- **The four edge probes in `verify.sh` still report `000` after the cutover, and the cause is
  lab DNS rather than the tunnel.** VM 111's resolver returns NXDOMAIN for `glasswell.rpx.sh`
  while `1.1.1.1` and `8.8.8.8` both return the Cloudflare edge addresses, so `curl` on the
  host cannot reach the public hostname at all. Measured off-host against the edge, the same
  surface answers correctly: `/healthz`, `/` and `/v1/session` 200; `/v1/wells/{api10}`,
  `/v1/conformance` and `/docs` 403; HSTS present. Public reachability and edge enforcement
  are therefore proven; the host-run assertions are blocked on split-horizon resolution.
  Either give the host a resolver that sees the public record, or have those four probes pin
  the edge address explicitly. Until then `verify.sh` reads **174 passed, 4 failed** and the
  failures are known and benign.
