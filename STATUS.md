# Current status

Reconciled on **2026-08-30** against the v0.66 release line, the checked-in OpenAPI
snapshot, current `main` history, and deployed `v0.62+204bebb` at schema head 54. This is the
short current-state ledger;
[`ROADMAP.md`](ROADMAP.md) owns phase scope and exit criteria, while
[`blueprint.md`](blueprint.md) remains the committed v0.5 contract and
[`blueprint-v0.6-draft.md`](blueprint-v0.6-draft.md) is the rc5 amendment set.

## Shipped baseline

- **Release line:** 47 tagged releases, v0.20 through v0.66, cut 2026-08-21 through
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
  registered as a source (`tx_pdq_dsv`, owner-triggered) with no ingest module, and allocation
  and the validators that would check it against the links are not built.
- **New Mexico:** ingest and promotion code exist and the OCD staging schema is created, but
  promotion remains deployment- and owner-gated, so those tables are unpopulated on the
  deployed instance; no resident NM production is claimed here.
- **Serving surface:** the frozen snapshot contains 34 operations, 33 under `/v1`, covering
  health, operational status, wells, ND production, source-observed completion context,
  current ND physical neighbours, canonical formations with alias counts, lineage, manifests,
  conformance, quarantine, glossary, keys, and tiles. Every well also carries a producing
  class, and `/v1/wells?producing=` scopes the collection to one, defined by
  `cr_producing_window_1`, `cr_producing_streams_1` and `cr_producing_evidence_1` rather than
  by a predicate in the serving path. Forecast, valuation, scenario, agent, and inventory
  operations are not served. Not served is not the same as not built: `src/glasswell/modeling/`
  is 5,211 lines that compute type curves, splits, feature matrices and model-ready datasets
  under the pinned `tcv1.0`, `fv2.0` and `mdv1.4` identities and an accepted publication, and
  no router imports it — `grep -rn "from glasswell.modeling" src/glasswell/api/` returns
  nothing.
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

## Immediate gaps

1. Implement the three-stream quantile-model writer, split-conformal calibration and model
   registry contract against the accepted `fv2.0` / `mdv1.4` split set; publish per-slice
   empirical coverage rather than serving a candidate early.
2. Build the persisted analog index and benchmark runner, enforce the identical split against
   accepted `tcv1.0`, and measure the control bracket and determinism gates end to end.
3. Promote New Mexico before implementing Texas lease allocation so the well-level
   Permian spine can act as the intended control.
4. Put the deployed app behind the ruled tunnel/Access scopes and exercise a non-interactive
   guest credential from outside the lab; public source visibility is not deployment access.
5. Let the next schema-54 backup pass the recurring restore drill, then prove remote-copy
   recency and full replacement-VM/raw-zone recovery separately from that same-cluster proof.
6. Resolve the owner-gated v0.6 §11 capability-matrix/IP review separately from the already
   public source repository.

## Verification state

- The full locked Python suite passes **2,916 tests with 1 explicit skip**, including the
  Docker-backed integration and contract tiers; Ruff passes.
- The web suite passes **1,290 tests across 86 files**; typecheck and production build pass.
- Browserless E2E guards, shell checks, collateral checks, changelog lint, and the
  headless-Chromium gates pass locally: 35 Map assertions and 88 Status assertions.
- The dependency lock exactly matches the installed environment and the generated OpenAPI
  snapshot reports current.
- Exact release SHA `204bebb` passed all six hosted CI jobs. The deployed `v0.62+204bebb`
  instance at schema head 54 passes 127 host checks and 20 API smoke checks, and serves the
  bundle this release built: the stamp reads version `0.62`, hash `204bebb`, date
  `2026-08-29`.
