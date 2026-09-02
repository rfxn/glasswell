# Current status

Reconciled on **2026-09-01** against the v0.75 release line, the checked-in OpenAPI
snapshot, current `main` history and a read-only census of the deployed database. Every
figure below is dated and names its source; three are carried forward from the previous
revision and say so on the line. [`ROADMAP.md`](ROADMAP.md) owns phase scope and exit criteria;
[`blueprint.md`](blueprint.md) is the committed v0.5 contract and
[`blueprint-v0.6-draft.md`](blueprint-v0.6-draft.md) the rc5 amendment set.

## Deployed

- **Release line:** 56 tagged releases, v0.20 through v0.75, cut 2026-08-21 through
  2026-09-01.

Measured on the deployed database (VM 111) and host, read-only, 2026-09-01.

| Item | Value | Source of the measurement |
|---|---|---|
| Code version | `v0.73+9796501` | `/etc/glasswell/code-version.env` |
| Schema head | `070` | `select max(version) from public.schema_migrations` |
| `canonical.wells` | 809,191 rows over 585,864 distinct API-10 | `select state_code, count(*), count(status_canonical) … group by 1` |
| `canonical.production_monthly` | 47,178,269 rows over four sources | `select source_id, count(*) … group by 1` |
| `canonical.well_spatial` | 1,041,407 rows | `select … count(*) … group by substr(api10,1,2)` |
| `marts.basin_boundaries_tile` | 48 rows | `select count(*) from marts.basin_boundaries_tile` |
| `main` | `39bd7f0`, level with `origin/main`; 54 version tags | `git rev-parse main origin/main`; `git tag \| grep -c '^v'` |

## Shipped baseline per state

All four states are resident. Rows and distinct API-10 differ where a state carries
bitemporal vintages; geometry is distinct API-10 per `geom_type`.

| State | Wells (rows / API-10) | Production rows | Geometry | `status_canonical` | Withheld, and the rule |
|---|---|---|---|---|---|
| **ND** 33 | 87,634 / 43,817 | 7,223,544 · `nd_mpr_xlsx`, well grain, 131 months from 2015-05 | surface 43,817 · lateral 22,263 · survey trace 525 | 87,634 of 87,634 · `cr_nd_status_vocab_1` | confidential-well production · `cr_nd_confidential_1` |
| **TX** 42 | 359,421 / 359,421 | **none** — `tx_pdq_dsv` is not a registered source; allocation and both validators unbuilt | surface 355,463 · bottomhole 355,545 · lateral 68,331 | 291,235 of 359,421 · `cr_tx_status_vocab_1` | `TOTAL_DEPTH`, `COMPLETION_DATE` · `cr_tx_ewa_measures_1`, the only TX withholding rule. Operator absence is not withholding · `cr_tx_operator_absence_1` |
| **NM** 30 | 321,510 / 142,000 | 17,597,960 · `nm_ocd_wcproduction`, completion-pool grain | surface 141,778 | **0 of 321,510 promoted, by design** — the column stays null and `cr_nm_wellhistory_status_vocab_2` resolves the class at read time: ten of fourteen OCD codes to canonical classes, `I`/`J`/`Q`/`Z` to a distinct `documented_unmapped` class, `unmapped_action = passthrough`. Tile-grain classes active 54,325 · plugged 50,935 · permitted 18,161 · expired 17,056 (`work-output/nm-status-status.md`, 2026-09-01) | lateral geometry `data-unreachable` · `cr_nm_wellhistory_geometry_scope_1`. No well-level rollup · `cr_nm_wcproduction_pool_rollup_1` |
| **MT** 25 | 40,626 / 40,626 | 17,547,951 well grain + 4,808,814 PRU lease grain · `mt_bogc_*` | surface 42,026 · lateral 2,835 | 40,626 of 40,626 · `cr_mt_gis_status_vocab_1` | lateral length · `cr_mt_paths_length_scope_1`. No basin tag · `cr_mt_basin_scope_1` |

Montana is a Williston extension rather than a phase; ROADMAP's N3 owns its exit criteria.

## Serving surface

**51 operations across 46 paths, 50 under `/v1`**, counted from `tests/contract/openapi_snapshot.json`
on 2026-09-01. Covered: health, operational status, wells and their facets, ND production, per-well
cumulatives, vintage cohorts, completion context and promoted completion design, ND physical neighbours,
formations, lineage, manifests, derivations, vintages, conformance, quarantine, glossary, error codes,
keys, sessions, accounts, tiles, and the pinned `tcv1.0` control.

Not served: forecast, valuation, scenario, agent and inventory operations; `/v1/spacingunits`
(land and spacing units serve as tiles only); training, calibration, the model registry, the
analog index and benchmark scoring, all built and unserved.

## Frontend

URL-backed Map, Explore and Status surfaces ship: a right-hand well flyout capped at 540 px
leading with production, a 60-month-default production chart on one plot-rect hit surface,
lineage drawer, glossary tooltip, satellite and hybrid basemaps, a searchable 15-row layer
panel in four groups with the four state well layers nested under one tri-state `Wells`
parent, a server-side status-summary legend census, and the "Wells by …" facet panel on both
Explore and the map. Basins and Plays are real Geology-group layer rows over the served
boundary tiles as of v0.74, off by default; nothing in the panel is a placeholder any more.
As of v0.75 the flyout carries a cumulative oil/gas/water row keeping `no_report`,
`reported_zero` and `withheld` distinct, and the glossary reaches the legend, layers panel and
Status page.

## Phase ledger

| Phase | Status | Remaining boundary |
|---|---|---|
| **P0** Scaffold and contracts | Met | `/v1/audit` is not served, and is not a P0 exit |
| **P1** ND spine | Met with named deferrals | PDF era 2003-01 → 2015-04 and FracFocus chemistry remain absent by design |
| **P2** Serving and map | Substantially met | 51 operations, tiles with the allowlist asserted in CI, map/card/drawer/glossary/explorer/Status all shipped. `/v1/spacingunits` unserved; permits, GOR and water-cut remain |
| **P3** Forecasting and benchmark | Entry gate met; control served; modeling remains | Publication `p3pub_8b434525d8c621762e31b06ca660bfcd` accepted and its control served. Quantile-model writer, split-conformal calibration, model-registry writer, persisted analog index and benchmark runner remain. `fv2.0` is a one-feature set |
| **P4** Dollars and scenarios | Not started | Entire phase |
| **P5** Intelligence, agents and alerts | Not started | Entire phase |
| **P6** Hardening | Partial | Six blocking CI jobs, session auth, rate limits, backup, restore drill, offsite receipt, public tunnel and Postgres tuning are live. Replacement-host recovery is mechanised and **never executed**; the last restore proof is at schema 47 (carried from the previous revision, not re-verified today); the off-LAN credential exercise has not been run; Cloudflare Access is ruled out, not deferred |
| **P7** Permian | NM and MT resident; TX half unbuilt | **NM headers and surface geometry are resident** and **Tier 1 production is promoted — 17,597,960 rows at completion-pool grain**. NM status is resolved at read time as of v0.74 — the promoted column stays null by design. Montana is resident on both grains with tiles and paths. **TX lease production is unbuilt**, and with it allocation v0, both validators and a TX geometry-provenance rule of its own |
| **P8** Living systems | Not started | Entire phase |

## Public access

Live at **`https://glasswell.rpx.sh`** through Cloudflare Tunnel `3b2d209f-7671-4497-ae4f-740dcbc34788`, closed by default: `/healthz`, the SPA shell and assets, `/basemap/*` and the two login routes answer anonymously; every other operation refuses before any database work.
Authorization is the application's own session login — two roles (`owner`, `viewer`) over `lineage.users`, `__Host-` cookie, CSRF. **Cloudflare Access is not enabled and is not used.**
The static owner key is refused at the tunnel edge, so it is a LAN and deploy-gate credential only; `/v1/keys*` and the `agent` scope are `deprecated: true` in the served document.
Rollback is three levels: delete the proxied CNAME, `systemctl stop cloudflared`, or revert and redeploy.
`verify.sh`'s four edge probes carry a publicly-resolved address, because lab DNS NXDOMAINs the public hostname from VM 111.
The off-LAN credential exercise has never been run: every probe so far originated on this network.

## Verification state

- **Hosted CI runs on every push** — six jobs: `python`, `web`, `e2e-guards`, `shell`,
  `collateral`, `map-chrome`. The last run is **green at `39bd7f0`** (`gh run list`, today).
- **`infra/verify.sh` and `scripts/smoke.sh`** last read **194/194** and **26/26** at the
  **v0.72** deploy, per the previous revision of this file. They have **not been re-run for
  v0.73**.
- **Deployed code version, schema head and the served operation count** were measured today.
- **No local suite count is stated here.** None was measured on 2026-09-01, and a test count
  that is not re-measured is not evidence.

## Open items

Each item names the release that carries it in [`ROADMAP.md`](ROADMAP.md) "Horizon"; the
per-release tables are working files outside git.

**Landed in v0.74:** NM read-time status resolution; the Map→Explore crossing, now writing
`f.api10`; Basins and Plays as real Geology-group layer rows, off by default.
**Landed in v0.75:** the N2 re-land — per-well cumulatives, vintage cohorts and promoted
completion design — and glossary coverage on the legend, layers panel and Status page.

1. **Jurisdiction registry** — 465 hardcoded state references across 59 files, four per-state
   dicts in `routers/wells.py` alone (`code-audit.md`, not re-measured here). v0.76.
2. **User administration UI** — `/v1/users` CRUD is complete server-side and `web/src` never
   calls it; no session-list endpoint exists. v0.76.
3. **Cadence-driven ingest scheduling** — the policy is a table; the unit is ten hand-written
   `ExecStart` lines and NM and MT are not scheduled at all. H2 (v0.77).
4. **Texas production** — the largest resident state has no production number. H2 (v0.78).
5. **P6 residuals** — a restore proof at the current schema, replacement-host recovery
   execution, and an off-LAN credential exercise. H3.
6. **P3–P5 modeling and economics**, sequenced after the registry lands. H3. The owner-gated
   v0.6 §11 capability-matrix / IP review stays out of scope.

---

> Copyright (C) 2026 Ryan MacDonald &lt;ryan@rfxn.com&gt; &#183; All rights reserved
