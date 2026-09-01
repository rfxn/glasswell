# Architecture

glasswell is a **single-VM analytical system** with a strict four-layer data path
and one non-negotiable invariant: every number it serves can be walked back to the
bytes it came from. This document maps the layers, their contracts, the canonical
model, the component inventory, and the rules that govern each boundary.

The authoritative source for scope and intent is [`blueprint.md`](blueprint.md).
Where this document restates the blueprint it is a convenience; where they
disagree, the blueprint wins.

<p align="center"><img src="assets/architecture.svg" alt="glasswell system architecture from public regulator files through raw, staging, canonical and marts layers into an API, map and agent gateway" width="1000"></p>

## Layer contracts

Four layers, and the boundaries between them are enforced rather than encouraged.

### Raw — immutable

The file exactly as downloaded. Original bytes on disk with a Parquet mirror for
columnar reads. Every file lands with an `ingest_manifest` row recording source
URL, fetch time, vintage, parser version, and `sha256`.

Nothing in the raw zone is ever edited. When a state restates its data, that is a
new file with a new vintage and a new hash — never an overwrite. This is what makes
a number from six months ago still reproducible today.

### Staging — source-faithful

One schema per regulator file type. Resident tables are `staging.nd_mpr_oil`, the
`staging.nd_gis_*`, `staging.tx_gis_wells_*`, `staging.blm_plss_*` and
`staging.stg_nm_ocd_*` families, `staging.tx_wellbore_ewa`, `staging.nm_c115b_upstream`,
`staging.nm_ocd_wells_gis` and `staging.fracfocus_disclosures`. Two of those are staging
termini by design rather than by omission — `nm_c115b_upstream` because its rolling window
cannot be re-fetched once it moves, and `nm_ocd_wells_gis` because the cross-source parity
measurement is what decides whether and how it promotes. Parsers write here and nowhere else. They hold no
opinions: a FracFocus timestamp remains source text until the conformance step validates it.

Rows that fail parsing or validation go to **quarantine** with a reason code, not
to `/dev/null`. Quarantine is served at `/v1/quarantine`, with `/v1/quarantine/summary`
over the reason codes, and its size is a published quality metric.

> **Staging never serves.** No endpoint, tile, or mart reads a `staging.` table.

### Canonical — conformed

One schema for the domain, and the layer this project is really about. The
promotion step reads staging, applies conformance rules, and emits a conformance
reference into every derivation it produces.

**Entities:** well (API-10), wellbore (API-12/14), operator, lease (TX),
production observation (well, month, stream, volume, granularity, allocation ref),
completion event and completion anchor, spatial features (surface point, bottomhole, lateral), formation
top, permit, land unit, spacing unit, well status.

**Identity policy.** API-10 identifies the well and is the spine. API-14 normalises
to API-10 for joins.

**Wellbore simplification (pinned decision).** One producing wellbore per API-10 is
assumed. Sidetracks and multi-completion wellbores are detected and quarantined with
a reason rather than mis-joined, on whatever the regulator publishes: the API-12
suffix in North Dakota (`cr_nd_multilateral_1`), the RRC wellbore code in Texas,
which files no API-12 (`cr_tx_multi_wellbore_1`), and nothing at all in New Mexico,
where the policy is vacuously satisfied (`cr_nm_wchistory_wellbore_policy_1`). The
quarantined share is reported in the scorecard per basin, and the revisit trigger is
2% in North Dakota and 5% in the Permian rather than one global number — re-entry
and multi-completion rates differ materially between the Bakken and a century-old
Permian wellbore population (blueprint-v0.6 §3.0.5).

### Marts — serving

Resident today: the PostGIS geometry martin turns into vector tiles
(`nd_wells_tile`, `nd_laterals_tile`, `nd_survey_traces_tile`, `tx_wells_tile`,
`tx_laterals_tile`, `nm_wells_tile` — a point layer with no lateral sibling, because no
in-scope New Mexico source ships one — `mt_wells_tile` and `mt_paths_tile` — whose lines are
cartographic centrelines carrying `geometry_class` and `vertex_count` on every feature, and no
length, because Montana carries no basin and so no registered length method —
`land_units_tile`, `land_metrics_tile`, plus spacing
units,
which are a view rather than a table), the `nd_well_card` table, and the current
physical-neighbour pair `nd_neighbor_subjects` / `nd_neighbor_edges`. martin reads
none of those directly: it selects from the `marts.tile_*` views over them, which is
where the tile-layer allowlist is enforced. `well_features` is resident as well, but on the analytical path
as the content-addressed `features.well_features` Parquet matrix rather than as a
PostGIS table, and the generic `rollups` slot is filled for observed quantities by
`land_metrics_tile`. Contracted and not built: `type_curve_sets`, `analog_index`,
`inventory_slots`, and any rollup over a forecast or a valuation. All derived from
canonical, all rebuildable at any time.

> **Marts never ingest.** A mart that reads staging is a build error, not a shortcut.

## Conformance as data — rule R8

> Every cross-source mapping decision is a row in `conformance_rules` (source,
> field, rule, rationale, effective date), served at `/conformance` and referenced
> by the derivations of every number it shaped. **A mapping that exists only in
> code fails review.**

This is the thesis of the whole build. In this category the unified data model *is*
the product — OSDU exists precisely because no two schemas agree — so rebuilding
the model and exposing every decision inside it is the work, not the plumbing under
it.

Registry tables: `conformance_rules`, `formation_aliases` (reported name, canonical
formation, benchmark formation group, confidence and knowledge vintage), `crs_registry` (compute CRS per basin — ND in UTM
14N, Permian in UTM 13N).

Seed rules, drawn from real cross-source gotchas:

| Field | Rule |
|-------|------|
| **Coordinate datum** | Legacy TX RRC coordinates are frequently NAD27; modern layers are NAD83/WGS84. Untransformed NAD27 is off by up to roughly 100 m — enough to silently corrupt spacing math. Datum is detected per file vintage, transformed to EPSG:4326 for storage, and the transform is recorded in the derivation. |
| **Compute CRS** | Storage is always EPSG:4326. Distance and spacing math is always done in the projected CRS for the basin, from `crs_registry`. |
| **Liquids** | Condensate versus oil classification differs by state. Regulator classification stays in staging; canonical carries the stream plus a `liquids_policy` tag. Oil-plus-condensate is the default modelling liquid, stated everywhere it appears. |
| **Gas conditions** | Volumes conform to mcf at the regulator's stated conditions. The conditions are recorded, not silently normalised. |
| **Month convention** | Production month versus report month is resolved per source and recorded. |
| **Formation names** | Current ND MPR pool labels resolve through append-only, knowledge-vintaged `formation_aliases`; ambiguous composites remain `__other__`, and explicit Three Forks never collapses into Bakken. |
| **Completion anchor** | FracFocus `JobEndDate` is retained as a hydraulic-fracturing completion event. The earliest valid event per API-10 anchors fv1.0; spud and first production are forbidden fallbacks. |
| **Well status** | Regulator vocabularies map to a small canonical set — as rows, not code. |

**Registry rot is the named risk.** Mitigation: the promotion step reads rules from
the table at run time wherever feasible, and CI asserts that every canonical field
maps to at least one rule.

## Component inventory

The full component inventory C1–C21 is defined in blueprint v0.4 §3.2 and is not
restated here. v0.5 amends it as follows, and these are the components with
current contracts:

| Component | Contract |
|-----------|----------|
| **C3** Parsers | Write staging only. Never canonical, never marts. |
| **C4** Promotion / conformance step | Promotes staging to canonical, applying rules from the registry and emitting conformance references into derivations. |
| **C7** Modelling engine | The pinned `tcv1.0` empirical type-curve control is built over exact `mdv1.4` splits, and is served read-only through a registered locator: the API resolves the artifact from the accepted P3 publication receipt and the `typecurve.build` derivation that wrote it, refuses any path outside `GLASSWELL_MODEL_ROOT`, and never writes the artifact tree. Gradient-boosted quantile models, conformal calibration, analog KNN, and batch scenario execution remain planned. |
| **C10** Economics | DCF at a named deck. Sensitivity runs (deck, opex, capex deltas → tornado rows) at trivial cost because valuation is pure. Assumptions include water handling cost and per-state severance defaults. |
| **C11** Scenario / valuation orchestration | The composition point the inventory engine wraps. |
| **C13 / C14** Map and UI | Type-curve builder (filter selection → curve with band and well count), operator league table, GOR and water-cut charts on the well card, inventory slot layer. |
| **C15** Agent gateway | Curated MCP tools mapping 1:1 onto public endpoints, including analogs, tornado, inventory, and conformance lookup. |
| **C22** Inventory engine *(new)* | Spacing-gap detection per section or spacing unit, slot generation at an assumed spacing, batch scenario forecasts, rollup with NPV. Thin orchestration over C11. |
| **C23** Alerting *(new)* | Saved AOI polygons, weekly diff on permits and new wells, digest output. One systemd timer and one table. |

Unchanged from v0.4: the raw zone, Parquet plus DuckDB, PostGIS, martin, MapLibre
plus deck.gl, and one VM.

## Rules

Rules R1–R7 are defined in blueprint v0.4 §3.2 and continue to apply. R8 is new in
v0.5 and is stated in full above. The two that bind hardest in day-to-day work:

- **R3 (valuation purity)** — economics is a pure function of `(forecast, deck,
  assumptions)`. This is what makes sensitivities, scenario runs, and batch
  inventory valuation nearly free.
- **R6 / R7 (derivation and explain coverage)** — every endpoint carries
  derivations and recipes, and every new endpoint inherits the obligation. There is
  no grandfather clause.

## Protocol guardrails

Protocols 4A, 4B, and 4C are pinned in blueprint v0.4 §4 and are normative. v0.5
adds:

- **4A.11 — three-stream discipline.** Gas and water are secondary targets under
  identical split, censoring, and control rules. GOR and water-cut trends are
  derived surfaces, never targets. Oil remains the headline; all three results are
  reported together.
- **4A.12 — analog quality check.** For a sample of wells, the top-10 analogs'
  actual cum12 IQR must bracket the subject's actual at stated rates. Reported like
  calibration.
- **4D — inventory.** Slots are generated only where existing lateral geometry
  admits a full lateral at the assumed spacing. Every slot forecast carries a
  `training_support` score. Rollups always state the spacing assumption and the
  support distribution. **No inventory number ships without both.**

Inventory is the feature most prone to confident nonsense. The guardrail is not
optional and it is not a rendering preference.

## Data model

Tables introduced or amended at v0.5. **Resident** means the migration is applied on
the deployed instance; the rest are contract, not schema:

| Table | Resident | Purpose |
|-------|----------|---------|
| `conformance_rules` | yes | rule_id, source, field, rule, rationale, effective_from |
| `formation_aliases` | yes | reported name, canonical formation, benchmark group, confidence, knowledge vintage |
| `crs_registry` | yes | Compute CRS per basin (projected, metres) |
| `production_monthly` | yes | Gains stream normalisation notes via conformance refs; oil, gas and water all first-class targets |
| `econ_assumptions` | no | Gains `opex_water_per_bbl` and severance defaults keyed by state |
| `analog_index` | no | api10, feature_version, vector ref — persisted only if an in-process rebuild exceeds 60 s |
| `inventory_runs` | no | run_id, area, spacing_assumption_ft, model_id, deck_id, created |
| `inventory_slots` | no | run_id, slot geometry, forecast_id, valuation_id, flags |
| `aois` | no | aoi_id, name, geom |
| `alert_digests` | no | aoi_id, period, payload jsonb |
| `well_sets` | no | set_id, name, api10s[] — portfolio rollups |

## Serving

One API, three consumers, no private path behind any of them.

- **API** — FastAPI with a complete OpenAPI document. Endpoints stay lean by
  default; `?explain=true` inlines the lineage block.
- **Map UI** — MapLibre plus deck.gl over martin vector tiles, targeting 20k+
  laterals with model-driven styling at interactive frame rates. The lineage drawer
  hangs off every number and reads the same `/explain` call an external caller gets.
- **Agent gateway** — curated MCP tools mapping onto public endpoints. The
  ten-question suite is the completeness test: if the agent cannot answer through
  public tools with every figure traceable, the API is incomplete.

## Cross-cutting

The audit stream is append-only and every layer writes to it. Restatements are new
events, never edits.

| Surface | Purpose |
|---------|---------|
| Audit stream | One ordered event log for the whole system |
| Derivations | Named inputs — forecast_id, model_id, feature_version, deck_id, code_version, run_id, input row keys |
| Recipes | The command that regenerates an artifact byte-for-byte on a clean checkout |
| Forecast ledger | Every forecast written at issue time and graded as actuals arrive |
| Quality scorecard | Published, reproducible from the API; carries the quarantined-wellbore share |
| Benchmark harness | Type curve versus model on one temporal holdout, sliced and published per basin |

Manifest-level lineage is a deliberate choice over row-level: the unit of custody
is the file. It is cheap to keep, sufficient to prove, and it does not rot into a
second database that has to be kept in sync with the first.

## Deployment

One VM. Parquet plus DuckDB for the analytical path, PostGIS for geometry, martin
for tiles, and systemd timers for ingest, the NM C-115B snapshot, the nightly
logical backup, the weekly restore drill, the lineage-retention sweep, and the
sanitized operational Status snapshot. Alerting is contracted at C23 and has no
deployed timer. No distributed infrastructure and no service that cannot be rebuilt
from the raw zone by replaying recipes.

Inventory batch runs are the only new load introduced at v0.5, and they run in
seconds at township scale.

---

> Copyright (C) 2026 Ryan MacDonald &lt;ryan@rfxn.com&gt; &#183; All rights reserved
