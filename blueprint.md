# glasswell

**Product and engineering blueprint. v0.5 (canonical model thesis, competitor harvest, rename)**
Formerly basinforge. Personal platform: well-level upstream analytics on public data, API-first, map-first, agent-ready, multi-basin, fully self-explaining.

Owner: Ryan MacDonald. Status: in build — the North Dakota slice is deployed and serving. This document is the contract to spec against; anything not in scope here is out until this doc changes.

v0.5 changes: project renamed glasswell (naming note, 1.3). Canonical data model promoted from implicit to thesis (Section 3.0) with rule R8 and a conformance registry seeded by real cross-source gotchas. Competitor feature harvest folded in: three-stream forecasting, analog finder, type-curve builder UI, econ tornado, operator league table, AOI alerts, portfolio sets, and inventory v0 (E17). Econ assumptions gain water handling cost and per-state tax defaults.

---

## 1. Purpose and framing

### 1.1 Dual mandate

**Mandate A, the stake in the sand.** Recreate the core product loop sold by Novi, EVA, ComboCurve, Enverus and Petro.ai, in a garage, on public data, by one builder. The point is a measured demonstration: what is reproducible without the proprietary network, and therefore where the real floor sits under the category's value. The closing artifact is a capability matrix against the incumbents' public product surfaces, with evidence per row and honest gaps stated.

**Mandate B, the learning instrument.** The system itself must teach. If a visitor cannot trace any figure on screen back to a checksummed regulator file, the system has failed Mandate B regardless of accuracy.

These are one mandate seen from two sides. Incumbents sell trust through brand and curation claims from a black box. A garage build cannot compete on brand or data volume, so its only trust mechanism is total transparency. Glass-box lineage is simultaneously the proof of capability, the pedagogy, and a live product thesis: audit-grade provenance is a feature this category should ship and does not.

Positioning note: the "against Novi/EVA" framing is internal motivation. Anything public-facing is gated behind the IP carve-out (8.2). The capability matrix is worded as what a garage build proves about the floor.

### 1.2 Questions this project exists to answer

1. Where does public data fail, and what exactly does proprietary data buy?
2. How large is the ML advantage over type curves when measured honestly?
3. What does the forecast-to-dollars path look like, and who consumes which output?
4. What does an API-complete analytics product feel like to build and operate?
5. Where does the agent layer fit, and what does it demand from the API?
6. What is the measured error rate of public data, and what does allocation cost in accuracy?
7. Does a model trained in one basin transfer to another, and what breaks when it moves?
8. What does audit-grade lineage cost, and is it viable as a product feature?
9. How much of the category's product surface is schema and conformance work rather than modeling, and can conformance-as-data stand as a differentiator?

### 1.3 Naming

**glasswell**: the glass-box thesis plus the domain object, one word, lowercase, in-house style. Renamed from basinforge at v0.5 because the project's center of gravity moved from "multi-basin, hand-built" to "fully self-explaining"; the name should carry the thesis. basinforge is retained as a repo alias so prior notes resolve.

**What this is not.** Not a commercial product. Not multi-user. Not an ownership graph. Not daily production. Not a lineage ontology platform. Not an OSDU implementation (mapping exercise only, 3.0.6).

---

## 2. Product brief

### 2.1 Problem statement

Upstream capital decisions (drill, buy, lend, trade) all reduce to: given rock, design, and depletion by neighbors, what will a well produce and what is that worth. Incumbent workflow is manual type curves in spreadsheets. Vendors sell curated data plus ML forecasts plus economics plus dashboards, from black boxes. This project rebuilds the public-data tier of that stack end to end, across two structurally different reporting regimes, as a fully self-explaining system.

### 2.2 Personas

| Persona | Decision | Needs |
|---|---|---|
| Reservoir engineer | Where and how to drill next | Scenario forecasts, spacing context, design sensitivity, analogs |
| A&D / PE analyst | Buy or pass | Acreage rollups, NPV per well, breakeven distribution, inventory, confidence per number |
| Minerals buyer | Price a royalty interest | PDP forecasts under NRI, valuation at a deck |
| Equity analyst | Long/short an operator | Activity pace, design evolution, capital efficiency, league tables |
| OFS BD | Which operators to call | Permits, DUC proxy, activity heatmaps, AOI alerts |
| Agent / developer | Answer questions programmatically | Complete self-describing API |
| Auditor / skeptic | Trust or reject a number | Full derivation to raw source; repro recipe; conformance rules |

The agent and the auditor are first-class. If the agent cannot do it, the API is incomplete. If the auditor cannot trace it, the number does not ship.

### 2.3 Scope

**In, phase order:**
- Basin 1: North Dakota (Bakken/Three Forks): well-level production, FracFocus, surveys, tops, permits, PLSS, spacing units.
- Basin 2: Permian. TX (Midland, TX Delaware): RRC PDQ lease production, W-2/G-1 completions, W-1 permits, GIS well lines, wellbore master; allocation v0. NM (Delaware): OCD well-level production as third spine and allocation validator.
- Cross-cutting: three-stream forecasting (oil primary; gas and water secondary), type curves, gradient-boosted quantile model with conformal calibration, DCF economics with sensitivities, scenarios, analogs, inventory v0, benchmark harness, forecast ledger, quality scorecard, conformance registry, glass-box lineage, vector-tile map, agent gateway.

**Out:** mineral ownership, daily production, multi-tenant auth (design only), distributed infra, mobile, lineage ontology, rig/frac-crew tracking (documented moat item), interpreted maturity mapping (moat item), news/research layer.

**Deferred until after P6:** Canada, NGL three-stream economics beyond simple gas pricing, fault-aware geology, additional basins, public release (IP-gated).

### 2.4 Success criteria

System outcomes:

- S1. A stranger with the OpenAPI doc and a key reproduces every number in the UI.
- S2. 20k+ laterals with model-driven styling at interactive frame rates on one VM.
- S3. Scenario returns forecast plus NPV in under 3 seconds.
- S4. Benchmark artifact per basin, sliced, type curve vs ML on identical temporal holdout.
- S5. Agent passes the 10-question suite via public tools, every figure traceable.
- S6. Allocation v0 with measured error bounds from both validators.
- S7. Forecast ledger live with one graded cycle complete.
- S8. Quality scorecard published, reproducible from the API.
- S9. Glass box holds: any UI number to raw manifest in 3 or fewer interactions and one /explain call.
- S10. Capability matrix with evidence links and honest gaps, each gap tagged data-unreachable or effort-unreachable.
- S11. Conformance registry served: every cross-source number can cite the rules that shaped it.
- S12. Inventory demo: remaining locations for a chosen township with forecasts and NPV at a deck.

Fluency outcomes: F1 through F9 as v0.4, plus
- F10. Can explain why cross-source conformance is most of the ETL moat, with the registry as evidence.

### 2.5 Design philosophy: glass box

1. **No naked numbers.** Every served figure carries a derivation handle. Untraceable equals wrong.
2. **The kitchen is the product.** Preparation, cleaning decisions, rejected rows, and conformance rules are queryable surfaces. The quarantine table has an endpoint.
3. **Reproducibility is an output.** Every artifact carries the recipe that regenerates it byte-for-byte.
4. **Quiet by default, verbose on request.** Lean responses; ?explain=true inlines lineage; the drawer holds the chain.
5. **Append-only memory.** One audit stream; restatements are new events, never edits.
6. **The build emits learning.** Findings memos live at /notebook with live data links.

---

## 3. Architecture brief

### 3.0 Canonical model thesis

The claim: in this category, the unified data model is the product. Novi's loudest technical claim is its ETL; EVA's is interpretation; OSDU exists because no two schemas agree. Rebuilding the canonical model, and exposing every decision inside it, is therefore Mandate A work, not plumbing.

**3.0.1 Three layers.** Staging is source-faithful: one schema per regulator file type, no opinions, quarantine for rejects. Canonical is conformed: one schema for the domain, every mapping decision recorded. Marts serve: features, tiles, rollups, all derived from canonical only. Staging never serves; marts never ingest.

**3.0.2 Canonical entities.** Well (API-10), wellbore (API-12/14, see 3.0.5), operator, lease (TX), production observation (well, month, stream, volume, granularity, allocation ref), completion event, spatial features (surface point, bottomhole, lateral), formation top, permit, land unit, spacing unit.

**3.0.3 Conformance as data (rule R8).** Every cross-source mapping decision is a row in `conformance_rules` (source, field, rule, rationale, effective date), served at /conformance and referenced by derivations. Seed rows from real gotchas:

- Legacy TX RRC coordinates are frequently NAD27; modern layers are NAD83/WGS84. Untransformed NAD27 is off by up to roughly 100 m, enough to silently corrupt spacing math. Rule: datum detected per file vintage, transformed to EPSG:4326 for storage, transform recorded in derivation.
- Compute CRS per basin in `crs_registry` (projected, meters): ND in UTM 14N, Permian in UTM 13N. Storage always 4326; distance math always projected.
- Condensate vs oil classification differs by state. Rule: keep regulator classification in staging; canonical carries stream plus a `liquids_policy` tag; oil-plus-condensate is the default modeling liquid, stated everywhere it appears.
- Gas volumes conform to mcf at the regulator's stated conditions; conditions recorded, not silently normalized.
- Month convention (production month vs report month) resolved per source and recorded.
- Formation names conform through `formation_aliases` (reported name, canonical formation, basin, confidence); tops and landing zones pass through it.
- Well status vocabularies map to a small canonical set; the mapping is rows, not code.

**3.0.4 Identity policy.** API-10 identifies the well and is the spine. API-14 normalizes to API-10 for joins.

**3.0.5 Wellbore simplification (pinned decision).** One producing wellbore per API-10 is assumed. Sidetracks and multi-completion wellbores are detected (API-12 suffix, multiple W-2s) and quarantined with reason rather than mis-joined. Measured share of quarantined wellbores is reported in the scorecard; if it exceeds 2% in a study area, revisit.

**3.0.6 OSDU stance.** No implementation. A short mapping memo (canonical entities to OSDU well-known schemas) is written in P6 as a literacy exercise; the lean bespoke model is the build.

### 3.1 What changed and why (cumulative)

| Change | Version | Why |
|---|---|---|
| Economics, scenarios, benchmark, activity, agent | v0.2 | Dollars, generative loop, control group, leading indicators, completeness test |
| Multi-basin, allocation v0, quality scorecard, ledger, transfer | v0.3 | Permian; allocation as highest-learning build; quality measured; compounding track record |
| Glass box: lineage, explain, audit, recipes, drawer, field notes | v0.4 | Transparency as trust mechanism and product thesis |
| Canonical model thesis, conformance registry, R8 | v0.5 | The unified model is the product; conformance decisions become served data |
| Competitor harvest: three-stream, analogs, type-curve UI, tornado, league table, alerts, portfolios, inventory | v0.5 | Low-effort, high-value features buildable on existing machinery |

Unchanged: raw zone, Parquet plus DuckDB, PostGIS, martin, MapLibre plus deck.gl, one VM.

### 3.2 Component inventory

C1 through C21 stand as v0.4 with these deltas:

- C3 Parsers write staging only; a new conformance step (C4 extended) promotes staging to canonical, emitting conformance references into derivations.
- C7 Modeling engine gains gas and water targets, analog KNN index over feature vectors, and batch scenario execution (inventory).
- C10 Economics gains sensitivity runs (deck, opex, capex deltas to tornado output) at trivial cost via R3 purity; assumptions gain water handling cost and per-state severance defaults.
- C13/C14 gain the type-curve builder (filter selection to curve with band and well count), league table view, GOR and water-cut chart on the well card, and inventory layer (remaining slots per section).
- C15 agent tools gain analogs, tornado, inventory, and conformance lookup.
- New C22 Inventory engine: spacing-gap detection per section/spacing unit, slot generation at assumed spacing, batch scenario forecasts, rollup with NPV. Thin orchestration over C11.
- New C23 Alerting: saved AOIs (polygons), weekly diff on permits and new wells, digest output. systemd timer plus one table.

Rules R1 through R7 stand. New:

- **R8 (conformance as data):** every cross-source mapping decision is a `conformance_rules` row served at /conformance; derivations reference the rules applied. A mapping that exists only in code fails review.

### 3.3 Data model (deltas from v0.4)

- `conformance_rules` (rule_id, source, field, rule, rationale, effective_from) and `formation_aliases`, `crs_registry` per 3.0.3.
- `production_monthly` gains stream normalization notes via conformance refs; oil, gas, water all first-class targets.
- `econ_assumptions` adds opex_water_per_bbl, severance defaults keyed by state.
- `analog_index` (api10, feature_version, vector ref) or an in-process index rebuilt from well_features; persisted only if rebuild exceeds 60 s.
- `inventory_runs` (run_id, area, spacing_assumption_ft, model_id, deck_id, created) and `inventory_slots` (run_id, slot geometry, forecast_id, valuation_id, flags).
- `aois` (aoi_id, name, geom) and `alert_digests` (aoi_id, period, payload jsonb).
- `well_sets` (set_id, name, api10s[]) for portfolio rollups.

### 3.4 API surface (deltas)

- `GET /conformance` and `GET /conformance/{rule_id}`.
- `GET /wells/{api10}/analogs?n=10` (feature-space; distinct from spatial /neighbors).
- `GET /typecurves` promoted to a first-class UI-backed builder (existing endpoint, richer params: any filter set, band, n, normalization choice).
- `POST /sensitivities` (forecast_id or valuation_id, parameter deltas) returning tornado rows.
- `POST /inventory/runs` (area, spacing, model, deck); `GET /inventory/runs/{id}` with slots, rollup.
- `GET /operators/league?basin=&vintage=&metric=cum12_per_kft`.
- `POST /aois`, `GET /aois/{id}/digest`.
- `POST /wellsets`, `GET /wellsets/{id}/rollup?deck=`.
- All new endpoints obey R6/R7: derivations, recipes, explain coverage.

### 3.5 Deployment

Unchanged. Inventory batch runs are the only new load and run seconds at township scale.

---

## 4. Protocols (pinned; normative)

4A, 4B, 4C stand as v0.4 with:

- 4A.11: gas and water are secondary targets under identical split, censoring, and control rules; GOR and water-cut trends are derived surfaces, never targets. Oil remains the headline; three-stream results reported together.
- 4A.12: analog quality check: for a sample of wells, the top-10 analogs' actual cum12 IQR must bracket the subject's actual at stated rates; reported like calibration.
- 4D (new, inventory): slots are generated only in sections where existing-lateral geometry admits a full lateral at the assumed spacing; every slot forecast carries training_support; inventory rollups always state spacing assumption and support distribution; no inventory number ships without both.

---

## 5. Key features and outcomes

E1 through E16 stand as v0.4 with these amendments and additions:

| Epic | Amendment / addition | Acceptance delta |
|---|---|---|
| E3 Forecasting | Three-stream targets; analog KNN | 4A.11 results per basin; analogs pass 4A.12 |
| E5 Economics | Tornado sensitivities; water opex; state tax defaults | Tornado on one well and one well-set, hand-checked directionally |
| E6 Scenario loop | Analog panel on the scenario card (10 nearest real wells with actuals) alongside support score | Card shows analogs; support and analogs agree or divergence is displayed |
| E7 Map UI | Type-curve builder view; league table; GOR and water-cut on well card | Builder produces a curve with band and n from any filter set via /typecurves only |
| E8 Activity | AOI alerts | One AOI digest generated and correct against manual diff |
| E11 Quality | Conformance registry (R8); wellbore quarantine share reported | S11; /conformance live; scorecard shows quarantine share |
| E12 Permian | NAD27 transforms recorded as derivations; conformance rules seeded from 3.0.3 | A TX well's spacing value explains through its datum transform |
| E17 (new) Inventory v0 | Spacing-gap slots, batch scenarios, NPV rollup, map layer | S12; 4D honored; one township demo recorded |

E16 capability matrix gains rows for the harvested features with their incumbent attribution (type-curve builder: ComboCurve; analogs: category-wide; inventory: Novi Intelligence flagship; alerts: Enverus; sensitivities: ComboCurve; league tables: Insight Engine dashboards), each marked reproduced with evidence links.

---

## 6. User stories

U1 through U15 stand. Additions:

- **U16 (OFS BD).** I save an AOI and receive a weekly digest of new permits and first-production wells inside it. AC: /aois plus digest endpoint; reproducible via curl.
- **U17 (RE).** For any well or scenario, I see its ten nearest analogs by feature distance with their actual outcomes. AC: /analogs; scenario card panel; 4A.12 check green.
- **U18 (analyst).** For any valuation, I get a tornado: NPV sensitivity to price, opex, capex, and cum12 error. AC: /sensitivities; renders on well card and well-set rollup.
- **U19 (analyst).** I pick a township and a spacing assumption and get remaining locations with forecasts and NPV at a deck, with support distribution stated. AC: inventory run end to end; 4D honored; map layer shows slots.
- **U20 (analyst).** I save a named well set and get rollups (production, forecast, valuation, tornado) for it. AC: /wellsets rollup at a chosen deck.
- **U21 (auditor).** I ask why two states' "oil" differs and get the conformance rules governing liquids, with rationale, from the API. AC: /conformance query; a production number's /explain cites the applied rules.

Anti-stories: prior list stands; additionally no slot generation outside 4D constraints, no inventory numbers without spacing assumption and support stated.

---

## 7. Build phases

| Phase | Contents | Exit criteria |
|---|---|---|
| P0 Scaffold | As v0.4 plus conformance_rules and crs_registry schema; staging/canonical split in repo layout | Audit stream live; first conformance rows (datum, CRS, liquids policy) committed |
| P1 ND spine and map | As v0.4; parsers write staging; promotion step emits conformance refs | Every production row explains to manifest and cites rules |
| P2 Forecasts and benchmark | As v0.4 plus three-stream targets and analog index | 4A.11, 4A.12 green for ND |
| P3 Dollars and scenarios | As v0.4 plus tornado and analog panel; type-curve builder UI | U17, U18 pass; builder live |
| P4 Intelligence and agents | As v0.4 plus league table and AOI alerts; ledger starts writing | U16 passes; question suite passes |
| P5 Hardening | As v0.4; /conformance in the naked-number CI scope | S1-S5, S9, S11 green |
| P6 Permian | As v0.4; datum transforms as derivations; OSDU mapping memo | S6, S8; U13 and U21 pass on TX data |
| P7 Living systems | E13 graded cycle; E17 inventory; E14 stretch; E16 matrix | S7, S10, S12; publish decision vs IP status |

Timebox: P1-P5 roughly ten to eleven focused weekends (harvest adds one to two); P6 three to four; P7 two plus waiting. Cut order under compression: E14, then E17 (inventory), then alerts and league table, then E8, then E7 polish, then field-notes UI. Never cut E4, E5, E11, E12 validators, derivation capture, or the conformance registry; the registry is cheap and load-bearing for S11.

*Phase-model note. The consolidated [v0.6 draft](blueprint-v0.6-draft.md) rewrites this table into nine phases (P0-P8), carving serving and map out of the ND spine above (P1) into a phase of its own ahead of forecasting, and re-estimating the timebox. That draft is in review and its own change control makes the review of its re-derived items the gate at which it becomes final; until that gate closes, the eight phases above are the committed numbering and derived documents tracking the nine-phase set say so where they use it. Adopting the nine-phase model here is a version promotion, not an editorial fix, and is the owner's call.*

---

## 8. Decisions, risks, open questions

### 8.1 Resolved decisions

Items 1 through 6 stand (CQR; both normalizations by role; quality measured; curated MCP tools; tile entitlement pattern; manifest-level lineage). New:

7. **Name:** glasswell, for the reasons in 1.3. basinforge retained as alias.
8. **Layering:** strict staging / canonical / marts; staging never serves, marts never ingest.
9. **Wellbore policy:** one producing wellbore per API-10 assumed; violations quarantined and measured (3.0.5).
10. **Liquids policy:** oil plus condensate as modeling liquid; regulator classification preserved in staging; policy stated wherever the number appears.
11. **Inventory guardrail:** no slot without geometric admissibility and support score (4D). Inventory is the feature most prone to confident nonsense; the guardrail is not optional.

### 8.2 Risks

v0.4 table stands (IP carve-out remains the top item and remains time-sensitive). Additions:

| Risk | Impact | Mitigation |
|---|---|---|
| Conformance registry rot | Rules drift from code; registry becomes decoration | Promotion step reads rules from the table at run time where feasible; CI check that every canonical field maps to at least one rule |
| Datum mishandling | Silent 100 m position errors corrupt spacing and inventory | 3.0.3 rules; a fixed test set of known TX wells with published NAD83 positions asserted in CI |
| Harvest scope creep | Seven small features quietly become seven medium ones | Each harvested feature is capped at its stated acceptance; anything more is a new doc version |
| Inventory misuse | Slot counts read as reserves | 4D statements mandatory in every rollup and export |

### 8.3 Open questions

Items 1 through 7 stand. New:

8. Analog distance metric: plain Euclidean on standardized features, or learned (model leaf co-occurrence)? Start Euclidean; compare once E3 is stable.
9. Inventory spacing assumption: single user input, or per-operator inferred from recent development? Start user input; inferred spacing is a P7 experiment.
10. League table normalization: cum12 per 1,000 ft alone, or a residual-based metric (actual minus model expectation) that adjusts for rock quality? The residual version is more honest and more interesting; decide after E3.

---

## 9. Glossary

v0.4 set stands, plus: Conformance rule: a recorded cross-source mapping decision with rationale. Staging / canonical / marts: source-faithful, conformed, and serving layers. Datum: geodetic reference frame (NAD27, NAD83, WGS84); mismatches shift positions. GOR: gas-oil ratio. Water cut: water share of gross liquids. Analog: a well near another in feature space. Slot: a geometrically admissible undrilled lateral position at an assumed spacing. Tornado: single-parameter sensitivity chart around a base case. AOI: area of interest. League table: ranked operator benchmark on a normalized metric.

---

*Change control: edits to Section 4 (protocols), Section 2.5 (philosophy), Section 3.0 (canonical thesis), or rules R1-R8 require a written rationale in the commit. Everything else is fair game.*
