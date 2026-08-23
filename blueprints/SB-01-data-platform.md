# SB-01 — Data Platform

**Sub-blueprint. Status: draft for review. Owner: Ryan MacDonald.**
Scope boundary per `assessment-blueprint.md:805` (SB-01 row): raw zone consumption, source
fetchers, parsers → staging, quarantine, conformance registry content, promotion to canonical,
canonical schema, marts, CRS/datum pipeline, allocation v0, restatement/idempotency.
Named there as **the highest-risk SB in the program**.

**Citation convention.** `v0.6 §N` = `blueprint-v0.6-draft.md` section N · `ad:N` =
`work-output/assessment-datasources.md` line N · `ab:N` = `work-output/assessment-blueprint.md`
line N · `dsl:N` = `work-output/data-sources-land.md` line N · `dsw:N` =
`work-output/data-sources-wellops.md` line N · `DIR-n` = `work-output/direction-log.md` ·
`SB-07 §N` / `SB-06 §N` = the sibling sub-blueprints. The two assessments now live under
`work-output/archive/overnight/`; the `ad:`/`ab:` line numbers are unchanged by the move.
Every requirement carries a citation; every design decision carries a one-line
justification. Rejected alternatives are in §14, deliberate cuts in §15, and defects found in
the contract are in §16 — **nothing diverges silently**.

**Consumption rule.** SB-07 is a contract, not a suggestion. This document consumes
`fetch_raw()`, `derive()`, `apply_rules()`, `quarantine()`, `release_quarantine()`,
`open_vintage()`, `as_of()`, `figure()`, `register_model()`, `resolve_model()` and `emit()`
**by name and unchanged**. Where SB-07's own text conflicts with v0.6 or with SB-06, the
conflict is recorded in §16.2 and handed back — it is not resolved by quiet redesign.

---

## 0. Scope and obligations

### 0.1 What SB-01 owns

| Owns | Does not own |
|---|---|
| The source register: `source_id` vocabulary, access method, cadence, licence status | Raw-zone directory contract and manifest schema (SB-07 §2, SB-06 §3.3) |
| Per-source fetchers, GUID/FTP/click-wall resolver *configuration* | The resolver framework and `fetch_raw()` idempotency algorithm (SB-07 §2.1) |
| One parser per source file type; staging schemas; parse determinism profile | The `derive()` capture mechanism and derivation schema (SB-07 §1) |
| `conformance_rules` **rows**: spec, rule text, rationale, evidence URL | The eight typed rule kinds and `apply_rules()` executor (SB-07 §6.1) |
| Reason-code semantics per source; basin quarantine thresholds | Quarantine schema and release loop mechanics (SB-07 §8) |
| Canonical column design, keys, units, null semantics, DDL | Bitemporal vintage mechanics and `report_vintage` semantics (SB-07 §3) |
| Identity resolution: API-10 normalisation, ND crosswalk, TX composite lease key, operator/formation aliasing | Model training, calibration, metrics (SB-02) |
| CRS/datum pipeline and the projected-compute contract | The `crs_registry` row's lineage treatment (SB-07 §6.4) |
| Marts substrate, the PostGIS/DuckDB division, tile source tables and attribute bundles | Tile styling, map client, drawer (SB-05); endpoint code and envelope transport (SB-04) |
| Allocation v0: method, versioning, both validators, error bounds | The model-registry row shape it registers into (SB-07 §7) |
| Ingest scheduling: timer inventory, ordering, idempotent re-run semantics | VM, mounts, systemd hardening, backup (SB-06) |
| `glossary_terms` table DDL (DIR-8 assigns the table to SB-01) | Glossary content, endpoints, UI component (SB-00 / SB-04 / SB-05) |

### 0.2 Requirements this SB satisfies

| Requirement | Source | Satisfied in |
|---|---|---|
| Staging source-faithful, one schema per regulator file type | v0.6 §3.0.1, C2/C3 | §3 |
| Canonical conformed, observations at native granularity only | v0.6 §3.0.1, DIR-3, §4F.1 | §6.3–6.4 |
| Marts derived from canonical only; marts never ingest | v0.6 §3.0.1, D-8 | §7 |
| R1 provenance floor — nothing enters except through the raw zone | v0.6 §3.3 R1 | §2, §9.2 |
| R2 append-only canonical observations | v0.6 §3.3 R2, DIR-2 | §5.4, §6.3 |
| R5 estimates are labelled — granularity on every number | v0.6 §3.3 R5, DIR-3 | §6.4, §8.7 |
| R8 conformance as data — a mapping in code fails review | v0.6 §3.3 R8 | §4 |
| Identity policy; ND API-10 vs file-number question | v0.6 §3.0.4, DIR-9, `ad:52,391,571-572` | §2.1.3, §5.3 |
| Wellbore simplification keyed on API-12; per-basin quarantine trigger | v0.6 §3.0.5, `ad:387` | §4.3, §5.3 |
| Datum: NAD27 detected per file vintage, transformed, transform recorded | v0.6 §3.0.3, `ad:224,583-584` | §2.8, §6.6 |
| TX composite lease key `(oil_gas_code, district_no, lease_no)` | v0.6 §3.0.3, `ad:176,549-551` | §2.4, §4.1, §6.2 |
| PDQ `}` delimiter, no enclosures | v0.6 §3.0.3, `ad:150,545-547` | §2.4, §4.1 |
| ND XLSX/PDF divergence pinned per period | v0.6 §3.0.3, `ad:51,480-486` | §2.1, §4.1 |
| NM undated filenames → self-stamped vintage | DIR-9, `ad:294,554-555` | §2.10 |
| NM even county codes must not be filtered | v0.6 §3.0.3, `ad:316` | §4.1 |
| Null vs zero vs withheld are three distinct states | v0.6 §3.0.3 | §5.8, §6.3 |
| 4E ingest/vintage/restatement protocol | v0.6 §4E | §5.4, §9.2 |
| 4F allocation and granularity protocol; S6 both validators | v0.6 §4F, S6 | §8 |
| Storage/compute division of labour | v0.6 §3.5 | §7.1 |
| Ingest cadence and freshness contract | v0.6 §3.7.4 | §9 |
| Test strategy; real-data fixtures | v0.6 §3.7.6, DIR-10 | §10 |
| Storage budget | v0.6 §3.7.1, DIR-9, `ad:592-597` | §11 |
| Licensing posture per source | v0.6 §3.7.9, `ad:411-419` | §1.1 |

### 0.3 Spine interfaces consumed, by name

| Spine surface | SB-01 use |
|---|---|
| `fetch_raw(source_id, source_key, resolver=)` | Every fetch in §2. SB-01 supplies resolver *config*, never a second fetch path. |
| Raw-zone layout, `lineage.manifests`, `manifest_head` | Change detection is `manifest_head` comparison, never a local cache. |
| `derive(operation=…)` | `raw.fetch`, `stage.parse`, `canonical.promote`, `mart.refresh`, `alloc.apply`, `tiles.build`. No other operation names are introduced. |
| `apply_rules(df, source_id=, stage=, as_of=)` | The **only** conformance execution path. Returns applied `rule_ids` → `derive(rules=…)`. |
| The eight rule kinds (SB-07 §6.1) | Every seed in §4.1 is typed to one of them. |
| `quarantine()` / `release_quarantine()` | Every reject. §4.2 defines reason-code semantics per source. |
| `open_vintage()` / `as_of()` | §5.4 promotion; §6.9 as-of views. |
| `register_model()` / `resolve_model()` | Allocation models are registry citizens, `target='allocation'` (SB-07 §7). |
| `figure()` | Every mart column SB-04 serves. |
| `emit()` | The SB-01 event rows in SB-07 §5.2 (ingest, staging, promotion, conformance, quarantine). |
| Determinism classes D1/D2/D3 (SB-07 §4.2) | All SB-01 artifacts are **D1**. §3.6 pins the write profile that makes that true. |
| Naked-number CI harness (SB-07 §10) | SB-01 supplies the fixture corpus (§10.2) and Checks 5/6 inputs. |

### 0.4 Invariants — these fail review, not lint

1. **No code constant may encode a conformance decision.** Delimiters, EPSG codes, unit
   factors, state codes, district literals, column layouts and vocabularies come from
   `conformance_rules` via `apply_rules()`. Enforced by SB-07 §6.3's denylist grep over
   `glasswell/parse/**` and `glasswell/promote/**`.
2. **No silent drop.** Parsed rows = promoted rows + quarantined rows, asserted per partition.
3. **Canonical never estimates** (v0.6 §3.0.1, DIR-3). Anything modelled, apportioned or
   assumed lives in marts with `granularity` set and a registered model id.
4. **Allocated volumes are never model training targets.** Allocation v0 apportions on a model
   expectation (§8.3); training on its output is circular. Stated here because v0.6 §4A does
   not say it and SB-02 would otherwise be free to do it.
5. **The CRS service is the only code path that transforms coordinates** (v0.6 C6). Loaders
   load in the source CRS; transformation is a promotion step with a derivation.
6. **Raw is never edited in place**; a re-fetch is a new manifest (SB-07 §2.1), never an update.
7. **Every numeric canonical column declares a unit** — in `canonical.field_units` for
   fixed-unit columns, per row in `uom` where the source's unit varies (v0.6 §3.0.3, A-13).

---

## 1. Source register

### 1.1 The register

`source_id` grammar: `<state|org>_<dataset>_<format>`, lowercase, stable forever — it is a
manifest key and appears in every partition path. Renaming one is a migration, not an edit.

| `source_id` | Agency / dataset | Access | Format | Upstream cadence | Pull cadence | Size (compressed) | Licence | Evidence |
|---|---|---|---|---|---|---|---|---|
| `nd_mpr_xlsx` | NDIC monthly production report | `https_get` | XLSX | monthly, +1 mo 15 d | weekly poll | 336.6 MB / 125 files (measured) | none found; accuracy disclaimer | `ad:37-46` |
| `nd_mpr_pdf` | NDIC MPR, PDF era | `https_get` | text-layer PDF | monthly | **deferred** (§2.11) | 354 MB / 282 files | as above | `ad:40,50` |
| `nd_gis_wells` | `OGD_Wells.zip` | `https_get` | shapefile, NAD83 | daily | weekly | 3.6 MB | disclaimer only | `ad:64-70,80` |
| `nd_gis_horizontals_line` | `OGD_Horizontals_Line.zip` | `https_get` | shapefile | daily | weekly | 15.2 MB | as above | `ad:78` |
| `nd_gis_dsu` | `OGD_DrillingSpacingUnits.zip` | `https_get` | shapefile | daily | weekly | 1.5 MB | as above | `ad:82` |
| `nd_gis_permits_prespud` | `OGD_PermitStatusBeforeSpud.zip` | `https_get` | shapefile | daily | **weekly (vintage-diffed)** | 22 KB | as above | `ad:85` |
| `nd_gis_sections` / `_townships` | PLSS `Sections.zip`, `Townships.zip` | `https_get` | shapefile | static since 2020 | monthly | 9.1 MB | as above | `ad:88-89,96` |
| `nd_gis_surveys` | `NDOGD_Surveys.gdb.zip` | `https_get` | file geodatabase | daily | monthly | 313.6 MB | as above | `ad:76,97` |
| `nd_gis_fields` / `_units` / `_rigs` | field, unit, rig layers | `https_get` | shapefile | daily | weekly | 335 KB | as above | `ad:83-86` |
| `tx_pdq_dsv` | RRC PDQ bulk, 16 tables | `mft_guid_resolve` | `}`-DSV in zip | monthly, last Sat | monthly + GUID monitor | 3.55 GB | free, no redistribution clause — **contradicted by the published grant; see §16.3** | `ad:147-160,244`, `dsw:1272-1290` |
| `tx_wellbore_dbf900` | RRC wellbore master | `mft_guid_resolve` | fixed-width ASCII `.gz` | weekly | weekly | 367.8 MB | as above | `ad:188-193` |
| `tx_wellbore_ewa_csv` | Wellbore Query export | `mft_guid_resolve` | CSV | monthly, 2nd working day | monthly | 457 MB | as above | `ad:178` |
| `tx_completions_daily` | W-2/G-1 completion feed | `mft_guid_resolve` | daily zip of ASCII segments | nightly | daily + backfill | 150 MB–1 GB (est.) | as above | `ad:201-213` |
| `tx_permits_daf420` | W-1 drilling permits, master+trailer with lat/long | `mft_guid_resolve` | ASCII | daily | daily | ~1.0–1.2 MB/day | as above | `ad:217-218` |
| `tx_gis_wells_county` | Well layers by county (248 zips) | `mft_guid_resolve` | shapefile, **NAD27** | twice weekly | weekly | 160 MB | as above | `ad:226-234` |
| `tx_gis_survey_county` | Survey layers by county (246 zips) | `mft_guid_resolve` | shapefile, **NAD27** | twice weekly | weekly | 147 MB | as above | `ad:229` |
| `nm_ocd_wcproduction` | OCD well-completion production | `ftp_anon` | XML in zip | nightly | nightly | 923.6 MB | **no published grant** | `ad:269,317` |
| `nm_ocd_core_<table>` | `wellhistory`, `wchistory`, `pod`, `podwc`, `ogrid`, `property`, `pool`, `spacingunit`, `acreage`, `punevent` | `ftp_anon` | XML in zip | nightly | nightly | ~97 MB total | as above | `ad:274-283` |
| `nm_ocd_othervolume` | dispositions | `ftp_anon` | XML in zip | nightly | nightly | 95.6 MB | as above | `ad:272` |
| `fracfocus_csv` | FracFocus bulk CSV | `click_wall_accept` | CSV in zip | business-daily | weekly | **440.2 MB → 3.26 GiB / 18 members** (measured) | §7 use "without restriction"; **no alteration** | `ad:330-335,358-363`, `dsw:39-79` |
| `proj_grid_nad27` | PROJ/NOAA NADCON grid used by the NAD27 transform | `https_get` | GeoTIFF | on PROJ release | on pin change | ~10 MB | public domain | §2.8 |

`lineage.sources` as shipped in P0 lacks the columns this register needs. SB-01 extends it
(migration `010_sources_register.sql`); the extension is the v0.6 §3.4.1 `sources` column set:

```sql
alter table lineage.sources
    add column dataset               text,
    add column access_method         text,
    add column cadence_upstream      text,
    add column cadence_pull          text,
    add column expected_pull_interval interval,   -- drives /v1/health degraded (v0.6 §3.7.4)
    add column licence_status        text not null default 'UNVERIFIED'
        check (licence_status in ('OPEN_NO_RESTRICTION','DISCLAIMER_ONLY','TERMS_ACCEPTED',
                                  'UNVERIFIED','RESTRICTED')),
    add column licence_evidence_url  text,
    add column tos_notes             text,
    add column promote_requires      text[] not null default '{}';  -- §9.1 ordering
```

`licence_status='UNVERIFIED'` is the honest value for `nm_ocd_*` — absence of a restriction is
not a grant (`ad:317,641`), and the scorecard reports it as such (v0.6 §3.7.9).

### 1.2 Access hazards, and what each one costs

| Hazard | Sources | Handling | Evidence |
|---|---|---|---|
| Opaque-GUID MFT portal; GUIDs rotate without notice; HTML listings paginate at 250 | all `tx_*` | `mft_guid_resolve` (SB-07 §2.4): hash the dataset page and the listing page into `acquisition_params`; a rotation surfaces as a listing-hash change, not a mystery 404. Weekly monitor job. | `ad:246,536-539` |
| FTP host published only as a PNG image | `nm_ocd_*` | Pin `164.64.106.6`; on failure, re-resolve by OCR-free fallback — fetch the EMNRD page, extract the image, and **halt with `raw.fetch_failed reason=host_unresolved`** rather than guess. Manual re-pin is a one-line config change and an audit event. | `ad:259,314` |
| Click-through terms wall — **acceptance is recorded by policy, not enforced by the server** (HEAD and range both succeed unauthenticated) | `fracfocus_csv` | `click_wall_accept` is **kept**: hashing the terms we agreed to is an evidentiary choice, not a technical workaround. Record `terms_url`, `terms_sha256`, `accepted_at`. A terms-text change is a manifest-visible event. | `ad:330,335`, `dsw:39-63` |
| ArcGIS REST **service-info** request token-gated (`code 499`) on the ND DMR mirror | `nd_gis_*` | Bulk file downloads only **for `gis.dmr.nd.gov`**. Not a general prohibition: every other host is governed by the §1.2.1 allowlist. | `ad:95`, `dsw:528-545` |
| Subscription ToS forbids automated mining and "practices that substantially duplicate OGD subscription services" | NDIC `/oilgas/basic/` | **Never fetched.** No credential exists in the system. §2.11. | `ad:123,575-576` |
| Bot-walled web app | OCD Online | Never fetched; FTP is the only NM path. | `ad:312` |

#### 1.2.1 `arcgis_rest_paginate` — the sanctioned REST harvest

*(Amendment, 2026-08-21. Narrows the ArcGIS row above to its own evidence and specifies the
method that row was blocking. Change-controlled: it lands one new clause in v0.6 §4E — 4E.7.)*

**What the 499 actually evidenced.** `ad:95` is a single observation:
`https://gis.dmr.nd.gov/dmrpublicservices/rest/services/.../FeatureServer?f=json` returned
`{"error":{"code":499,"message":"Token Required"}}`, and the handling generalised it into a
standing rule for every ArcGIS service anywhere. Two later measurements bound that inference:

- Five *other* ArcGIS hosts answer anonymous, unauthenticated queries and return data —
  `gis.blm.gov`, `ndgishub.nd.gov`, `gis.emnrd.nm.gov`, `mapservice.nmstatelands.org` and
  `services1.arcgis.com` — all queried by direct fetch on 2026-08-21 (`dsl:5-6,103-113`).
- On `gis.dmr.nd.gov` **itself**, `/query?where=1=1&returnCountOnly=true&f=json` against the
  same public service returned `HTTP 200 → {"count":43824}` with no token, reconciling exactly
  with the 43,824 records in `OGD_Wells.zip` (`dsw:528-545`). Whatever the 499 gates, it is an
  endpoint or a date — not the host, and certainly not the protocol.

So the prohibition narrows to what it evidenced. **`nd_gis_*` still ingests bulk files**: they
are cheaper, they carry a `Last-Modified` for conditional GET, and the fetchers exist — no REST
path is built against `gis.dmr.nd.gov` without an amendment. Everything else is governed by the
allowlist below. The blanket reading cost real coverage: six of the nine highest-value land
sources are REST-only, so one 499 made two thirds of that catalogue unreachable (`dsl:883-890`).

**Method.** `arcgis_rest_paginate` is a fifth acquisition method beside SB-07 §2.4's four. SB-01
owns its *configuration*, as it does for the GUID, FTP and click-wall resolvers (§0.1); the enum
value and `acquisition_params` shape are handed back to SB-07 as **H11** (§16.2).

- **Paging.** `resultOffset` / `resultRecordCount`, with `resultRecordCount` **≤ the layer's own
  advertised `maxRecordCount`** — read from the layer JSON, never guessed and never exceeded
  (2000 on the BLM national service, 1000 on the MT/Dakotas and ND Hub layers, 10000 on NMSLO:
  `dsl:76,122,243,339`). A layer that does not advertise `supportsPagination: true` is not
  harvested.
- **Total order.** `orderByFields` on the layer's object-id field, ascending, on every page.
  `resultOffset` over an unordered result set is undefined paging: features silently duplicate
  and drop across page boundaries, and nothing downstream can tell.
- **Format.** `f=geojson` where `supportedQueryFormats` advertises it, `f=pbf` where it is
  advertised and materially smaller, `f=json` (Esri JSON) as the fallback. What is recorded on
  the manifest is the **page** format, in `acquisition_params`; the artifact's own `media_type`
  is the concatenation's — newline-delimited — because a file of `FeatureCollection`s one per
  line is not a GeoJSON document, and a parser that reads `media_type` and guesses otherwise
  fails on the first member. Neither is re-inferred at parse time.
- **CRS.** `outSR` is the layer's own declared `spatialReference`, recorded and not converted.
  Invariant §0.4.5 — the CRS service is the only code path that transforms coordinates — is not
  relaxed for a fetcher; the BLM national service is EPSG:3857 with a NAD83 sibling, and picking
  between them is a registry decision, not a query parameter (`dsl:75-78`).
- **Count assertion.** `returnCountOnly=true` is issued **before and after** the walk.
  `count_before`, `count_after` and the harvested feature count all land in
  `acquisition_params`, and page count must equal `ceil(count_before / resultRecordCount)`. Any
  disagreement fails the fetch with `raw.fetch_failed reason=page_walk_incomplete` and **writes
  no manifest**. A partial walk that silently under-loads a map layer is the exact failure this
  method exists to make loud (`dsl:888-890`).
- **One artifact, one manifest.** Pages are concatenated in walk order into a single
  newline-delimited payload, hashed once, and written as one raw-zone artifact with one `sha256`
  and one `manifest.json` (SB-07 §2.2–§2.3). Pages are not separate manifests, on the same
  reasoning that makes archive members addressable inside one inventory rather than fifteen rows.
- **Vintage.** A service publishes no vintage, so the manifest is **self-stamped** with the
  retrieval vintage under v0.6 §4E.2 — the same treatment NM's undated `<table>.zip` and RRC's
  opaque MFT links already get. Where the layer or its portal item exposes an edit date it lands
  in `upstream_mtime`; where it does not, the column is null and the register says so.
- **Change detection.** `manifest_head` sha256 comparison, as everywhere else (§0.3). The
  assembled bytes are stable across pulls *because* the order is pinned; that is what lets an
  unchanged layer produce `raw.fetch_verified_unchanged` instead of a spurious new vintage.
- **Politeness** (§1.3, v0.6 §4E.6). One connection per host, pages issued serially with a
  minimum inter-request delay, the project `User-Agent`, and a poll cadence tracking the layer's
  own change rate — monthly for PLSS-class layers, which is the existing `nd_gis_sections`
  posture (`dsl:97-101`).

**Host allowlist**, seeded with the five hosts verified by direct fetch on 2026-08-21 (`dsl:5-6`):

| Host | Verified | Evidence |
|---|---|---|
| `gis.blm.gov` (`/arcgis`, `/mtarcgis`, `/nmarcgis`) | `MapServer?f=json` → `200` on all three; `supportedQueryFormats: JSON, geoJSON, PBF` and `supportsPagination: true` evidenced **on the national service only**; `maxRecordCount` 2000 (`/arcgis`) / 1000 (`/mtarcgis`); `/nmarcgis` evidences neither, and the method's own guard is what settles it per layer | `dsl:65-76`, `dsl:117-124`, `dsl:421` |
| `ndgishub.nd.gov` | `All_GovtLands_State/MapServer?f=json` → `200`; `maxRecordCount: 1000`; `supportsPagination: true` | `dsl:239-243` |
| `gis.emnrd.nm.gov` | `OCDView/OCD_PLSS/MapServer?f=json` → `200`; counts measured live | `dsl:128-131` |
| `mapservice.nmstatelands.org` | `/arcgis/rest/services?f=json` → `200`; `capabilities: Map,Query,Data`; `maxRecordCount: 10000` | `dsl:335-339` |
| `services1.arcgis.com` (orgs `YWG34dhJxrbxQWdF`, `KbxwQRRfWyEYLgp4`, `GOcSXpzwBHyk2nog`) | `FeatureServer/0?f=json` → `200`; `capabilities: Query,Extract`; `maxRecordCount: 2000` | `dsl:185-186`, `dsl:385-386`, `dsl:575-576` |

**Failure posture — hosts move by amendment, not by code.** An allowlisted service that starts
returning `499`, `403` or `429` halts with `raw.fetch_failed reason=host_token_gated`, emits the
audit event, and **stops**: no retry against a sibling host, no fallback mirror, no quiet
degrade to an unallowlisted path.

- **The halt unit is the service path, not the allowlist row.** An allowlist row can cover
  several service trees — `gis.blm.gov` covers `/arcgis`, `/mtarcgis` and `/nmarcgis`, and a row
  is an *authorisation* boundary, not a failure boundary. A `403` on one tree halts that tree's
  harvests and leaves the others running; halting the row would take three of the highest-value
  land sources off on one endpoint's bad day. This is the same endpoint-scoped reading the whole
  section rests on: `ad:95`'s 499 and `dsw:537`'s 200 are one host and one service tree apart,
  and RRC's own `rrc_internal` is 499 while `rrc_public` is open (`dsw:1079-1080`).
- **Resuming is not the same event as removing.** A halted service path is re-verified on the
  next scheduled run: one `returnCountOnly` probe, no harvest. Two consecutive successes and the
  path resumes on its own, with both the halt and the resume as audit events — a transient
  upstream `403` must not require a human to write a blueprint amendment before ingest restarts.
  What an amendment is for is the **standing** case: a service that stays gated leaves the
  allowlist by amendment, dated, carrying the failing response as its evidence.

Removal is therefore the deliberate act, and it carries the same discipline R8 puts on a
conformance decision, for the same reason: an access decision that lives only inside a
`try`/`except` is a decision nobody can review, and §2.2's `parse_directive` seed is superseded
rather than edited (v0.6 §4E.4). Admission runs the same way in the other direction, so three
hosts with real evidence and no amendment are **candidates, not allowlist entries**:

- `gis.dmr.nd.gov/dmrpublicservices` — `HTTP 200`, no token, `maxRecordCount: 10000`, and a count
  of 43,824 that reconciles **exactly** with `OGD_Wells.zip` (`dsw:528-545`). On evidence quality
  this is the strongest candidate in the set — a cross-validation against an independently
  published artifact that none of the five seeded hosts has. It is still **not seeded**, and the
  ground is not sequencing: **the evidence that found this service does not recommend it for
  *this* method.** `dsw:549-551` is explicit — *"this does not obsolete the bulk files — SB-01's
  determinism model wants checksummed payload bytes, and a paged REST query is harder to make
  byte-reproducible. Recommend REST for change **detection**, files for the manifest."* §1.2.1
  specifies an **ingest** method — assemble, hash, manifest — so seeding this host into it would
  license precisely the use its own evidence cautions against, on a source whose bulk files
  already work and are verified live. A second ground: the 499 at `ad:95` is on this host and
  this service tree, and the failure posture below halts on a 499 — seeding puts a recorded
  observation and a standing halt condition into the allowlist on the same day. **Admission
  requires both to be resolved:** the 499's scope explained (endpoint or date), and a ruling on
  whether DMR REST is a change-detector — which is a different mechanism, not this one — or an
  ingest path.
- `gis.rrc.texas.gov/server` — `HTTP 200`, `currentVersion 11.3`, `rrc_public/RRC_Public_Viewer_Srvs`
  advertising `maxRecordCount 1000`, `supportsPagination: true` and a 180,195-feature
  wellbore-line layer (`dsw:1068-1085`). Not seeded: the RRC grant text is unresolved and in the
  owner queue (§16.3), which is not this amendment's to read. **The path confusion is not a
  ground** — the two reports reconcile rather than disagree: `/server/rest/services` answers and
  `/arcgis/rest/services` is the `404` (`dsw:1078`, `dsl:224-225`). Worth recording for the row
  above: within that same host, `Hosted`, `SB3` and `rrc_internal` return
  `{"code": 499, "message": "Token Required"}` while `rrc_public` is open (`dsw:1079-1080`) — a
  **second worked example of a 499 scoped to an endpoint rather than to a host**, which is the
  pattern this whole section rests on.
- `gisweb.glo.texas.gov` — `HTTP 200` (`dsl:213`, `dsl:561`). Not seeded: outside the five the
  land report names as its verified set, and no TX land source is registered yet.

**This amendment registers no source.** No `source_id` is added, no cadence is scheduled, no
phase gains work, and §1.1's register gains no row. It removes an access prohibition broader than
its evidence and pins the method the land-layer roadmap would otherwise invent under deadline.

### 1.3 Politeness

Pull cadence is at or below upstream refresh (v0.6 §4E.6). Concretely: NM refreshes 22:55–00:22
local (`ad:269-283`) and we pull once at 03:30 UTC; ND MPR publishes monthly and we poll weekly
because publication is irregular within the month (v0.6 §3.7.4); TX PDQ publishes last Saturday
and we pull on the first Tuesday. One connection per source, no parallel fan-out inside a
source, `User-Agent: glasswell-ingest/<version> (+ryan@rfxn.com)`. Conditional GET wherever an
ETag or `Last-Modified` is offered — the 248 TX county GIS zips are the case where this matters,
turning a 160 MB weekly pull into a handful of changed files.

A paginated REST harvest (§1.2.1) is the one fetch that issues hundreds of requests for one
artifact, so politeness is stated for it in requests rather than in pulls: pages serially on one
connection, never in parallel, ≥ 1 s apart, and the harvest is scheduled at the layer's change
rate — monthly for a PLSS-class layer, not weekly because the fetcher is cheap. The measured
walks are large enough for that to matter: 36 pages for ND sections, 566 for ND intersected
(`dsl:91-93`). Run daily, that is the first thing this project does that a publisher could
reasonably call abuse (`dsl:97-101`).

---

## 2. Per-source ingest specifications

Each spec has the same five parts: **fetch mechanics · cadence · staging schema · parse strategy
· gotchas as conformance-rule seeds**. Staging schemas are source-faithful (v0.6 §3.0.1): every
column is `Utf8` unless the container format carries a type that cannot be losslessly rendered
as text, and no column is renamed, dropped, coerced or interpreted. Every staging table carries
the three universal columns from §3.1.

### 2.1 `nd_mpr_xlsx` — ND well-level monthly production

**Fetch.** The index page `https://www.dmr.nd.gov/oilgas/mprindex.asp` enumerates every file
(`ad:39`). It is fetched first, **as its own manifest** — the index is the evidence for which
periods exist and which format each period has, and pinning format per period (§4.1
`cr_nd_format_pin_1`) is a lineage decision, not a convenience (`ad:485`). File URLs are the
stable pattern `https://www.dmr.nd.gov/oilgas/mpr/YYYY_MM.xlsx` (`ad:38`). Per period:
`fetch_raw('nd_mpr_xlsx', '2026_06.xlsx')` with a conditional GET. Unchanged bytes → one
`raw.fetch_verified_unchanged` event, nothing else (SB-07 §2.1 step 4).

**Cadence.** Upstream monthly at roughly +1 month 15 days, publication irregular within the
month (`ad:43`); pull weekly (v0.6 §3.7.4). Backfill 2015-05 → present is a one-time bounded
harvest of 125 files, run once at P1, one file per 5 s.

**Staging schema** `stg_nd_mpr_xlsx__monthly` — all `Utf8`, column names taken verbatim from the
sheet's header row after `cr_nd_mpr_header_1` locates it:

| Column | Note |
|---|---|
| `<verbatim header columns>` | oil produced, runs, water produced, gas produced, gas sold, gas flared/vented, days produced, plus whatever identity column(s) the file carries (`ad:42`) |
| `sheet_name`, `header_row_ordinal` | recorded because the sheet layout is not contractual |
| `manifest_id`, `source_row_ordinal`, `ingested_at` | universal (§3.1) |

**Parse strategy.** `polars.read_excel(engine="calamine")`. Calamine is a Rust reader with no
date/float heuristics of its own, which is what makes the staging read reproducible;
`openpyxl`/`pandas` re-type columns on inspection and would put an interpretation in the
source-faithful layer. All cells read as strings (`infer_schema_length=0`). Header-row location,
sheet selection and the footer/total-row predicate are a `parse_directive` rule, not code.
Footer aggregate rows (NDIC files carry a totals row) are **quarantined** with
`reason_code='schema_mismatch'`, not dropped — they are the canonical demonstration that the
quarantine path is live.

**Gotchas → seeds.**

| Gotcha | Rule kind | Rule id | Evidence |
|---|---|---|---|
| Sheet layout is not contractual: header-row position, sheet selection and the footer/total-row predicate vary | `parse_directive` | `cr_nd_mpr_header_1` | `ad:42` |
| XLSX and PDF of the same month disagree because of amendments; pin format per period, never mix | `parse_directive` (`format_pin`) | `cr_nd_format_pin_1` | `ad:51,480-486` |
| XLSX coverage begins 2015-05; earlier periods are PDF-only | `parse_directive` | `cr_nd_format_pin_1` (same row, period map) | `ad:50` |
| Identity column may be NDIC file number, not API-10 | `code_ref` → §2.1.3 | `cr_nd_identity_1` | `ad:52,391,571-572` |
| Confidential wells: production withheld, a distinct state from zero and from no-report | `validity_filter` | `cr_nd_confidential_1` | v0.6 §3.0.3 |
| "Runs" (oil sold) and "gas sold/flared" are dispositions, not production | `vocab_map` | `cr_nd_disposition_1` | `ad:42`, §6.5 |
| Wells "capable of producing" appear with zero volumes — reported zero, not missing | `vocab_map` | `cr_null_semantics_1` | `ad:42` |

#### 2.1.3 P1-T0 — the first-hour ND identity verification task

DIR-9 and v0.6 §3.0.4 make this the first executable task of P1, before any production row is
promoted. `ad:52` states it plainly: whether the free MPR carries API-10 or only the NDIC file
number is UNVERIFIED, and 3.0.4's identity spine depends on the answer.

**Procedure.** Fetch `2026_06.xlsx` through `fetch_raw()` (never by hand — the answer must cite a
manifest). Read the header row. Classify every column by: (a) name matching `(?i)^\s*api`,
(b) values matching `^33\d{8}(\d{2})?$` after separator stripping, (c) name matching
`(?i)file\s*(no|num|number)?`, (d) values that are short monotonic integers.

**Outcomes and the branch each one commits to:**

| Outcome | Consequence | Rule row written |
|---|---|---|
| **A — API-10 present** | ND promotion joins `canonical.wells` directly. Chain depth as in SB-07 §1.8 minus the crosswalk branch. | `cr_nd_identity_1`, `spec.key='api10'`, evidence = manifest id + header row |
| **B — file number only** | `nd_gis_wells` becomes a **hard P1 sequencing dependency**: `promote_requires=['nd_gis_wells']` on `nd_mpr_xlsx`. A `canonical.nd_file_crosswalk` table is built from `OGD_Wells` and every production row joins through it. Unmatched file numbers quarantine `orphan_fk` — never dropped, never guessed. The ND `/explain` chain gains a second terminal branch, structurally identical to SB-07 §1.8's `drv_D`. | `cr_nd_identity_1`, `spec.key='ndic_file_no'`, plus `cr_nd_crosswalk_1` |
| **C — both present** | Prefer API-10; assert crosswalk agreement as a promotion-time data-quality check; disagreements quarantine `key_collision` and are a scorecard metric. | `cr_nd_identity_1`, `spec.key='api10'`, `spec.cross_check='ndic_file_no'` |

**Deliverables in all three cases**, before P1 continues: the rule row with evidence, a fixture
cut from the real file (§10.2), a parser test asserting the identity column is read from the
rule and not from a constant, and — in case B — the crosswalk table, its promotion job and its
orphan test. The `ndic_file_no` column on `canonical.wells` (v0.6 §3.4.3) is populated
regardless of outcome, because ND's own reporting keys on it and `/explain` prose that cannot
name the file number is unusable to a ND practitioner.

### 2.2 `nd_gis_*` — ND DMR GIS downloads

**Fetch.** Direct HTTPS, no auth, confirmed by HEAD with real `content-length` (`ad:64`). One
`source_id` per layer, because a layer is the unit that changes and the unit a promotion
partition keys on. `gisdownload.asp` is fetched as its own manifest for the same reason the MPR
index is.

**Cadence.** Downloads refresh **daily** even though the map viewer is weekly (`ad:68`); we pull
weekly for geometry, monthly for the 313 MB survey geodatabase and the static PLSS layers
(`ad:96`), and weekly for `nd_gis_permits_prespud` — see the note below, which is the reason
that 22 KB file gets its own cadence line.

**Staging schema.** Spatial staging is the one place SB-01 stages into PostgreSQL rather than
Parquet (§3.2). `staging.<source_id>` tables are created by `ogr2ogr` with the source's own
field names, plus the universal columns applied as a post-load `alter`:

```
ogr2ogr -f PostgreSQL PG:"service=glasswell" /vsizip/<raw payload path> \
        -nln staging.nd_gis_wells -nlt PROMOTE_TO_MULTI -lco GEOMETRY_NAME=geom \
        -lco FID=source_row_ordinal -a_srs <srs from the .prj, verbatim> \
        -lco SCHEMA=staging --config OGR_TRUNCATE YES
```

`-a_srs` **assigns** the declared CRS; `-t_srs` is prohibited. Transforming at load time would
put a coordinate transformation outside the CRS service and outside lineage, which violates v0.6
C6 and invariant §0.4.5. The transform happens in promotion (§6.6) and emits a derivation.

**Parse strategy.** GDAL via `ogr2ogr` for geometry-bearing layers; `pyogrio.read_dataframe`
into Polars for attribute-only extraction when a layer's attributes are needed in the columnar
store. The file geodatabase (`NDOGD_Surveys.gdb.zip`) is read with the OpenFileGDB driver.
Determinism: the ogr2ogr load is not byte-reproducible (PostgreSQL physical order), so the
**D1 artifact is the Parquet attribute projection**, written sorted by `source_row_ordinal`; the
PostGIS table is an `output_store='postgis'` derivation whose `output_sha256` is computed over
that projection. This is the honest reading of SB-07 §4.2 for a non-file store.

**ND permit history is constructed, not fetched.** `OGD_PermitStatusBeforeSpud.zip` publishes
*current* pre-spud status only (22 KB, `ad:85`), and the Daily Activity Reports that would give
a permit event stream are subscription-gated (`ad:129`). Consequence: ND permit history exists
**only because we snapshot it**. Weekly vintage-to-vintage diffs of this layer *are* the ND
permit event stream that E8/U16 consume. This is DIR-2 paying for itself in a place v0.6 does
not anticipate, and it is why the pull cadence is weekly on a 22 KB file.

**Gotchas → seeds.** ArcGIS REST on the DMR mirror is files-only (`ad:95`) — a `parse_directive`
recording the access decision, whose substance is now **host-scoped rather than universal**
(§1.2.1) and whose evidence gains the 2026-08-21 probe that got `HTTP 200` off the same host
without a token (`dsw:528-545`). If the row is already seeded, the narrowing is a supersession
with a new effective date, never an edit (v0.6 §4E.4).
PLSS layers static since 2020 with the ND GIS Hub as the
authoritative refresh path (`ad:96,99`) — a `parse_directive` naming the mirror and its
staleness, so a future reader does not "fix" it. `OGD_Wells` / `NDOGD_Surveys` attribute schemas
are **UNVERIFIED** (`ad:97,638`) — see P1-T1.

**P1-T1 — ND attribute-schema verification** (same shape as P1-T0, run in the same session):
confirm (i) whether `OGD_Wells` carries an operator *key* or only an operator *name* — DIR-5's
league table needs operator resolution and a name-only source forces `method='normalized_name'`
with confidence < 1.0 (§5.3); (ii) whether it carries a pool/field attribute that distinguishes
Middle Bakken from Three Forks — bulk formation tops are Premium-only (`ad:118`), so pool name
is the free landing-zone signal and the 10-question suite's Q3 depends on it; (iii) whether
`NDOGD_Surveys` holds station-level MD/INC/AZI or headers only (`ad:97`). Each answer is a rule
row or a recorded honest gap. Outcome (ii) negative is a **named honest gap tagged
data-unreachable** in the E16 matrix, not a silent feature omission.

**P1-T1 (iii) — supporting evidence exists, and G-12 is still the B-gate's to close.** Two
independent probes now point the same way: `OGD_Directionals.zip` (3.4 MB) and
`OGD_Horizontals.zip` (344 MB) carry `measdpth`, `inclinatio`, `azimuth` and `tvd` per record,
and a ranged read of `NDOGD_Surveys.gdb.zip`'s system catalog finds exactly those two feature
classes and nothing else (`dsw:482-521`). **This does not close G-12.** Closure belongs to the
pre-P3 B-gate track, against the actual field list, and the two probes disagree on the one thing
that decides which file gets fetched: the wellops report calls the shapefile's 52,579 records
*station* records, while SB-02 §1.3's geodatabase probe reads 52,579 **surveyed wellbores**
against 5,470,017 stations. The counts say the 3.4 MB layer is wellbore-grain and the 344 MB
layer (5,471,270 records) is station-grain; reading that backwards fetches the wrong file for
`landing_tvd_ft`. Three riders travel with the answer and are **recorded, not applied**: the
field name differs by container (`inclination` in the GDB, `inclinatio` truncated in the DBF);
the public extracts are served through non-confidential views, so free surveys **exclude
confidential wells by construction** and that belongs in a coverage rule row rather than an
unexplained hole; and the `api_wellno` attrdef states verbatim that ND's last four API digits
are unused, which is regulator-published support for `cr_api10_format_1`, a row currently
resting on inference. Whether the 313 MB monthly geodatabase pull in §1.1 is superseded by the
two shapefiles is an ingest-register decision on the same track, not this amendment's.

### 2.3 `fracfocus_csv` — completion chemistry, both basins

**Fetch.** `click_wall_accept`: the terms page is fetched and hashed, acceptance recorded, then
`https://www.fracfocusdata.org/digitaldownload/FracFocusCSV.zip` (`ad:330-331`). CSV is taken,
not the SQL Server `.bak` — see §14. **Size, measured 2026-08-21: 440,245,205 bytes compressed →
3,497,920,894 bytes (3.26 GiB) across 18 members**, taken by `HEAD` plus a ranged read of the
zip central directory rather than by downloading the archive (`dsw:39-79`). This is the figure
§11 and §16.3 were holding open. `ad:335,635` recorded HEAD and range as blocked; both succeed
unauthenticated today, and the later reproducible measurement stands — the terms live on
`fracfocus.org`, the payload on `fracfocusdata.org`, and only the first is gated (`dsw:55-63`).
The archive is ~8× its compressed size, so members are **streamed, never materialised together**
(§11).

**Cadence.** Business-daily upstream (`ad:333`), weekly pull (v0.6 §3.7.4). Corrections are
retroactive (`ad:349`), so every pull is a potential restatement of arbitrary history. Detection
is **not** by `DTMOD` — see below.

**Restatement detection — corrected, because the named column does not exist.** `ad:499` records
the detection key as `DTMOD` and this document repeated it here and in §5.4. **There is no
`DTMOD` column in the CSV distribution**: not in `DisclosureList` (17 columns), not in
`FracFocusRegistry` (31), not in `WaterSource` (9), confirmed against live header rows read out
of each member's local header and against the bundled `readme csv.txt` dictionary
(`dsw:82-105`). It is plausibly a column of the SQL Server `.bak`, which is a different artifact
and one §14 rejects on its own grounds. A design keyed on a field the source does not publish is
a design that fails on first run, so it is replaced rather than patched:

- **Did anything change?** Per-member `sha256` in the manifest's `decompressed_inventory`
  (SB-07 §2.2). The archive is 18 members — 15 `FracFocusRegistry` shards, one `DisclosureList`,
  one `WaterSource`, one readme (`dsw:68-79`) — and a member whose hash is unchanged is skipped
  whole, so the **row-wise compare is bounded by the changed set**. The archive is re-cut every
  business day and one shard changing does not implicate the other seventeen.
- **Which rows restated?** The existing bitemporal append (§5.4): `value_hash` over the mutable
  payload columns, keyed on `DisclosureId` for the disclosure grain and
  `(DisclosureId, IngredientsId)` for the ingredient grain. A row whose hash differs from the
  head appends at the new `report_vintage`; a row whose hash matches writes nothing. **No new
  subsystem is required** — this is what change-only append was built to do, and it is why the
  absent column costs a scan rather than a redesign.
- **What it costs — two stages, and only one of them is bounded by the changed set.**
  **Detect:** SB-07 §2.2's inventory hash is a content hash over the *decompressed* member, so
  producing it means inflating **all 18 members on every pull** — a ~3.26 GiB decompression floor
  each week no matter how little moved. **Compare:** the row-wise `value_hash` pass runs only
  over members whose hash changed — ~102–245 MB per registry shard, up to the full 3.26 GiB when
  they all move (`dsw:73-79`). Both are bounded by our pull cadence, not the upstream one
  (`dsw:100-105`). The cheaper detector — per-member CRC-32 and sizes straight from the zip
  central directory, one ranged request, which is the technique that produced this evidence
  (`dsw:68-79`) — is **rejected**: CRC-32 is a 32-bit integrity check, not a content identity,
  and a manifest that can collide is not a lineage primitive. Paying a weekly decompression to
  keep `sha256` as the only identity in the system is the right trade, and it is a CPU cost, not
  a storage one.
- **What of this exists today, precisely.** The `value_hash` change-only append **runs**
  (`src/glasswell/ingest/nm_ocd.py:980` appends on
  `where h.value_hash is distinct from b.value_hash`; migrations 008/009/020/024 carry the
  column). `decompressed_inventory` is a **column with no writer**: it exists
  (`003_manifests.sql:18`, GIN-indexed at `:36`), `register_manifest()` takes it as a kwarg
  (`lineage/manifests.py:58`) and the API serves it (`api/routers/lineage.py:468`), but the sole
  call site — `lineage/fetch.py:286` — does not pass it, so every manifest written today carries
  `'[]'`. **Populating it is code the FracFocus fetcher has to write.** No fetcher or parser for
  this source exists yet, so nothing is misled; what this design avoids is a *new subsystem*, not
  all new code, and saying "no new machinery" without that distinction would be the same
  overclaim this amendment exists to fix.
- **`upstream_mtime` is a trigger, not a detector.** The `Last-Modified` on the zip
  (`Fri, 21 Aug 2026 08:04:14 GMT`, `dsw:39-50`) tells us the archive was re-cut. It cannot tell
  us *which* disclosures moved, and treating a file-level date as a row-level change key is the
  same error `DTMOD` was standing in for.
- **The same root cause reaches one paragraph further, and is flagged rather than quietly
  rewritten.** `DTMOD` came from the SQL Server schema, and so do the staging table names and
  join key below: the CSV distribution ships `DisclosureList_1.csv`, `FracFocusRegistry_1..15.csv`,
  `WaterSource_1.csv` and `readme csv.txt`, joining on `DisclosureId` / `IngredientsId`, not
  `ru.pkey = ri.pKeyDisclosure` (`ad:337`, graded LIKELY and now superseded by measurement —
  `dsw:82-95`). Renaming a staging table is a migration, so the rename lands with the parser
  rather than here; **what this amendment fixes is the design that cannot run, and what it
  records is the one that will need renaming.**

**Staging schemas.** One per CSV member, source-faithful:
`stg_fracfocus_csv__registryupload`, `__registryuploadpurpose`, `__registryuploadingredients`,
`__watersource`. Join key `ru.pkey = ri.pKeyDisclosure` is LIKELY (`ad:337`) and is therefore a
`code_ref` rule with a promotion-time cardinality assertion rather than an assumption.

**Parse strategy.** Stream each member out of the zip with `zipfile.ZipFile.open()` into
`polars.read_csv_batched` — the archive is never fully extracted (§11). All columns `Utf8`,
`quote_char='"'`, `try_parse_dates=False`.

**Gotchas → seeds.**

| Gotcha | Rule kind | Rule id | Evidence |
|---|---|---|---|
| FracFocus 1.0 (2011-01 → 2013-05-31) is **header-only, no chemical rows**; 2012-11 → 2013-05 is a mixed-format overlap | `validity_filter` | `cr_ff_era_break_1` | `ad:348,563` |
| `TVD`, `TotalBaseWaterVolume`, `TotalBaseNonWaterVolume` dropped as unreliable by peer review | `validity_filter` → `quarantine('unreliable_numeric')` | `cr_ff_unreliable_numeric_1` | `ad:344` |
| **No lateral-length field.** Lateral length comes from state GIS, never from here | `code_ref` (documents the prohibition) | `cr_lateral_length_source_1` | `ad:343,564` |
| Trade-secret withholding is pervasive (>80% of disclosures) — a distinct state, never missing-at-random | `vocab_map` | `cr_ff_withheld_1` | `ad:350` |
| Terms forbid altering the data; the staging/canonical split is the compliance mechanism | `code_ref` | `cr_ff_terms_1` | `ad:358-363` |

**Proppant mass is derived, not sourced.** v0.6 C8 and §3.4.3 read as though proppant intensity
arrives from FracFocus. It does not: FracFocus is a chemical registry, proppant appears only as
an ingredient row with a mass percentage, and reconstructing pounds requires
`TotalBaseWaterVolume` — a field peer review calls unreliable (`ad:344`). Therefore
`completion_events.proppant_lb` sourced from FracFocus carries `granularity='modelled'` and its
own derivation, and TX additionally gets the free interval-level "Amount and Kind of Material
Used" path (§2.5). This is errata E4 (§16.1) and it is load-bearing: proppant intensity is the
most-cited completion-design variable (v0.6 §9).

### 2.4 `tx_pdq_dsv` — the TX lease production spine

**Fetch — GUID resolution is a first-class step.** `fetch_raw('tx_pdq_dsv','PDQ_DSV.zip',
resolver=mft_guid_resolve)`. The resolver (SB-07 §2.4) does: fetch the RRC downloads page →
hash it → extract the current `https://mft.rrc.texas.gov/link/<uuid>` for the PDQ dataset →
fetch the GoAnywhere listing (paginated at 250) → hash it → locate `PDQ_DSV.zip` → fetch.
`acquisition_params` records `{dataset_page_url, dataset_page_sha256, resolved_guid,
listing_page_sha256, resolved_at, listing_row}`, so a silent GUID rotation appears as a
listing-hash change in the next successful manifest rather than as an unexplained 404
(`ad:246,536-539`). Resolution failure emits `raw.fetch_failed reason=guid_unresolved`, which
flips `/v1/health` to degraded (v0.6 §3.7.4). A weekly **GUID monitor** job resolves every TX
GUID without downloading, purely to detect rotation between monthly pulls.

**Cadence.** Monthly, last Saturday (`ad:152`); pull first Tuesday.

**Members taken.** Of the 16 tables (`ad:158`), P7b loads seven and stages all sixteen — staging
is cheap and dropping a member at parse time is a decision that would have to be justified later:

| Member | Role |
|---|---|
| `OG_LEASE_CYCLE` | lease × YYYYMM production — the TX production spine |
| `OG_LEASE_CYCLE_DISP` | dispositions (§6.5) |
| `OG_WELL_COMPLETION` | in-dump well ↔ lease crosswalk; carries `API_COUNTY_CODE` + `API_UNIQUE_NO` (`ad:170-172`) |
| `OG_REGULATORY_LEASE_DW` | lease dimension |
| `OG_OPERATOR_DW` | operator dimension with the RRC operator number — the TX operator key |
| `OG_FIELD_DW`, `GP_COUNTY`, `GP_DISTRICT` | reference vocabularies |

**Parse strategy.** The zip is extracted **one member at a time** to
`/srv/glasswell/scratch/tx_pdq_dsv/`, staged, verified, and deleted before the next member — so
peak scratch is the largest single member, not the >25 GB whole (`ad:153`, §11). Each member is
read by DuckDB directly into Parquet:

```sql
SET threads = 1;                       -- D1: stable row order (SB-07 §4.4)
COPY (SELECT *, row_number() OVER () - 1 AS source_row_ordinal
        FROM read_csv('<member>.dsv',
                      delim = '}', quote = '', escape = '',
                      header = true, all_varchar = true, sample_size = -1,
                      ignore_errors = false, parallel = false))
  TO '<staging parquet path>' (FORMAT PARQUET, COMPRESSION zstd, COMPRESSION_LEVEL 3);
```

`quote=''` and `escape=''` are the literal encoding of "no enclosure characters" (`ad:150`), and
they come from `cr_pdq_delim_1.spec`, not from this snippet — the snippet is what the loader
renders after `apply_rules()`. `ignore_errors=false` is deliberate: a field-count shift must
fail loudly into quarantine, not be silently truncated. Rows whose field count differs from the
header are captured by a pre-pass that counts `}` per line and routes offenders to
`quarantine(reason_code='schema_mismatch')` with the raw line.

**Gotchas → seeds.**

| Gotcha | Rule kind | Rule id | Evidence |
|---|---|---|---|
| Delimiter is `}`, header present, **no enclosures**, despite the page saying "CSV" | `parse_directive` | `cr_pdq_delim_1` | `ad:150,545-547` |
| `LEASE_NO` unique **within district only** — key on `(OIL_GAS_CODE, DISTRICT_NO, LEASE_NO)` | `key_composite` | `cr_tx_lease_key_1` | `ad:176,549-551` |
| API-10 built as `'42' ‖ API_COUNTY_CODE ‖ API_UNIQUE_NO`, zero-padded | `key_composite` | `cr_tx_api10_build_1` | `ad:174` |
| County segment reflects county **at permitting**; never infer producing/bottomhole county | `code_ref` | `cr_api_county_semantics_1` | `ad:389` |
| Production is lease-reported; allocation is required and is an **oil-lease** problem | `code_ref` | `cr_tx_allocation_scope_1` | `ad:168,180,580` |
| The PDQ FAQ claiming the database must be purchased is **stale**; the free MFT path is authoritative | `parse_directive` (documents the access decision) | `cr_tx_pdq_free_1` | `ad:160,531-534` |

The composite-key rule is seeded in **P0**, five phases before TX ingest (v0.6 §3.0.3, `ad:551`)
— that is the point of R8: the rule exists before the data that could be corrupted by its
absence.

### 2.5 `tx_completions_daily` — W-2 / G-1 completion feed

**Fetch.** `mft_guid_resolve` against the completion-data dataset page; each artifact is one
`MM-DD-YYYY.zip` (`ad:201-203`). **Each zip contains only the previous day's approved/submitted
completions; there is no consolidated historical file** (`ad:212`), so history is built by
harvesting every daily zip. Observed archive floor is 2021-01-01 and the portal paginates at 250
entries, so the true floor is UNVERIFIED (`ad:213`). Backfill is therefore a bounded, resumable
job that walks the listing pages, records the earliest resolvable date in the source register,
and states it as an honest gap rather than asserting 2021-01-01 is the beginning.

**Cadence.** Nightly upstream, daily pull, backfill in batches (v0.6 §3.7.4).

**Staging schemas.** The feed is segment-oriented (`packetData_<packetID>_Approved.dat`,
partitioned by district, `ad:202`). One staging table per segment we take, plus a
`__packet_index` table recording every segment code seen — including ones we do not parse, so
"we saw it and chose not to promote it" is a recorded fact:

| Segment | Staging table | Why |
|---|---|---|
| Packet Data | `stg_tx_completions_daily__packet` | packet identity, dates, district |
| W-2 Data | `…__w2` | oil completion |
| G-1 Data | `…__g1` | gas completion |
| Amount and Kind of Material Used | `…__material` | interval treatment; `AMT_MATERIAL_PROCESS_CODE=2` is fracture (`ad:208`) |
| Production Interval | `…__prod_interval` | perforated interval |
| Formation Data | `…__formation` | **free TX formation tops** (`ad:209`) |
| P-4 | `…__p4` | avoids the EBCDIC P-4 file entirely (`ad:182`) |
| all others | `…__segment_other` (raw line + code) | recorded, not interpreted |

**Parse strategy.** Segment dispatch on record-type code, layout from the RRC user manual
(`ad:204`) held as a checked-in **layout artifact** with its own sha256, referenced by a
`parse_directive` rule (`layout_ref` + `layout_sha256`) rather than inlined — see §3.5 and
handback H4. Python line reader → Polars frame per segment → Parquet.

**Gotchas → seeds.** Previous-day-only zips (`cr_tx_completion_daily_only_1`, `parse_directive`);
archive floor unverified (recorded in the source register, not a rule); EBCDIC P-4 avoided in
favour of this feed's P-4 segment (`cr_tx_p4_path_1`, `parse_directive`, `ad:182`); `W-12` carries
form-header fields only and **no station data** (`cr_tx_no_survey_stations_1`, `code_ref`,
`ad:240,559-560`) — the rule row is where the honest gap is recorded as data, so E16 can cite it.

`cr_tx_no_survey_stations_1`'s **substance stands**: W-12 in this feed is header-only, and that
half of the finding was re-tested and not contradicted (`dsw:1016-1021`). Its **rationale is
superseded** (never edited — v0.6 §4E.4) so that a reader of the row cannot over-read it into
the blanket claim §2.11 used to make: station data exists elsewhere, from 2021-01-01, in a
different RRC dataset. E16 cites the two-part gap of §2.11, not one gap.

### 2.6 `tx_permits_daf420` — W-1 drilling permits

**Fetch.** `mft_guid_resolve`, the **Master & Trailer with Latitudes/Longitudes** daily variant
(`ad:217-218`) — the coordinate-bearing variant is the one that feeds `canonical.permits.geom`.
~1.0–1.2 MB/day. **Datum of those lat/longs is not stated by the assessment**; §2.8's P7b-T2
verification resolves it before any permit geometry is promoted, and until it does, permit
geometry stays in staging.

**Staging.** `stg_tx_permits_daf420__master`, `__trailer`, fixed-width per the OGA049M manual
layout artifact. **Parse.** As §2.5.

### 2.7 `tx_wellbore_dbf900` — wellbore master

**Fetch.** `mft_guid_resolve`, **always the `.gz`** — the uncompressed `dbf900.txt` and
`dbf900.ebc` on the portal are stale since 2022-04-23 (`ad:193`). This is a `parse_directive`
rule (`cr_tx_wellbore_gz_only_1`), not a code constant, because it is precisely the kind of
decision that a future maintainer would "simplify" back into a bug.

**Cadence.** Weekly (`ad:188`). 367.8 MB → 1.97 GB ASCII.

**Staging.** Multi-record-type fixed-width. `stg_tx_wellbore_dbf900__<record_type>`.
**Parse.** Streamed `gzip.open()` → record-type dispatch → per-type Polars frames → Parquet. The
record layout is UNVERIFIED in the assessment (it names the WBA091 manual, `ad:193`, but not the
structure), so **P7b-T3** builds the layout artifact from the manual at first pull and checks it
against a 10,000-record sample before any promotion. A layout mismatch quarantines
`encoding_error` per record rather than producing a plausible-looking wrong parse.

**Role.** Wellbore-policy input (v0.6 §3.0.5): API-12 suffixes for sidetrack detection, plugging
and completion status. It is the source that makes `canonical.wellbores` real for TX.

### 2.8 `tx_gis_wells_county` / `tx_gis_survey_county` — and the NAD27 pipeline

**Fetch.** `mft_guid_resolve` → 248 well zips + 246 survey zips, `well###.zip` / `surv###.zip`
named by county code (`ad:228-234`). Twice-weekly upstream; weekly pull with conditional GET so
only changed counties transfer. **Permian scope filter**: P7b takes the Permian counties first
and the remainder as a background backfill — the filter is a `validity_filter` rule listing
county codes with evidence, not a hardcoded list.

**Cadence.** Twice weekly upstream (`ad:233`), weekly pull.

**Staging.** `staging.tx_gis_wells_county` / `…_survey_county` via `ogr2ogr` as in §2.2, with
`-a_srs` set from **each file's own `.prj`**, plus a `source_county_code` column from the
filename. Layers include surface wells, **bottom-hole locations** and **well arcs** (`ad:235`) —
the well arcs are TX lateral geometry, and they are the substitute for the directional survey
station data that does not exist in free form (`ad:240,559-560`).

**The datum pipeline.** RRC's own GIS FAQ: *"Projection: Geographic Units: Decimal Degrees
Datum: NAD27"* (`ad:224,583-584`). Untransformed NAD27 is off by up to ~100 m in Texas — enough
to corrupt spacing silently (v0.6 §3.0.3, risk R-11). The pipeline:

1. **Detect per file vintage**, never assume. The `.prj` is parsed and hashed; the detected
   authority is compared against `cr_tx_nad27_1.spec.detect`. A file whose `.prj` says neither
   NAD27 nor NAD83 quarantines every feature with `datum_undetermined` — an undetermined datum
   is not a default, it is a reject.
2. **Load unchanged** in the detected CRS (`-a_srs`), never `-t_srs` (§0.4.5).
3. **Transform in promotion** through the CRS service, with an explicitly pinned PROJ pipeline
   (`+proj=pipeline +step +proj=hgridshift +grids=us_noaa_conus.tif …`). Grid shift, not a
   3-parameter approximation: a Molodensky/7-parameter fit on NAD27 CONUS carries metre-level
   residuals, which is the same order as the error we are removing.
4. **The grid file has its own manifest** (`proj_grid_nad27`, `grid_manifest_id` per SB-07 §6.4),
   so a TX coordinate's `/explain` chain terminates in checksummed bytes for the *transform*
   as well as for the *data*. This is the E12 acceptance criterion made literal.
5. **Emit a derivation** per transformed partition, citing `cr_tx_nad27_1`.

**P7b-T2 — the datum truth set.** v0.6 §3.7.6 item 3 requires "a fixed set of TX wells with
published NAD83 positions asserted in CI", and no such set is identified anywhere in the
assessment. P7b-T2 sources it, in preference order: (a) the `daf420` Master-plus-Lat/Long
permits, **if** their datum is confirmed to be NAD83 — which is itself unknown and must be
established from the OGA049M manual; (b) NGS-published control points co-located with known
well sites; (c) failing both, a PROJ round-trip invariance test plus a documented gap, which is
weaker and is labelled as such. The CI guard asserts both directions: transformed positions
within 1 m of truth, **and** untransformed positions differing by > 50 m — a guard that cannot
fail loudly is not a guard.

> **Amended 2026-08-21, on measurement (TX slice).** Source (a) was not needed: the RRC's own
> county well layers publish `LONG83`/`LAT83` beside `LONG27`/`LAT27`, so the truth set is in
> the same file as the data and no external control points are required. Two numbers change
> with it. The untransformed floor moves **50 m → 20 m**, because the measured untransformed
> shift over Andrews county is a median 42.6 m with a **minimum of 30.1 m**, so a 50 m floor
> could never have passed and would have been a guard that fails on correct data. And the
> transformed side gains two assertions beside the median — the share inside 1 m (≥ 0.75,
> measured 0.80) and a p99 ceiling of 5 m — because a median alone passes a transform that is
> right for half the rows. The RRC's published NAD83 is itself imperfect: 602 Andrews rows were
> never converted upstream and are counted rather than scored, and a further ~19% sit in a
> 3.4–3.9 m cluster that is the regulator's own conversion vintage, not spread in ours. All
> three thresholds are `cr_tx_nad27_1.spec`.

**Compute CRS note.** `crs_registry` pins Permian to UTM 13N / EPSG:32613 (v0.6 §3.0.3). The
Midland Basin extends roughly 1° east of that zone's edge; UTM scale error there is ≈ 1.1 mm/m,
i.e. ≈ 0.44 m across a 1,320 ft spacing distance — two orders below the datum hazard, and
systematic rather than random. The alternative, splitting the Permian across zones 13N and 14N,
would make Delaware-to-Midland distances incomparable and put a zone boundary through the middle
of the study area. One projected CRS per basin, stated, with its known distortion recorded in
`crs_registry.note`.

### 2.9 `tx_wellbore_ewa_csv` — the independent crosswalk

**Fetch.** `mft_guid_resolve`; `OG_WELLBORE_EWA_Report.csv`, ~457 MB, monthly on the second
working day, with monthly archives back to 2020-09 (`ad:178`). **Staging.**
`stg_tx_wellbore_ewa_csv__report`, all `Utf8`, standard CSV. Carries `API_NO`, `LEASE_NUMBER`,
`LEASE_NAME`, `COMPLETION_DATE`.

**Role.** This is **Validator A** for allocation v0 (§8.5) and nothing else. It is deliberately
*not* merged into the canonical well↔lease link: two regulator-published crosswalks that agree
prove nothing if you average them, and the disagreement between them is the measurement S6 needs
(`ad:178,579-580`). `OG_WELL_COMPLETION` is canonical; `OG_WELLBORE_EWA_Report` is the
independent check, and their disagreement rate is a published number.

### 2.10 `nm_ocd_*` — NM OCD anonymous FTP XML

**Fetch.** `ftp_anon` to `164.64.106.6`, path
`/Public/OCD/OCD Interface v1.1/{core,volumes,other}/<table>/<table>.zip` (`ad:259-260`). The
host is published only as a PNG image on the EMNRD page (`ad:314`), so it is pinned in the
source register with `host_resolved_from` recorded in `acquisition_params`, and a resolution
failure halts loudly (§1.2). Filenames are **undated** (`ad:294,554-555`) — every manifest's
`fetch_vintage` is glasswell's own stamp, which is DIR-9's requirement and SB-07 §2.2's
`fetch_vintage` column doing exactly what it exists for.

**Cadence.** The FTP refreshes **nightly** — observed 2026-08-19 22:55 → 2026-08-20 00:22 on a
Wednesday, contradicting the documentation's "first Monday of every month" (`ad:293`). Pull
nightly at 03:30 UTC during Permian phases, weekly otherwise (v0.6 §3.7.4). Because the same
bytes are republished nightly with a ~40% no-change rate, SB-07 §2.1's hash comparison is what
keeps this from creating 5,475 manifests a year instead of ~3,300 (SB-07 §1.5).

**Tables taken.** `volumes/wcproduction` (the well-level production spine, 923.6 MB),
`volumes/othervolume` (dispositions), `core/wellhistory`, `core/wchistory`, `core/pod`,
`core/podwc` (POD ↔ well-completion crosswalk), `core/ogrid` (the NM operator key),
`core/property`, `core/pool`, `core/spacingunit`, `core/acreage`, `core/punevent`
(`ad:269-289`).

**Staging schemas.** `stg_nm_ocd_<table>__records`, one row per XML record element, columns
from the record's child elements verbatim, all `Utf8`, plus `mod_dte` preserved as text.

**Parse strategy.** The zip member is streamed with `zipfile.ZipFile.open()` and consumed by
`xml.etree.ElementTree.iterparse(events=('end',))` with `elem.clear()` and parent-link pruning
after each record, emitting Arrow `RecordBatch`es of 65,536 rows into a Parquet writer. Peak
memory is one batch, not one document — the uncompressed XML is 10–20 GB (estimated, `ad:285`,
UNVERIFIED per `ad:640`) and a DOM parse of it is not an option on a 16 GB VM. Nothing is
extracted to disk: NM contributes **zero** to the scratch budget (§11).

**Gotchas → seeds.**

| Gotcha | Rule kind | Rule id | Evidence |
|---|---|---|---|
| Amendments **completely erase and replace** the prior file upstream; no as-reported history exists but ours | `code_ref` | `cr_nm_restatement_1` | `ad:302,490` |
| `mod_dte` on all five volume tables is the change-detection key | `parse_directive` | `cr_nm_mod_dte_1` | `ad:306` |
| Undated filenames → self-stamped retrieval vintage | `parse_directive` | `cr_nm_undated_vintage_1` | `ad:294,554-555` |
| **NM county codes break the odd-number rule** — never filter APIs on parity | `validity_filter` | `cr_nm_county_parity_1` | `ad:316` |
| Flaring/venting reported per **Property**, not per well — not allocable without assumption | `code_ref` | `cr_nm_flare_property_1` | `ad:315` |
| Documented cadence and file naming are superseded by observed behaviour | `parse_directive` | `cr_nm_ftp_layout_1` | `ad:293-294` |
| Native granularity is **well-completion × pool × month**, not well | `key_composite` | `cr_nm_entity_key_1` | `ad:258` |

`cr_nm_county_parity_1` is written as a **prohibition on parity filtering**, not as a list of
even-coded counties. The assessment marks the Cibola/Los Alamos evidence LIKELY, not VERIFIED
(`ad:316`), and a prohibition is correct under either truth while an enumerated list is only
correct under one. This is errata E9 (§16.1).

### 2.11 Deliberately not ingested

| Source | Why | Evidence |
|---|---|---|
| NDIC subscription (`/oilgas/basic/`, Basic $100 / Premium $500) | ToS forbids automated mining and "practices that substantially duplicate OGD subscription services" — which describes this project. **No credential exists in the system.** Bulk formation tops stay a separate later decision (OQ-12). | `ad:109-127,575-576`, v0.6 D-21 |
| `nd_mpr_pdf` back-extraction 2003-01 → 2015-04 | Deferred within P1 (v0.6 §7.1). Horizontal Bakken effectively starts ~2008 and the XLSX era covers the modern design space. The source is registered and the manifests are fetched so the bytes exist when the parser does. | `ad:50,613` |
| TX P-4 EBCDIC `p4f606.ebc.gz` | Same content is per-completion in the ASCII completion feed (§2.5). EBCDIC decode is avoided outright, removing a whole parse-risk class (v0.6 R-18). | `ad:182` |
| TX directional survey applications, **filings before 2021-01-01** | No free machine-readable index reaches them in bulk, and the era's filings are **UNVERIFIED** — characterised as scanned PDF/TIF by `ad:240`, which the 2021-onward half of that same finding refutes, and no pre-2021 filing has been opened. Honest gap, tagged **data-unreachable**; `W-12` remains form-header only. Lateral geometry comes from well arcs. **From 2021-01-01 the ruling is different — see the re-scope below.** | `ad:240,559-560`, `dsw:1014-1065` |
| ND Daily Activity Reports | Subscription-gated. ND permit history is constructed by vintage-diffing the pre-spud layer (§2.2). | `ad:129` |
| OCD GIS over FTP | Retired 2023-07-05; the directory holds only a redirect note. NM spatial comes from the ArcGIS Hub if and when needed. | `ad:296` |
| Go-Tech / NM Tech PRRC | Pre-ONGARD records with no API numbers, never reconciled. Relevant only to deep pre-database history, which is out of scope. | `ad:318` |
| EMNRD Water Data Act API | Requires a reviewed access request; FTP is the better path and coverage is unverified. | `ad:313` |
| Third-party FracFocus wrappers | Lag the registry and drop malformed rows — i.e. they silently do the thing this project exists not to do. | `ad:365` |

**TX directional survey stations — the ruling is re-scoped, not reversed (amendment,
2026-08-21).** The row above used to read *"No free parseable station data exists"* and carried
one `data-unreachable` tag over all of Texas, all vintages. Half of that finding was re-tested
and holds; the other half is stale, and flipping it outright would be as wrong as leaving it.

- **What holds.** `W-12` in the completion feed is form-header only —
  `SHOT_POINT_500FT`, `BORE_DISPLACEMENT_1/2`, `NEAREST_LEASE_LINE`, `WAS_WELL_DEVIATED`,
  remarks — and carries no station-by-station MD/INC/AZI (`ad:240`, re-tested `dsw:1016-1021`).
  §2.5's `cr_tx_no_survey_stations_1` keeps its substance.
- **What changed.** An MFT dataset **"Directional Survey Applications"** (GUID
  `01769aa7-dee8-4121-bb25-e7557307f6bd`, nightly, listing rowCount 2,181) publishes daily zips
  **from 2021-01-01**, up to ~14 MB/day, each containing a structured CSV type manifest —
  `API_NO, EXTERNAL_ATTACHMENT_ID, ATTACHMENT_TYPE_CODE, FROM_DEPTH, TO_DEPTH, SURVEY_START_DT,
  SURVEY_END_DT, LATERAL_LABEL` — beside **born-digital** PDFs. `ATTACHMENT_TYPE_CODE` pre-filters
  them: in `01-01-2024.zip`, 7 of 7 rows typed `Directional Survey - MWD` yielded full
  MD / inclination / azimuth / TVD station tables under `pdftotext -layout`, while the 2 typed
  `Directional Survey - Other` were single-page scanned plats (`dsw:1023-1050`). The extracted
  headers declare their own geodesy — `Map System: US State Plane 1927`, `Geo Datum: NAD 1927
  (NADCON CONUS)`, zone, grid convergence — which lands them directly in §2.8's datum pipeline
  rather than beside it.
- **The split, stated as the tag.** **Before 2021-01-01: `data-unreachable`**, and the ground is
  the *content*, not the index: a scanned plat yields no station table at any effort, which is
  what the two `Directional Survey - Other` rows in the sampled zip demonstrate
  (`dsw:1032-1034`). **The era's character is UNVERIFIED** — `ad:240` calls the whole dataset
  "daily zips of PDF/TIF images" and this amendment refutes that for the modern half, so the
  same characterisation cannot be treated as established for the older half; **no pre-2021 filing
  was opened by either report.** The tag is still the right bucket under the binary S10/E16
  vocabulary, and it is carried at the evidence grade §2.5 already applies to the adjacent
  archive floor rather than as a finding. The index half is secondary and weaker: the Directional
  Survey Query webapp does reach back to Nov 2009 (`dsw:1051-1059`), but it is a per-well web
  form, and driving it is refused on the same posture that refuses OCD Online and refuses to
  drive the TxGIO SPA (§1.2). **If a pre-2021 sample is ever opened and parses, this row moves**
  — that is what the grade is for.
  **From 2021-01-01: `effort-unreachable`** — reachable, and not built. It is per-well PDF
  parsing, **vendor-format dependent by construction** (two vendors' layouts already differ), and
  graded **effort L** (`dsw:1057-1060`). Both tags are v0.6's own vocabulary (v0.6 §2.4 S10,
  v0.6 §5 E16); the honest gap becomes two gaps with different reasons, which is what an E16 row
  can defend.
- **The access path, if it is ever built.** The nightly MFT zips under `mft_guid_resolve` — the
  resolver every other TX bulk source already uses (§1.2) — with the CSV type manifest as the
  pre-filter and a multi-template PDF parser behind `layout_ref`/`layout_sha256` (handback H4,
  §2.5). No `source_id` is registered by this amendment and no phase gains work; registration is
  a P7b-or-later decision that needs the licence question answered first — **§16.3, "TX RRC
  licence grant"**, which this amendment adds because the question had a pointer and no home.
- **The coverage boundary is a stated limitation, not a footnote.** No current feature depends on
  these stations: TX lateral geometry comes from the county well-arc layers (§2.8) and TX
  `landing_tvd_ft` from this feed's free Formation Data segment (`ad:209`, §2.5). Should a TX
  feature ever source one, every figure derived from it carries **`coverage_from = 2021-01-01`**
  and reports the excluded pre-2021 population — the same discipline v0.6 §4D.2 puts on
  low-support slots. A basin-wide TX claim resting on a 2021-onward sample without saying so
  misstates its own denominator, which is the failure mode R5 and R6 exist to prevent.
- **The floor is not specific to this dataset.** v0.6 §3.7.4 already records the TX completion
  and permit archives as appearing to start 2021-01-01, and §2.5 records the same observed floor
  with the portal's 250-entry pagination as the reason the *true* floor stays UNVERIFIED
  (`ad:213`). One MFT archive floor, three datasets — and the same honest caveat applies here:
  2021-01-01 is the observed floor, not a proven beginning.

---

## 3. Staging layer

### 3.1 Design rules

*Staging is source-faithful: one schema per regulator file type, no opinions, quarantine for
rejects* (v0.6 §3.0.1, C2). Operationally:

1. **All columns `Utf8`** unless the container carries a type that text cannot render losslessly
   (geometry, which stays a GDAL geometry). Type coercion is an opinion and opinions belong in
   canonical.
2. **Verbatim column names**, including the ugly ones. A rename is a mapping decision and a
   mapping decision is a `conformance_rules` row.
3. **Three universal columns on every row**: `manifest_id` (SB-07 §2.2), `source_row_ordinal`
   (0-based, stable, from file order), `ingested_at`. `source_row_ordinal` is what makes a
   quarantine row locatable in the original bytes without row-level lineage (v0.6 D-6).
4. **Staging never serves** (v0.6 §3.0.1). No API path reads a `stg_*` table; enforced by grant
   — `glasswell_api` has no privilege on the `staging` schema and no read path to the staging
   Parquet root.
5. **One partition per manifest.** Staging partition key is `(source_id, manifest_id)`, exactly
   SB-07 §1.2's lineage-visible key.

### 3.2 Physical placement — the SB-06 reconciliation

SB-06 §1.3/§3.2 promises a PostgreSQL tablespace `bulk` on the HDD zvol "for staging tables
only", sized against DIR-9's 60–90 GB peak. v0.6 C2 says staging is "Parquet under DuckDB". Both
are right about part of it. The split:

| Staging class | Store | Path / tablespace | Why |
|---|---|---|---|
| **Tabular** (XLSX, DSV, CSV, XML, fixed-width) | Parquet, read by DuckDB | `/srv/glasswell/staging/<source_id>/<artifact>/manifest=<manifest_id>/part-0000.parquet` | v0.6 C2 and DIR-4. Columnar + zstd turns a 25 GB text member into single-digit GB, is D1-reproducible, and never touches WAL or autovacuum for data that is deleted in 30 days. |
| **Spatial** (shapefile, file geodatabase) | PostGIS `staging` schema | tablespace `bulk` → `/srv/glasswell/pgbulk` | Geometry has to land in PostGIS eventually (v0.6 §3.5). Loading shapefile → Parquet → PostGIS is a double conversion with a CRS round-trip in the middle, and GDAL's PostgreSQL driver is the boring, auditable path. Uses SB-06's `bulk` tablespace exactly as promised. |

The staging Parquet root and the extraction scratch root are **not currently allocated by
SB-06** — handback H8 (§16.2).

**Retention.** Truncate 30 days after the promotion that consumed a partition (v0.6 §3.7.5:
staging is regenerable). Truncation is a job that verifies the source manifest still exists and
its raw payload still hashes correctly before deleting anything derived from it.

### 3.3 Naming

`stg_<source_id>__<artifact>` for tables and views; `staging.<source_id>` for PostGIS spatial
tables. The double underscore separates a `source_id` (which itself contains underscores) from
the artifact — `stg_tx_pdq_dsv__og_lease_cycle` parses unambiguously; a single separator does
not.

### 3.4 Parser tier by format

| Format | Sources | Library | Determinism notes |
|---|---|---|---|
| XLSX | `nd_mpr_xlsx` | Polars + calamine | No type inference; header row from rule |
| `}`-DSV | `tx_pdq_dsv` | DuckDB `read_csv` | `threads=1`, `parallel=false`, `all_varchar`, no quote/escape |
| CSV | `fracfocus_csv`, `tx_wellbore_ewa_csv` | Polars `read_csv_batched` | `infer_schema_length=0` |
| XML | `nm_ocd_*` | `iterparse` + Arrow batches | Streamed from zip member; batch size fixed at 65,536 |
| Fixed-width ASCII | `tx_wellbore_dbf900`, `tx_completions_daily`, `tx_permits_daf420` | Python slicing from a layout artifact | Layout hash pinned in the rule |
| Shapefile / GDB | `nd_gis_*`, `tx_gis_*` | GDAL `ogr2ogr`, `pyogrio` | `-a_srs` only; D1 asserted on the Parquet attribute projection |
| text-layer PDF | `nd_mpr_pdf` (deferred) | — | Deferred within P1; registered so the deferral is visible |

### 3.5 Parser contract

Every parser is a function `parse(manifest) -> ParseResult(staged_rows, quarantined_rows)` run
inside `derive(operation='stage.parse', output=…, inputs=[Ref('manifest', manifest_id)])`. It:

- reads its configuration from `apply_rules(..., stage='parse')` — delimiters, encodings, header
  policy, format pins, layout references. **Zero literals** (invariant §0.4.1);
- emits a staging row or a `quarantine()` row for **every** input row, never neither
  (invariant §0.4.2), asserted by a row-count reconciliation at derive-exit;
- records `parsed_rows`, `staged_rows`, `quarantined_rows` in the derivation params so the
  reconciliation is auditable after the fact;
- writes with the §3.6 profile.

**Layout artifacts.** Fixed-width layouts are 100+ fields and belong in a versioned file, not in
a `spec` jsonb blob. A `parse_directive` rule gains `layout_ref` (a repo path) and
`layout_sha256`; CI asserts the file hashes to the recorded value — the same drift discipline
SB-07 §6.3 applies to `code_ref`. This is a requested extension to SB-07's `parse_directive`
JSON schema (handback H4).

### 3.6 Write profile — what makes staging D1

Pinned once, applied to every Parquet write in SB-01 (SB-07 §4.2's four conditions made
concrete):

| Setting | Value |
|---|---|
| Compression | zstd, level 3, dictionary autotuning off |
| Row group size | 122,880 rows |
| Data page size | 1 MiB |
| Sort order | explicit, declared per dataset (`source_row_ordinal` for staging; the natural key for canonical) |
| Threads | pinned to 1 for artifact-producing writes |
| Statistics | on |
| Custom key/value metadata | none — no wall clock, no hostname, no run id |
| `created_by` | pinned by the library version in the lockfile |

DECIMAL, not float, for every volume and money column (SB-07 §4.4): float summation order varies
with the scan plan, so a float aggregate is not reproducible across thread counts.

---

## 4. Conformance seeds owned by SB-01

R8: *a mapping that exists only in code fails review* (v0.6 §3.3). SB-01 supplies the rows; SB-07
supplies the eight kinds and `apply_rules()`. Every row carries `rule_text`, `rationale`,
`evidence_url` and `evidence_sha256` — the evidence is fetched and hashed, so a regulator quietly
editing an FAQ is detectable.

### 4.1 Seed catalogue

**P0 seeds** — written before any ingest exists (v0.6 §7.1 P0, `ad:605-606`). These are the ones
where absence causes silent corruption:

| `rule_id` | Kind | Applies to | Substance | Evidence |
|---|---|---|---|---|
| `cr_tx_nad27_1` | `datum_transform` | `tx_gis_*` geometry | detect NAD27 per file vintage; PROJ hgridshift pipeline to EPSG:4326; `grid_manifest_id` set | `ad:224,583-584` |
| `cr_crs_compute_nd_1` / `_permian_1` | `datum_transform` | all geometry | compute CRS EPSG:32614 (ND) / 32613 (Permian); storage always 4326; distance never in degrees | v0.6 §3.0.3 |
| `cr_tx_lease_key_1` | `key_composite` | `leases`, `production_monthly` | `(oil_gas_code, district_no, lease_no)`; uniqueness scope = district | `ad:176,549-551` |
| `cr_pdq_delim_1` | `parse_directive` | `tx_pdq_dsv` | delimiter `}`, header true, **no enclosures**, no escape | `ad:150,545-547` |
| `cr_nd_format_pin_1` | `parse_directive` | `nd_mpr_*` | XLSX vs PDF pinned per period; never mixed within a month | `ad:51,480-486` |
| `cr_nm_county_parity_1` | `validity_filter` | `nm_ocd_*` | **prohibits** parity filtering of NM API county codes | `ad:316` |
| `cr_api10_format_1` | `key_composite` | all | zero-padded `SSCCCUUUUU`; API state codes ND 33 / TX 42 / NM 30, **not FIPS** | `ad:385` |
| `cr_api_county_semantics_1` | `code_ref` | all | county segment = county at permitting; never infer producing/bottomhole county | `ad:389` |
| `cr_liquids_policy_1` | `vocab_map` | `production_monthly` | regulator classification preserved in staging; canonical carries `stream` + `liquids_policy`; oil+condensate is the modelling liquid, stated everywhere | v0.6 §3.0.3 |
| `cr_unit_declaration_1` | `unit_conform` | all numeric | every numeric field declares a unit; `canonical.field_units` is the registry | v0.6 §3.0.3, A-13 |
| `cr_null_semantics_1` | `vocab_map` | `production_monthly` | `reported_zero` \| `no_report` \| `withheld_confidential` \| `withheld_trade_secret` — never collapsed | v0.6 §3.0.3 |
| `cr_gas_conditions_1` | `unit_conform` | gas volumes | mcf at the regulator's stated conditions; conditions recorded, not normalised | v0.6 §3.0.3 |
| `cr_month_convention_1` | `code_ref` | `production_monthly` | production month vs report month resolved per source and recorded | v0.6 §3.0.3 |
| `cr_wellbore_api12_1` | `code_ref` | `wellbores` | sidetrack detection keys on **API-12**; API-14 is convention, not standard | `ad:387,567-568` |

**Per-source seeds** are catalogued in §2 alongside the gotcha that motivates each. Count at P0:
14 rows; at P1 exit: ~22; at P7b exit: ~40. Every row is exercised by at least one derivation or
CI Check 7 flags it stale (SB-07 §10).

### 4.2 Reason-code semantics per source

SB-07 §8.2 defines the enum; SB-01 defines what each code *means* per source, which is the part
that makes `/v1/quarantine` pedagogical rather than cryptic:

| Reason code | ND | TX | NM | FracFocus |
|---|---|---|---|---|
| `parse_error` | XLSX cell unreadable | fixed-width record shorter than layout | malformed XML element | CSV row unterminated |
| `schema_mismatch` | footer/total row; unexpected header | **field-count shift from an embedded `}`** | unexpected child element | column count drift |
| `unknown_vocab` | unmapped well status | unmapped `AMT_MATERIAL_PROCESS_CODE` | unmapped pool code | unmapped purpose |
| `alias_unresolved` | operator name unmatched (name-only source) | operator number unmatched | OGRID unmatched | operator unmatched |
| `datum_undetermined` | — | `.prj` says neither NAD27 nor NAD83 | — | — |
| `key_collision` | file number ↔ API-10 disagreement (P1-T0 case C) | bare `LEASE_NO` used without district | duplicate `(api10, pool, month)` | duplicate `pkey` |
| `orphan_fk` | production row with no crosswalk match | completion with no lease | wc with no POD | ingredient with no disclosure |
| `multi_wellbore_policy` | >1 producing wellbore per API-10 | as ND | as ND | — |
| `impossible_volume` | negative or > physical bound | as ND | as ND | — |
| `confidential_withheld` | ND statutory confidential well | — | — | — |
| `unreliable_numeric` | — | — | — | `TVD`, `TotalBaseWaterVolume` (`ad:344`) |
| `out_of_range_date` | production month outside source coverage | cycle outside 1993→ | outside coverage | treatment date implausible |

Two additions are requested from SB-07 (handback H5): `withheld_trade_secret` — a FracFocus
trade-secret claim is not a regulator statutory withhold and collapsing them would corrupt the
scorecard's withheld-share metric (v0.6 R-05) — and `crosswalk_disagreement` for §8.5's
Validator A, which is a *measurement*, not a parse failure, and must not be filed under
`key_collision`.

### 4.3 Basin quarantine thresholds

SB-07 §15 hands the threshold policy to SB-01. Per v0.6 §3.0.5: **ND 2%, Permian 5%**, of
wellbores quarantined under `multi_wellbore_policy`, measured per basin per promotion run,
served through `GET /quarantine/summary` (SB-07 §8.4) and reported on the scorecard.

The asymmetry is a judgment, not a measurement (v0.6 §11 flags exactly this), so SB-01 makes it
falsifiable: the P7 exit gate publishes the **measured** share per basin alongside the trigger,
and if the Permian share lands under 2% the trigger is tightened to ND's value with a rule-row
supersession rather than left loose because it was written loose. A trigger that can only ever
be met is not a gate.

---

## 5. Promotion — staging → canonical

### 5.1 The five stages

One `derive(operation='canonical.promote')` per output partition
(`(source_id, report_vintage, production_month)` for production, `(source_id, report_vintage)`
for dimensions — SB-07 §1.2). Inside it, five stages, each with its own `apply_rules()` call and
its own quarantine exit:

| Stage | `apply_rules(stage=)` | Does | Quarantine exits |
|---|---|---|---|
| 1 **validate** | `validate` | range, parity, date-bound, impossible-volume predicates | `impossible_volume`, `out_of_range_date`, `unreliable_numeric` |
| 2 **conform** | `conform` | unit conversion, vocab mapping, null-semantics assignment, liquids policy, datum transform | `unknown_vocab`, `datum_undetermined` |
| 3 **identify** | `join` | API-10 construction/normalisation, composite key construction, crosswalk join, alias joins | `key_collision`, `orphan_fk`, `alias_unresolved`, `multi_wellbore_policy` |
| 4 **vintage** | — | `value_hash`, change-only append against the current head, `open_vintage()` | — |
| 5 **emit** | — | Parquet/PostGIS write, `restatement_summary`, audit events | — |

Stage 3 is where the promotion can *lose* rows, so it is the stage where the reconciliation
assertion is strictest: `staged = promoted + quarantined + unchanged_suppressed`, with
`unchanged_suppressed` reported separately because change-only append (SB-07 §3.2) is a
suppression, not a drop, and conflating the two would make the quarantine share look wrong.

### 5.2 Rule application

`apply_rules()` returns `(frame, applied_rule_ids)`; the ids go straight to `derive(rules=…)` and
land in `lineage.derivation_rules` with `applied_rows`. Every promotion derivation therefore
cites ≥1 rule, which is SB-07 §10 Check 4's `PROMOTION_OPS` assertion. A promotion that applies
zero rules is a bug: it means the source's mapping decisions are somewhere else.

### 5.3 Identity resolution

**API-10.** Normalised to zero-padded `SSCCCUUUUU` via `cr_api10_format_1`. Separators stripped;
API-12/14 truncated to 10 for joins with the discarded suffix retained on
`canonical.wellbores.api12`. TX builds it: `'42' ‖ API_COUNTY_CODE(3) ‖ API_UNIQUE_NO(5)`
(`ad:174`). NM and ND carry it (subject to P1-T0).

**ND file number.** Under P1-T0 outcome B, `canonical.nd_file_crosswalk (ndic_file_no, api10,
manifest_id, derivation_id, effective_from)` is built from `nd_gis_wells` and is a hard
dependency of every ND production promotion. Unmatched → `orphan_fk`, counted, never dropped.

**TX lease key.** `(oil_gas_code, district_no, lease_no)` everywhere, constructed by
`cr_tx_lease_key_1`. A promotion that sees a bare `LEASE_NO` in a join predicate fails CI's
constant-denylist grep before it fails in data.

**Wellbore policy.** One producing wellbore per API-10 assumed (v0.6 §3.0.5). Detection on
API-12 suffix (`ad:387`): more than one non-`00` suffix with production or completion activity →
`quarantine('multi_wellbore_policy')` for the extra wellbores, with the API-10 flagged on
`canonical.wells`. TX's `dbf900` is the detection source for TX; `wchistory` for NM; `OGD_Wells`
for ND.

**Operator.** Three different keys and one of them is not a key:

| Source | Key | `operator_aliases.method` | Consequence |
|---|---|---|---|
| TX | RRC operator number (`OG_OPERATOR_DW`) | `exact_key` | confidence 1.0 |
| NM | OGRID (`core/ogrid`) | `exact_key` | confidence 1.0 |
| ND | **operator name only** (pending P1-T1) | `normalized_name`, then `manual` | confidence < 1.0; unmatched → `alias_unresolved` |

ND being name-only is on DIR-5's critical path — the league table is ND-first and is not
computable without operator resolution (v0.6 A-12). Normalisation is a `code_ref` rule (case
fold, punctuation strip, corporate-suffix vocabulary from a `vocab_map` table); everything the
normaliser does not resolve goes to a **manual** alias row with an evidence field, not to a
fuzzy match. A fuzzy operator match is an unlabelled estimate in the identity layer, which is
the one place this system cannot afford one. `operator_events` (rename/merge/acquisition) is
seeded manually with source references and drives the `as_reported` vs `parent_rollup` modes
(v0.6 §3.4.3); neither mode is a silent default.

**Formation.** `formation_aliases` `alias_join` with `min_confidence`; unmatched →
`alias_unresolved`. Seeds differ by source: ND pool/field names (pending P1-T1), TX Formation
Data segment (`ad:209`), NM `pool.zip`.

### 5.4 Bitemporal append

Straight consumption of SB-07 §3.2: `value_hash` over the mutable payload columns; a row is
appended only when the hash differs from the current head for the natural key; nothing is ever
updated or deleted. `open_vintage()` opens the `(source_id, vintage_date)` row and receives
`rows_examined`, `rows_appended`, `months_touched` and `restatement_summary`.

Detection per source (v0.6 §4E.3, `ad:496-499`):

| Source | Detection |
|---|---|
| TX | re-pull the monthly dump; diff on `(lease_key, cycle)` — the RRC states there is **no point beyond which corrected reports may not be filed** (`ad:472`) |
| ND | re-pull; diff on `(entity_key, production_month)` with the format pinned per period |
| NM | nightly re-pull; diff on `mod_dte` — a promotion optimisation, not a lineage concept (SB-07 §2.1) |
| FracFocus | per-member `sha256` from the manifest inventory decides *whether* a shard changed; `value_hash` on `DisclosureId` / `(DisclosureId, IngredientsId)` decides *which rows* restated. **No `DTMOD` column exists in the CSV distribution** (`dsw:96-105`) — §2.3 |

`canonical.restatement_detected` is emitted with the SB-07 §5.4 payload and is the trigger for
`mart.invalidated`. **Vintage capture starts at P1** (v0.6 §4E.5): history not snapshotted
cannot be reconstructed from any of these four regulators (`ad:501`).

### 5.5 Quarantine paths

Every quarantine call carries `manifest_id`, `stage`, `reason_code`, `rule_id` (null only for
parse failures) and the row payload capped at 8 kB (SB-07 §8.1). Fingerprint dedupe means a row
rejected nightly by NM for a year is one entry with `occurrence_count=365`, not 365 entries —
which is what makes `/v1/quarantine` readable.

### 5.6 Rule change → re-promotion

SB-07 §6.5 owns the mechanism; SB-01 owns the trigger and the cost. On `conformance.rule_added`
or `rule_superseded`, the affected surface is computed from `derivation_rules`, affected
partitions are re-promoted **at the same `report_vintage` with a new `derivation_id`** (SB-07
§3.6 — the ruleset is lineage-visible, not query-visible), marts are invalidated and rebuilt on
the next scheduled run, and matching quarantine rows become release candidates.

Cost control, because OQ-15 asks the question and nobody has measured it: every re-promotion job
records `partitions_repromoted` and `duration_ms`, and the scorecard carries a rolling
"re-promotion compute share" metric. If that share crosses 25% of ingest compute, the answer is
a batched rule-change window (rules accumulate, one re-promotion), not a rebuild — stated now so
the decision is not made under pressure later.

### 5.7 Idempotency

`glasswell ingest run <source_id>` is safe to re-run at any time. Re-running with no upstream
change produces: N `raw.fetch_verified_unchanged` audit events, **0** manifests, **0**
derivations, **0** canonical rows. Re-running promotion over an unchanged manifest produces the
same `derivation_id` by content addressing (SB-07 §1.3) and therefore a primary-key collision;
if the recorded `output_sha256` differs, the store raises `DeterminismViolation` — non-determinism
is caught in production, not just in CI. That behaviour is the §10.4 integration test, not a
hope.

### 5.8 Null, zero and withheld

Three states, never collapsed (v0.6 §3.0.3). Canonical carries `null_semantics` as a non-null
enum and `volume` as nullable:

| `null_semantics` | `volume` | Meaning |
|---|---|---|
| `reported_zero` | `0.000` | The operator filed a zero |
| `no_report` | NULL | No report was filed for that entity-month |
| `withheld_confidential` | NULL | Regulator withholds it (ND confidential period) |
| `withheld_trade_secret` | NULL | Filer claimed trade secret (FracFocus) |
| `not_applicable` | NULL | Stream does not exist for that entity |

The withheld share is a scorecard metric and a distinct censoring class in 4A.4, because it is
not missing at random (v0.6 R-05) — ND's confidential period systematically hides *new* wells,
which is exactly the population inventory and scenarios care about (OQ-7).

---

## 6. Canonical schemas

### 6.1 Store assignment

Per v0.6 §3.5. **PostGIS is authoritative for geometry and identity that geometry joins to;
DuckDB-over-Parquet is authoritative for everything columnar.**

| Canonical table | Store | Rationale |
|---|---|---|
| `wells`, `wellbores`, `operators`, `operator_aliases`, `operator_events`, `leases`, `well_completions`, `formations`, `formation_aliases`, `field_units`, `gas_conditions`, `glossary_terms` | **PostGIS** | Identity and reference data; small, joined to geometry, read by the API on every request |
| `well_spatial`, `land_units`, `spacing_units`, `permits` | **PostGIS** | Geometry |
| `production_monthly`, `disposition_monthly`, `completion_events`, `frac_disclosures`, `formation_tops` | **Parquet / DuckDB** | Time series and wide fact tables; v0.6 §3.5: "PostGIS … does not hold time series" |
| `nd_file_crosswalk`, `well_lease_link` | **Parquet / DuckDB** | Fact-shaped, joined columnar |

`marts.well_dim` (§7.2) is the non-geometry projection of `wells` into Parquet, so the common
columnar joins do not cross stores on every query. It is a **mart**, not a second canonical copy
— canonical has exactly one authoritative row for a well, and "marts never ingest" holds because
its input is canonical.

### 6.2 Identity and dimensions (PostGIS)

```sql
create table canonical.wells (
    api10                  char(10) primary key
        check (api10 ~ '^[0-9]{10}$'),
    state_code             char(2)  not null,          -- API code, not FIPS (cr_api10_format_1)
    county_code_at_permit  char(3)  not null,          -- never infer producing county
    ndic_file_no           text,                       -- ND; populated regardless of P1-T0 outcome
    operator_id            text     references canonical.operators (operator_id),
    well_name              text,
    well_number            text,
    status_canonical       text     not null,          -- vocab_map target
    status_reported        text,                       -- kept: the mapping must be inspectable
    spud_date              date,
    completion_date        date,
    first_production_month date,
    confidential_flag      boolean  not null default false,
    confidential_release_date date,
    basin                  text     not null,
    landing_zone_formation_id text  references canonical.formations (formation_id),
    multi_wellbore_flag    boolean  not null default false,   -- §5.3
    land_unit_id           text     references canonical.land_units (land_unit_id),
    spacing_unit_id        text     references canonical.spacing_units (spacing_unit_id),
    effective_from         date     not null,
    effective_to           date,
    source_manifest_id     text     not null references lineage.manifests (manifest_id),
    derivation_id          text     not null references lineage.derivations (derivation_id),
    rule_ids               text[]   not null default '{}'
);

create table canonical.wellbores (
    api12          char(12) primary key check (api12 ~ '^[0-9]{12}$'),
    api10          char(10) not null references canonical.wells (api10),
    wellbore_type  text     not null check (wellbore_type in ('original','sidetrack','recompletion')),
    detected_from  text     not null,       -- source_id that evidenced it
    api14_observed text,                    -- convention, not standard (cr_wellbore_api12_1)
    quarantine_id  text     references lineage.quarantine_rows (quarantine_id),
    derivation_id  text     not null
);

create table canonical.operators (
    operator_id        text primary key,
    canonical_name     text not null,
    parent_operator_id text references canonical.operators (operator_id),
    ticker             text,
    notes              text
);

create table canonical.operator_aliases (
    alias_id           text primary key,
    source_id          text not null references lineage.sources (source_id),
    source_operator_key text,               -- RRC operator no. | NM OGRID | null for ND
    reported_name      text not null,
    normalized_name    text not null,
    operator_id        text not null references canonical.operators (operator_id),
    effective_from     date not null,
    effective_to       date,
    confidence         numeric(4,3) not null check (confidence > 0 and confidence <= 1),
    method             text not null check (method in ('exact_key','normalized_name','manual')),
    rule_id            text references lineage.conformance_rules (rule_id),
    evidence           text
);

create table canonical.operator_events (
    operator_id           text not null references canonical.operators (operator_id),
    event_type            text not null check (event_type in ('rename','merge','acquisition','subsidiary')),
    effective_date        date not null,
    successor_operator_id text references canonical.operators (operator_id),
    source_ref            text not null,
    primary key (operator_id, event_type, effective_date)
);

create table canonical.leases (                      -- TX only (cr_tx_lease_key_1)
    oil_gas_code   char(1) not null,
    district_no    text    not null,
    lease_no       text    not null,
    lease_name     text,
    operator_id    text    references canonical.operators (operator_id),
    field_id       text,
    county_names   text[],
    effective_from date    not null,
    effective_to   date,
    derivation_id  text    not null,
    primary key (oil_gas_code, district_no, lease_no)
);

-- NM's native reporting entity: well-completion x pool (ad:258). v0.6 3.0.2 names no such
-- entity though 3.4.3 keys production on it — errata E5.
create table canonical.well_completions (
    completion_key text primary key,          -- <api10>:<pool_code>
    api10          char(10) not null references canonical.wells (api10),
    pool_code      text     not null,
    pool_name      text,
    formation_id   text references canonical.formations (formation_id),
    pod_id         text,                      -- NM POD (podwc crosswalk)
    effective_from date not null,
    derivation_id  text not null
);
```

`canonical.field_units (dataset, column_name, unit, unit_system, rule_id)` is the unit registry
for fixed-unit columns; `canonical.gas_conditions (source_id, psi, deg_f, statement, rule_id)`
records the regulator's stated gas conditions rather than normalising them away
(`cr_gas_conditions_1`). `canonical.glossary_terms` is DDL'd here per DIR-8 with the v0.6 §3.4.3
column set; its content is SB-00's.

### 6.3 `production_monthly` — bitemporal, native granularity

Logical schema; materialised as Parquet, enforced by the Arrow schema in
`glasswell.canonical.schema`. This is SB-07 §3.2's table with the key corrected for DIR-3
(handback H1): SB-07's illustrative DDL keys on `api10`, which cannot represent a TX lease row,
and SB-07 §0.1 assigns canonical column design to SB-01.

```sql
canonical.production_monthly (
  entity_type        text          not null,   -- well | lease | well_completion_pool
  entity_key         text          not null,   -- api10 | 'O:08:12345' | '30015200010000:72319'
  production_month   date          not null,   -- VALID time
  stream             text          not null,   -- oil | gas | water | condensate
  source_id          text          not null,
  report_vintage     date          not null,   -- KNOWLEDGE time = manifest.fetch_vintage
  volume             numeric(18,3),            -- DECIMAL, nullable per null_semantics
  uom                text          not null,   -- bbl | mcf  (cr_unit_declaration_1)
  days_produced      smallint,
  granularity        text          not null,   -- R5 vocabulary: always 'observed' here
  reporting_level    text          not null,   -- well | lease | well_completion_pool
  null_semantics     text          not null,   -- §5.8
  liquids_policy     text,                     -- oil_only | oil_plus_condensate | condensate_only
  conditions_ref     text,                     -- -> canonical.gas_conditions
  mod_dte            timestamptz,              -- NM change-detection key (cr_nm_mod_dte_1)
  api10              char(10),                 -- denormalised; NULL for lease rows
  value_hash         text          not null,   -- sha256 over the payload columns
  source_manifest_id text          not null,
  derivation_id      text          not null,
  rule_ids           text[]        not null,
  primary key (entity_type, entity_key, production_month, stream, source_id, report_vintage)
)
```

Partitioned `source_id=… / report_vintage=… / production_month=…`, matching SB-07 §1.2 exactly.
Sorted within a partition by `(entity_key, stream)` for D1.

**`granularity` is always `observed` in canonical.** DIR-3 and v0.6 §3.0.1 are unambiguous:
canonical never estimates. `reporting_level` carries what SB-07 §9.1's compound token encodes,
without conflating "what kind of number is this" with "at what level was it reported" — see §6.4.

### 6.4 Native granularity and the served token

| Regulator | Native reporting level | Canonical `entity_type` | Allocation needed |
|---|---|---|---|
| ND | well | `well` | no |
| NM | well-completion × pool | `well_completion_pool` | no (validator) |
| TX | lease | `lease` | **yes** (marts, §8) |

`(granularity, reporting_level)` composes into SB-07 §9.1's envelope token:

| Canonical `(granularity, reporting_level)` | Served token |
|---|---|
| `(observed, well)` | `well_observed` |
| `(observed, well_completion_pool)` | `well_observed` + `aggregation='sum_over_pools'` when pools are summed |
| `(observed, lease)` | `lease_reported` |
| `(allocated, well)` — marts only | `lease_allocated` + `allocation_model_id` + `error_bounds` |

Summing NM pools to a well-month is exact arithmetic on observations, not an estimate, so it
stays `observed` — but the aggregation is recorded in the derivation params and surfaced, because
a well producing from two pools is a different object from a well producing from one and the
consumer is entitled to know which they have. The `(granularity, reporting_level)` → token
mapping is a two-vocabulary reconciliation that SB-00 should ratify (handback H3).

### 6.5 Dispositions, completions, disclosures, tops

**`canonical.disposition_monthly`** — same key shape as `production_monthly` plus
`disposition_type` (`sold` | `flared_vented` | `stored` | `injected`). It exists because ND MPR
publishes runs and gas sold/flared (`ad:42`), TX ships `OG_LEASE_CYCLE_DISP`, and NM ships
`othervolume`; collapsing "runs" into "oil produced" would be an unrecorded conformance decision
of exactly the class R8 exists to prevent. **Scope guard: promoted, not served in v0.6** — no
endpoint, no feature, no model input. It costs one table and it keeps a regulator-published
column from being silently discarded. NM flaring is per-Property and **not allocable to wells**
(`cr_nm_flare_property_1`, `ad:315`), which is recorded as a rule so the limitation is queryable.

**`canonical.completion_events`** — `completion_id`, `api10`, `event_date`, `event_type`,
`lateral_length_ft`, `proppant_lb`, `fluid_bbl`, `stage_count`, `landing_zone_formation_id`,
`source_id`, `manifest_id`, `rule_ids[]`, and a **per-field** `null_semantics` map plus a
per-field `granularity` map. The per-field granularity is required, not decorative:
`lateral_length_ft` is `modelled` when computed from GIS lateral geometry and `observed` when a
regulator publishes it; `proppant_lb` from FracFocus is `modelled` (§2.3). v0.6 §3.4.3 carries
per-field null semantics but not per-field granularity — errata E4.

**`canonical.frac_disclosures`** — vintaged (SB-07 §3.1: retroactive corrections), with
`disclosure_era` ∈ `1.0 | 2.0 | 3.0 | 4.0` so the pre-2013-06 header-only break (`ad:348`) is a
queryable structural fact rather than a puzzling absence of chemistry rows.

**`canonical.formation_tops`** — `api10`, `formation_id`, `md_ft`, `tvd_ft`, `source_id`,
`confidence`, `manifest_id`. TX populated from the completion feed's Formation Data segment
(free, `ad:209`); ND effectively empty on the free path because bulk log tops are Premium-only
(`ad:118`) — a recorded honest gap feeding OQ-2's geology ablation, not an empty table nobody
explains.

### 6.6 Spatial and the CRS policy

```sql
create table canonical.well_spatial (
    api10             char(10) not null references canonical.wells (api10),
    geom_type         text     not null check (geom_type in ('surface','bottomhole','lateral')),
    geom              geometry(Geometry, 4326) not null,   -- storage always 4326
    geom_compute      geometry(Geometry)       not null,   -- basin compute CRS, materialised
    compute_epsg      integer  not null,
    source_datum      text     not null,                   -- detected, never assumed
    source_epsg       integer  not null,
    transform_rule_id text     references lineage.conformance_rules (rule_id),
    grid_manifest_id  text     references lineage.manifests (manifest_id),
    derivation_id     text     not null,
    source_manifest_id text    not null,
    primary key (api10, geom_type)
);
create index well_spatial_geom_idx    on canonical.well_spatial using gist (geom);
create index well_spatial_compute_idx on canonical.well_spatial using gist (geom_compute);
```

`geom_compute` is **materialised**, not a generated column or a query-time `ST_Transform`: every
spacing, neighbour and admissibility query runs against it with a spatial index, and a
query-time transform would both defeat the index and put a transform outside the recorded
derivation. It is refreshed by the promotion that wrote `geom`, in the same derivation, so the
two can never disagree.

`land_units` (`system` ∈ `plss` | `tx_abstract` | `nm_plss`), `spacing_units` and `permits`
follow the same pattern: 4326 storage, materialised compute geometry, detected source datum,
transform rule cited. `land_units` exists **from P0** so that TX is a data problem rather than a
schema migration (v0.6 D-11); TX has no spacing units (it uses field rules), so
`spacing_units` is legitimately ND/NM-only and that is recorded rather than left looking broken.

### 6.7 Types and units

DECIMAL for every volume, rate and money column (SB-07 §4.4). Float only for model features,
model outputs and geometry (D2/D3). Every fixed-unit column has a `canonical.field_units` row;
every variable-unit column carries `uom` per row. Feet and metres coexist by necessity —
`lateral_length_ft`, `cum12_per_kft` in feet; projected CRS and datum offsets in metres — which
is exactly why unit declaration is an obligation and not a style preference (v0.6 §3.0.3, A-13).

### 6.8 Parquet layout

```
/srv/glasswell/parquet/canonical/
  production_monthly/source_id=<>/report_vintage=<>/production_month=<>/part-0000.parquet
  disposition_monthly/…same…
  completion_events/source_id=<>/report_vintage=<>/part-0000.parquet
  frac_disclosures/report_vintage=<>/part-0000.parquet
  formation_tops/source_id=<>/part-0000.parquet
  well_lease_link/report_vintage=<>/part-0000.parquet
```

The DuckDB catalog at `/var/lib/glasswell/duckdb/glasswell.duckdb` holds **views over Parquet
globs only — no base tables**. The catalog is therefore regenerable from a schema file, the
single-writer constraint never binds on the serving path, and a partition is addressable by the
same key lineage uses. Rejected: loading canonical into DuckDB native tables (duplicates the
data, reintroduces a writer bottleneck, and breaks partition-level derivation addressing).

### 6.9 As-of access — and the QUALIFY correction

SB-07 §3.3 defines the semantics (*greatest vintage ≤ as_of*, per natural key) and expresses them
with `QUALIFY`. **PostgreSQL has no `QUALIFY` clause**, so the "DuckDB and Postgres both express
this as a window function" claim does not hold as written (handback H2). Both forms, defined once
in `glasswell.lineage.vintages` and used everywhere:

```sql
-- DuckDB (Parquet-resident canonical)
create view canonical.production_monthly_latest as
select * from canonical.production_monthly
qualify row_number() over (partition by entity_type, entity_key, production_month, stream, source_id
                           order by report_vintage desc, derivation_id desc) = 1;

-- PostgreSQL-portable form (used for PG-resident vintaged tables, e.g. permits)
create view canonical.permits_latest as
select * from (
  select p.*, row_number() over (partition by permit_id
                                 order by report_vintage desc, derivation_id desc) as rn
    from canonical.permits p) t
 where rn = 1;
```

The tiebreak on `derivation_id` after `report_vintage desc` is SB-07 §3.6's requirement that a
re-promotion under a corrected rule appends at the same vintage and wins — SB-07 words it as
`created_at desc`, which is wall-clock and therefore not reproducible under replay;
`derivation_id` is content-addressed and stable. Noted in H2.

---

## 7. Marts — the PostGIS / DuckDB division of labour

### 7.1 The division, drawn explicitly

v0.6 §3.5 states the principle. This is the operational table: **which store holds which
artifact, and which API or tile query it serves.**

| Artifact | Store | Serves |
|---|---|---|
| `marts.well_month_production` | Parquet/DuckDB | `GET /v1/wells/{api10}/production` · well-card charts · GOR/water-cut derived series · exports |
| `marts.well_month_allocated` | Parquet/DuckDB | the TX contribution to the above; `granularity=allocated`, `error_lo/hi` |
| `marts.well_features` | Parquet/DuckDB | SB-02 training and scoring; `/v1/analogs` feature vectors |
| `marts.well_dim` | Parquet/DuckDB | columnar joins that would otherwise cross stores per query |
| `marts.type_curves`, `forecasts`, `valuations`, `ledger_entries`, `scorecard_metrics`, `operator_league` | Parquet/DuckDB | SB-02/SB-03 outputs; `/v1/typecurves`, `/v1/forecasts`, `/v1/ledger`, `/v1/scorecard`, `/v1/operators/league` |
| `marts.tile_geom_<layer>` (laterals, wells, sections, townships, abstracts, spacing units, permits) | **PostGIS** | martin vector tiles at `/tiles/{z}/{x}/{y}` — geometry only, no model output |
| `marts.tile_attributes` | **PostGIS** | `GET /v1/tiles/attributes` — the Arrow IPC bundle deck.gl joins client-side |
| `marts.neighbor_edges` | **PostGIS** | `GET /v1/wells/{api10}/neighbors`; distances in `geom_compute` |
| `marts.slot_candidates` | **PostGIS** | E17 inventory geometry (SB-03 consumes) |
| AOIs, well sets, scenarios, jobs, audit, API keys | **PostGIS** | mutable operational state (v0.6 §3.5) |

**The rule in one line: geometry, spatial predicates and mutable state in PostGIS; every time
series, every wide fact table and every model artifact in Parquet under DuckDB.**

The consequence v0.6 §3.5 cares about holds: geometry tiles regenerate on GIS refresh (weekly at
most), attribute bundles regenerate on model publication, and **a model rerun does not require
tile regeneration**. `tile_attributes` lives in PostGIS despite being model-derived — it is a
small denormalised keyset that martin's own bbox query filters, and moving it to Parquet would
put a DuckDB read on the tile path's latency budget (150 ms warm, v0.6 §3.7.8). v0.6 §3.4.4
lists it under Marts alongside the DuckDB artifacts; §3.5 puts it in PostGIS. §3.5 wins here and
the ambiguity is errata E10.

### 7.2 Mart definitions owned by SB-01

**`marts.well_month_production`** — the union artifact the API serves:

| Input | Contribution |
|---|---|
| `canonical.production_monthly` where `entity_type='well'` | ND, direct |
| `canonical.production_monthly` where `entity_type='well_completion_pool'` | NM, summed over pools per `(api10, month, stream)`; `aggregation='sum_over_pools'` |
| `marts.well_month_allocated` | TX, `granularity='allocated'` with bounds |

Columns: the `production_monthly` payload plus `granularity`, `reporting_level_source`,
`allocation_model_id` (null unless allocated), `error_lo`, `error_hi`, `aggregation`,
`derivation_id`. Partitioned `(basin, report_vintage, production_month)`. This is the one table
`/v1/wells/{api10}/production` reads, and every row of it carries the four things R5 demands.

**`marts.well_dim`** — non-geometry projection of `canonical.wells` + resolved operator + landing
zone, refreshed whenever a `canonical.promote` touches `wells`. Explicitly a mart, so canonical
keeps exactly one authoritative copy and "marts never ingest" is not bent.

**`marts.tile_geom_*`** — simplified geometry per zoom band, built from `canonical.well_spatial`,
`land_units`, `spacing_units`, `permits`; rebuilt only when the upstream GIS manifest changes.
`tiles.build` derivation per layer build, its `derivation_id` carried in the TileJSON metadata
(SB-07 §12, SB-05 row).

**`marts.tile_attributes`** — `api10`, `model_id`, `as_of_vintage`, plus styling columns
(p50 cum12 per 1,000 ft, operator, well vintage, formation, training-support bucket). Rebuilt on
model publication. **Every model-derived styling attribute carries its own handle** — otherwise
map-styled numbers are naked numbers (SB-07 §12, API-09).

**`marts.neighbor_edges`** — precomputed `(api10, neighbor_api10, distance_m, formation,
neighbor_completion_date)` from `geom_compute` within a configured radius, so `/neighbors`
(p95 budget inside v0.6 §3.7.8) is an index lookup rather than a live spatial join. Recomputed on
geometry change; the radius is a rule parameter.

### 7.3 Cross-store joins

Per v0.6 §3.5: **in Python (Polars) on `api10`, never a foreign data wrapper**, and every
cross-store join emits a derivation naming both store revisions — the Parquet partition manifest
set and the PostGIS transaction id. DuckDB's `postgres` extension is therefore not used, and the
prohibition is v0.6's, not a preference of this document. The helper is
`glasswell.canonical.crossstore.join(pg_query, parquet_scan, on='api10')`, which is the only
sanctioned path and records both revisions itself so a caller cannot forget.

### 7.4 Refresh and invalidation

`canonical.restatement_detected` → `mart.invalidated` (recorded) → rebuild on the next scheduled
run (SB-07 §14 item 4: no automatic cascade). Mart refresh order: `well_dim` → `well_month_*` →
`tile_attributes` → `tile_geom_*` (geometry only when a GIS manifest changed). Each is one
`mart.refresh` derivation over a declared partition.

### 7.5 Attribute-bundle ceiling

OQ-14 asks at what feature count the client-side attribute join needs server-side filtering. The
bundle is measured — not assumed — at every rebuild: `marts.tile_attributes` records
`bundle_bytes` per `(layer, bbox_tier)` and the scorecard carries it. ND's ~20k laterals is the
baseline (`ad:78`, S2); the Permian is an order of magnitude larger, so the measurement exists
before P7 rather than after the map goes slow.

---

## 8. Allocation v0

*Canonical never estimates* (DIR-3, v0.6 §4F.1). Everything in this section produces **marts**.

### 8.1 Placement and identity

`marts.well_month_allocated` — partition key `(basin, report_vintage, production_month,
allocation_model_id)`, exactly SB-07 §1.2. Every allocation model is a **registry citizen**:
`register_model(target='allocation', …)` with `error_bounds` jsonb carrying the measured bounds
from **both** validators (SB-07 §7). No allocated number is served from an unregistered model
(v0.6 4A.13, D-22), and `error_bounds` is a required field, not an optional one.

Row shape: `api10`, `production_month`, `report_vintage`, `stream`, `volume`, `uom`,
`allocation_model_id`, `allocation_tier`, `allocation_basis` (jsonb: the inputs that produced the
split), `lease_key`, `lease_volume`, `error_lo`, `error_hi`, `granularity='allocated'`,
`derivation_id`. `lease_volume` is carried so U13's "what was the underlying lease volume"
is answered from the row rather than by a second query.

### 8.2 Scope measurement first

**Gas leases hold one gas well per lease; allocation is an oil-lease problem** (`ad:180,580`).
The very first P7b allocation task measures the affected share from `OG_WELL_COMPLETION`:

- share of lease-months that are `OIL_GAS_CODE='O'` with more than one active wellbore;
- volume-weighted share of TX Permian production those represent;
- distribution of wells-per-lease, and vintage spread within a lease.

That distribution is published (v0.6 §4F.3) and it drives both the effort estimate and §8.6's
covariate matching. It may be materially smaller than assumed — in which case the honest headline
is "most TX Permian volume passes through unallocated", which is a better result than a large
allocated population with wide bounds.

### 8.3 Method v0 — the basis ladder

Four tiers, evaluated in order, each labelled on every row it produces:

| Tier | Condition | Basis | Granularity |
|---|---|---|---|
| **T0** | lease maps to exactly one well | pass-through | **`observed`** with an explicit 1:1 note (v0.6 §4F.6) |
| **T1** | lease-month in which exactly one wellbore is active (others shut-in, plugged, or pre-first-production) | assign the whole lease volume to that well | `allocated`, narrowest bounds |
| **T2** | ≥2 active wells with sufficient design and age data | apportion **proportional to each well's expectation from a rock-and-design decline model at its own age**, normalised to the lease total | `allocated`, bounds from §8.6 stratum |
| **T3** | ≥2 active wells, insufficient data for T2 | equal split | `allocated`, **widest** bounds |

T0 matters: it is a large share of the population and inflating the allocated count would
understate the system's honesty (v0.6 §4F.6). T2 is the method proper, and its justification is
that differential decline — not lateral length, not equal shares — is the dominant driver of how
a lease total distributes across wells of different ages. The expectation model is a registered
SB-02 artifact, so an allocated volume's `/explain` chain reaches the model that shaped it.

**Circularity guard.** T2 uses a model expectation, so allocated volumes must never become
training targets (invariant §0.4.4). TX models train on TX *lease-level* aggregates or on
transferred ND/NM well-level models — never on allocated output.

### 8.4 What allocation does not do

It does not reallocate across leases, does not infer wells that the crosswalk does not name, does
not smooth across months, and does not fill `no_report` months. A lease-month with no report
produces no allocated rows — `no_report` propagates.

### 8.5 Validator A — crosswalk disagreement (identity-mapping error)

Two regulator-published crosswalks: `OG_WELL_COMPLETION` inside the dump, and
`OG_WELLBORE_EWA_Report.csv` fetched independently (`ad:170-178,579-580`). Neither is corrected
against the other; the **disagreement is the measurement**.

Reported quantities: share of API-10s assigned to different leases; share of lease-months whose
well set differs; **volume-weighted exposure** of the disagreement (the number that actually
matters); and disagreement rate stratified by district and by wells-per-lease. Disagreeing rows
are quarantined `crosswalk_disagreement` (handback H5) — a measurement, not a parse failure —
and remain visible at `/v1/quarantine`.

This bounds **identity-mapping** error. It cannot bound method error, because two crosswalks
agreeing says nothing about whether the split is right.

### 8.6 Validator B — NM synthetic lease-equivalents (method error)

v0.6 §4F.4(b) names this validator; here is how it is built. NM is well-level (`ad:258`), so the
truth is known.

1. **Measure the TX lease population** from §8.2: joint distribution of wells-per-lease, vintage
   spread within lease, operator concentration, stream mix.
2. **Synthesise NM lease-equivalents** by grouping NM well-completions on `(operator, pool,
   spatial contiguity within a stated distance in `geom_compute`)` — the covariates that actually
   define a TX lease — and **resample the groups to match** the TX joint distribution from step 1.
3. **Aggregate** NM well-level volumes into synthetic lease-month totals. Exact arithmetic; no
   estimate enters here.
4. **Run the §8.3 ladder** on the synthetic lease as though the well-level truth were unknown,
   using only inputs that exist in TX (design, age, wellbore status).
5. **Score** per well-month: signed relative error, absolute relative error, and volume-weighted
   bias. Stratify by tier, wells-per-lease, vintage spread and stream.
6. **Publish** the study as an artifact with its own recipe, per stratum.

**Bound construction.** `error_lo`/`error_hi` on an allocated row are the empirical
5th/95th percentiles of the matching stratum's error distribution — not a global constant, and
not a symmetric fraction.

**Composition of the two validators.** They are not added algebraically. Identity-mapping error
changes *which* wells share a lease, which changes the split, so the two interact. Composition is
a **Monte Carlo**: resample the well↔lease assignment from Validator A's disagreement set,
re-run the allocation, and accumulate the empirical distribution; the published bound is that
composed distribution's 5th/95th percentiles. Quadrature or additive combination would assume
independence that does not hold.

**Honest caveat, stated in the artifact and in the E16 matrix.** Bounds transfer on
*lease-composition* covariates, not on rock: NM Delaware is not TX Midland. What Validator B
bounds is the method's error given a lease of a given shape — which is the question — and it does
not claim the same absolute error would obtain on Midland rock.

### 8.7 Error bounds are mandatory

No allocated number is served without `error_lo` and `error_hi` (v0.6 §4F.5), enforced by SB-07
§10 Check 5. If the measured bounds are wide, they ship wide and the notebook says so — a
labelled bad number is Mandate B content; an unlabelled one is a defect (v0.6 R-06).

---

## 9. Scheduling and job orchestration

### 9.1 Timer inventory and ordering

systemd timers invoking one job entry point that writes `jobs` rows (v0.6 C26, §3.1). No Airflow.

| Unit | Schedule (UTC) | Job | Notes |
|---|---|---|---|
| `glasswell-ingest@nd_mpr_xlsx.timer` | Mon 05:00 | fetch → parse → promote | weekly poll; publication irregular |
| `glasswell-ingest@nd_gis.timer` | Sun 04:00 | all `nd_gis_*` layers | includes the weekly pre-spud permit snapshot (§2.2) |
| `glasswell-ingest@fracfocus_csv.timer` | Wed 04:30 | fetch → parse → promote | click-wall acceptance recorded per fetch |
| `glasswell-ingest@nm_ocd.timer` | daily 03:30 | all `nm_ocd_*` | after the observed 22:55–00:22 refresh window (`ad:269-283`) |
| `glasswell-ingest@tx_pdq_dsv.timer` | 1st Tue 06:00 | GUID resolve → member-wise stage → promote | after the last-Saturday publish |
| `glasswell-guidmonitor.timer` | Thu 06:00 | resolve every TX GUID, download nothing | detects rotation between monthly pulls |
| `glasswell-ingest@tx_completions_daily.timer` | daily 07:00 | previous day's zip | plus a resumable backfill job |
| `glasswell-ingest@tx_permits_daf420.timer` | daily 07:15 | daily master+trailer | |
| `glasswell-ingest@tx_wellbore_dbf900.timer` | Sat 06:00 | weekly `.gz` | |
| `glasswell-ingest@tx_gis.timer` | Sat 07:00 | county layers, conditional GET | Permian counties first |
| `glasswell-mart-refresh.timer` | hourly | rebuild marts whose watermark moved | no-op when nothing moved |
| `glasswell-staging-gc.timer` | daily 09:00 | truncate staging older than 30 d | verifies raw integrity before deleting |

**Ordering** is declared, not implied: `lineage.sources.promote_requires` lists the sources whose
current promotion must be present before this one may promote. `nd_mpr_xlsx` requires
`nd_gis_wells` under P1-T0 outcome B; `tx_pdq_dsv` production promotion requires the crosswalk
promotion from the same manifest; `marts.well_month_production` requires all three basins'
production watermarks. A missing prerequisite **fails the job loudly** rather than quarantining
every row as `orphan_fk` — a hundred thousand orphan quarantines is a broken pipeline
masquerading as a data-quality finding.

### 9.2 Idempotent re-runs

Guaranteed by four mechanisms already specified: content-addressed manifests (SB-07 §2.1),
change-only append (SB-07 §3.2), content-addressed derivation ids (SB-07 §1.3), and per-source
`flock`. A single `flock` per source, held for the whole fetch→parse→promote run — never a second
lock on the same file from a callee, which deadlocks. Partial failure leaves the raw zone and
manifests intact (they commit first), staging partial-and-replaceable, and canonical untouched
because the promotion derivation commits atomically or writes `status='failed'` and re-raises.

### 9.3 Concurrency

v0.6 §3.7.3: at most two batch jobs concurrently, batch capped at 5 of 8 vCPU via a systemd
slice, interactive API and tile serving never preempted. SB-01's contribution: ingest units are
`Type=oneshot` in `glasswell-batch.slice`, and the D1 write profile pins `threads=1` for
artifact-producing writes anyway — so the parse stage is single-threaded by determinism
requirement, which conveniently makes it a poor neighbour to nothing.

### 9.4 Backfills

Three bounded, resumable backfills, each a job with a cursor in `jobs.progress`: ND MPR 125
files; TX completion feed daily zips from the resolvable floor; TX county GIS 248+246 zips. Each
rate-limits itself, records the earliest resolvable artifact in the source register, and can be
stopped and resumed without re-fetching (content addressing makes a resumed fetch a no-op).

### 9.5 Freshness contract

`meta.source_freshness` (v0.6 §3.6.2, §3.7.4) needs, per source: latest manifest's
`fetch_vintage`, the upstream declared vintage where one exists, and the last *attempt*. The last
attempt is the part v0.6 §3.4.1 solves with a `fetch_log` table and SB-07 §2.1 solves with audit
events. **SB-07's design wins** — the check is the evidence, and a second table would drift —
but the v0.6 contract keeps its name as a view:

```sql
create view lineage.fetch_log as
select event_id                        as fetch_id,
       (payload->>'source_id')         as source_id,
       occurred_at                     as attempted_at,
       case event_type
         when 'raw.manifest_created'            then 'new'
         when 'raw.fetch_verified_unchanged'    then 'unchanged'
         when 'raw.fetch_failed'                then 'failed'
       end                             as outcome,
       (payload->>'manifest_id')       as manifest_id,
       (payload->>'http_status')       as http_status,
       (payload->>'error')             as error
  from lineage.audit_events
 where event_type in ('raw.manifest_created','raw.fetch_verified_unchanged','raw.fetch_failed');
```

`/v1/health` reports `degraded` when `now() - max(attempted_at) > sources.expected_pull_interval`
for any source (v0.6 §3.7.4). "We checked and nothing changed" and "we did not check" are
distinguishable, which is the whole point (v0.6 R-03).

---

## 10. Test strategy

DIR-10: tests written with or before implementation, never backfilled; fixtures cut from real
regulator downloads so parsers are tested against reality (DIR-1).

### 10.1 Fixture policy

Real bytes, **sanitised only by truncation**. No synthetic idealisations, no hand-written
"representative" rows. Every fixture records the manifest it was cut from and the byte range;
a fixture whose parent manifest cannot be re-fetched and re-hashed is stale and CI says so.
Corpus budget: **< 25 MB** checked in, so a clone is not a download. All content is public
record; no redaction is required and none is performed (redaction would make the fixture a
fiction).

### 10.2 Fixture inventory

| Fixture | Cut from | Contents | ~Size |
|---|---|---|---|
| `nd_mpr_2026_06.xlsx` | `2026_06.xlsx` | 200 data rows + header + the **footer/total row** + a confidential/withheld row + a reported-zero row | 45 KB |
| `nd_mprindex.html` | index page | the period listing incl. an XLSX/PDF overlap period | 30 KB |
| `nd_gis_wells_1township.zip` | `OGD_Wells.zip` | ~50 features in one township, `.prj` intact | 40 KB |
| `nd_gis_horizontals_line_30.zip` | `OGD_Horizontals_Line.zip` | 30 laterals | 60 KB |
| `nd_gis_sections_1township.zip` | `Sections.zip` | one township's sections | 25 KB |
| `tx_pdq_og_lease_cycle.dsv` | `OG_LEASE_CYCLE` | 500 rows; **two districts sharing a `LEASE_NO`**; a row with a field-count shift; a zero-volume row | 120 KB |
| `tx_pdq_og_well_completion.dsv` | `OG_WELL_COMPLETION` | the matching completions incl. a multi-well oil lease and a single-well lease | 60 KB |
| `tx_completions_day.zip` | one `MM-DD-YYYY.zip` | one district; a W-2, a G-1, a **fracture material row (code 2)**, a Formation Data segment, an unparsed segment code | 110 KB |
| `tx_wellbore_dbf900_200.txt` | `dbf900.txt` | 200 records across ≥3 record types incl. a short record | 90 KB |
| `tx_gis_well_permian.zip` | one `well###.zip` | a Permian county subset, **NAD27 `.prj`**, well arcs + bottom-hole points | 300 KB |
| `tx_datum_truth.csv` | P7b-T2 | the NAD83 truth positions for the CI datum guard | 4 KB |
| `nm_wcproduction_300.xml` | `wcproduction.xml` | 300 records incl. an amended row, a `mod_dte` change pair, and an **even-county-code API** | 250 KB |
| `nm_podwc_50.xml` | `podwc.xml` | 50 crosswalk rows | 20 KB |
| `fracfocus_subset.csv` | `FracFocusCSV.zip` | a pre-2013-06 header-only disclosure, a withheld-ingredient row, an implausible `TotalBaseWaterVolume` | 80 KB |

### 10.3 Per-parser unit tiers

Every parser gets four tiers. A parser with fewer than four is not done.

| Tier | Asserts |
|---|---|
| **T1 shape** | fixture parses; column set matches verbatim source names; every column `Utf8`; `source_row_ordinal` is dense and monotonic from 0; row count is exact |
| **T2 adversarial** | each nasty row lands in quarantine with the **exact expected `reason_code` and `rule_id`**; and `staged + quarantined == parsed` (no silent drop) |
| **T3 golden** | the staging Parquet's sha256 equals a checked-in value (D1), and re-running in a fresh subprocess reproduces it |
| **T4 rule-binding** | the parser reads its `parse_directive` from the registry — mutate the rule row (e.g. delimiter `}` → `|`) and assert the parse *changes*. This is the test that proves invariant §0.4.1 rather than asserting it |

T4 is the one that catches the failure mode R8 exists for: a parser that happens to work because
a constant matches the rule, until the rule changes.

### 10.4 Promotion integration tests

Ephemeral PostGIS container + a temp DuckDB per test session (DIR-10). Scenarios, each a named
regression guard:

| Scenario | Assertion |
|---|---|
| Restatement | promote vintage 1, then vintage 2 with one changed month → the changed row appends, prior rows are byte-identical, `_latest` returns v2, `as_of(v1)` returns v1, `restatement_summary` names the touched months |
| Unchanged re-promote | zero rows appended, `unchanged_suppressed` reported, no new derivation output hash |
| Full re-run idempotency | `ingest run` twice with no upstream change → N audit events, 0 manifests, 0 derivations, 0 canonical rows |
| Rule change | supersede a rule → affected partitions re-promote at the **same `report_vintage`** with a new `derivation_id`; `_latest` breaks the tie on `derivation_id` |
| Quarantine release | add the rule that would have accepted a quarantined row → `release_quarantine()` re-parses **from the manifest**, not the payload → row promotes, state `released` |
| ND identity, outcome B | file-number-keyed production joins via the crosswalk; a file number absent from the crosswalk quarantines `orphan_fk` and is **not** dropped |
| TX composite key | two districts with the same `LEASE_NO` produce two distinct leases and their volumes never merge |
| **Datum guard** | the NAD27 fixture transforms to within 1 m of `tx_datum_truth.csv`, **and** the untransformed coordinate differs by > 50 m — both directions, so the guard can fail |
| Undetermined datum | a `.prj` naming neither NAD27 nor NAD83 quarantines every feature `datum_undetermined` |
| Tri-state nulls | reported-zero, no-report and withheld survive promotion as three distinct states |
| NM pool aggregation | summing two pools for one well produces `granularity=observed` with `aggregation='sum_over_pools'`, and the sum is exact |
| Allocation T0 | a single-well lease passes through as `observed` with the 1:1 note, and produces **no** allocated row |
| Allocation T2 | allocated volumes sum to the lease total within DECIMAL rounding, and every row carries `error_lo`/`error_hi`/`allocation_model_id` |
| Cross-store join | a PG↔Parquet join emits a derivation naming both store revisions |
| Ordering guard | promoting `nd_mpr_xlsx` with a stale `nd_gis_wells` fails the job rather than mass-quarantining |

### 10.5 Data-quality assertions and CI participation

Per-promotion assertions expressed as rules and quarantine counts (v0.6 §3.7.6 item 3): row
reconciliation, referential integrity to `wells`, per-basin quarantine share against §4.3's
trigger, unit presence on every numeric column, and the datum regression guard. SB-01 supplies
the fixture database for SB-07 §10's harness (~200 ND wells, ~50 TX leases with crosswalk,
~30 NM wells) and is the owner of Checks 5 and 6's inputs: every production-derived figure
carries unit/granularity/report_vintage, and every canonical column maps to ≥1 rule or appears
in `ci/conformance_exempt.yml` with a reason.

### 10.6 Budget

pytest markers `unit` / `integration` / `contract` (already in `pyproject.toml`). Unit tier
< 20 s; SB-01 integration tier < 3 minutes; both inside SB-07 §10's 5-minute harness budget on
one VM. A gate nobody can afford to run is not a gate.

---

## 11. Storage and volume budget

Reconciled to DIR-9 (`ad:592-597`) and mapped onto SB-06 §3.1–3.2's mounts.

| Zone | DIR-9 figure | SB-01 realised | Mount | Note |
|---|---|---|---|---|
| Raw / immutable | ~15 GB | **~15 GB + ~2 GB/yr of changed re-pulls** | `/srv/glasswell/raw` (HDD) | ND 1.4 GB · TX ~5.5–7 GB · NM 1.72 GB · FracFocus **440 MB per changed pull** (`dsw:39-50`). Growth is bounded by the change rate, not the pull rate — unchanged bytes create no artifact (SB-07 §2.1) |
| Staging, **resident** | "60–90 GB peak" | **8–15 GB** | `/srv/glasswell/staging` (HDD) | The 60–90 GB figure is *uncompressed parsed text* (`ad:456`). Staging is zstd Parquet, so >25 GB of PDQ DSV lands as single-digit GB. |
| Staging, **transient scratch** | not separately stated | **≤ 30 GB peak, TX PDQ only** | `/srv/glasswell/scratch` (HDD) | Only `tx_pdq_dsv` needs on-disk extraction, and only one member at a time (§2.4). NM streams from the zip member (§2.10) and contributes zero. Purged after each member; purged on boot. |
| Spatial staging | — | ~5 GB | tablespace `bulk` → `/srv/glasswell/pgbulk` (HDD) | 248+246 TX county layers plus ND layers, truncated after promotion |
| Canonical + marts Parquet | single-digit GB | **4–8 GB**, plus ~1–2 GB/yr of restatement vintages | `/srv/glasswell/parquet` (HDD) | Change-only append means vintages cost the *churn*, not a full copy (SB-07 §3.2) |
| PostGIS | ~20 GB | **12–20 GB** | PGDATA (SSD) | geometry + compute geometry + GiST indexes + tile sources + operational state |
| DuckDB spill | — | ≤ 20 GB headroom | `/var/lib/glasswell/duckdb/tmp` (SSD) | SB-06 §3.1 |
| Model artifacts, backups | ~20 GB | ~20 GB | SSD / HDD | SB-02, SB-06 |

**Where SB-01 narrows DIR-9, and why it is a narrowing rather than a contradiction.** DIR-9's
60–90 GB assumes every source is materialised uncompressed. The per-source pipeline never does
that: NM is streamed, TX is extracted one member at a time, and everything lands as Parquet. The
honest budget is therefore ~15 GB resident staging plus a ≤30 GB transient peak that exists for
the duration of one member's load, once a month. **The DIR-9 conclusion is unaffected: storage
is not a constraint** (`ad:597`). HDD total at maturity: 15 + 15 + 30 + 5 + 8 ≈ 73 GB of 1,000 GB.
SSD: SB-06 §3.2's ≈104 GB of 150 GB budget stands, with SB-01's PGDATA share inside its ~60 GB
allowance.

**The measured number.** FracFocus is **440.2 MB compressed → 3.26 GiB across 18 members**,
measured 2026-08-21 by `HEAD` plus a ranged read of the zip central directory, without
downloading the archive (`dsw:39-79`). It was the one unmeasured figure in this budget. Three
consequences, none of which move the conclusion: raw gains 440 MB per *changed* pull, not per
pull; the ~8× expansion ratio is why §2.3 streams each member out of the zip rather than
extracting the archive, so like NM it contributes **zero** to the scratch line and single-digit
GB of Parquet to resident staging; and the weekly restatement compare (§2.3) reads every changed
member in full — ~102–245 MB per registry shard, 3.26 GiB in the worst case — which is a CPU and
I/O cost on a source that publishes no per-row modification stamp, not a storage cost. **Storage
is still not a constraint** (`ad:597`).

---

## 12. Phase mapping

| Phase | SB-01 work | Exit |
|---|---|---|
| **P0** | 14 P0 conformance seeds with evidence URLs and hashes (§4.1); `crs_registry` rows; canonical DDL for identity, dimensions, `land_units`, `field_units`, `glossary_terms`; `sources` register extension; staging/scratch path allocation; write profile pinned; fixture harness scaffolded | Seeds committed with evidence; `land_units` abstraction exists before any TX data; one staging Parquet write replays byte-exact |
| **P1** | **P1-T0 identity (first hour)**; **P1-T1 attribute schemas**; `nd_mpr_xlsx` + `nd_gis_*` fetchers, parsers, staging, promotion; ND canonical spine; PostGIS geometry load with datum handling; FracFocus first pull and size measurement; quarantine live; vintage capture from day one | Every ND production row explains to a manifest and cites its rules; the identity decision is a committed rule with evidence; a synthetic restatement appends without touching prior rows; a re-fetch of unchanged bytes is a logged no-op; the quarantine path is **exercised by an injected fixture** (see errata E8) |
| **P2** | `marts.well_month_production`, `well_dim`, `tile_geom_*`, `tile_attributes`, `neighbor_edges`; attribute-bundle sizing baseline | Every UI figure has a reproducing endpoint reading a mart, not canonical directly |
| **P7a NM** | `nm_ocd_*` FTP fetch with host-resolution failure handling; streaming XML parsers; `wcproduction`, `wellhistory`, `wchistory`, `spacingunit`, `podwc`; `mod_dte` detection; well-level Permian spine; NM county-parity rule exercised | NM well-level spine promoted; NM restatement detected and vintaged; parity rule cited by a real derivation |
| **P7b TX** | GUID resolution + rotation monitor; `tx_pdq_dsv` member-wise staging; composite lease key; `dbf900` (**P7b-T3** layout); county GIS with **P7b-T2** datum truth set; completion feed + permits; **allocation v0** with both validators; TX abstracts into `land_units` | S6: bounds from both validators published; oil-lease share measured and published; quarantine share reported **by basin** against §4.3's trigger; U13/U21 pass on TX data |

---

## 13. Interfaces

| Counterparty | SB-01 consumes | SB-01 emits |
|---|---|---|
| **SB-07** | `fetch_raw`, `derive`, `apply_rules`, `quarantine`, `release_quarantine`, `open_vintage`, `as_of`, `figure`, `register_model`, `resolve_model`, `emit`; the eight rule kinds; determinism classes; the CI harness | one manifest per changed artifact; `stage.parse` / `canonical.promote` / `mart.refresh` / `alloc.apply` / `tiles.build` derivations with rules on every promotion; quarantine rows with reason codes; vintage rows with `restatement_summary`; `canonical.restatement_detected`; `conformance_rules` rows with `spec`, `evidence_url`, `code_ref_sha256` |
| **SB-02** | model registry for the allocation expectation model | `marts.well_features` inputs; `canonical.production_monthly` at a pinned `as_of`; per-field granularity on completion design; the **prohibition** on training against allocated volumes; censoring inputs (withheld share, confidential release dates) |
| **SB-03** | — | `marts.well_month_production` with granularity and bounds; `marts.slot_candidates` geometry; `land_units`/`spacing_units`; `neighbor_edges`; AOI diff inputs incl. the ND constructed permit stream |
| **SB-04** | envelope helpers, error envelope | mart columns through `figure()` with unit/granularity/report_vintage/basis; `/v1/quarantine`, `/v1/conformance`, `/v1/manifests` content; `source_freshness` inputs; the `lineage.fetch_log` view |
| **SB-05** | — | `tile_geom_*` layers and their `tiles.build` derivation ids; the Arrow attribute bundle and its per-attribute handles |
| **SB-06** | mounts, PG roles/tablespaces, timers, backup set | required additions: `/srv/glasswell/staging`, `/srv/glasswell/scratch` (≥30 GB, purge-on-boot); two OS users for pipeline/API role separation (H9); raw-zone layout reconciliation (H7) |
| **SB-00** | v0.6 as the contract | §16.1 errata; the granularity-vocabulary ratification (H3); glossary rows for *reporting level, disposition, crosswalk, allocation tier, scratch zone, layout artifact* |

---

## 14. Rejected alternatives

- **All-PostgreSQL staging** — 60–90 GB of transient rows through WAL, autovacuum and a spinning pool, for data that never serves and is deleted in 30 days.
- **All-Parquet staging including geometry** — shapefile → Parquet → PostGIS is a double conversion with a CRS round-trip in the middle; GDAL's PG driver is the boring path.
- **`ogr2ogr -t_srs` at load time** — fast, and it puts a coordinate transform outside the CRS service and outside lineage.
- **3-parameter / Molodensky NAD27→WGS84** — metre-level residuals, the same order as the error being removed; grid shift with a manifested grid file or nothing.
- **One projected CRS for both Permian sub-basins split by UTM zone** — makes Delaware↔Midland distances incomparable and puts a zone boundary through the study area; the 1.1 mm/m distortion of a single zone is two orders below the datum hazard.
- **DuckDB `postgres` extension / FDW for cross-store joins** — prohibited by v0.6 §3.5; also hides the two store revisions a cross-store derivation must name.
- **DuckDB native tables for canonical** — duplicates the data, reintroduces a single-writer bottleneck on the serving path, and breaks partition-level derivation addressing.
- **FracFocus SQL Server `.bak`** — requires a SQL Server (or a fragile `.bak` reader) on a VM whose stack is Python/DuckDB/PG; the CSV carries the same four components (`ad:332,337`).
- **`pandas`/`openpyxl` for XLSX** — re-types columns on inspection, which puts an interpretation in the source-faithful layer.
- **`lxml.objectify` / `xmltodict` for NM** — DOM parse of 10–20 GB on a 16 GB VM.
- **FIFO/named-pipe streaming of the PDQ zip** — no restart, no re-read, and a re-run cannot be byte-identical.
- **Extracting the whole `PDQ_DSV.zip`** — >25 GB of scratch where one member at a time needs ≤30 GB.
- **TX EBCDIC P-4 file** — the same content ships as ASCII in the completion feed; an EBCDIC decoder is a parse-risk class avoided outright.
- **Fuzzy operator matching** — an unlabelled estimate in the identity layer; unmatched goes to a manual alias row with evidence instead.
- **Merging the two TX crosswalks into one canonical link** — destroys the disagreement measurement that S6 depends on.
- **Equal-split allocation as the method** (rather than the T3 fallback) — indefensible for leases mixing 2015 and 2024 completions.
- **Allocation proportional to lateral length alone** — ignores age and decline, the dominant drivers.
- **Allocation from operator-reported well tests** — sparse, point-in-time, and biased by test conditions.
- **Quadrature combination of the two validators' errors** — assumes an independence that does not hold; Monte Carlo composition instead.
- **A `fetch_log` table** — SB-07's audit events already record the fact; a second table drifts. Kept as a view so the v0.6 contract name still resolves.
- **Row-level provenance in staging** — v0.6 D-6 pins manifest-level lineage; `source_row_ordinal` already makes any row locatable.
- **Airflow/Dagster/Prefect for ingest ordering** — a dozen jobs and a `promote_requires` array on the source register.

## 15. Cut as gold-plating

1. **ND MPR PDF back-extraction (2003-01 → 2015-04)** — deferred within P1 (v0.6 §7.1); manifests are still fetched so the bytes exist when the parser does.
2. **TX P-4 EBCDIC, TX directional surveys, ND Daily Activity Reports, Go-Tech, EMNRD WDA API** — §2.11, each with a reason. TX surveys are two cuts, not one: pre-2021 filings are `data-unreachable` and cannot be bought back with effort; 2021-onward filings are `effort-unreachable` and could be, at effort L, whenever a feature justifies it.
3. **A staging query surface.** Staging never serves; there is no `/v1/staging` and no debugging endpoint over it. The quarantine surface plus the raw manifest is the debugging path.
4. **Column-level provenance in promotion** — answers a question no S-criterion asks (SB-07 §14).
5. **Automatic mart recomputation cascade on restatement** — recorded invalidation plus the next scheduled rebuild (SB-07 §14 item 4).
6. **A generic ingest DSL / plugin framework.** Eleven sources, seven formats, one function signature each.
7. **Incremental XML diffing for NM.** `mod_dte` at promotion is the delta mechanism; the whole zip still gets one manifest (SB-07 §2.1).
8. **Serving `disposition_monthly` in v0.6.** Promoted so nothing is discarded; no endpoint, no feature, no model input.
9. **Flaring analytics.** NM reports it per Property and it is not allocable to wells (`ad:315`); the limitation is a rule row, not a feature.

---

## 16. v0.6 errata and handbacks

### 16.1 v0.6 errata — defects found in the contract

Fifteen. Each is a defect in `blueprint-v0.6-draft.md`, not a divergence taken by this document.

| # | § | Defect | Proposed resolution |
|---|---|---|---|
| **E1** | §3.4.3 vs SB-07 §3.2 | The bitemporal production table exists twice under two names (`production_observations` / `canonical.production_monthly`) with two different keys. v0.6's key omits `source_id`; SB-07's hardcodes `api10`, which **cannot represent a TX lease row** and therefore contradicts §4F.1 and DIR-3. | One name, `canonical.production_monthly`; key `(entity_type, entity_key, production_month, stream, source_id, report_vintage)` per §6.3 |
| **E2** | §3.4.1 | The `fetch_log` table is superseded by SB-07 §2.1/§5.2's audit events; keeping both guarantees drift | Define `fetch_log` as a view over `audit_events` (§9.5) |
| **E3** | §3.4.1 | `manifests.parser_id` / `parser_version` is a normalisation error: one manifest may be parsed by several parser versions over time. Parser identity belongs on the `stage.parse` derivation | Drop both columns; `code_version` on the derivation plus the `parse_directive` rule ids carry it |
| **E4** | §3.2 C8, §3.4.3 | Proppant and fluid intensity are described as arriving *from* FracFocus. FracFocus has no proppant-mass field; reconstructing pounds requires `TotalBaseWaterVolume`, which peer review calls unreliable (`ad:344`). Proppant intensity is "the most-cited single completion-design variable" (§9) resting on an unstated derivation | Per-field `granularity` on `completion_events`; FracFocus-derived proppant is `modelled` with its own derivation; TX also uses the free interval-level material segment |
| **E5** | §3.0.2, §3.4.3 | `production_observations.entity_type` includes `well_completion_pool` but §3.0.2's canonical entity list has no well-completion entity and no table defines the NM completion key | Add `canonical.well_completions` (§6.2) and the entity to §3.0.2 |
| **E6** | §3.4.4 | `allocated_production.allocation_id` is simultaneously the row's own id and the FK to `allocation_runs` — one column, two cardinalities. No uniqueness statement and no allocation-tier field | Split into `allocation_row_id` and `allocation_model_id`; add `allocation_tier` (§8.1) |
| **E7** | §3.7.6 item 2 | The prescribed golden fixture is "the `}` delimiter with an **embedded `}`**". With **no enclosure characters** (§3.0.3) an embedded delimiter is unrepresentable — such a row cannot exist as valid data. The fixture as specified is incoherent | Replace with a **field-count-shift** row asserted to quarantine `schema_mismatch` (§10.2) |
| **E8** | §7.1 P1 exit | "quarantine share measured and **non-zero**" makes a clean source a phase-exit failure and rewards manufacturing rejects | Exit on the quarantine *path* being exercised by an injected fixture, plus the share being *measured* whatever it is |
| **E9** | §3.0.3 | The NM even-county-code rule is stated as fact; the assessment marks it **LIKELY**, not VERIFIED (`ad:316`) | Seed the rule as a **prohibition on parity filtering**, correct under either truth, with the evidence tagged LIKELY (§2.10) |
| **E10** | §3.4.4 vs §3.5 | `tile_attributes` is listed among the DuckDB marts in §3.4.4 and assigned to PostGIS in §3.5 | §3.5 wins; §3.4.4 should say so (§7.1) |
| **E11** | §2.3, §7.1 P1 | ND directional surveys are committed as in-scope, but whether `NDOGD_Surveys` carries station-level MD/INC/AZI is UNVERIFIED (`ad:97,638`) — an in-scope commitment with no verification gate | Gate it: P1-T1 (§2.2); a negative answer is an honest gap tagged data-unreachable |
| **E12** | §3.6.12 row 6 | `/v1/wells/{api10}/production` takes `granularity` as a **request** parameter, but granularity is an output property (R5), not a user-selectable dimension | Rename to `granularity_filter` with an explicit enum, or drop it; SB-04 to decide |
| **E13** | §3.7.1 | The sizing table labels 60–90 GB as *staging residency*. That figure is uncompressed parsed text (`ad:456`); Parquet staging never materialises it wholesale. The line conflates a transient decompression scratch requirement with resident cost | Replace with §11's decomposition: ~8–15 GB resident, ≤30 GB transient scratch, one member at a time |
| **E14** | §3.7.4 | The ND DMR GIS row reads as though the whole DMR mirror is stale. `ad:68` says the *downloads* refresh daily; `ad:96` says only the PLSS layers are stale | Scope the staleness note to the PLSS layers |
| **E15** | §4E.3, §3.7.4 | FracFocus restatement detection is specified against a **modification date the CSV distribution does not carry** — no `DTMOD` and no per-row stamp in any of its three schemas (`dsw:82-105`). SB-01 inherited the same defect in §2.3 and §5.4 from `ad:499`. A detection design keyed on an absent field does not fail at review, it fails on the first pull, and it fails by finding nothing | Member-level `sha256` for *whether*, `value_hash` on `DisclosureId` / `(DisclosureId, IngredientsId)` for *which* — the append-only vintage model already does both (§2.3, §5.4). **Applied in this amendment**, in v0.6 §4E.3 and §3.7.4 and here |

### 16.2 Cross-SB conflicts handed back

| # | To | Conflict | Proposed resolution |
|---|---|---|---|
| **H1** | SB-07 | §3.2's `canonical.production_monthly` keys on `api10`, contradicting DIR-3/§4F.1 for TX. SB-07 §0.1 assigns canonical column design to SB-01 | Adopt §6.3's key. SB-07 §1.2's partition key and §1.8's worked example are unaffected |
| **H2** | SB-07 | §3.3's as-of view uses `QUALIFY`, which **PostgreSQL does not support**; the claim that "DuckDB and Postgres both express this as a window function" is only half true. The tiebreak `created_at desc` is wall-clock and therefore not replay-stable | Adopt §6.9's two forms; tiebreak on `derivation_id` |
| **H3** | SB-07 / SB-00 | Granularity vocabulary conflict: §9.1's `well_observed \| lease_reported \| lease_allocated` vs v0.6 R5's `observed \| allocated \| modelled \| assumed` | Canonical stores `(granularity, reporting_level)`; the envelope token is the composition in §6.4. SB-00 ratifies |
| **H4** | SB-07 | `parse_directive`'s spec shape cannot express a 100-field fixed-width layout, and `member_glob` does not cover the stream-from-zip-member case | Add `layout_ref` + `layout_sha256` (CI-verified like `code_ref`) and `member_stream: bool` |
| **H5** | SB-07 | Reason-code gaps: a FracFocus trade-secret claim is not a regulator statutory withhold, and §8.5's crosswalk disagreement is a measurement, not a parse failure | Add `withheld_trade_secret` and `crosswalk_disagreement` |
| **H6** | SB-07 / P0 code | The shipped `lineage.sources` lacks the v0.6 §3.4.1 columns (cadence, licence status/evidence, ToS notes) that the freshness contract and the scorecard need | §1.1's `alter table`, plus `promote_requires` for §9.1's ordering |
| **H7** | SB-06 / SB-07 | **Two incompatible raw-zone layouts.** SB-06 §3.3: `/srv/glasswell/raw/<source>/<dataset>/<vintage>/` with `MANIFEST.sha256` + `FETCH.json`. SB-07 §2.3: `/data/raw/<source_id>/<source_key_slug>/<vintage>T<hhmmss>Z-<sha256[:12]>/` with `payload.<ext>` + `manifest.json`. SB-01 is the consumer of both and cannot implement two | SB-07's **grammar** (the hash suffix is what makes two same-day fetches of different bytes non-colliding) at SB-06's **root** (`/srv/glasswell/raw`), retaining SB-06's `MANIFEST.sha256` *in addition* to `manifest.json` because "`sha256sum -c` with no arguments and no external state" is a genuinely valuable restore property |
| **H8** | SB-06 | Two paths are unallocated: the tabular staging Parquet root and the extraction scratch root (≤30 GB peak, purge-on-boot) | Add `/srv/glasswell/staging` and `/srv/glasswell/scratch` to §3.1/§3.2, both on the HDD zvol |
| **H9** | SB-06 / SB-07 | **Role separation is defeated.** SB-06 §1.3 promises one login role `glasswell` with `peer` auth; SB-07 §11 requires `glasswell_pipeline` (RW on lineage) and `glasswell_api` (RO plus narrow inserts) to be genuinely separated. One OS user peer-mapped to one role means the API can rewrite pipeline lineage | Two OS users — `glasswell` (API) and `glasswell-ingest` (pipeline) — each peer-mapped to its own login role inheriting the corresponding `nologin` group role |
| **H10** | SB-06 | DIR-9's 60–90 GB staging figure is carried into SB-06 §3.2's `bulk` tablespace sizing. Under §3.2's split, `bulk` holds only spatial staging (~5 GB) and the bulk of staging is Parquet | Re-scope the `bulk` tablespace note; the disk budget is unchanged and gains headroom |
| **H11** | SB-07 | §2.4's `acquisition_method` enum has four values and no way to express a paginated service harvest, which §1.2.1 now sanctions for hosts outside the ND DMR mirror | Add `arcgis_rest_paginate` to the enum, with `acquisition_params` = `{service_url, layer_id, layer_json_sha256, service_version, where, out_sr, format, result_record_count, order_by, pages, count_before, count_after, features_written}`, and `page_walk_incomplete` / `host_token_gated` to the `raw.fetch_failed` reason vocabulary |

### 16.3 Open items handed back

| Item | Owner | Why not decided here |
|---|---|---|
| P1-T0: ND MPR keyed on API-10 or NDIC file number | SB-01, **first hour of P1** | Requires opening the file; both branches are fully specified (§2.1.3) |
| P1-T1: ND operator key, pool/landing-zone attribute, survey station granularity | SB-01, P1 | Requires opening the archives; each outcome maps to a rule row or a recorded honest gap |
| P7b-T2: the NAD83 truth set for the CI datum guard | SB-01, P7b | No source is identified anywhere in the assessment; the daf420 lat/long datum is itself unknown |
| P7b-T3: `dbf900` record layout | SB-01, P7b | The assessment names the manual, not the structure |
| ~~FracFocus download size~~ — **CLOSED 2026-08-21** | — | Measured without downloading: 440,245,205 bytes → 3.26 GiB, 18 members (`dsw:39-79`). The stated blocker was wrong as well as stale — HEAD and range both succeed unauthenticated (`dsw:55-63`). Register, §2.3 and §11 carry the figure |
| NM uncompressed XML size | SB-01, first pull | 10–20 GB is a compression-ratio estimate (`ad:640`) |
| TX completion-feed true archive floor | SB-01, backfill | Portal pagination caps at 250 entries (`ad:213`) |
| Whether Permian wellbore quarantine share justifies the 5% trigger | SB-01, P7 exit | The threshold is a judgment (v0.6 §11); §4.3 makes it falsifiable |
| Geology feature boundary (OQ-2) | SB-02 | Depends on P1-T1's landing-zone answer and the ablation |
| Confidential/tight-hole censoring policy (OQ-7) | SB-02 | SB-01 supplies the measured affected share; the policy is modelling |
| Re-promotion compute share threshold (OQ-15) | SB-01, once ~40 rules are live | §5.6 instruments it; the batching decision needs the measurement |
| TX inventory geometry (OQ-11) | SB-03 | `land_units` keeps it a design question, not a migration |
| **TX RRC licence grant** — §1.1's register asserts a posture the published grant contradicts | **OWNER / COUNSEL** | RRC's site policy, re-fetched verbatim 2026-08-21: *"RRC grants permission to copy and distribute the information on its website for **noncommercial use, as long as the content remains unaltered** and is not presented in a misleading way"*, plus *"as long as a fee is not charged to access our material"* (`dsw:1272-1290`). §1.1's seven `tx_*` rows read **"free, no redistribution clause"** (`ad:411-419`), which is not what the grant says. Countervailing facts, stated without a preferred reading: this is Texas public information under Gov. Code Ch. 552, the policy is a website disclaimer rather than a negotiated data licence, the bulk page says "free of charge", and the GIS service returns an empty `copyrightText` (`dsw:1289-1293`). **Whether that grant admits a commercial derived-analytics product is a legal reading and SB-01 does not take one** — `dsw:1453-1455` says so in terms ("Needs counsel, not a preferred reading"), and `work-output/QUEUE-DISPATCH.md` routes it to the owner queue. The 2026-08-21 owner ruling ("publicly reachable ⇒ usable; counsel gates lifted") lifts the gate on *proceeding*; it does not ratify the register cell, which is a claim about a licence and not about reachability. **Recorded here, unresolved, and it gates every `tx_*` row already in scope — not only new TX sources.** |

### 16.4 Apply-order adjacency with the carried-forward amendments

`work-output/CADENCE.md` §1.3 carries six amendments accepted in the reconciliation set and never
applied — SB-01 **E9**, **H4**, **H5**, **H6**, plus SB-03 E-14 and an SB-02 open item — and
assigns them to the pre-P3 B-gate track (§"B-gate"). **None of them is applied here**, and
nothing in §1.2.1, §2.11 or §2.3 depends on one landing first. What follows is the adjacency, so
that whoever applies them next is not surprised by a document that moved underneath them:

| Carried-forward | Touched by this set? | Adjacency, and what it means for order |
|---|---|---|
| **E9** — grade the NM even-county-code evidence `LIKELY`, not `VERIFIED` | No | No NM text moved. It is the **same class** as two amendments here, though: a claim carried at a confidence its evidence does not support. E9 fixes a grade; §1.2.1 and §2.3 fixed a scope and an absent field. Independent — apply in any order |
| **H4** — `parse_directive` gains `layout_ref`, `layout_sha256`, `member_stream` | Yes, twice | It gains two consumers. §2.11 names `layout_ref`/`layout_sha256` as the mechanism a multi-template TX survey PDF parser would need, and §2.3's per-member detection makes the **member** the unit of both parse and change — which is exactly `member_stream`, previously justified by TX PDQ alone. H4 is now load-bearing for two more sources; **apply before any FracFocus or TX-survey parser**, not before this set |
| **H5** — quarantine reason codes `withheld_trade_secret`, `crosswalk_disagreement` | Adjacent, unchanged | §2.3's measured schema **strengthens** H5's FracFocus half: `ClaimantCompany` is confirmed present in the CSV distribution (`dsw:90-95`), so the trade-secret claim is a column, not an inference. A restatement is not a quarantine, so nothing in §2.3's detection rewrite touches H5's substance. Independent |
| **H6** — `alter table lineage.sources`, `promote_requires` | Adjacent, no constraint | §1.1's `alter table` **is** the H6 migration, and §1.2.1 adds a fifth value to the `access_method` vocabulary it carries. No ordering constraint today for two reasons: §1.2.1 registers no source, and §1.1's `access_method` is plain `text` with no `check`, so a new value needs no DDL. The constraint arrives with the first REST source registration, and it is on **H11** (the SB-07 enum), not on H6 |
| **SB-03 E-14**, **SB-02 open item** | No | Neither is SB-01's surface. No interaction |

One thing this set **adds** to that queue rather than resolving: **H11** (§16.2), which is H4's
sibling — both are SB-07 surface changes that SB-01 needs and cannot make itself. If the B-gate
track batches SB-07 handbacks, H11 travels with H4.
