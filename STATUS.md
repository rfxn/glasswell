# Current status

Reconciled on **2026-09-05** against the v0.82 release line, the checked-in OpenAPI
snapshot, current `main` history and a read-only census of the deployed database. Dates are
UTC, the serving clock `lineage/clock.py` defines; v0.75 was cut 2026-09-01 20:33 -0500, which
is 2026-09-02. Every figure below is dated and names its source; one is carried forward from the previous revision and says
so on the line. [`ROADMAP.md`](ROADMAP.md) owns phase scope and exit criteria;
[`blueprint.md`](blueprint.md) is the committed v0.5 contract and
[`blueprint-v0.6-draft.md`](blueprint-v0.6-draft.md) the rc6 amendment set.

## Deployed

- **Release line:** 63 tagged releases, v0.20 through v0.82, cut 2026-08-21 through
  2026-09-05.

Measured on the deployed database (VM 111) and host, read-only, 2026-09-02.

| Item | Value | Source of the measurement |
|---|---|---|
| Code version | `v0.75+2189262` | `/etc/glasswell/code-version.env` |
| Schema head | `072` | `select max(version) from schema_migrations` |
| `canonical.wells` | 809,191 rows over 585,864 distinct API-10 | `select count(*), count(distinct api10) from canonical.wells` |
| `canonical.production_monthly` | 47,178,269 rows | `select count(*) from canonical.production_monthly` |
| `canonical.well_spatial` | 1,041,407 rows | `select count(*) from canonical.well_spatial` |
| `marts.basin_boundaries_tile` | 48 rows | `select count(*) from marts.basin_boundaries_tile` |
| `main` | `2189262`, level with `origin/main`; 56 version tags | `git rev-parse main origin/main`; `git tag \| grep -c '^v'` |

## Shipped baseline per state

All five states are resident; Colorado landed 2026-09-05 (run 2, 6 min 55 s on the host runner, every gate exact). Rows and distinct API-10 differ where a state carries bitemporal
vintages; geometry is distinct API-10 per `geom_type`. Montana is a Williston extension rather
than a phase; ROADMAP's N3 owns its exit criteria.

| State | Wells (rows / API-10) | Production rows | Geometry | `status_canonical` | Withheld, and the rule |
|---|---|---|---|---|---|
| **ND** 33 | 87,634 / 43,817 | 7,223,544 · `nd_mpr_xlsx`, well grain, 131 months from 2015-05 | surface 43,817 · lateral 22,263 · survey trace 525 | 87,634 of 87,634 · `cr_nd_status_vocab_1` | confidential-well production · `cr_nd_confidential_1` |
| **TX** 42 | 359,421 / 359,421 | **none** — `tx_pdq_dsv` is not a registered source; allocation and both validators unbuilt | surface 355,463 · bottomhole 355,545 · lateral 68,331 | 291,235 of 359,421 · `cr_tx_status_vocab_1` | `TOTAL_DEPTH`, `COMPLETION_DATE` · `cr_tx_ewa_measures_1`, the only TX withholding rule. Operator absence is not withholding · `cr_tx_operator_absence_1` |
| **NM** 30 | 321,510 / 142,000 | 17,597,960 · `nm_ocd_wcproduction`, completion-pool grain | surface 141,778 | **0 of 321,510 promoted, by design** — the column stays null and `cr_nm_wellhistory_status_vocab_2` resolves the class at read time: ten of fourteen OCD codes to canonical classes, `I`/`J`/`Q`/`Z` to a distinct `documented_unmapped` class, `unmapped_action = passthrough`. Tile-grain classes active 54,325 · plugged 50,935 · permitted 18,161 · expired 17,056 (`work-output/nm-status-status.md`, 2026-09-01) | lateral geometry `data-unreachable` · `cr_nm_wellhistory_geometry_scope_1`. No well-level rollup · `cr_nm_wcproduction_pool_rollup_1` |
| **MT** 25 | 40,626 / 40,626 | 17,547,951 well grain + 4,808,814 PRU lease grain · `mt_bogc_*` | surface 42,026 · lateral 2,835 | 40,626 of 40,626 · `cr_mt_gis_status_vocab_1` | lateral length · `cr_mt_paths_length_scope_1`. No basin tag · `cr_mt_basin_scope_1` |
| **CO** 05 | 124,392 / 124,392 | 1,261,665 · `co_ecmc_production` rolling file, 244,491 pool + 1,017,174 well grain, 98,226 disclosed `sum_over_pools` | surface 124,392 · bottomhole 39,048 · lateral 39,048 (staged 124,410 / 39,048 / 39,048; 18 `duplicate_row` quarantined) | 124,392 of 124,392 via the resolver (G-3) · `cr_co_wells_status_vocab_1` | 1,172 wells carry a blank `well_type_reported` — F-3, `fix/co-blank-well-type` in flight (the status summary refuses their bbox until it lands) |

### Basin context, measured before it ships

`marts.well_basin_context` is built by this release line and is not on the deployed host yet;
these are its answers, taken read-only on the spine 2026-09-03 with the mart's own query — one
containing basin polygon per well, driven off `canonical.wells_latest` and left-joined to the
surface point in `canonical.well_spatial`.

**One denominator, and it is the well count.** Every share below is over the jurisdiction's own
wells in `canonical.wells_latest`, which is the population the mart is driven off and therefore
the figure the card serves with a handle. Wells with no surface point are counted in that
denominator and answered `no_geometry`.

| State | Wells | Inside a published basin | `outside_published_boundaries` | No geometry | Rule |
|---|---:|---|---|---:|---|
| **ND** 33 | 43,817 | 43,424 (99.1 %) | 393 (0.9 %) | 0 | `cr_nd_basin_context_1` |
| **TX** 42 | 359,421 | 344,611 (95.9 %) | 10,852 (3.0 %) | 3,958 | `cr_tx_basin_context_1` |
| **NM** 30 | 142,000 | 137,505 (96.8 %) | 4,273 (3.0 %) | 222 | `cr_nm_basin_context_1` |
| **MT** 25 | 40,626 | 13,062 (32.2 %) | **27,564 (67.8 %)** | 0 | `cr_mt_basin_context_1` |

Asked of the geometry table instead — distinct surface api10s in `canonical.well_spatial`, which
is the base the spec's §6.2 quotes — the four shares read ND 43,424/43,817 (99.1 %), TX
344,611/355,463 (96.9 %), NM 137,505/141,778 (97.0 %) and MT 13,623/42,026 (32.4 %). Only
Montana moves materially, and by exactly the 1,400 surface points that have no well behind them,
561 of which are inside a basin. **The served figure is the well-base one**, because that is what
the mart writes and what the card resolves; the geometry-base figures are recorded here so a
reader comparing this page against the spec finds the difference stated rather than implied.

Two thirds of Montana is `outside_published_boundaries`: a served answer about the EIA boundary
set, not a gap in the record. Texas files `permian` on all 359,421 rows as an ingest scope label,
and 10,896 of the 344,611 inside a polygon (3.2 %) are in a different one — 10,030 Fort Worth,
456 Palo Duro, 410 Marfa — which the card serves beside the label rather than overwriting.

## Serving surface

**58 operations across 53 paths, 57 under `/v1`**, counted from `tests/contract/openapi_snapshot.json`
on 2026-09-02 — the three added on `release/v0.76` are `GET /v1/jurisdictions` and `GET`/`DELETE` on
the session list. Covered: health, operational status, wells and their facets, ND production, per-well
cumulatives, vintage cohorts, completion context and promoted completion design, ND physical
neighbours, formations, the jurisdiction registry, lineage, manifests, derivations, vintages,
conformance, quarantine, glossary, error codes, keys, sessions, accounts, tiles, and the pinned
`tcv1.0` control. Not served: forecast, valuation, scenario, agent and inventory operations;
`/v1/spacingunits` (land and spacing units serve as tiles only); training, calibration, the model
registry, the analog index and benchmark scoring, all built and unserved.

## Frontend

URL-backed Map, Explore and Status surfaces ship: a right-hand well flyout capped at 540 px leading
with production, a 60-month-default production chart on one plot-rect hit surface, lineage drawer,
glossary tooltip, satellite and hybrid basemaps, a searchable 15-row layer panel in four groups with
the four state well layers nested under one tri-state `Wells` parent, a server-side status-summary
legend census, and the "Wells by …" facet panel on both Explore and the map. Basins and Plays are
real Geology-group layer rows over the served boundary tiles as of v0.74, off by default; nothing in
the panel is a placeholder any more. As of v0.75 the flyout carries a cumulative oil/gas/water row
keeping `no_report`, `reported_zero` and `withheld` distinct, and the glossary reaches the legend,
layers panel and Status page. On `release/v0.76`, not yet deployed: an owner-only Accounts section on
the Status page over `/v1/users` and the session list, and a `?well=` deep link that flies to the
well when the link named no viewport of its own.

## Phase ledger

| Phase | Status | Remaining boundary |
|---|---|---|
| **P0** Scaffold and contracts | Met | `/v1/audit` is not served, and is not a P0 exit |
| **P1** ND spine | Met with named deferrals | PDF era 2003-01 → 2015-04 and FracFocus chemistry remain absent by design |
| **P2** Serving and map | Substantially met | 58 operations, tiles with the allowlist asserted in CI, map/card/drawer/glossary/explorer/Status all shipped. `/v1/spacingunits` unserved; permits, GOR and water-cut remain |
| **P3** Forecasting and benchmark | Entry gate met; control served; modeling remains | Publication `p3pub_8b434525d8c621762e31b06ca660bfcd` accepted 2026-08-28 and its control served. Quantile-model writer, split-conformal calibration, model-registry writer, persisted analog index and benchmark runner remain. `fv2.0` is a one-feature set |
| **P4** Dollars and scenarios | Not started | Entire phase |
| **P5** Intelligence, agents and alerts | Not started | Entire phase |
| **P6** Hardening | Partial | Six blocking CI jobs, session auth, rate limits, backup, restore drill, offsite receipt, public tunnel and Postgres tuning are live. Replacement-host recovery is mechanised and **never executed**; the last restore proof is at schema 47 (carried from the previous revision, not re-verified today); the off-LAN credential exercise has not been run; Cloudflare Access is ruled out, not deferred |
| **P7** Permian | NM and MT resident; TX half unbuilt | **NM headers and surface geometry are resident** and **Tier 1 production is promoted — 17,597,960 rows at completion-pool grain**. NM status is resolved at read time as of v0.74 — the promoted column stays null by design. Montana is resident on both grains with tiles and paths. **TX lease production is unbuilt**, and with it allocation v0, both validators and a TX geometry-provenance rule of its own |
| **P8** Living systems | Not started | Entire phase |

## Public access

Live at **`https://glasswell.rpx.sh`** through Cloudflare Tunnel `3b2d209f-7671-4497-ae4f-740dcbc34788`, closed by default: `/healthz`, the SPA shell and assets, `/basemap/*` and the two login routes answer anonymously; every other operation refuses before any database work.
Authorization is the application's own session login — two roles (`owner`, `viewer`) over `lineage.users`, `__Host-` cookie, CSRF. **Cloudflare Access is not enabled and is not used.** The static owner key is refused at the tunnel edge, so it is a LAN and deploy-gate credential only; `/v1/keys*` and the `agent` scope are `deprecated: true` in the served document.
Rollback is three levels: delete the proxied CNAME, `systemctl stop cloudflared`, or revert and redeploy. `verify.sh`'s four edge probes carry a publicly-resolved address, because lab DNS NXDOMAINs the public hostname from VM 111; every probe so far originated on this network, so the off-LAN credential exercise remains unrun.

## Verification state

- **Hosted CI runs on every push** — six jobs: `python`, `web`, `e2e-guards`, `shell`,
  `collateral`, `map-chrome`. The last run is **green at `2189262`** (PR #47, 2026-09-02).
- **`infra/verify.sh` and `scripts/smoke.sh`** last read **197 passed / 0 failed** and **31 passed /
  0 failed** at the **v0.75** deploy, 2026-09-02 (`/tmp/ship-v075.log`); smoke moved 26 checks to 31.
- **Deployed code version, schema head and every row count above** were measured today. No
  local suite count is stated here: a test count that is not re-measured is not evidence.

## Open items

Each item names the release that carries it in [`ROADMAP.md`](ROADMAP.md) "Horizon".

**Landed in v0.74:** NM read-time status resolution; the Map→Explore crossing; Basins and Plays as
real Geology-group layer rows. **Landed in v0.75:** the N2 re-land · per-well cumulatives, vintage
cohorts and promoted completion design · and glossary coverage on the legend, layers and Status.
**Merged on `release/v0.76`, neither tagged nor deployed as of 2026-09-02:** the jurisdiction registry
(migration 073, `/v1/jurisdictions`, the per-state dicts now rows) and the Accounts surface with the
session list (migration 074); the two items this list carried for v0.76 close when that train ships.

1. **Cadence-driven ingest scheduling** — the policy is a table; the unit is ten hand-written
   `ExecStart` lines and NM and MT are not scheduled at all. H2 (v0.77).
2. **Texas production** — the largest resident state has no production number. H2 (v0.78).
3. **P6 residuals** — a restore proof at the current schema, replacement-host recovery
   execution, and an off-LAN credential exercise. H3.
4. **P3–P5 modeling and economics**, sequenced after the registry lands. H3. The owner-gated
   v0.6 §11 capability-matrix / IP review stays out of scope.
7. **Cumulative production is North Dakota only** · `marts/cumulatives.py:64` pins
   `STATE_API_PREFIXES = ("33",)`; 43,817 of 585,864 wells carry a cumulative. H2 (v0.77).

---

> Copyright (C) 2026 Ryan MacDonald &lt;ryan@rfxn.com&gt; &#183; All rights reserved
