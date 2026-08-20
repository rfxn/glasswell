# SB-07 — Lineage & Reproducibility Spine

**Sub-blueprint. Status: draft for review. Owner: Ryan MacDonald.**
Scope boundary per `assessment-blueprint.md:805`. This SB is a **contract**, not a feature:
SB-01 through SB-05 code against it. Freezing it late is the program's largest rework
risk (`ab:807-810`).

**Citation convention.** `bp:N` = `blueprint.md` line N · `ab:N` =
`work-output/assessment-blueprint.md` · `ad:N` = `work-output/assessment-datasources.md` ·
`ai:N` = `work-output/assessment-infra.md` · `DIR-n` = `work-output/direction-log.md`.
Every design decision below carries a one-line justification. Rejected alternatives are
in §13; deliberate omissions are in §14.

---

## 0. Scope and obligations

### 0.1 What the spine owns

| Owns | Does not own |
|---|---|
| Derivation record schema + capture mechanism | Any transform's *content* (SB-01/02/03) |
| Raw-zone manifest schema, fetch idempotency, supersession | Source fetchers, parsers (SB-01) |
| Bitemporal vintage mechanics (DIR-2) | Canonical column design (SB-01) |
| Recipe format, determinism classes, replay CLI | Training code (SB-02) |
| Append-only audit stream | Alert delivery (SB-03) |
| Conformance-rule *runtime loader* and typed rule kinds | Rule *rows* and rationale text (SB-01) |
| Model registry identity + lineage | Model training, tuning, calibration (SB-02) |
| Quarantine schema + release loop | Reason-code semantics per source (SB-01) |
| `/explain`, `/derivations`, `/manifests`, `/recipes`, `/audit`, `/quarantine`, `/conformance`, `/models`, `/vintages` response shapes | HTTP framework, auth, error envelope, pagination policy globally (SB-04) |
| Naked-number CI harness + registry drift/coverage checks | Glossary CI content (DIR-8, SB-04/05) |
| `glasswell.lineage` Python package | Everything that imports it |

### 0.2 Requirements this SB satisfies

| Requirement | Source | Satisfied in |
|---|---|---|
| No naked numbers; every served figure carries a derivation handle | `bp:97` | §1.3, §9.1, §10 |
| The kitchen is the product; quarantine has an endpoint | `bp:98` | §8, §9.4 |
| Reproducibility is an output; recipe regenerates byte-for-byte | `bp:99` | §4 (with a required amendment, §4.6) |
| Quiet by default, `?explain=true` inlines lineage | `bp:100` | §9.1, §9.2 |
| Append-only memory; restatements are new events | `bp:101` | §3, §5.4 |
| R8 conformance as data; derivations reference applied rules | `bp:116,158` | §6 |
| R6 (reconstructed) every endpoint serves derivations/recipes/explain | `bp:180`, `ab:96` | §9.4, §10 |
| R7 (reconstructed) explain coverage / naked-number rule | `bp:180`, `ab:96-97` | §10 |
| S1 stranger reproduces every UI number | `bp:79` | §4.5, §9.4, §9.6 |
| S5 agent traces every figure via public tools | `bp:83` | §9.3 (machine-readable chain) |
| S9 UI number → raw manifest, ≤3 interactions + one `/explain` | `bp:87` | §1.8 |
| S11 conformance registry served; numbers cite the rules | `bp:89` | §6.3, §9.4 |
| Manifest-level lineage (resolved decision 6) | `bp:253` | §1.2, §2 |
| DIR-2 bitemporal vintages, as-of `/explain` and grading | DIR-2 | §3 |
| DIR-3 allocation as versioned derived artifacts, granularity flag | DIR-3 | §9.1, §7 |
| A-05 `/explain` mechanism decided once | `ab:580-588` | §1.1 |
| A-10 ingest idempotency / restatement | `ab:617-621` | §2.1, §3 |
| A-11 manifest + checksum design | `ab:623-628` | §2 |
| A-01 model registry | `ab:551-556` | §7 |
| A-14 determinism honesty | `ab:650-656` | §4.2 |
| D-09 conformance runtime enforcement (not aspiration) | `ab:479-486` | §6.3 |
| A-16 quarantine remediation loop | `ab:666-671` | §8.3 |
| A-15 analog index stable identity | `ab:658-664` | §1.7 |
| A-03 cross-store lineage (DuckDB ↔ PostGIS) | `ab:564-570` | §1.7 |
| A-09 naked-number CI is real, not asserted | `ab:610-615` | §10 |
| API-04/05/06 ID stability, envelope, machine-readable explain | `ab:741-754` | §1.3, §9.1, §9.3 |

### 0.3 R6 / R7 working definitions

R6 and R7 are dangling (`ab:96-97`); `bp:180` only says "derivations, recipes, explain
coverage". The spine cannot be written without them, so it adopts these and **SB-00 must
ratify or replace them in v0.6** (change-controlled per `bp:288`):

> **R6 (lineage completeness).** Every artifact a served figure depends on — raw file,
> staging load, canonical promotion, feature build, model run, forecast, valuation, mart,
> tile layer — is produced inside a recorded derivation whose inputs terminate in raw-zone
> manifests. An artifact produced outside a derivation may not be served.

> **R7 (explain coverage).** Every numeric leaf in every API response resolves to a
> derivation handle, or appears in a checked-in non-figure allowlist with a reason. The
> handle resolves to its terminal manifests in one `/explain` call. Enforced by CI (§10),
> not by review.

Justification: this split gives R6 to *producers* and R7 to *the serving surface*, which
is the only division under which each rule has a single enforcement point.

---

## 1. Derivation model

### 1.1 Capture mechanism — the A-05 decision

**Decision: instrument the compute layer. Derivations are emitted as a side effect of a
`derive()` context manager wrapped around every artifact-producing transform. `/explain`
is a read over the recorded graph; it never reconstructs lineage at request time.**

Justification: hand-authored explain paths cost ~25 endpoints × forever (`ab:584-588`) and
each endpoint invents its own chain shape — precisely the rot this SB exists to prevent
(`ab:790-794`). Instrumentation costs one package and a discipline rule.

Two capture sites, one mechanism:

| Site | What is wrapped | When it runs | Volume behaviour |
|---|---|---|---|
| **Pipeline** | fetch, parse, promote, feature build, train, batch forecast, mart refresh, tile build | scheduled / manual batch | bounded by source cadence × change rate (§1.5) |
| **Request-time** | scenarios, sensitivities, type-curve builds, inventory runs, analog queries | per API call | content-addressed, deduped, TTL'd (§1.6) |

Request-time capture is safe *because of* R3 purity (`bp:150`, `ab:93`): a pure function of
(forecast, deck, params) yields a deterministic `derivation_id`, so repeated calls collapse
onto one row instead of growing the table.

**Not instrumented:** individual Polars expressions, SQL clauses, or columns. The
instrumentation boundary is the **transform**, defined as "a function that produces a
named artifact or a named request-time result". Expression-level lineage is §14's first cut.

### 1.2 Granularity — artifact-partition, with figure addressing

**Decision: one derivation per (operation, output partition, input set, code version,
params). A served figure is addressed *into* that derivation by a selector; it does not
get its own row.**

This is the concrete reading of resolved decision 6, "manifest-level lineage"
(`bp:253`, `ab:193`): lineage is recorded at artifact granularity and *addressed* at
figure granularity.

Rejected granularities (one line each):

- **Per-figure rows** — 10⁷–10⁸ rows (§1.5); makes `/explain` a table scan and kills S9's latency implicitly.
- **Per-run rows only** — cannot distinguish which manifest fed which production month; fails S9's "to raw manifest" for restated months.
- **Per-column lineage inside a transform** — buys attribute provenance nobody in S1/S5/S9/S11 asks for; the operation + code ref answers "how" adequately.

Partition keys by dataset (SB-01 owns the physical layout; these are the lineage-visible keys):

| Dataset | Partition key |
|---|---|
| `staging.<source_table>` | `(source_id, manifest_id)` |
| `canonical.production_monthly` | `(source_id, report_vintage, production_month)` |
| `canonical.<dimension>` | `(source_id, report_vintage)` |
| `marts.well_month_allocated` | `(basin, report_vintage, production_month, allocation_model_id)` |
| `features.well_features` | `(feature_version, as_of_vintage)` |
| `models.<target>` | `(model_id)` |
| `forecasts.batch` | `(model_id, as_of_vintage, basin)` |
| `tiles.<layer>` | `(layer, build_id)` |

### 1.3 Derivation handle format

```
d = "drv_<id>"                              # whole-artifact figure (e.g. a series)
d = "drv_<id>#<selector>"                   # single figure inside an artifact
selector = key "=" value *("&" key "=" value)   # over the output's key columns + col=
```

Example: `drv_7QK3M2XR4V9B0TFA#api10=33053012340000&pm=2024-03&stream=oil&col=volume`

- Selector grammar is a fixed key/value list over declared key columns plus `col=`. No
  operators, no expressions, no eval — justification: the handle is attacker-reachable
  through `/explain` (`ab:360` names input validation as an open surface).
- A selector must resolve to at most one figure; `/explain` returns `422 selector_ambiguous`
  otherwise.

**`derivation_id` is content-addressed over the derivation *spec*:**

```
derivation_id = "drv_" + base32(sha256(canonical_json({
    operation, input_refs, params_hash, code_version, env_id,
    conformance_ruleset_hash, output_dataset, output_partition
}))[:12]).lower()          # 96 bits, ~19 chars
```

Justifications, in order of weight:
1. **Immutable, stable IDs** as API-04 requires (`ab:741-745`) — nothing about the output can change the ID.
2. **Free determinism detector.** A repeat run with an identical spec collides on the primary key; if the recorded `output_sha256` differs, the store raises `DeterminismViolation` and records both hashes. Non-determinism is caught in production, not just in CI (§4).
3. **Request-time dedupe** — identical scenarios/sensitivities cost one row.
4. Computable *before* the output exists, so a nested transform can name its parent.

### 1.4 Schema

`lineage.derivations` (PostgreSQL):

| Column | Type | Notes |
|---|---|---|
| `derivation_id` | text PK | content-addressed, §1.3 |
| `operation` | text NOT NULL | dotted, from a checked-in enum: `raw.fetch`, `stage.parse`, `canonical.promote`, `features.build`, `model.train`, `model.calibrate`, `forecast.batch`, `forecast.scenario`, `econ.value`, `econ.sensitivity`, `alloc.apply`, `typecurve.build`, `analog.index`, `analog.query`, `mart.refresh`, `tiles.build`, `ledger.grade`, `inventory.run` |
| `output_store` | text | `parquet` \| `postgres` \| `postgis` \| `duckdb_view` \| `file` \| `response` |
| `output_dataset` | text | e.g. `canonical.production_monthly` |
| `output_partition` | jsonb | key/value; empty for whole-dataset outputs |
| `output_locator` | text | path, table name, or `response` |
| `output_sha256` | text NULL | artifact hash; NULL for `response`-store rows |
| `output_rows` | bigint NULL | |
| `output_schema_version` | text | SB-01 owns the value |
| `params` | jsonb | small, fully serialized |
| `params_hash` | text | sha256 of canonical JSON (sorted keys, decimals as strings) |
| `code_version` | text | `git:<sha>` |
| `code_dirty` | boolean | true only when `GLASSWELL_ALLOW_DIRTY=1`; CI rejects any `true` |
| `env_id` | text FK → `lineage.environments` | §4.1 |
| `model_id` | text NULL FK → `lineage.models` | set for every operation whose output depends on a model |
| `recipe_id` | text FK → `lineage.recipes` | §4.1 |
| `created_vintage` | date | **knowledge-time**: max source vintage over all inputs, not wall clock |
| `created_at` | timestamptz | wall clock |
| `duration_ms` | integer | |
| `correlation_id` | text | ties every derivation and audit event in one run |
| `status` | text | `ok` \| `failed`; failed rows are retained |
| `determinism_class` | text | `D1` \| `D2` \| `D3` (§4.2) |
| `ttl_class` | text | `permanent` \| `ephemeral` (§1.6) |

`lineage.derivation_inputs` — the edge table, PK `(derivation_id, ord)`:

| Column | Type | Notes |
|---|---|---|
| `derivation_id` | text FK | |
| `ord` | int | stable ordering, part of the content address |
| `kind` | text | `derivation` \| `manifest` \| `rule` \| `model` \| `external` |
| `ref_id` | text | target id |
| `selector` | text NULL | narrows the input (e.g. a partition subset) |
| `as_of_vintage` | date NULL | the vintage this input was read at (§3.3) |
| `role` | text | `primary` \| `crosswalk` \| `validator` \| `calibration` \| `grid` |

`lineage.derivation_rules` — PK `(derivation_id, rule_id)`, plus `applied_rows bigint`.
Separated from `derivation_inputs` so "which derivations cite rule X" is one index scan —
that reverse index is the U21 path (`bp:226`).

Indexes: `derivations(output_dataset, output_partition jsonb_path_ops)` GIN;
`derivations(correlation_id)`; `derivation_inputs(ref_id)`; `derivation_rules(rule_id)`.

**Why Postgres and not DuckDB for the lineage store:** the access pattern is concurrent
point lookups and recursive-CTE traversal with a writer (pipeline) and a reader (API) live
at once. DuckDB is the single-writer analytics engine (`bp:142`, DIR-4) and is the wrong
shape for this. The lineage store is small (§1.5); it costs Postgres nothing.

### 1.5 Volume math

Inputs: 20k+ ND laterals (`bp:80`), ~4M ND production rows (`ai:48`), TX PDQ >25 GB
uncompressed (`ad:447`), NM nightly refresh across 15 tables (`ad:265-285,293`),
FracFocus business-daily (`ad:333`), raw zone ~15 GB (`ad:455`), 250 GB provisioned
(`ad:458`), 1 TB hdd-pool for raw + Parquet (`ai:530`).

**Manifests/year** (a manifest is created only when bytes change, §2.1):

| Source | Pull cadence | Artifacts/pull | Change rate | Manifests/yr |
|---|---|---|---|---|
| ND MPR XLSX | monthly (`ad:43`) | 1 | ~1.0 | ~12 |
| ND DMR GIS | weekly geometry / daily permits+rigs (`ad:68`) | 10 / 3 | ~1.0 | ~1,600 |
| TX PDQ | monthly (`ad:143-160`) | 1 | 1.0 | 12 |
| TX completions + permits | daily (`ad:197,215`) | 2 | ~1.0 | ~730 |
| TX wellbore + P-4 + GIS | weekly/monthly (`ad:184,193,228`) | ~5 | ~1.0 | ~300 |
| NM OCD FTP | nightly (`ad:293`) | 15 | ~0.6 | ~3,300 |
| FracFocus | business-daily (`ad:333`) | 2 | ~1.0 | ~520 |
| **Total** | | | | **≈ 6,500/yr** |

**Derivations/year:**

| Class | Count/yr | Reasoning |
|---|---|---|
| `raw.fetch` | ≈ 6,500 | one per created manifest (unchanged re-fetch → audit event only) |
| `stage.parse` | ≈ 6,500 | one per manifest |
| `canonical.promote` | ≈ 40,000 | one per (source, vintage, touched production-month); TX restatement window is 6–8 months (`ad:472`), so ≈ 8–11 partitions per production pull |
| `features.build` + `analog.index` | ≈ 200 | weekly |
| `model.train` / `calibrate` | ≈ 300 | 3 streams × basins × retrain cadence + experiments |
| `forecast.batch` | ≈ 500 | |
| `mart.refresh` + `tiles.build` | ≈ 3,000 | |
| `ledger.grade` | ≈ 2,000 | monthly re-grade per forecast cohort |
| **Pipeline total** | **≈ 60,000/yr** | |
| Request-time (scenarios, sensitivities, inventory slots, typecurves) | ≈ 20,000/yr | inventory dominates: ~300 derivations per township run (§1.6) |

At ~1.5 kB per `derivations` row plus ~0.3 kB per input edge (≈3 edges/row), that is
**≈ 130 MB/year including indexes**; five years < 1 GB, against 250 GB provisioned
(`ad:458`). The lineage store is not a capacity concern.

**The rejected alternative, quantified.** Per-figure lineage over ND alone: ~4M
production rows × ~6 numeric columns ≈ 2.4×10⁷ figures, before TX lease-level PDQ, marts,
forecasts, valuations and vintages. Realistic system total is **10⁷–10⁸ figures against
10⁵ derivations retained** — a ~10³ reduction. At 300 B/row that is ~10 GB of lineage rows
and a 10⁸-row join on every `/explain`; artifact-partition granularity turns the same
question into a ≤8-hop recursive CTE over ~10⁵ rows. **That factor is the whole design.**

### 1.6 Retention and TTL

- `ttl_class = permanent` — every pipeline derivation, and every request-time derivation
  referenced by a persisted artifact (ledger entry, saved valuation, inventory run, well set).
- `ttl_class = ephemeral` — request-time derivations with no persistent referrer. Swept
  after **90 days** by a nightly job. Justification: S5's agent loop (`bp:83`) and an
  unrate-limited `/scenarios` (`ab:327-329`) are an unbounded write source; the audit
  event for each call is retained forever, so the *fact* of the computation survives even
  when the row is swept.
- A sweep never removes a derivation that is an input to a surviving derivation
  (FK `ON DELETE RESTRICT`).
- Failed derivations (`status='failed'`) are retained permanently — a failed promotion is
  the most interesting thing in the audit trail.

### 1.7 Cross-store chains, and the analog-index fix

The derivation graph is **store-agnostic**: `output_store` + `output_locator` name where
the artifact lives, and edges reference `derivation_id`, never a store-native identifier.
A spacing figure computed in PostGIS (`bp:119`) and a cum12 aggregation computed in
DuckDB/Parquet therefore stitch into one chain with no adapter — this closes A-03's
"no stated mechanism for stitching a derivation across two engines" (`ab:564-570`).

**A-15 (analog index) is closed as a side effect** (`ab:658-664`): `analog.index` is a
recorded operation with an `output_sha256` over the serialized index (or over the feature
matrix when the index is in-process). The persist-vs-rebuild performance choice at
`bp:165` therefore no longer decides whether analogs can be served under R6 — the index
has a stable derivation id either way.

### 1.8 Worked example, and the S9 interaction budget

The hardest real chain in the system: a **TX well-month allocated oil volume** (lease-level
source, DIR-3 derived artifact, NAD27-era geometry in the crosswalk path).

```
figure  marts.well_month_allocated[api10=42383401230000, pm=2024-03, col=oil_bbl]
  └ drv_A  alloc.apply            model_id=alloc_v0_2026_07   rules=[cr_tx_lease_key]
      ├ drv_B  canonical.promote  canonical.production_monthly
      │        partition=(tx_rrc_pdq, vintage=2026-08-01, pm=2024-03)
      │        rules=[cr_pdq_delim, cr_tx_lease_key, cr_liquids_policy, cr_month_convention]
      │    └ drv_C  stage.parse   staging.pdq_lease_cycle
      │        └ man_9c3f…        PDQ_DSV.zip  3.55 GB  fetched 2026-08-01T05:02Z   ◀ terminal
      └ drv_D  canonical.promote  canonical.well_lease_link
           └ drv_E  stage.parse   staging.og_well_completion
                └ man_71ba…       OG_WELL_COMPLETION  fetched 2026-08-01T05:41Z      ◀ terminal
```

Depth 5, breadth 2 terminals, 5 conformance rules cited. Every rule row is already
evidenced: PDQ `}` delimiter (`ad:545`), TX composite lease key
`(OIL_GAS_CODE, DISTRICT_NO, LEASE_NO)` (`ad:549`), liquids policy (`bp:120`), month
convention (`bp:122`).

**S9 budget** (`bp:87`, "3 or fewer interactions and one `/explain` call"):

| Step | Action | Cost |
|---|---|---|
| 1 | Click the number in the UI → drawer opens → **the one `/explain` call**, `depth=full`, returns the whole graph above including terminal manifest records | 1 interaction, 1 explain call |
| 2 | Click a terminal manifest node → `GET /manifests/man_9c3f…` full record + acquisition URL | 1 interaction |
| 3 | *(spare)* Click a rule chip → `GET /conformance/cr_tx_lease_key` | 1 interaction |

S9 holds with one interaction in reserve. The agent path (`bp:83`) is a single
`GET /explain?h=…&depth=full`.

**Depth cap = 8.** The deepest realistic chain is 6 (allocated figure through a re-promoted
partition). `/explain` returns `truncated:true` beyond 8 and CI fails any handle that
truncates (§10). Justification: an uncapped recursive CTE is a resource-exhaustion surface,
and a chain deeper than 8 means someone built an unrecorded intermediate layer.

---

## 2. Manifest schema — the raw zone

The manifest is the terminal node of every lineage chain (`ab:623-628`) and the thing
Mandate B promises the visitor (`bp:18`). It has three jobs: identify bytes, record how
they were acquired, and record *when we learned them* — because no regulator dates their
artifacts reliably (`ad:294,555`, DIR-9).

### 2.1 Identity and idempotency (closes A-10)

**Manifest identity is the content hash. A fetch is an event, not an identity.**

```
manifest_id = "man_" + sha256_hex[:32]      # 128 bits
```

Fetch algorithm — the normal path, not the edge case:

```
1. resolve_url(source_id, source_key)        # GUID resolution for RRC MFT (§2.4)
2. conditional GET / FTP fetch to a temp file      # ETag/Last-Modified when offered
3. sha256 the bytes
4. if sha256 already in lineage.manifests:
       emit audit  raw.fetch_verified_unchanged {manifest_id, checked_at, method}
       discard temp; NO new manifest; NO new derivation; NO re-parse
5. else:
       write raw zone (§2.3), chmod 0444
       insert manifest with supersedes_manifest_id = current head for (source_id, source_key)
       emit audit  raw.manifest_created  (+ raw.manifest_superseded when head existed)
       record derivation raw.fetch
       enqueue stage.parse for this manifest
```

Consequences, stated plainly because they are the whole point:

- **Re-fetch of identical bytes is a no-op with a recorded check** — step 4. The check is
  the evidence; "we looked and nothing changed" is a first-class fact.
- **Changed bytes under the same source name are a NEW manifest plus a supersedes link** —
  step 5. NM OCD overwrites `<table>.zip` in place with undated filenames every night
  (`ad:294,298-306`), so this is the **common** path, roughly 3,300 times a year (§1.5),
  not an exception branch.
- **Nothing is ever overwritten in the raw zone.** Supersession is a link between two
  immutable artifacts.
- **`mod_dte` is a promotion optimisation, not a lineage concept** (`ad:306`). The whole
  NM zip still gets one manifest; row-level delta detection lives in SB-01's promotion
  step and shows up in lineage only as `applied_rows` and a `canonical.restatement_detected`
  audit event.

### 2.2 Schema

`lineage.manifests`:

| Column | Type | Notes |
|---|---|---|
| `manifest_id` | text PK | `man_<sha256[:32]>` |
| `sha256` | text UNIQUE | full 64 hex |
| `bytes` | bigint | |
| `source_id` | text FK → `lineage.sources` | e.g. `nd_mpr_xlsx`, `tx_pdq_dsv`, `nm_ocd_wcproduction`, `fracfocus_csv`, `nd_gis_horizontals_line` |
| `source_key` | text | the upstream slot that gets overwritten: `2024_03.xlsx`, `wcproduction.zip`, `PDQ_DSV.zip` |
| `acquisition_url` | text | the exact URL fetched |
| `acquisition_method` | text | `https_get` \| `ftp_anon` \| `mft_guid_resolve` \| `click_wall_accept` |
| `acquisition_params` | jsonb | §2.4 |
| `fetched_at` | timestamptz | **self-stamped** at fetch completion, UTC (DIR-9, `ad:294`) |
| `fetch_vintage` | date | `fetched_at::date` — the knowledge-time label used everywhere downstream |
| `upstream_mtime` | timestamptz NULL | when the source offers one (NM FTP does, `ad:269-283`; the ND MPR index does not) |
| `upstream_etag` | text NULL | |
| `media_type` | text | |
| `decompressed_inventory` | jsonb | `[{path, bytes, sha256, media_type}]` for archive members |
| `supersedes_manifest_id` | text NULL FK | previous head for `(source_id, source_key)` |
| `storage_uri` | text | raw-zone path, §2.3 |
| `license_note` | text | free-text, seeded from `ad:407-419` |
| `redistributable` | boolean | false by default; gates `/manifests/{id}/bytes` (§9.6) |
| `fetch_derivation_id` | text FK | the `raw.fetch` derivation |
| `staging_load_ref` | text NULL FK | the `stage.parse` derivation; NULL until parsed |
| `integrity_verified_at` | timestamptz NULL | last successful re-hash (§2.6) |

Archive members are addressable as `man_9c3f…#members/wcproduction.xml` and are **not**
separate manifest rows. Justification: one NM pull would otherwise create 15 manifests
where one artifact was fetched; member sha256s in the inventory give identical
verifiability at a fifteenth of the rows. GIN index on the inventory for member lookup.

**View `lineage.manifest_head`**: latest non-superseded manifest per `(source_id, source_key)`,
which is what an ingest job compares against.

### 2.3 Raw-zone layout — the co-location contract with SB-06

```
/data/raw/                                       # 1 TB hdd-pool zvol (ai:530)
  <source_id>/
    <source_key_slug>/
      <fetch_vintage>T<hhmmss>Z-<sha256[:12]>/
        payload.<ext>          0444
        manifest.json          0444   ← byte-identical serialization of the DB row
```

Contract:
1. **Files and manifests are co-located.** `manifest.json` is written in the same directory
   as its payload and is the byte-identical canonical JSON of the `lineage.manifests` row.
   Postgres is the index; the filesystem is the truth. A restored VM with an empty database
   can rebuild `lineage.manifests` by walking the tree.
2. **Directory names are unique by construction** (vintage + time + hash prefix), so two
   fetches on the same day of different bytes never collide.
3. **Mode 0444, directories 0555, owned by the pipeline role.** WORM by convention plus
   the integrity job (§2.6); the spine does not ask SB-06 for a WORM filesystem —
   justification: on a single VM with a single owner, immutable-mode filesystems buy
   ceremony, not safety.
4. **Backups of `/data/raw` are non-negotiable** (SB-06, `ab:331-334`): every other layer is
   reproducible from it and it is reproducible from nothing — NM and FracFocus retain no
   upstream history (`ad:298-306,349,501`).

### 2.4 Acquisition methods

| Method | Sources | `acquisition_params` records |
|---|---|---|
| `https_get` | ND MPR, ND GIS, TX GIS direct | `{status, content_length, etag, last_modified, redirect_chain}` |
| `ftp_anon` | NM OCD `164.64.106.6` (`ad:259-260`) | `{host, path, ftp_mtime, ftp_size, host_resolved_from}` |
| `mft_guid_resolve` | all TX RRC bulk (`ad:246`) | `{dataset_page_url, dataset_page_sha256, resolved_guid, listing_page_sha256, resolved_at, listing_row}` |
| `click_wall_accept` | FracFocus (`ad:330`) | `{terms_url, terms_sha256, accepted_at}` |

**RRC MFT GUID resolution is a lineage-visible step**, not a hidden detail. RRC bulk data
sits behind opaque GUIDs (`https://mft.rrc.texas.gov/link/<uuid>`) that are published only
on the dataset page, are not stable predictable URLs, and can rotate without notice
(`ad:246,536-539`). Therefore:

- The resolver hashes the dataset page and the portal listing page, and records both in
  `acquisition_params`. A silent GUID rotation shows up as a listing-page hash change in
  the manifest of the *next* successful fetch — visible in lineage rather than as a
  mystery 404.
- Resolution emits `raw.guid_resolved`; a resolution failure emits `raw.fetch_failed` with
  `reason=guid_unresolved`, which is a monitored condition for SB-06.
- The `.gz` variants are the only refreshed wellbore artifacts (`ad:193`); the format pin
  is a `parse_directive` conformance rule (§6.1), not a code constant.

### 2.5 Supersession semantics

- `supersedes_manifest_id` forms a per-`(source_id, source_key)` chain. Chains are never
  broken or rewritten.
- A new manifest **never invalidates** a prior derivation. Existing derivations keep
  citing the manifest they actually read. A restatement produces a *new* vintage of
  canonical rows (§3), leaving the old ones addressable forever.
- ND publishes the same report in two formats that disagree because they were generated at
  different vintages (`ad:480-486`). Both are ingested and both get manifests; **which one
  feeds canonical is a `parse_directive` conformance rule** (`format_pin`), cited in every
  ND promotion derivation. That is the natural `/explain` demonstration for S9
  (`ad:486`) and it is registry-driven, not code-driven.

### 2.6 Integrity verification

`glasswell lineage verify-raw [--sample N | --chain <handle> | --all]`:
re-hashes payloads, compares to `lineage.manifests.sha256`, updates
`integrity_verified_at`, emits `raw.integrity_verified` / `raw.integrity_failed`.
Runs nightly over a rotating sample sized to cover the whole raw zone monthly, and in full
over every manifest reachable from a served figure before a release. Justification: a
checksum recorded once and never re-checked is a claim, not a guarantee — and `bp:18`
sells the guarantee.

---

## 3. Bitemporal vintages (DIR-2 made concrete)

Restatement is confirmed for all three regulators, in three different mechanisms
(`ad:462-501`), and TX states outright that **"there is no point beyond which an operator
may not file corrected production reports"** (`ad:472`). DIR-2 is therefore not a
preference; it is forced.

### 3.1 Which tables get vintages

**Rule: a table carries `report_vintage` if and only if its upstream source restates.**

| Vintaged | Not vintaged |
|---|---|
| `canonical.production_monthly` (all three regulators restate) | `canonical.wells`, `operators`, `formations` — dimensional; corrections are rare and handled as new rows with `effective_from` |
| `canonical.completion_events` (TX W-2 amendments, `ad:197`) | `conformance_rules` — append-only with `effective_from`/`supersedes` (`bp:162`) |
| `canonical.permits` (status transitions) | `crs_registry`, `formation_aliases`, `operator_aliases` — same |
| `canonical.frac_disclosures` (retroactive corrections, `ad:349`) | Derived artifacts — they carry their *inputs'* vintages via the derivation, not their own |

Justification: universal bitemporality doubles the key of every table for a property most
of them do not have. DIR-1 asks what a hostile reviewer cannot dismantle; "we vintage the
things that restate, and here is the evidence each one does" survives that better than
"we vintage everything" does.

### 3.2 Schema and change-only append

```sql
canonical.production_monthly (
  api10               text        not null,
  production_month    date        not null,   -- VALID time
  stream              text        not null,   -- oil | gas | water
  source_id           text        not null,
  report_vintage      date        not null,   -- KNOWLEDGE time = manifest.fetch_vintage
  volume              numeric(18,3) not null, -- DECIMAL, not float (§4.4)
  unit                text        not null,
  days_produced       smallint,
  granularity         text        not null,   -- well_observed | lease_reported (DIR-3)
  value_hash          text        not null,   -- sha256 over the mutable payload columns
  source_manifest_id  text        not null,
  derivation_id       text        not null,
  primary key (api10, production_month, stream, source_id, report_vintage)
)
```

- **Vocabulary:** `production_month` is valid time; `report_vintage` is knowledge time.
  Used consistently in schema, API, and prose — DIR-8 gets both as glossary rows.
- **Change-only append.** A promotion inserts a row only when `value_hash` differs from
  the current head for `(api10, production_month, stream, source_id)`. Unchanged
  observations do not append. Volume consequence: ~4M ND rows plus restatement churn
  (a minority of (well, month) pairs, `ad:470-472`), not 4M × vintages.
- **Never updated, never deleted.** Enforced by the same role-grant pattern as the audit
  stream (§5.1).

`lineage.vintages` — one row per (source, vintage) promotion, the thing `/explain` and the
ledger cite:

| Column | Notes |
|---|---|
| `vintage_id` | `vin_<source_id>_<date>` |
| `source_id`, `vintage_date` | |
| `manifest_ids` | text[] — the artifacts that opened it |
| `opened_at`, `promotion_derivation_id` | |
| `rows_examined`, `rows_appended`, `months_touched` | restatement magnitude, feeds the scorecard |
| `restatement_summary` | jsonb: `{production_month: changed_rows}` |

### 3.3 As-of query semantics

Two access paths, both defined once in `glasswell.lineage.vintages`:

```sql
-- default serving view
create view canonical.production_monthly_latest as
select * from canonical.production_monthly
qualify row_number() over (
  partition by api10, production_month, stream, source_id
  order by report_vintage desc) = 1;

-- as-of: the state of knowledge on a given date
-- vintages.as_of(v) → same window with  where report_vintage <= v
```

- Serving default is **latest**; every response carries the `report_vintage` actually used
  per series (§9.1). Justification: a UI that silently mixes vintages is the failure
  DIR-2 exists to prevent.
- `?as_of=YYYY-MM-DD` is supported on production-serving endpoints (SB-04 owns the
  parameter's placement); the spine owns the semantics: *greatest vintage ≤ as_of*, applied
  per (well, month, stream, source).
- DuckDB and Postgres both express this as a window function; no temporal extension is
  used (§13).

### 3.4 How `/explain` answers "which vintage did this train on"

Three linked facts, all already in the schema:

1. Every read of a vintaged dataset records `as_of_vintage` on the **input edge**
   (`lineage.derivation_inputs.as_of_vintage`, §1.4).
2. Every derivation records `created_vintage` = max input vintage — the knowledge-time of
   the artifact as a whole.
3. `lineage.models.training_data_vintage` (jsonb, `{source_id: vintage_date}`) restates the
   same fact at model granularity for fast lookup (§7).

So the answer is one hop from the forecast's handle: `/explain` on a forecast figure
returns the `model.train` node, whose input edges carry `as_of_vintage` per source and
whose params carry the training window. No extra machinery, no second index.

### 3.5 Forecast ledger: trained-on vs graded-against

`ledger.grade` is a recorded operation, and a grade is an **event**, not a mutable score.

| Column (SB-02 owns the metrics, spine owns the identity) | Notes |
|---|---|
| `grade_id` | |
| `forecast_derivation_id` | the forecast being graded |
| `model_id`, `trained_on_vintage` | copied from the model registry at grade time |
| `graded_against_vintage` | the actuals vintage used |
| `graded_at`, `grade_derivation_id` | |
| `metrics` | jsonb |

Rules:

- **Grade against latest vintage at grading time; record both vintages.** A forecast is
  never re-scored in place.
- **Re-grading appends.** The same forecast graded against a later vintage is a new row —
  the restatement-as-new-event pattern applied to grading (`bp:101`).
- **Restatement drift is separable from model error.** Grading the same forecast against
  two vintages yields Δ(metric) attributable to the actuals moving rather than the model
  being wrong. This is the direct answer to `ab:598-602` ("a track record that grades
  against a moving target is not a track record") and it is a *reportable number*, not a
  caveat — recommended as a quality-scorecard row (`bp:86`).

### 3.6 What was deliberately not built

- **No SQL:2011 system-versioned tables.** Postgres has no native support and DuckDB has
  none at all; append + window view is the same semantics with zero machinery.
- **No third temporal axis for the ruleset.** Re-promotion under a corrected rule appends
  rows at the *same* `report_vintage` with a new `derivation_id`; the latest view breaks
  ties on `(report_vintage desc, created_at desc)`. The ruleset dimension is
  **lineage-visible, not query-visible** — justification: no S-criterion asks
  "what would this number have been under last month's rules", and tri-temporal keys would
  land in every downstream join. Revisit only if a rule correction ever needs to be shown
  side-by-side in the product.

---

## 4. Recipes and determinism

### 4.1 Recipe

A recipe is the closure required to regenerate an artifact. It is derived from the
derivation, stored once, and served at `/recipes/{recipe_id}`.

```json
{
  "recipe_id": "rcp_5H2K…",
  "operation": "canonical.promote",
  "output": {"dataset": "canonical.production_monthly",
             "partition": {"source_id": "nd_mpr_xlsx", "report_vintage": "2026-08-01",
                           "production_month": "2024-03"},
             "sha256": "…", "determinism_class": "D1"},
  "inputs": [{"kind": "manifest", "id": "man_9c3f…", "sha256": "…"},
             {"kind": "derivation", "id": "drv_C…", "output_sha256": "…"}],
  "conformance_rules": ["cr_nd_format_pin", "cr_month_convention", "cr_liquids_policy"],
  "params": {"month_convention": "production_month", "volume_type": "numeric(18,3)"},
  "params_hash": "sha256:…",
  "code_version": "git:9f2c1ab", "code_dirty": false,
  "seeds": {"global": 20260801, "numpy": 20260801, "lightgbm": 20260801},
  "environment": {"env_id": "env_ubuntu2404_py312_2026w32",
                  "image_digest": "sha256:…", "python": "3.12.7",
                  "lockfile_sha256": "…", "threads": 1,
                  "cpu_model": "Intel Xeon E5-26xx v4", "tz": "UTC", "locale": "C"},
  "replay": "glasswell repro rcp_5H2K…"
}
```

`lineage.environments` is a first-class table (`env_id`, image digest, lockfile hash,
python version, thread pin, CPU model, created_at) supplied by SB-06's build pipeline.
Justification: an environment that is not identified cannot be pinned, and A-14 fails on
exactly that (`ab:650-656`).

### 4.2 Determinism classes — the honest table

**`bp:99` as written ("every artifact carries the recipe that regenerates it
byte-for-byte") is not achievable for every artifact class.** Rather than quietly
under-deliver, the spine defines three classes and states which artifacts land where.

| Class | Guarantee | Artifacts | Check |
|---|---|---|---|
| **D1 byte-identical** | Replay in *any* pinned environment produces identical bytes | Raw manifests (by construction); all staging/canonical/mart Parquet; type-curve artifacts; feature matrices; recipe and manifest JSON | `sha256(replayed) == output_sha256` |
| **D2 environment-pinned byte-identical, otherwise prediction-equivalent** | Same `env_id` + same CPU → identical bytes. Different env → predictions equal within a recorded tolerance | LightGBM model artifacts; conformal calibration artifacts | same-env: sha256 equality. cross-env: max abs deviation over a stored probe set ≤ `probe_tolerance` |
| **D3 semantically identical after normalization** | Volatile fields removed, floats rounded to declared precision, sets compared order-insensitively | API responses; vector tiles; anything embedding wall-clock or request identity | canonical-form diff against a declared `volatile_fields` list per endpoint/layer |

D1 is achievable because of four enforced conditions, none of which is optional:
pinned library versions via the lockfile hash; **fixed compression codec and level**
(zstd-3) with no dictionary autotuning; **explicit output sort order** on every write;
and **no wall-clock or hostname embedded in artifact content** (`created_by` metadata is
pinned by the library version, and the pipeline writes no custom key/value metadata that
varies per run).

### 4.3 LightGBM specifics, not hand-waved

LightGBM (DIR-4) is deterministic only under a specific configuration, and only within one
build:

- Required training params: `deterministic=true`, `force_row_wise=true`, `num_threads=<pinned>`,
  `seed`/`bagging_seed`/`feature_fraction_seed` all set from the recipe's `seeds`, and
  `data_random_seed` set. Recorded in `params`, not defaulted in code.
- `deterministic=true` costs training throughput. Accepted: a model is trained rarely and
  its reproducibility is the product (`bp:99`, `bp:18`).
- Determinism does **not** survive a LightGBM version change, an OpenMP/thread-count
  change, or a different CPU instruction path. Therefore D2, not D1, and the tolerance is
  a recorded property of the model, not a global constant.
- **Probe set:** at model registration, predictions over a stored, versioned probe set
  (N = 1,000 feature rows, itself a D1 artifact with its own manifest-free derivation) are
  saved. Cross-environment replay asserts max abs deviation ≤ `probe_tolerance`
  (default 1e-9 same-arch, recorded per model otherwise). A replay that exceeds tolerance
  is a **failed** replay and is reported as such — not silently accepted.
- Conformal calibration inherits the class of the model it calibrates.

### 4.4 Numeric type policy (removes a whole nondeterminism class)

- **Volumes and money are DECIMAL, never binary float.** Regulator volumes are integers in
  bbl/mcf; canonical stores `numeric(18,3)`; economics uses DECIMAL with a declared
  rounding mode per calculation step. Justification: float summation order varies with
  DuckDB's parallel scan plan, so a float aggregate is *not* reproducible across thread
  counts — DECIMAL makes the aggregate order-independent and removes the need to pin
  threads for D1 correctness.
- Floats remain acceptable for model features, model outputs, and geometry, all of which
  are D2/D3.
- Pipeline sessions still pin `SET threads` for D1 Parquet writes (row order), and record
  it in the environment.

### 4.5 Replay

`glasswell repro <recipe_id> [--into <dir>] [--check]` — CLI, not an API job.

1. Verify `env_id` matches the current environment (or `--allow-env-drift`, which downgrades
   the expected class from D1/D2 to D3 and says so in the output).
2. Materialize inputs from the raw zone / prior artifacts, verifying each sha256.
3. Execute the operation.
4. Compare per the artifact's determinism class; print a pass/fail table.
5. Emit `repro.attempted` / `repro.succeeded` / `repro.failed` audit events.

**Replay is CLI-only, deliberately.** `POST /recipes/{id}/verify` would require an async job
contract, run states, cancellation and a queue on one VM (API-02, `ab:733-736`). The
stranger of S1 gets the recipe document and replays it in their own environment — which is
the stronger claim anyway.

### 4.6 Required blueprint amendment

`bp:99` must be amended in v0.6 (change-controlled, `bp:288`) to:

> **Reproducibility is an output.** Every artifact carries the recipe that regenerates it,
> and a declared determinism class: byte-identical (data artifacts), environment-pinned
> byte-identical with cross-environment prediction equivalence within a recorded tolerance
> (model artifacts), or semantically identical after declared normalization (responses,
> tiles).

Justification: a hostile reviewer will test the byte-for-byte claim against a LightGBM
artifact first. Stating the limit precisely is stronger than a promise that fails on
inspection, and the failure mode of the current wording is exactly the credibility loss
Mandate B cannot afford (`bp:18-20`).

---

## 5. Audit stream

One stream (`bp:101`). Every consequential state change in the system appears in it.

### 5.1 Schema and append-only enforcement

```sql
lineage.audit_events (
  event_id        text primary key,          -- ULID: time-ordered, no coordination
  occurred_at     timestamptz not null,
  actor           text not null,             -- system:ingest | system:promote | system:model
                                             -- | user:owner | agent:<token_id>
  event_type      text not null,             -- dotted, from a checked-in enum
  subject_type    text not null,             -- manifest|derivation|rule|model|quarantine
                                             -- |vintage|key|config|aoi|wellset|ledger
  subject_id      text not null,
  correlation_id  text,                      -- run id; joins to derivations
  payload         jsonb not null default '{}'
) partition by range (occurred_at);
```

Append-only is enforced twice:
1. **Role grants.** `glasswell_pipeline` and `glasswell_api` hold `INSERT, SELECT` and are
   explicitly `REVOKE UPDATE, DELETE`. Only the migration role can alter the table. This is
   the primary guarantee.
2. **Trigger.** `BEFORE UPDATE OR DELETE` raises `append_only_violation`. Belt and braces
   against a future role misconfiguration.

Monthly range partitions, created a month ahead by the scheduler. Justification: partition
pruning keeps `/audit?since=` cheap, and the whole stream is <10⁵ rows/year anyway.

### 5.2 Event taxonomy and emitters

| Emitter | Events |
|---|---|
| Ingest (SB-01) | `raw.fetch_attempted`, `raw.fetch_verified_unchanged`, `raw.manifest_created`, `raw.manifest_superseded`, `raw.guid_resolved`, `raw.fetch_failed`, `raw.integrity_verified`, `raw.integrity_failed` |
| Staging (SB-01) | `staging.load_completed`, `staging.load_failed`, `staging.rows_quarantined` |
| Promotion (SB-01) | `canonical.promotion_completed`, `canonical.vintage_opened`, `canonical.restatement_detected`, `canonical.repromotion_required` |
| Conformance (SB-01) | `conformance.rule_added`, `conformance.rule_superseded`, `conformance.rule_applied_summary` |
| Quarantine (SB-01) | `quarantine.opened`, `quarantine.reoccurred`, `quarantine.released`, `quarantine.accepted_loss` |
| Modeling (SB-02) | `model.training_started`, `model.training_completed`, `model.registered`, `model.promoted`, `model.retired`, `ledger.graded` |
| Marts / tiles (SB-01/05) | `mart.refreshed`, `mart.invalidated`, `tiles.built` |
| API (SB-04) | `key.issued`, `key.revoked`, `access.denied`, `config.changed` |
| Repro (spine) | `repro.attempted`, `repro.succeeded`, `repro.failed` |

**Derivations do not emit a per-derivation audit event.** Audit records *run-level* facts
and references derivation ids in the payload. Justification: the derivations table is
already the per-artifact record; duplicating 60k rows/year into audit buys nothing and
doubles the write path.

### 5.3 Volume, retention, backup

Order 10⁴–10⁵ events/year at ~0.5 kB → tens of MB/year. **Retention is permanent** — the
stream is the append-only memory (`bp:101`) and the only answer to "what did we believe in
month N" (`ad:501`). Audit and lineage tables are in SB-06's backup set alongside
`/data/raw`; everything else in Postgres is reproducible.

### 5.4 Restatement as a new event

`canonical.restatement_detected` carries:

```json
{"source_id":"nm_ocd_wcproduction","prior_manifest":"man_71ba…","new_manifest":"man_9c3f…",
 "report_vintage":"2026-08-20","rows_examined":4118203,"rows_appended":9412,
 "months_touched":["2026-05","2026-04","2026-03","2026-02"],
 "detection_key":"mod_dte","downstream":["mart.well_month_allocated","forecasts.batch"]}
```

It is the trigger for `mart.invalidated` (recorded, then recomputed on the next scheduled
run — §14) and for ledger re-grading (§3.5). It is never an update to a prior event, and
the prior vintage's rows remain queryable forever.

---

## 6. Conformance registry — runtime enforcement (closes D-09)

D-09 is precise: `bp:267`'s "reads rules from the table at run time **where feasible**"
guts R8, and a coverage check cannot detect a rule row whose text has diverged from the
code (`ab:479-486`). The fix is to make most rule kinds **structurally undriftable** and to
make the remainder **mechanically drift-detectable** — and to say plainly which is which.

### 6.1 Typed rule kinds

`conformance_rules` gains `rule_kind` and a typed `spec` jsonb. Eight kinds, each with a
JSON schema and a loader in `glasswell.lineage.conformance`:

| Kind | `spec` shape | Real seeds |
|---|---|---|
| `unit_conform` | `{from_unit, to_unit, factor, rounding, conditions_note}` | gas to mcf at stated conditions, conditions recorded not normalized (`bp:121`) |
| `vocab_map` | `{mapping_table, key_col, value_col, unmapped_action}` | well-status vocabularies to a small canonical set (`bp:124`); condensate/oil classification + `liquids_policy` tag (`bp:120`) |
| `alias_join` | `{alias_table, key_cols, target_col, min_confidence, unmatched_action}` | `formation_aliases` (`bp:123`); `operator_aliases` (§6.4, closes A-12) |
| `datum_transform` | `{detect: {…}, source_epsg, target_epsg, pipeline, grid_manifest_id}` | NAD27 → EPSG:4326 per file vintage (`bp:118`, `ad:584-586`); `crs_registry` compute CRS (`bp:119`) |
| `key_composite` | `{cols[], separator, uniqueness_scope}` | TX `(OIL_GAS_CODE, DISTRICT_NO, LEASE_NO)` — bare `LEASE_NO` collides across districts (`ad:549`) |
| `parse_directive` | `{delimiter, encoding, format_pin, header_policy, member_glob}` | PDQ `}` delimiter (`ad:545`); EBCDIC wellbore; ND XLSX-vs-PDF format pin (`ad:480-486`); RRC `.gz`-only rule (`ad:193`) |
| `validity_filter` | `{predicate_ast, on_fail: quarantine\|drop_flag, reason_code}` | NM even-numbered county codes must not be filtered out (`ad:316`); impossible volumes; date ranges |
| `code_ref` | `{module_function, version, source_sha256, contract_note}` | allocation apportionment; wellbore-policy detection (`bp:128`); PDF table extraction; month-convention resolution where it is conditional |

`predicate_ast` is an **allowlisted AST**, not a DSL: node types `and|or|not|cmp|in|between|is_null|regex_match`, leaves are column references and literals, compiled to a Polars expression by the loader. No `eval`, no arbitrary attribute access. Justification: rules are data and data is attacker-reachable (`ab:356-360`); a general expression language is a code-execution surface for a handful of predicates.

### 6.2 Row schema

`conformance_rules` (SB-01 owns content; the spine owns these columns):

| Column | Notes |
|---|---|
| `rule_id` | `cr_<slug>_<n>` — **immutable**; a change means a new row |
| `rule_family` | groups versions for `/conformance` display |
| `supersedes_rule_id` | version chain |
| `source_id`, `applies_to_fields` text[] | drives the coverage check (§10) |
| `rule_kind`, `spec` jsonb | §6.1 |
| `rule` text, `rationale` text | human-readable, as `bp:116` requires |
| `evidence_url`, `evidence_sha256` | primary-source citation (`ad:606`) |
| `effective_from`, `effective_to` | `bp:162` |
| `code_ref`, `code_ref_sha256` | `code_ref` kind only |
| `created_by_event_id` | audit link |

Rules are append-only. Editing a rule in place is impossible by grant, as with audit (§5.1).

### 6.3 The guarantee, by kind — stated plainly

| Kinds | Guarantee | Mechanism |
|---|---|---|
| `unit_conform`, `vocab_map`, `alias_join`, `datum_transform`, `key_composite`, `parse_directive`, `validity_filter` | **Drift is structurally impossible.** There is no second place the value can live. | Promotion code contains no literal for these decisions; it calls `apply_rules()`, which loads rows and executes typed specs. Reinforced by a CI constant-denylist grep over `glasswell/parse/**` and `glasswell/promote/**` (EPSG codes, unit factors, delimiter literals, state codes, district literals) outside the loader module. |
| `code_ref` | **Drift is detectable, not impossible.** CI proves the referenced code has not changed since the row was written; it does **not** prove the prose rationale describes what the code does. | CI asserts: (a) the symbol imports, (b) `module.__rule_version__ == spec.version`, (c) `sha256(inspect.getsource(fn)) == code_ref_sha256`. Changing the function without updating the rule row fails CI; updating the row forces a human to re-read the rationale. |

That second row is the honest limit of D-09's fix, and it is stated in the blueprint rather
than buried: **`bp:267`'s "where feasible" is replaced by "table-driven for seven kinds;
hash-pinned code references for the eighth"**, which is a testable claim rather than an
escape hatch. Recommended R8 amendment for SB-00:

> **R8 (conformance as data).** Every cross-source mapping decision is an immutable
> `conformance_rules` row served at `/conformance` and cited by the derivations it shaped.
> Rules of table-driven kinds are executed from the row; rules whose logic cannot be
> table-driven carry a hash-pinned code reference that CI verifies. A mapping decision that
> exists only in code fails CI, not merely review.

### 6.4 Registry citizens

`crs_registry`, `formation_aliases` and `operator_aliases` are lineage-visible registries,
not loose tables:

| Registry | Role | Lineage treatment |
|---|---|---|
| `crs_registry` | compute CRS per basin — ND UTM 14N, Permian UTM 13N, storage always 4326 (`bp:119`) | referenced by `datum_transform` specs; each row change is a new `conformance_rules` version; the NTv2/NADCON grid file used by the transform **has its own manifest** (`grid_manifest_id`), so a datum transform's chain terminates in checksummed bytes like any other |
| `formation_aliases` | reported name → canonical formation, with confidence (`bp:123`) | `alias_join` spec target; unmatched rows quarantine with `alias_unresolved` |
| `operator_aliases` | **new** — resolves ND DMR names, RRC operator numbers, NM OGRID identifiers, plus name changes, subsidiaries and M&A across the vintage window | `alias_join` spec target. Closes A-12 (`ab:630-637`): `/operators/league` (`bp:177`) is not computable without it, and DIR-5's residual metric aggregates by operator |

Every alias table row carries `effective_from` so an M&A event is a new mapping rather than
a rewrite of history — the same append-only discipline as everything else.

### 6.5 Rule change → re-promotion (closes G-15)

1. New rule row inserted (`conformance.rule_added` / `rule_superseded`).
2. The spine computes the affected surface: derivations citing the superseded rule
   (one index scan on `derivation_rules`), and their downstream closure.
3. `canonical.repromotion_required` audit event lists affected partitions.
4. Re-promotion appends new canonical rows at the same `report_vintage` with a new
   `derivation_id` (§3.6); downstream marts are invalidated and rebuilt on the next
   scheduled run.
5. Quarantined rows whose `rule_id` matches are candidates for release (§8.3).

---

## 7. Model registry (interface only — SB-02 owns training)

Closes A-01 (`ab:551-556`). The spine owns model **identity and lineage**; it owns no
training logic and no metric definitions.

`lineage.models`:

| Column | Notes |
|---|---|
| `model_id` | `mdl_<ulid>` — registry identity, stable across re-registration attempts |
| `artifact_sha256`, `artifact_uri` | the trained file; content-addressed for verification |
| `algo`, `algo_version` | `lightgbm_quantile`, library version string |
| `target` | `oil` \| `gas` \| `water` \| `allocation` (allocation models are registry citizens — DIR-3 requires a versioned allocation model) |
| `basin`, `feature_version`, `feature_set_hash` | |
| `training_window` | `{from_production_month, to_production_month}` |
| `training_data_vintage` | jsonb `{source_id: vintage_date}` — the §3.4 fast path |
| `holdout_def` | jsonb: temporal split spec per protocol 4A (`bp:190`) |
| `hyperparams`, `seeds` | jsonb; must include the §4.3 determinism params |
| `env_id`, `determinism_class` | `D2` for LightGBM |
| `probe_set_ref`, `probe_tolerance` | §4.3 |
| `calibration_report_ref` | derivation id of the `model.calibrate` run (conformal coverage report) |
| `conformal_alpha`, `coverage_observed` | |
| `training_derivation_id` | the `model.train` derivation |
| `promotion_status` | `candidate` \| `shadow` \| `promoted` \| `retired` |
| `promoted_at`, `retired_at`, `supersedes_model_id` | |
| `error_bounds` | jsonb — for allocation models, the measured bounds from **both** validators (`bp:84`, DIR-3) |

Spine-enforced invariants:

- **Model rows are immutable except `promotion_status` and the two timestamps.** Retraining
  creates a new row with `supersedes_model_id`; it never mutates a prior model. An old
  forecast therefore remains re-derivable after a retrain — the thing A-01 says is
  currently impossible.
- **A forecast may not be served from a model that is not `promoted`**, unless the
  derivation is explicitly flagged `shadow=true` and the response marks it. Enforced in
  `resolve_model()`, not in each caller.
- **Every forecast, valuation, inventory slot and allocated volume carries `model_id`** in
  its derivation, and DIR-3's granularity flag plus `error_bounds` propagate into the
  figure envelope (§9.1).
- `GET /models` and `GET /models/{id}` are read-only registry views (`ab:715` names them as
  required-but-unspecified endpoints).

---

## 8. Quarantine

"The kitchen is the product. … The quarantine table has an endpoint" (`bp:98`).
A-16 (`ab:666-671`) is that exposure exists without a workflow. Both are fixed here.

### 8.1 Schema

`lineage.quarantine_rows`:

| Column | Notes |
|---|---|
| `quarantine_id` | |
| `row_fingerprint` | sha256 over the canonically-serialized source row — **dedupes across re-pulls**, so a row rejected nightly for a year is one entry with `occurrence_count`, not 365 entries |
| `source_id`, `staging_table`, `stage` | `parse` \| `validate` \| `conform` \| `join` |
| `reason_code` | enum, §8.2 |
| `rule_id` | the conformance rule that rejected it; NULL for parse failures |
| `row_payload` | jsonb, capped at 8 kB; oversized rows store `{manifest_id, byte_offset, length}` instead |
| `first_seen_at`, `first_seen_manifest_id` | |
| `last_seen_at`, `last_seen_manifest_id`, `occurrence_count` | |
| `state` | `open` \| `released` \| `accepted_loss` \| `superseded` |
| `released_by_rule_id`, `released_at`, `release_derivation_id` | |
| `notes` | |

### 8.2 Reason codes (seed set)

`parse_error` · `encoding_error` · `schema_mismatch` · `unknown_vocab` ·
`alias_unresolved` · `datum_undetermined` · `key_collision` (bare TX `LEASE_NO`, `ad:549`) ·
`multi_wellbore_policy` (`bp:128`) · `impossible_volume` · `orphan_fk` ·
`confidential_withheld` (ND withholds confidential-well production — `ab:646`) ·
`duplicate_row` · `out_of_range_date` · `unreliable_numeric` (FracFocus TVD /
base-water-volume, `ad:344`).

**Rejects are quarantined with a reason, never dropped** — project rule, `CLAUDE.md`.

### 8.3 Release loop

`release_quarantine(reason_code | rule_id | quarantine_id[])`:

1. Resolve affected rows and their **original manifests**.
2. Re-run parse/promotion **from the manifest**, never from `row_payload` — the payload is
   a diagnostic copy, the manifest is truth.
3. Rows that now pass: `state='released'`, `released_by_rule_id`, `release_derivation_id`.
4. Emit `quarantine.released` with counts.
5. Rows are **never deleted**; `accepted_loss` is an explicit, recorded decision with a note.

### 8.4 Share metrics and the wellbore-policy consumer

`quarantine_share(source_id, stage, reason_code, vintage) = quarantined / total_parsed`,
materialized per promotion run, served at `GET /quarantine/summary` and consumed by the
quality scorecard (`bp:86`, `bp:209`).

The wellbore policy (`bp:128`) is a **consumer of this machinery, not a parallel system**:
sidetrack / multi-completion wellbores are quarantined with `multi_wellbore_policy`, and
the scorecard reads their share. Two spine-side notes:

- The summary is **sliced by basin and study area**, because D-17 (`ab:540-545`) is right
  that a single global 2% trigger is basin-blind — Permian wellbore history is materially
  messier than the Bakken's. The spine serves the slice; the threshold policy is SB-01's.
- Detection keys on **API-12**, not API-14: PPDM defines digits 1–12 only and is explicit
  that the number should not be used for wellbores; API-14 is convention (`ad:387`). The
  API-14 handling is itself a `vocab_map`/`code_ref` conformance rule.

---

## 9. `/explain` and the lineage API contract

Shapes here are at the level SB-04 can freeze against. SB-04 owns transport, auth,
versioning, the global error envelope and global pagination policy; the spine owns these
payloads and the handle semantics.

### 9.1 Response envelope — how a figure carries its handle

Two forms, chosen by payload shape:

**(a) Figure object** — headline and derived scalars:

```json
{"cum12_oil": {"value": "128340.000", "unit": "bbl", "basis": "oil+condensate",
               "granularity": "well_observed", "report_vintage": "2026-08-01",
               "d": "drv_7QK3M2XR4V9B#api10=33053012340000&col=cum12_oil"}}
```

**(b) `_lineage` sidecar** — dense series and collections:

```json
{"series": {"pm": ["2024-01","2024-02"], "oil_bbl": ["12034.000","11120.000"],
            "report_vintage": ["2026-08-01","2026-07-01"]},
 "_lineage": {"series.oil_bbl": "drv_7QK3M2XR4V9B",
              "series.water_bbl": "drv_7QK3M2XR4V9B"},
 "_units": {"series.oil_bbl": "bbl", "series.water_bbl": "bbl"},
 "_basis": {"series.oil_bbl": "oil+condensate"}}
```

Decisions and justifications:

- **Series carry one handle for the whole series plus a per-point `report_vintage` column.**
  Per-point figure objects would triple the payload on the chart and map path and break
  S2/S3's budgets (`bp:80-81`). The handle plus the selector grammar still addresses any
  single point.
- **Units are mandatory on every figure** — the blueprint itself mixes ft, m, kft and mcf
  with no unit policy (A-13, `ab:641-644`).
- **`granularity` is mandatory on every production-derived figure** (DIR-3): `well_observed`
  or `lease_allocated`. Allocated figures additionally carry `allocation_model_id` and
  `error_bounds`. **Estimates never pose as observations** — DIR-3, enforced by CI (§10).
- **`report_vintage` is mandatory on every restatable figure** (DIR-2), so a response can
  never silently mix vintages.
- **`basis` is mandatory on liquids figures** — the liquids policy must be stated wherever
  the number appears (`bp:258`, project `CLAUDE.md`).

### 9.2 `?explain=true` semantics (closes D-14 / API-11)

| Method | Semantics |
|---|---|
| `GET …?explain=true[&explain_depth=N]` | Response gains `_explain: {handle: chain}` for every handle it contains. Default depth 3, max 8. |
| `POST …?explain=true` | Explains the artifact the request **created** (post-hoc). Well-defined because a POST body is the `params` of a recorded derivation: `POST /inventory/runs?explain=true` explains the run it just created. |
| `POST` on pure endpoints (`/sensitivities`, R3 purity) | Explains each returned row's derivation; identical requests return the identical `derivation_id` by content addressing. |
| `GET /explain?h=…&depth=full` | The S9 one-call path; accepts up to 20 handles. |

`?explain=true` never changes the values in a response — only adds `_explain`. Stated so
that a cached or replayed comparison is unaffected by the flag.

### 9.3 Chain JSON (machine-readable — closes API-06)

```json
{
  "handle": "drv_7QK3M2XR4V9B#api10=42383401230000&pm=2024-03&col=oil_bbl",
  "root": "drv_7QK3M2XR4V9B", "depth": 5, "truncated": false,
  "as_of_vintage": "2026-08-01",
  "nodes": [
    {"id": "drv_7QK3M2XR4V9B", "type": "derivation", "operation": "alloc.apply",
     "output": {"store": "parquet", "dataset": "marts.well_month_allocated",
                "partition": {"basin": "permian", "report_vintage": "2026-08-01",
                              "production_month": "2024-03"},
                "sha256": "…", "rows": 41822},
     "code_version": "git:9f2c1ab", "params_hash": "sha256:…",
     "created_vintage": "2026-08-01", "model_id": "mdl_01J…",
     "determinism_class": "D1", "recipe_id": "rcp_5H2K…",
     "conformance_rules": [{"rule_id": "cr_tx_lease_key_1", "family": "cr_tx_lease_key",
                            "kind": "key_composite"}],
     "explanation": "Allocated lease-reported volumes to wells using allocation model alloc_v0_2026_07; granularity flag lease_allocated."},
    {"id": "man_9c3f…", "type": "manifest", "source_id": "tx_pdq_dsv",
     "source_key": "PDQ_DSV.zip", "sha256": "…", "bytes": 3812345678,
     "fetched_at": "2026-08-01T05:02:11Z", "fetch_vintage": "2026-08-01",
     "acquisition_method": "mft_guid_resolve",
     "acquisition_url": "https://mft.rrc.texas.gov/link/1f5ddb8d-…",
     "supersedes": "man_71ba…", "redistributable": false,
     "explanation": "Texas RRC PDQ bulk production dump, fetched 2026-08-01 via MFT GUID resolution."}
  ],
  "edges": [{"from": "drv_7QK3M2XR4V9B", "to": "drv_B…", "role": "primary",
             "as_of_vintage": "2026-08-01"}],
  "terminals": ["man_9c3f…", "man_71ba…"],
  "recipe": "rcp_5H2K…",
  "warnings": []
}
```

`nodes` + `edges` serve the agent and the auditor; the per-node `explanation` string serves
the UI drawer. Both, not one — API-06 (`ab:751-754`) fails if the payload is prose, and the
drawer is unbuildable if it is only a graph.

### 9.4 Endpoints

| Endpoint | Request | Response |
|---|---|---|
| `GET /explain` | `h` (1–20, repeatable), `depth` (int \| `full`, ≤8), `format=json\|dot` | `{chains: [Chain]}` |
| `GET /derivations/{id}` | `include=inputs,rules,recipe` | Derivation record |
| `GET /derivations` | `operation`, `output_dataset`, `since`, `until`, `model_id`, `rule_id`, `correlation_id`, `cursor`, `limit≤200` | `{items, next_cursor}` |
| `GET /manifests/{id}` | | Manifest record + `supersedes`/`superseded_by` + members |
| `GET /manifests` | `source_id`, `source_key`, `vintage_from/to`, `head_only`, `cursor` | `{items, next_cursor}` |
| `GET /manifests/{id}/bytes` | | Raw passthrough — **owner-scoped**, §9.6 |
| `GET /recipes/{id}` | | Recipe document (§4.1) |
| `GET /vintages` / `GET /vintages/{id}` | `source_id`, `from`, `to` | Vintage records incl. `restatement_summary` |
| `GET /audit` | `since`, `until`, `event_type`, `subject_type`, `subject_id`, `correlation_id`, `actor`, `cursor` | `{items, next_cursor}` |
| `GET /quarantine` | `source_id`, `reason_code`, `rule_id`, `state`, `cursor` | `{items, next_cursor}` |
| `GET /quarantine/summary` | `basin`, `source_id`, `vintage`, `group_by=reason_code\|stage` | share rows for the scorecard |
| `GET /conformance` | `source`, `field`, `kind`, `family`, `as_of`, `cursor` | rule rows incl. `rationale`, `evidence_url`, `spec` |
| `GET /conformance/{rule_id}` | `include=applied_by` | rule + reverse index of citing derivations (the U21 path, `bp:226`) |
| `GET /models` / `GET /models/{id}` | `target`, `basin`, `status` | registry records |

### 9.5 IDs, pagination, errors

- **All spine IDs are immutable and stable** (API-04, `ab:741-745`): derivations are
  content-addressed, manifests are content-addressed, models/vintages/quarantine are ULIDs
  that are never reissued.
- **Deterministic pagination**: sort key `(created_at, id)` (or `(occurred_at, event_id)`
  for audit); `cursor` is base64 of that tuple. An agent replaying a paginated traversal
  gets the same order (`ab:773-778`).
- **`lineage_unresolved`** — an auditor must never get a bare 404. The problem-details body
  names the handle, the last resolvable node, and why resolution stopped
  (`selector_ambiguous`, `depth_exceeded`, `derivation_swept`, `unknown_id`). SB-04 owns
  the general error envelope; this error code and its fields are the spine's contribution.

### 9.6 Raw bytes and redistribution — an honest boundary

S1 hands a key to a stranger (`bp:79`) and S9 promises a path to the raw manifest
(`bp:87`). Re-serving regulator bytes to a third party is *redistribution*, which is a
different legal question from the competitor IP carve-out and is unaddressed in the
blueprint (G-08, `ab:337-342`).

**Decision:** `/manifests/{id}` — the record, the checksum, and the exact `acquisition_url`
— is available to every key. `/manifests/{id}/bytes` is **owner-scoped** unless the
manifest's `redistributable` flag is true (default false; set per source from the ToS
analysis at `ad:407-419`).

Justification: the auditor's need is *verifiability*, and the checksum plus the exact
acquisition URL lets them re-fetch from the regulator and hash it themselves — arguably a
stronger audit than trusting our copy. S9 is satisfied; the redistribution question is
avoided rather than assumed away. FracFocus is the sharpest case: its terms grant download
use "without restriction" but forbid altering the data (`ad:358-363`), which the
staging/canonical split already honours.

---

## 10. Naked-number CI — the harness that makes R6/R7 real

A-09 (`ab:610-615`) is that the check is named but undefined. This is the definition.
It runs in the `lineage` CI job against a seeded fixture database.

**Fixture:** ~200 ND wells with full production history, ~50 TX leases with their
well crosswalk, ~30 NM wells, one trained fixture model, one inventory run, one AOI, one
well set. Checked-in checksums for every fixture manifest. Sized so the whole harness runs
in **< 5 minutes on one VM** — a CI gate nobody can afford to run is not a gate.

**Check 1 — endpoint coverage.** Walk `/openapi.json`. Every operation must supply at least
one request example in its OpenAPI `examples`. **No example → FAIL.** This is how a newly
added endpoint is forced into scope; there is no manual endpoint list to forget to update.

**Check 2 — naked numbers (R7).** Call every operation with its example(s). Walk the
response JSON. Every numeric leaf must be one of:
(a) inside a figure object with a `d`;
(b) covered by a `_lineage` entry at its container path;
(c) matched by a path pattern in `ci/non_figure_allowlist.yml`, each entry carrying a
reason (counts, page sizes, echoed request parameters, coordinates, ids).
Otherwise FAIL, reporting the JSON pointer. The allowlist is checked in and reviewable — a
hostile reviewer can read exactly what we exempted and why.

**Check 3 — handle resolution (R6, S9).** For each distinct handle (capped per endpoint for
runtime), call `GET /explain?h=…&depth=full` and assert:
`truncated == false` · `depth <= 8` · `terminals` non-empty · **every terminal is a
manifest** · each terminal manifest row exists · for a sampled subset, the on-disk payload
re-hashes to `manifest.sha256`.

**Check 4 — node completeness.** Every derivation node has non-null `code_version`,
`params_hash`, `created_vintage`, `recipe_id`, `determinism_class`, and `code_dirty=false`.
Every node whose operation is in `PROMOTION_OPS` cites ≥1 conformance rule. Every node with
a `model_id` resolves in the registry with `promotion_status='promoted'` (or the response
is flagged `shadow`).

**Check 5 — envelope obligations.** Every production-derived figure carries `unit`,
`granularity` and `report_vintage`; every liquids figure carries `basis`; every figure with
`granularity='lease_allocated'` carries `allocation_model_id` and `error_bounds`
(DIR-3: estimates never pose as observations).

**Check 6 — registry coverage.** Every column in the canonical schema definition (read from
the schema file, not a hand-maintained list) appears in ≥1 `conformance_rules.applies_to_fields`
or in `ci/conformance_exempt.yml` with a reason. This is `bp:267`'s coverage check with the
exemptions made visible.

**Check 7 — registry drift (D-09).** For every `code_ref` rule: symbol imports,
`__rule_version__` matches, `sha256(inspect.getsource(fn))` matches `code_ref_sha256`.
For every table-driven rule: `spec` validates against its kind's JSON schema. Plus the
constant-denylist grep over `glasswell/parse/**` and `glasswell/promote/**` (§6.3).

**Check 8 — determinism.** Regenerate the fixture canonical Parquet twice in-process and
once in a fresh subprocess; assert sha256 equality (D1). Train the fixture model twice in
the pinned environment; assert artifact sha256 equality and probe-prediction equality (D2).
Any `DeterminismViolation` recorded in the fixture run fails the build.

**Check 9 — append-only.** Attempt `UPDATE` and `DELETE` against `lineage.audit_events`,
`conformance_rules` and `canonical.production_monthly` as the pipeline and API roles;
assert both are refused.

**Shared with DIR-8's glossary CI.** The glossary check ("every served label resolves to a
`glossary_terms` row") is the same OpenAPI walk with a different assertion. The spine
exports `glasswell.lineage.ci.walk_api()` so SB-04/SB-05 reuse the walker rather than
building a second one — one walker, two assertion sets.

---

## 11. Python library shape

The spine ships as **one internal package**, `glasswell.lineage`. Ingest, promotion,
modeling, economics and the API import it. Nothing reimplements any of it — a second
derivation writer anywhere in the tree is a review failure.

```
glasswell/lineage/
  __init__.py            public surface (the seven callables below + models)
  ids.py                 ULIDs, content addressing, handle parse/format, selector grammar
  models.py              pydantic: Derivation, Manifest, Recipe, AuditEvent,
                         QuarantineRow, ModelRecord, Vintage, Figure, Chain
  store.py               Postgres access, role separation, cursors, recursive-CTE traversal
  capture.py             derive() context manager, @derives decorator, contextvar nesting
  manifests.py           fetch_raw(), resolvers (https/ftp/mft_guid/click_wall), raw-zone layout
  vintages.py            open_vintage(), as_of(), latest view helpers
  conformance.py         load_rules(), apply_rules(), the eight rule-kind executors,
                         predicate-AST compiler, code_ref resolution
  recipes.py             build_recipe(), replay(), determinism classes and checks
  audit.py               emit()
  quarantine.py          quarantine(), release_quarantine()
  registry_models.py     register_model(), promote_model(), resolve_model()
  explain.py             resolve_chain(), to_json(), to_dot()
  envelope.py            figure(), attach_lineage(), FastAPI response helpers
  cli.py                 glasswell lineage {verify-raw, explain, repro, replay-check}
  ci/                    walk_api(), naked_number_check(), coverage_check(), drift_check()
```

Core surface:

```python
@contextmanager
def derive(operation: str, *, output: OutputSpec, params: Mapping[str, Any],
           inputs: Sequence[Ref] = (), rules: Sequence[str] = (),
           model_id: str | None = None,
           ttl_class: str = "permanent") -> Iterator[DerivationContext]:
    """Record one derivation. Nested calls auto-link parent←child via contextvars.
    ctx exposes add_input/add_rule/set_output_hash/set_rows. Commits on success;
    on exception writes status='failed' and re-raises."""

def fetch_raw(source_id: str, source_key: str, *,
              resolver: Resolver | None = None) -> FetchResult:
    """Idempotent by sha256. FetchResult(manifest, created: bool, unchanged: bool)."""

def apply_rules(df: "pl.DataFrame", *, source_id: str, stage: str,
                as_of: date | None = None) -> tuple["pl.DataFrame", list[str]]:
    """Load and execute conformance rules from the registry. Returns the frame and the
    applied rule_ids, which the caller passes to derive(rules=...)."""

def figure(value, *, unit: str, derivation: str, selector: str | None = None,
           granularity: str | None = None, basis: str | None = None,
           report_vintage: date | None = None,
           allocation_model_id: str | None = None) -> Figure:
    """The only way to put a number in an API response."""

def resolve_chain(handle: str, *, depth: int | Literal["full"] = 3) -> Chain: ...

def emit(event_type: str, *, subject: Ref, payload: Mapping[str, Any],
         correlation_id: str | None = None, actor: str | None = None) -> str: ...

def quarantine(rows: "pl.DataFrame", *, reason_code: str, manifest_id: str,
               stage: str, rule_id: str | None = None) -> int: ...
```

Two process-level guarantees:

- **Role separation.** `glasswell_pipeline` has RW on lineage tables; `glasswell_api` has
  RO on lineage plus INSERT on `derivations`/`derivation_inputs` for request-time capture
  only, and INSERT on `audit_events`. The API structurally cannot rewrite pipeline lineage.
- **Nesting.** `derive()` uses a contextvar, so a promotion that calls a parse helper
  produces a correct parent→child edge with no hand-wiring. This is what makes
  instrumentation cheap enough to be universal (§1.1).

---

## 12. Interfaces — the integration contract

| SB | Consumes from the spine | Must emit to the spine |
|---|---|---|
| **SB-01 Data platform** | `fetch_raw()`, resolvers, raw-zone layout; `apply_rules()` and the eight rule kinds; `quarantine()` / `release_quarantine()`; `open_vintage()` / `as_of()`; `derive()` for parse/promote/mart/alloc | One manifest per changed artifact; `stage.parse` and `canonical.promote` derivations with **rule refs on every promotion**; quarantine rows with reason codes; vintage rows with `restatement_summary`; `canonical.restatement_detected` events; `conformance_rules` rows with `rule_kind`, `spec`, `evidence_url`, and `code_ref_sha256` where applicable |
| **SB-02 Modeling & benchmark** | `derive()`; `register_model()` / `promote_model()` / `resolve_model()`; `as_of()` for vintage-locked training sets; recipes + determinism classes; probe-set helpers | Model registry rows (incl. `training_data_vintage`, `holdout_def`, `seeds`, `probe_tolerance`, `calibration_report_ref`); `model.train`/`calibrate`/`forecast.batch` derivations; `ledger.grade` rows with **both** `trained_on_vintage` and `graded_against_vintage`; `analog.index` derivations with an artifact hash |
| **SB-03 Econ, scenarios, inventory, alerts** | `derive()` for request-time compute; `figure()`; `resolve_model()`; recipes | `econ.value`, `econ.sensitivity`, `forecast.scenario`, `inventory.run` derivations with `deck_id` + `model_id` in params; DIR-3 granularity + `error_bounds` on every allocated input it consumes and re-serves; 4D's spacing assumption and support distribution as recorded params, not prose |
| **SB-04 API & agent gateway** | `envelope.figure()` / `attach_lineage()`; `resolve_chain()`; the nine spine endpoint handlers; `ci.walk_api()`; the `lineage_unresolved` error code | An OpenAPI **example for every operation** (or CI fails); `key.issued` / `key.revoked` / `access.denied` / `config.changed` audit events; request-time derivations through `derive()` only; MCP tool schemas that expose `/explain`, `/manifests`, `/conformance` so the agent's traceability path (S5) is not UI-only |
| **SB-05 Map & UI** | Handles from the envelope; the Chain JSON for the drawer (`nodes`/`edges` + per-node `explanation`); `/quarantine` and `/conformance` surfaces | A `tiles.build` derivation per layer build, with the build's `derivation_id` carried in the TileJSON metadata and any model-derived styling attribute carrying its own handle — otherwise map-styled numbers are naked numbers (API-09, `ab:763-767`) |
| **SB-06 Infrastructure** | Nothing | `/data/raw` mount with the §2.3 layout and mode discipline; Postgres roles, monthly partition creation, and lineage+raw in the backup set; `lineage.environments` rows from the build pipeline (image digest, lockfile hash, thread pin); the CI runner and its 5-minute budget |
| **SB-00 v0.6 consolidation** | — | Ratify R6/R7 (§0.3); amend `bp:99` per §4.6; amend R8 per §6.3; add glossary rows for *derivation handle, manifest, recipe, vintage, valid time, knowledge time, quarantine, audit stream, determinism class, naked number* (all listed as undefined at `ab:220-227`) |

---

## 13. Rejected alternatives

- **OpenLineage / Marquez** — another daemon, another schema, and `bp:40` says this is not a lineage ontology platform.
- **DataHub / OpenMetadata** — catalog-shaped, not figure-addressing-shaped; heavy for one VM.
- **W3C PROV / RDF triples** — expressive enough to model anything and queried by nobody here; S9 needs a chain, not a reasoner.
- **dbt / Dagster / Airflow asset lineage** — buys DAG lineage but not serve-time figure handles, and couples the compute layer to a framework DIR-4 did not pick.
- **Hand-authored `/explain` per endpoint** — cost scales with ~25 endpoints forever and each one invents its own shape (A-05, `ab:580-588`).
- **Row-level / per-figure derivations** — 10⁷–10⁸ rows against 10⁵ (§1.5).
- **Column-level lineage inside transforms** — answers a question no S-criterion asks.
- **SQL:2011 system-versioned temporal tables** — unsupported natively in Postgres, absent in DuckDB.
- **Tri-temporal (ruleset as a query axis)** — leaks into every downstream join for no criterion (§3.6).
- **General expression DSL for conformance rules** — an eval surface; typed kinds plus an allowlisted predicate AST cover the real seeds.
- **Hash-chained audit log** — no threat model with a single owner who is also the auditor (§14).
- **Content-addressed object store (IPFS-style) for the raw zone** — sha256 plus a path convention gives the same verification with no store to operate.
- **Per-point figure objects in series** — triples payload on the chart/map path against S2/S3.
- **`POST /recipes/{id}/verify` as an API job** — drags in a job runner, run states and a queue (§4.5).
- **Postgres `LISTEN/NOTIFY` invalidation cascade** — a recorded invalidation plus the next scheduled rebuild is sufficient at this cadence.
- **A separate manifest row per archive member** — 15× the rows for identical verifiability (§2.2).

## 14. Cut as gold-plating

Each of these was designed and then dropped because it does not serve S1/S5/S9/S11 or
DIR-2/3 on a single-builder, single-VM system. Listed so the cut is a decision, not an
omission:

1. **Audit hash chain / tamper evidence.** One writer, one owner, who is also the party the
   evidence would be shown to. Role grants plus the trigger are the guarantee.
2. **Ruleset as a third temporal axis** (§3.6).
3. **Row- and column-level lineage** (§1.2).
4. **Automatic downstream recomputation cascade on restatement.** The invalidation is
   recorded (`mart.invalidated`); the rebuild happens on the next scheduled run.
5. **Any lineage UI beyond the drawer.** The drawer plus `format=dot` on `/explain` is
   enough; a lineage explorer is SB-05's call, later, if ever.
6. **API-triggered replay** (§4.5) — CLI only.
7. **Per-tile lineage.** Per tile-*build* (layer, zoom range) is the granularity.
8. **A generic rules DSL** (§13).
9. **Immutable-mode / WORM filesystem for the raw zone.** Mode 0444 plus the integrity job
   (§2.6) gives the same practical guarantee without an operational trap.
10. **A lineage service separate from the API process.** One FastAPI app, one package.

## 15. Open items handed back

| Item | Owner | Why it is not decided here |
|---|---|---|
| Ratify R6/R7 wording; amend `bp:99` (§4.6) and R8 (§6.3); add the glossary rows | SB-00 | Change-controlled sections (`bp:288`) |
| Per-source pull cadence (drives manifest volume, §1.5) | SB-01 | Ingest scheduling is SB-01/SB-06 |
| Basin-specific quarantine thresholds (the 2% trigger, D-17) | SB-01 | The spine serves the sliced metric; the policy is SB-01's |
| Whether ND MPR is keyed on API-10 or NDIC file number (`ad:52,391`) | SB-01, **first hour of P1** | Decides whether the ND chain needs a crosswalk branch |
| Global error envelope, pagination policy, API versioning, key auth | SB-04 | Spine contributes `lineage_unresolved` and a cursor convention only |
| Grading metrics and holdout definitions | SB-02 | Spine owns grade identity and the two vintages, not the metric |
| Whether restatement-drift decomposition (§3.5) becomes a published scorecard row | SB-02 / E11 | Recommended; not the spine's to schedule |
