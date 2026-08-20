# SB-02 — Modeling & Benchmark

**Sub-blueprint. Status: execution-grade draft for review. Owner: Ryan MacDonald.**
**Authored:** 2026-08-20.

Scope: everything between a conformed canonical row and a served forecast number —
features, targets, splits, the quantile model, conformal calibration, the type-curve
control, analogs, the benchmark harness, the forecast ledger, the basin-transfer test, and
the model-registry usage that binds them. Epics **E3** and **E4**, protocol **4A**,
criteria **S4** and **S7**, and the ledger half of **E13**.

**This document is written to be attacked.** DIR-1 sets the bar: every methodological
choice has to survive a hostile data-science reviewer, so every choice below carries its
defence inline, and the choices that *give something up* say what they give up. Where v0.6
is silent, a decision is made and pinned. Where v0.6 is wrong or self-contradicting, it is
recorded in §16 (errata) — **there is no silent divergence anywhere in this document.**

**Citation convention.** `v0.6 §X` = `blueprint-v0.6-draft.md` section X (section refs, not
line refs: v0.6-draft is still churning and line numbers rot) · `SB-07 §X` =
`blueprints/SB-07-lineage-spine.md` · `SB-06 §X` = `blueprints/SB-06-infrastructure.md` ·
`ad:N` = `work-output/assessment-datasources.md` line N · `ab:N` =
`work-output/assessment-blueprint.md` line N · `DIR-n` = `work-output/direction-log.md`.

**Consumption discipline.** SB-07 is a **contract**, not a menu. `derive()`,
`register_model()`, `promote_model()`, `resolve_model()`, `as_of()`, the recipe format, the
determinism classes and the naked-number CI walker are consumed as specified. Where SB-02
needs something SB-07's schema does not hold (§16 ER-07), the resolution is expressed
*within* SB-07's existing tables, and the schema gap is handed to SB-00 rather than
patched locally.

---

## 0. Scope, obligations, and pinned constants

### 0.1 What SB-02 owns

| Owns | Does not own |
|---|---|
| Feature specification, the feature registry, `feature_version` semantics, the leakage frontier | Canonical column design, conformance rule rows, promotion (SB-01) |
| Target definitions for all three streams; censoring policy | Bitemporal mechanics, `as_of()` implementation (SB-07 §3) |
| Split construction: temporal boundary, pad grouping, calibration window, rolling origins | Derivation capture, recipes, determinism classes (SB-07 §1, §4) |
| LightGBM quantile training, hyperparameter protocol, monotone constraints | Model registry schema and identity (SB-07 §7) |
| Conformal calibration: variant, groups, fallback, tolerances | The `lineage.models` table itself (SB-07 §7) |
| Type-curve engine (control-group *and* product builder) | Type-curve builder **UI** (SB-05); `/typecurves` transport (SB-04) |
| Analog index, standardization, distance metric, `training_support` | Analog **panel** rendering (SB-05) |
| Benchmark harness, metrics, slicing, artifact schema, honest-loser reporting | Scorecard rendering and scheduling (E11 / SB-04) |
| Forecast ledger write path, grading job, grade metrics | Grade *identity* and the two vintage columns (SB-07 §3.5) |
| Transfer-test design and its pre-registered thresholds | Whether E14 survives the cut order (v0.6 §7.4, owner) |
| Promotion gate, shadow mode, rollback policy | Job scheduling, concurrency slices (SB-06; v0.6 §3.7.3) |
| Every test in §11 | The naked-number CI walker itself (SB-07 §10) |
| Economics **inputs** (a forecast object with quantiles and a model ref) | DCF, decks, assumptions, tornado (SB-03; v0.6 §4B) |

### 0.2 Requirements satisfied

| Requirement | Source | Satisfied in |
|---|---|---|
| S4 benchmark artifact per basin, sliced, TC vs ML on an identical temporal holdout | v0.6 §2.4 | §7 |
| S7 ledger live with one graded cycle, graded as-of the forecast's own vintage | v0.6 §2.4 | §8 |
| 4A.1 unit of analysis is the well | v0.6 §4A.1 | §2.1 |
| 4A.2 cum12/cum24 by stream, both normalizations | v0.6 §4A.2 | §2.2, §2.3 |
| 4A.3 temporal holdout only; random splits prohibited | v0.6 §4A.3 | §3.3 (+ §16 ER-03) |
| 4A.4 censoring, not imputation; censored share reported | v0.6 §4A.4 | §2.6 (+ §16 ER-09) |
| 4A.5 type-curve control mandatory on the identical split | v0.6 §4A.5 | §5, §7.1 |
| 4A.6 / R4 feature availability declared and enforced in code | v0.6 §4A.6, §3.3 R4 | §1.2, §1.6, §11.4 |
| 4A.7 quantile objective + split conformal on a disjoint calibration set; 80% central | v0.6 §4A.7 | §4 |
| 4A.8 empirical coverage tables by slice, published with every model | v0.6 §4A.8 | §4.6, §7.3 |
| 4A.9 slicing; Arps extrapolation labelled and visually broken | v0.6 §4A.9 | §7.3, §2.4 |
| 4A.10 `training_support` with declared k, metric and scale | v0.6 §4A.10 | §6.5 (+ §16 ER-06) |
| 4A.11 three streams under identical rules; GOR/water-cut derived, never targets | v0.6 §4A.11 | §2.5 (+ §16 ER-08) |
| 4A.12 analog IQR-bracket quality check, reported like calibration | v0.6 §4A.12 | §6.4 (+ §16 ER-05) |
| 4A.13 no number from an unregistered artifact | v0.6 §4A.13, §8.1 D-22 | §10 |
| 4A.14 as-of-vintage grading, both bases reported | v0.6 §4A.14 | §8.3 |
| D-1 conformalized quantile regression, not a heuristic band | v0.6 §8.1 D-1 | §4.3 |
| D-2 both normalizations, selected by role | v0.6 §8.1 D-2 | §2.3, §5.3 |
| D-17 residual league metric on a rock-and-location-only expectation model | v0.6 §8.1 D-17, DIR-5 | §3.7 |
| D-23 analog index always persisted | v0.6 §8.1 D-23 | §6.1 |
| D-24 determinism is classed; models are D2 | v0.6 §8.1 D-24, SB-07 §4.2 | §4.7 |
| DIR-2 train on data as-known-at-cutoff; grade as-of vintage | DIR-2 | §3.2, §8.3 |
| DIR-4 Python stack: Polars, DuckDB, LightGBM, pytest | DIR-4 | §0.4 |
| DIR-10 TDD; tests with or before implementation | DIR-10 | §11 |
| A-01 model registry closes | `ab:551` | §10 |
| A-02 feature-store lifecycle closes | `ab:558` | §1.6, §1.7 |
| A-07 ledger grading automation closes | `ab:601` | §8 |
| A-15 analog index has stable identity | `ab:658` | §6.1 |

### 0.3 What SB-02 must emit to the spine

Restating SB-07 §12's SB-02 row as an acceptance list, because it is the integration
contract and it is testable:

- Model registry rows carrying `training_data_vintage`, `holdout_def`, `seeds`,
  `probe_set_ref`, `probe_tolerance`, `calibration_report_ref`, `feature_version`,
  `feature_set_hash`.
- `model.train`, `model.calibrate`, `forecast.batch`, `forecast.scenario`, `analog.index`
  and `ledger.grade` derivations, each with an `output_sha256`.
- `ledger.grade` rows carrying **both** `trained_on_vintage` and `graded_against_vintage`.
- Every input edge on a training derivation carrying `as_of_vintage` — this is not
  bookkeeping, it is the mechanism by which the leakage guard in §11.4 is checked *through
  the lineage record* rather than in process memory.

### 0.4 Stack

Python 3.12 per DIR-4 and the existing `pyproject.toml`. Additions this SB requires, all
pinned by the uv lockfile whose hash lands in every recipe (v0.6 §3.1):

| Package | Use | Determinism note |
|---|---|---|
| `lightgbm` | quantile objective, the only learner | D2; §4.7 pins the params |
| `numpy` | scores, order statistics, standardization | D1 given a fixed dtype and reduction order |
| `scipy` | Clopper–Pearson coverage intervals, Wasserstein-1 for §9 | pure functions, D1 |
| `scikit-learn` | `NearestNeighbors(algorithm="brute")` only | exact, no tree-build nondeterminism (§6.2) |
| `polars` | feature assembly, joins, aggregation | already a dependency |
| `duckdb` | canonical/mart reads behind `as_of()` | already a dependency |
| `hypothesis` (dev) | property tests on the conformal machinery (§11.3) | dev-only |

**Rejected:** any hosted ML platform, MLflow/W&B (the registry is SB-07's and the audit
stream is the experiment log), Optuna (§3.6 pins a fixed grid), XGBoost/CatBoost (a second
learner doubles the determinism surface for a benchmark that is not about learner choice),
statsmodels, PyTorch. Each rejection is recorded so a future reader does not read it as
oversight.

### 0.5 Every constant pinned in this document

An implementer must not invent any of these, and a reviewer must be able to find all of
them in one place. Each is defended at its section.

| Symbol | Value | Where | Why this value |
|---|---|---|---|
| `ALPHA` | 0.20 (80% central) | §4.3 | v0.6 §4A.7 |
| `ALPHA_LO`, `ALPHA_HI` | 0.10 each | §4.3 | asymmetric CQR, per-tail |
| `CAL_MIN_N` | 100 per Mondrian group per tail | §4.4 | finite-sample slack ≤ ~1% |
| `CAL_WINDOW_MONTHS` | 12 (well-time) | §3.3 | nearest-to-test cohort |
| `EMBARGO_MONTHS` | 0 | §3.3 | grouping does the work, not an embargo |
| `PAD_RADIUS_M` | 150 | §3.4 | surface-hole cluster |
| `PAD_WINDOW_DAYS` | 180 | §3.4 | co-completion window |
| `COVERAGE_PASS_BAND` | [0.72, 0.88] pooled | §4.6, §10.2 | promotion gate |
| `COVERAGE_SLICE_BAND` | [0.65, 0.92] per slice with n ≥ 200 | §4.6 | promotion gate |
| `CROSSING_RATE_MAX` | 0.02 pre-rearrangement | §4.2 | mis-specification flag |
| `ROLLING_ORIGINS` | 4, annual spacing | §3.5 | a single cutoff is one draw |
| `KNN_K` | 25 (`training_support`), 10 (served analogs) | §6.5, §6.4 | declared per 4A.10 |
| `IQR_BRACKET_TARGET` | 0.50, tolerance ±0.10 | §6.4 | an IQR brackets half by definition |
| `TC_MIN_N` | 20 peer wells | §5.4 | below this the curve is noise |
| `TC_FALLBACK_LADDER` | 3 levels | §5.4 | recorded per subject, never silent |
| `OFFSET_RADII_FT` | 500, 1000, 2000 | §1.3 D | OQ-4 ablation grid |
| `DECAY_LAMBDA_FT` | 1000 | §1.3 D | OQ-4 ablation parameter |
| `MONOTONE_LATERAL` | +1 | §4.1 | physical, and it protects U14 |
| `SLICE_MIN_N` | 50 (report), 200 (gate) | §7.3 | below: "insufficient n", never dropped |
| `BOOTSTRAP_B` | 2000 paired resamples | §7.2 | CIs, not p-values |
| `LEDGER_CYCLE_MIN_N` | 100 ND oil cum12 entries | §8.5 | makes S7 testable |
| `SEED` | 20260820 (global, per-run overridable in the recipe) | §4.7 | recorded, never defaulted in code |

---

## 1. Feature engineering

### 1.1 The prediction regime — decided before anything else

A forecast model is defined by *when it stands*. v0.6 §4A.6 describes a model "predicting
from a completion date", and every consumer that matters — the scenario loop (v0.6 §5 E6),
inventory slots (E17), the league expectation model (D-17) — is asking about a well that
does not yet produce. So:

**Decision: v0 trains exactly one regime — the pre-production regime. The anchor is the
completion date. No subject-well production is available to the model at any point.**

Two consequences, both deliberate:

1. **A producing well's served "model forecast" is the forecast made at its own anchor**,
   not a refreshed forecast conditioned on its history. The well card (v0.6 §6 U1) shows
   three labelled series: actuals, the anchor-time model forecast with its band, and an
   Arps DCA fit on the actuals (v0.6 §4A.9) for the remaining life. Each carries its own
   method label. This is more honest than a single blended curve and it is strictly more
   informative — "what we said" against "what happened" is the ledger's whole content.
2. **The history-conditioned regime is deferred, named, and not smuggled in.** A model that
   sees six months of a well's production and predicts its cum12 is a *different estimand*
   with a much easier task, and mixing the two would make the S4 benchmark
   uninterpretable — the type-curve control has no history-conditioned analogue, so the
   comparison would be against a handicapped control. Deferred to §15 as a named later
   experiment, not cut silently.

**Defence against the obvious objection** — "you are throwing away information for producing
wells" — is that the PDP path (v0.6 §2.2, minerals buyer) is served by DCA on actuals,
which is the industry's own answer and needs no ML, and that the ML product's value is
precisely in the pre-production regime where DCA has nothing to fit. Stating which
question each method answers is the point of the exercise (v0.6 §1.2 Q2).

### 1.2 The leakage frontier — two clocks, both enforced

R4 (v0.6 §3.3) says a model may only see information that existed at the as-of date of the
prediction. That single sentence hides two independent constraints, and conflating them is
how leakage survives review. SB-02 separates them explicitly:

| Constraint | Clock | Statement | Enforcement |
|---|---|---|---|
| **C1 — well time** | the subject well's own timeline | Every feature's `knowable_at` ≤ the well's anchor date. No event that happened after the anchor may influence any feature value. | Feature registry declares `knowable_at_rule` per feature; the builder stamps `knowable_at` per (well, feature) and raises `FeatureLeakageError` on violation (§11.4) |
| **C2 — knowledge time** | glasswell's own timeline (DIR-2) | Every canonical row read while building a training set was read at `report_vintage ≤ C`, the training cutoff. No restatement published after C may enter. | `as_of(C)` (SB-07 §3.3) is the only read path; the resulting derivation input edges carry `as_of_vintage ≤ C`, and CI asserts it from the lineage record (§11.4) |

Neither implies the other. C1 without C2 lets a 2026 restatement of a 2021 production month
into a model whose cutoff is 2022 — the value was "knowable" in well time but was not
*known*. C2 without C1 lets a well's own month-9 volume into the features for its cum12
because both were published before the cutoff. **Both are required, and the tests in §11.4
test them separately.**

**The `knowable_at` loophole, closed.** `knowable_at` is attacker-shaped: an implementer
under deadline can declare any feature "knowable at completion" and the constraint
evaporates. Two guards:

- `knowable_at_rule` is an enum, not free text: `permit_date | spud_date | completion_date |
  first_production_month | anchor`. Every value is a dated regulator event already in
  canonical. There is no `"analyst judgement"` option.
- **The mutation-invariance test (§11.4) is the real enforcement.** For every feature in the
  registry, inject synthetic production rows dated after the anchor and assert the feature
  value is byte-identical. A feature that moves has leaked, regardless of what its
  registry row claims. This is a class-level test parameterized over the whole registry, so
  a newly added feature is in scope automatically.

**Publication lag is recorded, not enforced.** A lateral polyline exists physically at
completion but appears in ND DMR GIS days-to-weeks later. C1 governs *events*, so the
lateral length is admissible; the deployment gap is real and is recorded as
`publication_lag_days_p50` on the feature registry row and reported per feature on the
scorecard. Suppressing the feature would be wrong (it is genuinely design intent, and a
scenario supplies it directly); pretending the lag does not exist would be worse. Measure
it, publish it, and let the ledger — which grades forecasts actually published at their
anchor — be the arbiter of whether the gap costs anything.

### 1.3 Feature families

Every feature is a row in the feature registry (§1.5). Families below name the design
space; the registry is the source of truth for what a given `feature_version` contains.

**A — Completion design.** Available at `completion_date`.

| Feature | Source | Note |
|---|---|---|
| `lateral_length_ft` | `OGD_Horizontals_Line` geometry, projected CRS (ND); RRC well arcs (TX) — `ad:78`, `ad:235` | **Never from FracFocus** — no such field exists (`ad:343`, DIR-9) |
| `proppant_lb`, `proppant_lb_per_ft` | FracFocus header; TX completion feed "Amount and Kind of Material Used", `AMT_MATERIAL_PROCESS_CODE=2` (`ad:208`) | per-ft is the industry's variable (v0.6 §9 "proppant intensity") |
| `fluid_bbl`, `fluid_bbl_per_ft` | FracFocus `TotalBaseWaterVolume` | **flagged unreliable** (`ad:344`) — admitted only behind a `validity_filter` rule, else missing-indicator |
| `stage_count`, `stage_spacing_ft`, `proppant_lb_per_stage` | TX completion feed; FracFocus where present | `stage_spacing_ft = lateral_length_ft / stage_count` |
| `landing_zone_formation_id` | `formation_aliases` (v0.6 §3.0.3) | categorical; unmatched → quarantine `alias_unresolved` (SB-07 §8.2) |
| `lateral_azimuth_deg`, `lateral_sinuosity` | lateral geometry, projected CRS | azimuth as sin/cos pair, not degrees — a tree splitting raw azimuth cuts the compass at 0° |
| `design_source` | which source supplied design fields | categorical; makes source-driven missingness visible to the model instead of hidden |

**B — Location and land.** Available at `permit_date`.

`x_m`, `y_m` (lateral midpoint in the basin compute CRS — v0.6 §3.0.3), `county_code`,
`land_unit_id` (PLSS section) and its parent township, `basin`, `spacing_unit_id`,
`spacing_unit_area_acres`.

Raw projected coordinates as tree features are standard and defensible: they let the model
carve the basin into empirical rock provinces without an interpreted map, which is exactly
what a garage build on public data can honestly do. The known hazard is that coordinates
plus enough depth let a tree memorize individual pads — which is precisely why the pad-group
split constraint (§3.4) is not optional. **The two decisions are load-bearing together and
neither is safe alone.**

**C — Geology proxies.** Available at `spud_date` (surveys) / `completion_date` (tops).

| Feature | Availability reality |
|---|---|
| `landing_tvd_ft` | ND: `NDOGD_Surveys` — **station-level, confirmed** (see below). TX: free Formation Data segment (`ad:209`) |
| `depth_below_formation_top_ft` | Requires tops. **ND bulk tops are Premium-only, $500/yr** (`ad:119`, v0.6 §8.1 D-21). Not on the critical path |
| `formation_thickness_ft` | Two tops. Same constraint |
| `structural_residual_ft` | `landing_tvd_ft` minus an IDW-smoothed regional TVD surface fitted on **other wells' geometry** (not outcomes), leave-one-well-out, as-of anchor. Safe: TVD is geometry, not performance |

**ND ships station-level directional surveys — measured, not assumed.** The archive had never
been opened, which is why v0.6 made it a P3 gate. It is now open: probed 2026-08-20 by ranged
reads over the remote geodatabase (201 KB pulled against a 321,052,648-byte archive, no
download — `scripts/experiments/e9-survey-probe.py`, re-runnable), `NDOGD_Surveys.gdb.zip`
carries two point feature classes with identical field lists — **5,470,017 survey stations**
and **52,579 surveyed wellbores** — and both carry `measdpth`, `inclination`, `azimuth` and
**`tvd`** as float64, alongside `wl_permit`, `api_wellno`, `api_format`, `well_sub`, `long`,
`lat`, `coordns`/`coordew` and `surveytype`.

Consequences, pinned:

- `landing_tvd_ft` and `structural_residual_ft` are **in scope for ND at P3**, keyed on
  `api_wellno[:10]` = API-10 with `well_sub` discriminating wellbores — the same
  multi-wellbore distinction v0.6 §3.0.5 already quarantines on.
- `tvd` is carried directly, so landing TVD is a **selection over observations**, not a
  reconstruction: `landing_tvd_ft` = `tvd` at the **first station with `inclination` ≥ 88°**,
  `granularity = observed`, citing the selection rule. Minimum-curvature reconstruction from
  `measdpth`/`inclination`/`azimuth` is retained as a **validator**; disagreement beyond 25 ft
  quarantines as `crosswalk_disagreement`. Computing what the regulator already publishes
  would be an estimate posing as an observation (DIR-3).
- `structural_residual_ft` — landing TVD minus a fitted structural surface — stays
  `granularity = modelled`, `method = structural_fit`, and is never served without its band.
- Canonical stores the **per-wellbore reduction**, one row per `(api10, well_sub)`, not
  5.47 M stations. The stations live in the raw zone under R1 and are re-derivable; the
  feature is one number per well and a 771 MB table has no place in the serving path.
- **Two riders.** (i) **Units are UNVERIFIED** — the layer declares none, so E-9's units check
  ships as a `conformance_rules` row with evidence: median `landing_tvd_ft` over Bakken
  horizontals must fall in [8,000, 12,000] ft, and a median in [2,400, 3,700] means metres and
  **rejects the parse rather than converting it silently**. (ii) The layer is **NAD83
  geographic** — `GEOGCS["GCS_North_American_1983", DATUM["D_North_American_1983", …]]`, read
  out of the same probe — while storage is EPSG:4326; the datum answer is recorded as a
  `parse_directive` rule, not inherited by convention. Depth features are unaffected by it.
- Identity and monotonicity are conformance rules too: `api_wellno[:10]` must join
  `canonical.wells` for ≥ 99% of surveyed wellbores (the rest quarantine as `orphan_fk`), and
  `measdpth` must be non-decreasing within `(api10, well_sub)` (violations quarantine as
  `unreliable_numeric`).

**The honest position on geology (OQ-2):** ND v0 ships the **design-plus-location** tier
plus survey-derived `landing_tvd_ft` and `structural_residual_ft`. Tops-based features are
built and tested on **TX** (free) and are an **ablation study** in ND that quantifies what
the $500 Premium tier would buy. That ablation *is* the answer to OQ-2 and to v0.6 §1.2 Q1
("what exactly does proprietary data buy") — it is a deliverable, not a gap.

**D — Spacing and parent-child, from lateral geometry (OQ-4).** All computed in the basin's
projected CRS (v0.6 §3.0.3); all restricted to offsets **completed strictly before the
anchor**; all three encodings built and ablated, because OQ-4 explicitly asks for the
ablation and this is likely the highest-value family in the Bakken.

1. **Count encoding.** `offset_count_{500,1000,2000}ft`, split into `same_zone` and
   `other_zone` (planar vs stacked spacing are different physics and a single count
   conflates them).
2. **Distance encoding.** `nearest_offset_dist_ft`, `mean_offset_dist_ft`,
   `nearest_same_zone_dist_ft` — lateral-to-lateral minimum distance between the two
   polylines, not surface-hole distance. Surface-hole distance is nearly meaningless for
   horizontals sharing a pad and pointing opposite directions.
3. **Depletion encoding.** `depletion_proxy = Σ_j w(d_j) · cum_oil_j(t_anchor)` over
   same-zone offsets within 2000 ft, `w(d) = exp(−d / DECAY_LAMBDA_FT)`, where
   `cum_oil_j(t_anchor)` is offset *j*'s cumulative oil **through the anchor month at
   knowledge vintage ≤ C**. This is the one outcome-derived feature family and it is the
   most dangerous thing in the set.
4. **Timing.** `months_since_nearest_offset_completion`, `co_completion_flag` (an offset
   completed within ±`PAD_WINDOW_DAYS` — co-development is not parent-child and treating
   them alike is a standard error), `is_parent | is_child | is_infill | is_standalone`
   derived from 1–3.
5. **Unit density.** `wells_in_spacing_unit_at_anchor`, `wells_per_section_at_anchor`.

**Defence of including the depletion encoding at all.** The instinct is to ban
outcome-derived features. That instinct is wrong here, and stating why is important,
because a reviewer will raise it: **the type-curve control is itself a neighbour-performance
estimator.** A peer-group type curve is, definitionally, an average of nearby analogous
wells' actual outcomes. Banning neighbour-performance features from the ML arm while the
control arm is built entirely from them would rig S4 *against* ML and produce a false
negative — the mirror image of the leakage failure everyone worries about. Both arms get
the same information at the same as-of constraint. The guard is not prohibition, it is
**C1/C2 enforcement plus the mutation-invariance test plus a published ablation** that says
how much of the lift this family carries. If it carries most of it, that is a finding about
where the signal lives, and it belongs in the notebook (v0.6 §5 E15).

**E — Operator and vintage.**

- `operator_id`, resolved through `operator_aliases` (v0.6 §3.4) — LightGBM native
  categorical with a minimum-count threshold and an `__other__` bucket for the long tail.
  **No target encoding, ever** (§1.4 exclusion 3).
- `completion_year` as a **numeric** feature, deliberately. A tree splitting numeric year
  degrades at test time to "the most recent regime the model saw", which is the correct
  inductive bias under a temporal holdout. One-hot year would present an unseen category on
  every test well. The cost — the model cannot extrapolate a continuing design trend — is
  real, is stated, and is measured by the rolling-origin evaluation (§3.5), which shows the
  degradation as a function of how far the test cohort sits from the training window.

### 1.4 Exclusion register

Every exclusion, with its reason. This table is the artifact a hostile reviewer reads
first, so it is exhaustive rather than tasteful.

| # | Excluded | Why |
|---|---|---|
| 1 | Subject well's production at or after the anchor, and anything derived from it | It is the label. Definitional. |
| 2 | Subject well's IP90 / first-month rate / early cumulative | The cheat feature. Knowable only post-anchor; including it silently changes the estimand from "what will this design produce" to "given this start, what is the total", and inflates every accuracy number in the benchmark against a control that has no such input |
| 3 | Target / mean encoding of operator, formation, land unit or any categorical | Encodes the label into a feature. Out-of-fold encoding does not save it under a temporal split with pad-group structure: the folds are not exchangeable and the encoding carries cross-boundary information |
| 4 | `first_production_month` as a feature | Post-anchor by construction, and it defines the label window — using it to predict the label is circular |
| 5 | `days_produced`, well status, current status | Post-anchor, and status is restated (DIR-2) so its value is knowledge-time-dependent |
| 6 | Any offset well's production dated after the subject's anchor month | The single most likely accidental leak. Enforced by mutation invariance (§11.4), not by care |
| 7 | Any model output — a neighbour's forecast, a prior model's prediction | Circular; makes the ledger self-referential and lets error compound invisibly across retrains |
| 8 | EUR, reserves, booked locations, or any vendor-modelled quantity | Not available on public data, and would be an extrapolation used to predict an observation |
| 9 | Formation tops read at an interpretation vintage later than the anchor | C2 violation; bound by `as_of()` like everything else |
| 10 | Allocated TX volumes as **labels** | Allocation error (v0.6 §4F.5) would enter the label and contaminate the measured model error with the allocation model's error — the two would be inseparable. **TX well-level ML targets in v0 come only from 4F.6 single-well leases** (`granularity = observed`). Allocated-label training is a separately gated experiment with the error bounds propagated, never the default |
| 11 | Confidential-well production during the confidential period | Withheld ≠ zero (v0.6 §3.0.3). Treating it as zero would teach the model that confidential wells are dry |
| 12 | FracFocus `TVD` and `TotalBaseWaterVolume` in raw form | Independently flagged unreliable (`ad:344`); admitted only after a `validity_filter` conformance rule, otherwise carried as missing with an indicator |
| 13 | Any feature from a paid tier not on the critical path | v0.6 §8.1 D-21. NDIC Premium tops are an ablation input, never a production dependency |
| 14 | Free-text remarks, well names, lease names | Operator naming conventions encode operator identity and sometimes pad identity — a memorization channel that survives the pad-group split |
| 15 | Anything with `knowable_at_rule` outside the enum | §1.2. There is no analyst-judgement availability |

### 1.5 The feature registry — features as data

R8 makes conformance decisions data (v0.6 §3.3). The same argument applies with equal force
to features: a feature set that exists only in code cannot be audited, cannot be diffed
across model versions, and cannot answer "what did this model see" from the API. So the
feature specification is a table, `features.feature_specs`, and the builder reads it:

| Column | Notes |
|---|---|
| `feature_id` | stable slug, e.g. `design.proppant_lb_per_ft` |
| `family` | `design \| location \| geology \| spacing \| operator \| vintage` |
| `dtype`, `unit` | unit is mandatory — v0.6 §3.0.3 units policy, `ab:641` |
| `knowable_at_rule` | the §1.2 enum. Drives C1 enforcement |
| `publication_lag_days_p50` | measured, not assumed; recorded per source |
| `transform_id`, `params` | a registered transform (mirrors SB-07 §6.1 `parameterized` kinds) |
| `source_refs[]` | canonical tables and conformance rules it depends on |
| `missing_policy` | `native_nan \| indicator \| quarantine` (§1.7) |
| `member_of[]` | named feature sets: `full`, `rock_location_only`, `design_adjusted`, `no_depletion` |
| `introduced_in_fv`, `retired_in_fv` | append-only lifecycle; a feature is never edited in place |

**`geology.formation_group` is a registry row like any other, and it is the one the gate
added** (G-13): `family = geology`, `dtype = categorical`, `knowable_at_rule = completion_date`,
`transform_id = lookup_formation_alias` with the reported pool as its parameter,
`source_refs = [canonical.well_completions.formation_group, cr_formation_group_rollup]`,
`missing_policy = native_nan` — a well whose pool reads `CONFIDENTIAL` is `__confidential__`,
which is information, not absence — and `member_of = [full, rock_location_only,
design_adjusted, no_depletion]`, because the peer group, the Mondrian taxonomy and the analog
space all read it and the league expectation model is *about* rock. Its value comes from the
LOOKUP table, never from a code branch, so "which formations were grouped together" is a
query against `formation_aliases` and not an archaeology exercise in the builder.

`member_of` is what makes D-17's league expectation model a **data declaration rather than a
code branch**: `rock_location_only` is a set membership, so "the expectation model excluded
operator and design" is provable from the registry and citable from `/models`, not asserted
in a docstring.

### 1.6 `feature_version` discipline

- `feature_version` is `fv<MAJOR>.<MINOR>`. **MAJOR** bumps when any existing feature's
  semantics change or a feature is removed; **MINOR** bumps on pure addition. A MAJOR bump
  invalidates cross-version model comparison and the benchmark says so.
- `feature_set_hash` = sha256 over the ordered, canonically-serialized spec rows for the
  named set. This is the machine-checkable identity; `feature_version` is the human label.
  `resolve_model()` (SB-07 §7) **refuses a feature matrix whose hash differs from the
  model's** — the mismatch is an error, not a warning, because a silently reordered or
  redefined column is the failure mode that produces plausible wrong numbers.
- Feature partitions are keyed `(feature_version, as_of_vintage)` per SB-07 §1.2, so a
  rebuild at a new vintage never overwrites the matrix a published model trained on.
- **Conformance-rule change (closes A-02, `ab:558`).** SB-07 §6.5 hands back the set of
  derivations citing a superseded rule. SB-02's response is pinned: affected feature
  partitions are rebuilt into a **new** `as_of_vintage`; **published models are not
  auto-retrained** — they remain valid at their own vintage, which is the entire point of
  4A.13 and DIR-2 — and a `feature_rebuild_backlog` metric is published on the scorecard
  so the drift between the newest feature vintage and the vintage the promoted model uses
  is *visible* rather than discovered later. Retraining onto a rebuilt vintage is a normal
  promotion cycle (§10.2), not an emergency.

### 1.7 Missingness, and why it is not imputed

LightGBM handles NaN natively by learning a default direction per split. That is used, and
**mean/median imputation is rejected**: imputation invents an observation, and v0.6 §2.5
rule 6 says estimates never pose as observations — a rule that applies inside the model as
much as at the API surface. Where missingness is informative (FracFocus coverage differs by
operator and by era — the pre-2013-06 header-only break, `ad:348`), an explicit
`_is_missing` indicator column accompanies the feature so the model can use the *fact* of
absence without a fabricated value.

Three states are kept distinct end to end, per v0.6 §3.0.3: `no_report`, `reported_zero`,
`withheld`. `reported_zero` is a real zero. `withheld` and `no_report` are NaN with
different indicators, because collapsing them would teach the model that confidentiality
predicts poor performance — a bias that would then show up in exactly the recent-vintage
population that inventory and scenarios care about (OQ-7).

### 1.8 Standardization

Trees do not need scaling, so the model matrix is unscaled. The **analog index and
`training_support` do** (§6), and there the standardization statistics are computed on the
**training split only**, stored inside the index artifact, and applied unchanged to
calibration, test and serving rows. Recomputing statistics on the full population is a
textbook leak that is invisible in every metric except the one that matters. The stored
statistics are part of the index's `output_sha256` (SB-07 §1.7).

---

## 2. Targets — three streams

### 2.1 Unit and grain

The well (API-10), per v0.6 §4A.1. Multi-wellbore API-10s are quarantined upstream
(`multi_wellbore_policy`, SB-07 §8.2) and never reach the training set. One row per
(api10, stream, horizon) in the label table.

### 2.2 Definitions — cum12, cum24, and the monthly rate curve

**Producing month, defined once** (this is undefined in v0.6 — §16 ER-09):

> A **producing month** for a well is a canonical `production_observations` month for that
> well, at the applicable vintage, with `null_semantics = reported_zero` **and**
> `days_produced > 0`, **or** with `volume > 0`. Months with `null_semantics = no_report` or
> `withheld` are **not** producing months and do not advance the horizon counter. Months
> with `days_produced = 0` and zero volume (shut-in) are **not** producing months.

Consequences, all deliberate:

- The horizon counts **producing** months, not calendar months. A well shut in for three
  months reaches cum12 three calendar months later. This is the industry convention and it
  is the only one under which two wells' cum12 are comparable.
- A `withheld` month inside the horizon makes the well **censored**, not zero (§2.6).
- `cum12(w, stream) = Σ` volume over the first 12 producing months from
  `first_production_month`. `cum24` likewise. Both in the stream's canonical unit (bbl for
  oil and water, mcf for gas), DECIMAL throughout per SB-07 §4.4.

**Monthly rate curve — the coherence decision.** v0.6 §4A.2 defines only cumulative targets,
but the product needs a monthly series (well card, DCF in v0.6 §4B.1 which is
*monthly* cash flows). Three options and one choice:

| Option | Verdict |
|---|---|
| A per-month model (24 months × 3 streams × 3 quantiles) | 216 artifacts, each thin; rejected on determinism surface and training budget |
| One model with `month_index` as a feature, predicting monthly rate | Rejected: the sum of monthly P50s is **not** the P50 of the cumulative, so the served monthly series would not reconcile with the served cum12 — a naked incoherence that a reviewer finds in ten seconds |
| **Chosen: hierarchical.** ML predicts the **cumulative** quantiles; the monthly shape comes from a peer-group normalized decline shape vector (unit-sum over the horizon, from the type-curve engine §5), scaled to the predicted cumulative | Coherent by construction: the monthly series sums exactly to the cum forecast at every quantile |

**What the hierarchical choice gives up, stated plainly:** the shape is peer-group-specific,
not well-specific, so early-time accuracy (IP90-like questions) is worse than a dedicated
early-rate model would give. That cost is **measured** — the benchmark reports month-1 to
month-3 error alongside the cumulative metrics (§7.2) — and a well-specific shape model is
a named later experiment (§15). Shipping a coherent series with a measured shape error
beats shipping an incoherent one with a better-looking headline.

Beyond the trained horizon, extrapolation is the Arps hyperbolic-with-terminal-exponential
step already pinned by v0.6 §4A.9, labelled `modelled` + extrapolated, with the visual break
the blueprint requires.

### 2.3 Normalization — trained absolute, served both (D-2)

v0.6 §8.1 D-2 keeps both normalizations and selects by role: per-1,000 ft for comparison,
absolute for dollars. v0.6 §4A.2 says targets are "reported both absolute and per 1,000 ft"
without saying which one is **trained**. That gap is load-bearing (§16 ER-01):

**Decision: the model target is absolute cumulative volume, with `lateral_length_ft` as a
feature. Per-1,000 ft is a post-hoc division of the served absolute number.**

Defence: training on a per-kft target and multiplying by lateral length imposes exact
proportionality between recovery and completed length. That assumption is empirically false
— per-foot productivity declines with length — so a per-kft-trained model would be
structurally wrong in exactly the direction that matters for the longest, newest, most
economically interesting wells, and the error would be invisible in per-kft metrics because
the metric shares the assumption. Training absolute lets the model learn the curvature; the
per-kft view remains available by division, so D-2's "both, by role" is satisfied with no
loss. This asymmetry is also why the type-curve control gets **both** normalization arms
(§5.3) — otherwise the ML advantage could be an artifact of the control's linearity
assumption rather than a real advantage, and S4 would be measuring the wrong thing.

**No log transform.** Quantile regression fits each quantile separately and therefore
handles heteroscedasticity by construction; variance-stabilizing transforms exist to rescue
*mean* regression and buy nothing here. Fitting in log space and back-transforming preserves
the quantiles (monotone equivariance) but changes the pinball loss being optimized,
re-weighting the fit toward small wells — precisely the wrong direction when the output
feeds a DCF. Raw-scale training directly optimizes the served quantity. Log-space is an
ablation, reported, not the default.

### 2.4 The three streams

Oil is the headline (v0.6 §4A.2). Gas and water are secondary targets under **identical**
split, censoring and control rules per v0.6 §4A.11 — identical is meant literally: the same
`split_id`, the same pad groups, the same calibration windows, the same type-curve control
construction, the same slices. The only per-stream differences permitted are the label
column, the unit, and the hyperparameters selected by the inner validation (§3.6).

Liquids policy: oil means oil-plus-condensate (v0.6 §8.1 D-10), and every served figure
carries `basis: "oil+condensate"` per SB-07 §9.1.

### 2.5 GOR and water cut — derived surfaces with no band

v0.6 §4A.11 says GOR and water cut are derived surfaces, never targets. It does not say what
happens to their *uncertainty*, and v0.6 §3.6.12 endpoint 6 serves them under R6. The trap:

> P50(gas) / P50(oil) is **not** P50(GOR). Ratios of independently-fitted marginal quantiles
> have no quantile interpretation, because the joint dependence between the oil and gas
> errors is never modelled.

**Decision: GOR and water cut are served as the ratio of the P50 forecasts only, labelled
`modelled` with `method = derived_ratio`, and carry no band.** Serving a band built from
P10/P90 ratios would be a fabricated interval — the exact class of defect v0.6 §2.5 rule 6
prohibits, dressed as rigour. A joint-distribution model (copula or multi-output) that
would license a real band is §15 gold-plating: no success criterion asks for a GOR band, and
the honest scalar answers the product question ("is this a gassy area").

For **historical** wells, GOR and water cut are computed from actuals and are
`granularity = observed` ratios — a different object from the forecast ratio, labelled
differently, never plotted in the same series without a break.

### 2.6 Censoring — the policy v0.6 leaves half-stated

v0.6 §4A.4 requires censored wells to be counted, not imputed and not silently dropped, and
treats withheld/confidential as a distinct class. It does not say what censored wells are
*for*. Pinned:

| Role | Censored well (fewer than H producing months at the label vintage) |
|---|---|
| As a **training label** | Excluded. There is no cum12 to fit |
| As a **feature input to other wells** | **Included.** A censored parent still depletes its neighbours, and dropping it from `depletion_proxy` would silently understate depletion for exactly the newest, most infill-heavy child wells. This is the half v0.6 omits (§16 ER-09) |
| In the **denominator of reported accuracy** | Counted. `censored_share` is published beside every accuracy figure (4A.4) and per slice |
| In the **type-curve control** | Included up to its last producing month; the control's month-*m* statistic uses only wells with ≥ *m* producing months, and `n_m` is published per month (§5.4) |

**Withheld and confidential wells (OQ-7).** Interim policy: excluded from train, calibration
and test as a distinct class; the share is reported by cohort and by basin. This is a
*stated interim*, because ND withholds production for confidential wells and the
confidential period systematically hides the newest wells — the population inventory and
scenarios care most about. The measurement that closes OQ-7 is a P3 deliverable:
`withheld_share_by_completion_cohort`, published. Until it exists, no claim is made about
whether the exclusion biases the model; after it exists, the policy is revisited with a
number. Asserting missing-at-random here would be the single most consequential unforced
error available in this section (v0.6 §8.2 R-05).

---

## 3. Training protocol

This section is written to be read adversarially. A DS reviewer looking for leakage will
look in five places: the split boundary, the calibration set, the label vintage, the group
structure, and the hyperparameter search. All five are specified below, with the failure
each specification prevents.

### 3.1 Objects and clocks

| Symbol | Meaning |
|---|---|
| `t_a(w)` | **anchor** — the well's completion date (§1.1) |
| `t_fp(w)` | first production month |
| `H` | label horizon in producing months, 12 or 24 |
| `t_L(w)` | **label completeness date** — the report vintage at which the well's *H*-th producing month was first published ≈ `t_fp + H − 1 + reporting_lag` |
| `B` | **well-time split boundary**, a first-production month |
| `C` | **knowledge cutoff**, a report vintage — the date the model is pretending to be trained on |
| `split_id` | content-addressed identity of one complete split object (§3.3) |

`reporting_lag` is per source and is not a guess: ND MPR publishes ~1 month + 15 days after
the reporting month (`ad:43`, v0.6 §3.7.4); NM refreshes nightly with `mod_dte`; TX PDQ is
monthly with a 6–8 month restatement window (`ad:472`). The lag used per basin is recorded
in `holdout_def` on the model row, not hardcoded.

### 3.2 Vintage-aware training data (DIR-2)

**The training set at cutoff `C` is exactly what glasswell knew on `C`.** Every canonical
read goes through `as_of(C)` (SB-07 §3.3), which selects the greatest `report_vintage ≤ C`
per (well, month, stream, source). Nothing else is permitted to read canonical during
training — there is no second path, and CI checks the derivation input edges rather than
trusting the code (§11.4).

Three consequences a reviewer will probe:

1. **Labels are the as-known-at-`C` labels, restatements after `C` excluded.** A well whose
   2024 volumes were restated in 2026 trains on the 2024-vintage values if `C` is 2024. This
   is correct and it is the point: a model trained on future restatements would show an
   accuracy the deployed system could never have achieved, and the ledger's "trained on
   vintage" (SB-07 §7) would be a fiction.
2. **The training population is `{w : t_L(w) ≤ C}`.** A well whose horizon had not finished
   reporting by `C` is not in the training set at `C`, no matter how good its data looks
   today.
3. **This selection is not neutral, and the bias is measured.** Wells that report late —
   operational trouble, confidential status, amended filings — are under-represented at any
   given `C`. `late_report_share_by_cohort` is computed and published beside every model,
   because "we selected on reporting promptness" is a criticism that is answerable with a
   number and indefensible without one.

**The two-vintage arrangement for a retrospective benchmark.** Running a benchmark *today*
for a cutoff `C` in the past requires two distinct vintages and they must not be confused:

- **Feature/label vintage `C`** for train and calibration — everything the model sees.
- **Evaluation vintage `V_eval`** for the test cohort's labels, which necessarily exceeds
  `C` because the test wells' horizons complete after the cutoff. `V_eval` is recorded on
  the benchmark artifact, and the benchmark additionally reports the test metrics at the
  *earliest* vintage at which each test label completed, so restatement drift in the
  evaluation labels is separable from model error (the same decomposition the ledger uses,
  §8.3).

Recording both vintages is not fastidiousness — without it, "the model got worse in 2024"
and "the 2024 actuals were restated downward" are indistinguishable.

### 3.3 The split, spelled out

One split object per (basin, origin), content-addressed as `split_id`, consumed unchanged
by the ML arm, every type-curve control arm, the naive control, and the analog index.

```
Given a boundary B (a first-production month) and horizon H:

  GROUPS   g(w) = pad group of w                                (§3.4)
           every group is assigned wholly to one partition, by the group's median t_fp

  TRAIN    { w : t_fp(w)  <  B − CAL_WINDOW_MONTHS }
  CAL      { w : B − CAL_WINDOW_MONTHS ≤ t_fp(w) < B }
  TEST     { w : t_fp(w)  ≥  B }

  KNOWLEDGE  C  =  max over (TRAIN ∪ CAL) of t_L(w)
             i.e. the vintage at which the last calibration label completed.
             TRAIN and CAL features and labels are read at as_of(C).

  TEST features are built at each test well's own anchor under C1, read at
  as_of(t_a(w) + publication_lag) — i.e. as the deployed system would have had them.
  TEST labels are read at V_eval (§3.2) and never enter any fitted object.

  EMBARGO_MONTHS = 0                                             (defended below)
```

**Why the calibration set is a temporal window and not a random subset of train.**
Split-conformal's finite-sample guarantee needs calibration and test to be exchangeable.
Under a temporal holdout with real drift — design evolution, operator turnover, price
regimes — **neither** a random subset of train nor a recent window is exchangeable with
test. Given that the guarantee is going to be approximate either way, the correct move is to
choose the calibration set that is *closest in distribution to test*, which is the most
recent pre-boundary cohort, and then to **measure** the resulting coverage and report a miss
as a miss (v0.6 §4A.7 explicitly licenses this). A random subset of train would be older on
average and would predictably under-cover on test.

**This is stated as a limitation, not hidden as a feature.** The conformal coverage claim in
this system is: *distribution-free coverage under exchangeability, plus a measured empirical
coverage under the actual temporal split, published by slice with a confidence interval.*
v0.6 §3.1 and §8.1 D-1 currently claim distribution-free coverage without the qualifier;
that is the same class of overclaim SB-07 §4.6 corrected for "byte-for-byte", and it is
§16 ER-02.

**Why `EMBARGO_MONTHS = 0`.** The usual reason for an embargo is that features near the
boundary encode post-boundary information. Here they cannot: C1 fixes every feature to its
own well's anchor, so a train well's features never see anything after that well's anchor.
The real cross-boundary hazard is *shared unobserved rock plus co-completion* — pad-mates
landing on opposite sides of the boundary — and an embargo addresses that only by accident
and at the cost of discarding the most recent, most drift-relevant cohort, which is exactly
the cohort the calibration window needs. **The pad-group constraint addresses it directly.**
An embargo remains available as an ablation parameter and is reported when non-zero.

### 3.4 Pad grouping — the leak v0.6 §4A.3 does not close

A temporal holdout alone does not prevent near-duplicate wells straddling the boundary.
Wells drilled from a common pad into a common zone within one completion campaign share
unobserved rock, share the same crew and design, and are frequently completed within days of
one another; their outcomes are strongly correlated. If one lands in train and its
pad-mate in test, the ML model can recall the pad through coordinates and design and the
type-curve control cannot exploit it in the same way — so the leak inflates ML's measured
advantage **asymmetrically**, which is the worst possible failure for S4.

```
pad_group_id = connected component over wells where
    surface_hole_distance(i, j) ≤ PAD_RADIUS_M              (projected CRS)
  AND |completion_date(i) − completion_date(j)| ≤ PAD_WINDOW_DAYS

fallback for wells with no surface point:
    group = (spacing_unit_id, completion half-year)
```

Every group is assigned wholly to TRAIN, CAL or TEST by its median `t_fp`. The split object
records `n_wells_reassigned_by_group_rule`; **a zero there is a red flag** — it means the
rule found nothing and should be investigated rather than celebrated.

Note what this is *not*: it is not a random group split (v0.6 §4A.3 prohibits random splits
and is right to). Temporal order is primary; grouping only moves the small number of wells
that straddle the boundary, and it moves them to the side their group's centre of mass sits
on.

### 3.5 Rolling origins — one split is one draw

`ROLLING_ORIGINS = 4`, annually spaced (e.g. B ∈ {2021-01, 2022-01, 2023-01, 2024-01}, pinned
per basin in `holdout_def`). Each origin yields its own `split_id`, its own models, its own
calibration and its own benchmark run.

Defence: the ML-versus-type-curve gap is a noisy statistic, and a single cutoff invites
exactly one criticism — "you picked a favourable year". Reporting four origins turns the
headline from a point into a distribution and makes a regime-dependent result visible
instead of averaged away. The pooled figure is reported *with* the per-origin figures, never
instead of them.

Cost: four times the training compute. Accepted; §12 shows it fits the budget, and one
training job runs system-wide at a time (v0.6 §3.7.3).

### 3.6 Hyperparameters — selected without touching calibration or test

- Search space is a **fixed, checked-in grid** (not random, not Bayesian): `num_leaves ∈
  {15, 31, 63}`, `min_data_in_leaf ∈ {20, 50, 100}`, `learning_rate ∈ {0.03, 0.05}`,
  `feature_fraction ∈ {0.7, 0.9}`, with `n_estimators` chosen by early stopping. A fixed
  grid is reproducible by construction and removes the tuner as a source of
  nondeterminism; adaptive search would need its own seed discipline for no measurable
  benefit at this scale.
- Selection uses an **inner temporal validation split carved out of TRAIN only** — the last
  `CAL_WINDOW_MONTHS` of TRAIN, under the same pad-group rule. CAL and TEST are untouched.
  This is the specific defence against "you tuned on the test set", and it is asserted by a
  test (§11.4 `test_train_cal_test_are_disjoint` plus an inner-split containment assertion).
- The selected configuration, the full grid, and the inner-split scores are recorded in
  `hyperparams` on the model row and in the recipe. A reviewer can see what was tried, not
  just what won.
- Early stopping uses the inner validation set's pinball loss at the model's own quantile.

### 3.7 The model inventory, and the league expectation models

Per basin, per origin:

| Artifact | Count | Note |
|---|---|---|
| Quantile models | streams(3) × horizons(≤2) × quantiles(3) = **18** | cum24 gated on history (OQ-1); ND at P3 may ship 9 |
| CQR bundles | streams × horizons = **6** | one served identity per (stream, horizon) — §4.5, §16 ER-07 |
| Calibrator artifacts | bundles × tails(2) = **12** | Mondrian tables, §4.4 |
| Shape library | per peer group | type-curve artifacts (§5), not models |
| League expectation models | **2** | `residual_cum12` (rock+location only) and `residual_cum12_design_adj` |
| Analog index | **1** per (feature_version, as_of_vintage) | §6 |

**The league expectation models are models and obey 4A in full** — v0.6 §4A never mentions
them, which is §16 ER-14. They serve numbers (v0.6 §3.6.12 endpoint 22), so 4A.13 applies:
registered, versioned, cited by `model_id` on every league row. They use the same
`split_id`, the same censoring, the same leakage constraints, and the same conformal
machinery. The only difference is the feature set: `rock_location_only` (which by §1.5 is a
registry membership, so the exclusion of operator and design is *provable*) and
`design_adjusted`. The residual is `actual − P50(expectation)`, per 1,000 ft, with a
bootstrap CI over wells and `n_wells` shown always (v0.6 §8.1 D-17).

### 3.8 What is deliberately not done

- **No sample weighting** (recency, volume, or operator-balance). Recency weighting is a
  soft, unauditable version of the cutoff the split already encodes, and volume weighting
  would tell the model that big wells matter more — which is true for dollars and false for
  the estimand. Available as an ablation; off by default.
- **No target clipping or winsorization.** Quantile regression is already robust to tail
  observations at P50; clipping would distort P90 precisely where the interesting wells are.
- **No cross-validation folds.** v0.6 §4A.3 prohibits random splits, and K-fold over a
  temporal population is a random split wearing a lab coat. Rolling origins (§3.5) are the
  temporal analogue and are used instead.

---

## 4. Quantile model and conformal calibration

### 4.1 LightGBM configuration

Objective `quantile` with `alpha ∈ {0.10, 0.50, 0.90}`, one model per quantile per (stream,
horizon), per v0.6 §4A.7 and §8.1 D-1.

**Monotone constraint: `+1` on `lateral_length_ft`, and nothing else.** Physically, holding
design and rock fixed, more completed lateral cannot reduce total recovery; empirically, an
unconstrained tree will happily produce local decreases in sparse regions. The constraint
matters beyond tidiness: U14 is a scenario tool whose whole interaction is "change the
lateral length", and a tool that shows a longer lateral recovering less is a credibility
loss with no offsetting truth. Constraints on proppant intensity are **not** imposed —
diminishing and occasionally negative returns to intensity are a live empirical question and
constraining it would bake in an answer the benchmark is supposed to measure. The
constraint's cost in pinball loss is reported in the ablation table; if it costs materially,
that is a finding.

`monotone_constraints_method` is pinned in the recipe. All determinism-relevant parameters
are in §4.7.

### 4.2 Quantile crossing

Independently fitted quantile models can cross (P10 > P50). Handling, in order:

1. **Rearrangement**: sort the three predictions per row ascending. This is a monotone
   rearrangement and cannot increase the pinball loss of the set.
2. **Rearrange before conformal calibration**, so nonconformity scores are computed on
   coherent quantiles. Calibrating first would let a crossed pair produce a nonsensical
   score.
3. **Report `crossing_rate`** (share of rows crossed pre-rearrangement) as a model quality
   metric. Above `CROSSING_RATE_MAX = 0.02` the model is flagged as likely mis-specified and
   **blocked from promotion** (§10.2) — rearrangement fixes the symptom and hides the
   disease, so the disease gets its own number.

### 4.3 The conformal variant — chosen and defended

**Decision: split-conformalized quantile regression (CQR) with asymmetric, per-tail
nonconformity scores, applied group-conditionally (Mondrian).**

v0.6 §8.1 D-1 and §9 already name CQR; what v0.6 does not choose is the *score* and the
*conditioning*, and both change the numbers materially.

**The mechanics, pinned so an implementer cannot drift:**

```
Fit  q̂_lo(·), q̂_50(·), q̂_hi(·)  on TRAIN     (α_lo = 0.10, α_hi = 0.90 quantile models)
Rearrange (§4.2).

On CAL, per group g and per tail:
    E_lo^i = q̂_lo(x_i) − y_i           i ∈ CAL_g
    E_hi^i = y_i − q̂_hi(x_i)

    k_lo = ⌈ (n_g + 1)(1 − ALPHA_LO) ⌉       (index into the sorted scores, 1-based)
    Q_lo(g) = k_lo-th smallest of {E_lo^i}    (if k_lo > n_g → +∞, i.e. an infinite band,
                                               which is the honest answer for a tiny group)
    Q_hi(g) likewise.

Serve:  [ q̂_lo(x) − Q_lo(g(x)) ,  q̂_hi(x) + Q_hi(g(x)) ],  point = q̂_50(x)
```

Ties are broken by a stable sort on `(score, api10)` so the calibrator is deterministic —
the conformal quantile is an order statistic, and an unstable sort is a silent D2 violation.

**Why asymmetric rather than the standard symmetric CQR score** `E = max(q̂_lo − y, y − q̂_hi)`:

- The symmetric score buys a slightly tighter single-shot guarantee (exact `1 − α` from one
  order statistic) but applies **one** correction to both ends. Production distributions are
  strongly right-skewed and heteroscedastic, so the score is dominated by upper-tail misses;
  the correction that fixes P90 then pushes P10 down by the same amount.
- **P10 is the number that drives conservative valuation** (v0.6 §4B.7 requires NPV at P10,
  P50 and P90 together). Systematically inflating the downside band to compensate for
  upper-tail behaviour would make every downside NPV wrong in the same direction — a
  reviewer would find it immediately by comparing measured lower-tail and upper-tail
  coverage.
- 4A.8 asks for coverage tables. Per-tail scores make **per-tail coverage reportable**,
  which is what a coverage table should contain.

**What it costs, stated:** the asymmetric construction gives marginal coverage ≥ `1 −
ALPHA_LO` on the lower tail and ≥ `1 − ALPHA_HI` on the upper tail; central coverage
follows by union bound as ≥ `1 − ALPHA_LO − ALPHA_HI` = 0.80, which is slightly conservative
compared with the symmetric score's exact 0.80. The slack is of order `1/(n_g + 1)` per
tail. At `CAL_MIN_N = 100` that is ≈ 1% per tail. Paying 1–2% of conservatism to get
correct, separately reportable tails is the right trade for a system whose output becomes
dollars.

**P50 is not conformalized.** It is the median prediction from the `alpha = 0.50` model, and
it is labelled a point estimate. Conformal produces intervals, not points; presenting a
"calibrated median" would be a category error.

### 4.4 Mondrian (group-conditional) calibration

Marginal conformal coverage is the weakest guarantee that is still useful: it holds on
average across the whole population and can hide systematic under-coverage in a slice. v0.6
§4A.8 demands coverage tables **by slice**, so a marginal calibrator would be shipped
knowing its slice table would fail.

```
Taxonomy  g(x) = (basin, stream, horizon, formation_group, lateral_length_bucket)

lateral_length_bucket ∈ { <7500, 7500–9500, 9500–11000, >11000 } ft
formation_group        = canonical formation via formation_aliases, collapsed to the
                         basin's principal targets, with an __other__ bucket

Fallback ladder when n_g < CAL_MIN_N:
    (basin, stream, horizon, formation_group, length_bucket)
 →  (basin, stream, horizon, formation_group)
 →  (basin, stream, horizon)
```

Every prediction records `calibration_group_used` and `calibration_n`, and these appear in
the response envelope alongside the interval. A user reading a wide band on an unusual well
can see that the band came from a fallback group with n = 130, which is the glass-box
answer to "why is this band so wide".

**The impossibility result is acknowledged, not dodged.** Distribution-free *conditional*
coverage — valid for every x — is unattainable without further assumptions; group-conditional
coverage over a pre-declared partition is the strongest attainable form and is what is
implemented. Claiming per-well conditional validity would be false, and it is not claimed
anywhere in this system.

### 4.5 The served identity: the CQR bundle

A single forecast requires three quantile models plus a calibrator, but v0.6 §3.4.4's
`models` table has singular `quantile` and `target_stream` columns, and SB-07 §7's
`lineage.models` has neither a quantile column nor a home for calibrator parameters. A
forecast that "cites a `model_id`" (v0.6 §4A.13) is therefore ambiguous today (§16 ER-07).

**Resolution, expressed inside SB-07's existing registry rather than by redesigning it:**

- Each quantile model is registered as a normal `lineage.models` row with its `alpha` in
  `hyperparams`.
- A **bundle** is registered as one further `lineage.models` row with `algo = "cqr_bundle"`,
  whose `artifact_sha256` is taken over a canonically-serialized manifest listing the three
  member `model_id`s, the calibrator artifact hash, `feature_version`, `feature_set_hash`,
  `conformal_alpha` and the Mondrian taxonomy definition.
- **The bundle's `model_id` is what every forecast, valuation, inventory slot, tile
  attribute and ledger entry cites.** Member models are reachable one hop away through the
  bundle's derivation inputs.
- The calibrator table (per-group `Q_lo`, `Q_hi`, `n_g`) is a D1 artifact with its own
  `model.calibrate` derivation, referenced by `calibration_report_ref`.

This consumes SB-07 as written. The schema gap in v0.6 §3.4.4 is handed to SB-00 (§16
ER-07), not patched locally.

### 4.6 Calibration reporting (4A.8)

Published with every bundle, and on the scorecard:

| Metric | Why it is here |
|---|---|
| Empirical central coverage, pooled and per slice | 4A.8's headline |
| **Per-tail coverage** (lower and upper separately) | Asymmetric calibration's payoff; a symmetric report hides which tail is wrong |
| Clopper–Pearson 95% CI on each coverage figure | A coverage of 0.78 on n = 40 is not evidence of anything, and reporting it bare invites a false conclusion |
| **Mean interval width (sharpness), absolute and per 1,000 ft** | **Coverage alone is trivially gameable by widening intervals.** Coverage without sharpness is not a calibration report |
| **Interval score (Winkler)** at 80% | The proper scoring rule that penalizes width and miscoverage jointly — the single number that cannot be gamed by either |
| Pinball loss per quantile | Comparable to the benchmark's primary metric |
| `calibration_group_used` distribution and fallback share | Shows how much of the population is on a fallback group |
| `crossing_rate` | §4.2 |
| `censored_share`, `late_report_share`, `withheld_share` | 4A.4, §3.2, OQ-7 |

A slice whose measured coverage falls outside `COVERAGE_SLICE_BAND` is reported as a **miss**
in plain language in the artifact, per v0.6 §4A.7's "a miss is reported as a miss". It is
not quietly rolled into the pooled figure.

### 4.7 Determinism (SB-07 §4.2, class D2)

LightGBM artifacts are **D2**: byte-identical within a pinned `env_id`, prediction-equivalent
within `probe_tolerance` across environments. SB-02 supplies the parameters SB-07 §4.3
requires and does not default them in code:

```
deterministic            = true
force_row_wise           = true
num_threads              = <pinned by env_id>
seed, bagging_seed, feature_fraction_seed, data_random_seed  = from recipe seeds
monotone_constraints, monotone_constraints_method            = pinned
```

- **The conformal calibrator is D1**, not D2: it is an order statistic over a sorted array
  with a declared tie-break. It inherits D2 only through the model whose scores it
  calibrates, which is exactly SB-07 §4.3's "conformal calibration inherits the class of the
  model it calibrates" — SB-02 additionally records that the calibration *step* is itself
  reproducible byte-exactly given the same scores, which localizes any determinism failure
  to the learner.
- **Probe set**: 1,000 feature rows, a D1 artifact with its own derivation, versioned with
  `feature_version`. Registered at model registration per SB-07 §4.3;
  `probe_tolerance` default 1e-9 same-architecture, recorded per model otherwise.
- The determinism check (SB-07 §10 Check 8) trains the fixture model twice in the pinned
  environment and asserts artifact hash equality plus probe-prediction equality. SB-02 owns
  the fixture and the assertion; SB-07 owns the harness.

---

## 5. The type-curve engine — the control group

### 5.1 The control must be built in good faith

v0.6 §4A.5 makes the peer-group type curve the mandatory control for every ML claim, and
v0.6 §7.4 puts E4 on the never-cut list because "without it every accuracy claim is
marketing". Both are correct, and both are undermined by the same failure: **a weak control.**

A benchmark whose control is a strawman proves nothing, and a hostile reviewer's first move
is to attack the control, not the model. So the control is specified as the *best-practice
manual workflow* a competent reservoir engineer would actually run — peer filter,
normalization, censoring-aware per-month aggregation, empirical band, Arps tail — and it is
given every advantage the ML arm gets: the same split, the same as-of constraints, the same
slices, and **two normalization arms** so that the comparison cannot be an artifact of the
control's assumptions (§5.3).

The engine is one object with two callers: the benchmark control (fixed peer definition) and
the product's user-driven type-curve builder (v0.6 §3.6.12 endpoint 12, U2). Same code, same
artifact schema, same `type_curve_id` content addressing.

### 5.2 Peer-group definition

OQ-3 leaves the peer-group definition open, which is fine for the product and **not** fine
for the benchmark: an unpinned control makes S4 irreproducible across runs (§16 ER-04).

**Pinned benchmark control peer group:**

```
peer(subject) = wells w in TRAIN ∪ CAL  (never TEST) such that
      formation_group(w) == formation_group(subject)
  AND area(w)            == area(subject)             # county in ND; RRC district in TX
  AND lateral_length_bucket(w) == lateral_length_bucket(subject)
  AND t_fp(w) within VINTAGE_WINDOW (36 months) before B
  AND w has ≥ 1 producing month at as_of(C)
```

The **product** builder accepts any user filter set (that is its purpose, and it is the
ComboCurve-attributed harvest row in v0.6 §5.1); the **benchmark** uses the pinned
definition, and the benchmark artifact records it verbatim so a reader can reproduce it. A
learned peer neighbourhood is the OQ-3 comparison and is run as an additional control arm
once E3 is stable, not as a replacement.

### 5.3 Normalization — both arms, by role (D-2)

| Arm | Construction | What it assumes |
|---|---|---|
| `typecurve_per_kft` | build the peer curve per 1,000 ft, scale by the subject's `lateral_length_ft / 1000` | Recovery is proportional to completed length |
| `typecurve_absolute` | build the peer curve in absolute volumes, no rescaling; the length bucket in the peer filter does the normalizing | No proportionality; relies on bucketing for comparability |

**Both are always run and both are always reported.** This is the specific defence against
the strongest available attack on S4: "your control assumes recovery is linear in lateral
length, so of course the ML model wins on long laterals". If the ML advantage survives
against `typecurve_absolute`, the advantage is not a normalization artifact. If it does not,
that is the honest finding and the benchmark says so.

D-2's "both normalizations by role" is honoured at the serving layer too: the curve artifact
carries both series, `normalization` is stated on every served series, and anything that
becomes dollars uses the absolute series (v0.6 §8.1 D-2).

### 5.4 Aggregation — censoring-aware, and the two traps

```
Time zero  = first producing month (not the calendar month, not the completion date)
For month m ∈ 1..H:
    peers_m = { w ∈ peer(subject) : w has ≥ m producing months at as_of(C) }
    if |peers_m| < TC_MIN_N: mark month m insufficient (do not extend the curve silently)
    rate_m(q) = equal-weight empirical q-quantile of { volume_m(w) : w ∈ peers_m }
    report n_m
```

**Trap 1 — the decaying-n curve.** A type curve whose peer count falls from 200 wells at
month 1 to 12 wells at month 24 is a curve that changes population mid-flight, and the tail
is usually the *oldest* wells (they are the only ones with 24 months), so the tail silently
becomes a vintage statement. `n_m` is published per month and rendered on the chart; below
`TC_MIN_N` the month is marked insufficient rather than drawn.

**Trap 2 — cumulative quantiles are not cumulative sums of quantiles.**
`Σ_m P50(rate_m) ≠ P50(cum)`. The cumulative control quantiles are computed as the
**empirical quantiles of the peers' own cumulatives**, full stop. This is asserted by a test
(§11.4 `test_typecurve_cum_quantiles_not_summed_from_monthly`) because it is the exact error
that produces a plausible, slightly-wrong number.

Weighting is **equal per well**, not volume-weighted: volume weighting lets one monster well
define the "typical" curve, which is the opposite of what a type curve is for.

**Fallback ladder** when the pinned peer group is below `TC_MIN_N`:
`(formation, area, length_bucket)` → `(formation, area)` → `(formation, basin)`. The level
used is recorded per subject. If even the basin level fails, the control is **unavailable**
for that subject and the benchmark records `control_unavailable` — it never falls back
silently, and `control_unavailable_share` is a reported benchmark field, because a comparison
that quietly drops the hard subjects is a rigged comparison.

### 5.5 The control's band, and why the comparison is fair

The control's P10/P50/P90 are the peer group's **empirical quantiles**, which makes the
control a genuine distribution-free interval estimator — not a point forecast with an
invented band. Consequences:

- The control gets a **coverage measurement on the same test set**, so §7's comparison
  covers uncertainty quality, not just central accuracy. A model that is more accurate at
  P50 but badly calibrated is not obviously better, and the benchmark should be able to say
  so.
- The control gets the same interval score (Winkler) as the ML arm. This is the single
  metric on which the two are most fairly compared.

### 5.6 Leakage rules apply to the control identically

The peer group is drawn from TRAIN ∪ CAL only, at `as_of(C)`, with the same pad-group
constraint (a subject's own pad-mates are excluded from its peer group — otherwise the
control is reading a near-copy of the answer). Stating this is not pedantry: a control built
on today's full population against a model trained at a past cutoff is the most common way
benchmarks in this category are quietly rigged, in the direction that flatters the *control*
and therefore looks conservative and trustworthy.

### 5.7 The naive floor

A third control arm, `naive_median`: the basin-and-formation median cum12 per 1,000 ft,
scaled to the subject's length. It exists to contextualize the headline — "ML beats the type
curve by X" means little without "and the type curve beats the naive floor by Y". If the
type curve does not beat the naive floor on some slice, that slice's peer definition is
broken and the benchmark surfaces it rather than reporting an ML win against a broken
control.

---

## 6. Analog KNN

Two consumers, one artifact: the served analog list (U17, v0.6 §3.6.12 endpoint 10) and
`training_support` (4A.10), which gates every slot and every scenario (4D.2, 4D.3). Building
them from one index is not an optimization — it means the number that gates a slot and the
neighbours a user is shown are the *same* neighbours, so a user can audit the gate.

### 6.1 Identity and persistence

`analog_index` is **always persisted** (v0.6 §8.1 D-23), keyed
`(feature_version, as_of_vintage, basin)`, with an `analog.index` derivation and an
`output_sha256` over the serialized index (SB-07 §1.7). An in-process index is a read-through
cache of the persisted artifact and never a substitute — v0.5's 60-second rebuild threshold
silently decided whether analog results could carry a derivation at all (A-15, `ab:658`),
and that decision is now made once, in the right direction.

The index contains: the standardized feature matrix, the standardization statistics
(train-only, §1.8), the feature id list and order, the family weights (§6.2), and the
`api10` ordering. All of it is inside the hash, so a reordered column produces a different
index id rather than silently different neighbours.

### 6.2 Feature space, standardization, metric

**Space.** Design + location + rock only. Outcome-derived features are **excluded from the
analog space** — including `depletion_proxy`. This differs from the model's feature set and
the difference is deliberate: an analog is "a well like this one" in the sense a reservoir
engineer means it (v0.6 §9 defines an analog as near in *feature* space, distinct from a
neighbour, which is near in *physical* space), and including a depletion feature would make
"similar" partly mean "similarly depleted", which is a different and less useful question.
The excluded set is recorded on the index so the space is auditable.

**Standardization.** Z-score using TRAIN-only mean and standard deviation (§1.8), stored in
the artifact. Categorical features (formation, landing zone) enter as one-hot columns scaled
so each categorical contributes at most 1.0 to squared distance — otherwise a 20-level
formation encoding would dominate a 6-feature design family purely by cardinality.

**Metric: plain Euclidean on standardized features**, per OQ-8's "start Euclidean; compare
once E3 is stable". Defence and its limit, both stated:

- Euclidean on standardized features is transparent, cheap, and explains itself in one
  sentence to a user — which matters for a feature whose product value is trust.
- Its known weakness is that it weights correlated features by how many of them there are:
  five collinear design columns get five times the influence of one location column. The
  mitigation is **family-level weight normalization** — each family (`design`, `location`,
  `geology`, `spacing`) contributes equal total weight by default, with the weights recorded
  on the index and exposed as a parameter. This is a small, defensible correction, not a
  learned metric.
- The learned alternative (model leaf co-occurrence — how often two wells land in the same
  LightGBM leaf) is the OQ-8 comparison arm, run once E3 is stable and evaluated by the same
  §6.4 check. It is not the default because a learned metric inherits the model's biases and
  makes the analog panel a restatement of the model rather than an independent view of it.

**Implementation.** `sklearn.neighbors.NearestNeighbors(algorithm="brute", metric="euclidean")`
— exact, with no tree-construction nondeterminism. Ties are broken by a stable sort on
`(distance, api10)`. At ND scale (2×10⁴ wells × ~30 columns) brute force is milliseconds and
buys exactness; approximate indexes are §15 gold-plating.

### 6.3 As-of discipline

Analogs for a subject at `as_of = v` are drawn only from wells whose **actual outcomes were
knowable at v** and whose features satisfy C1 at their own anchors. A scenario's analogs at
`as_of = v` therefore cannot include a well whose cum12 completed after v. Without this, the
analog panel would leak future outcomes into a scenario that the model itself was forbidden
from seeing — an inconsistency that a reviewer comparing the two panels would find
immediately.

### 6.4 The 4A.12 quality check — with the number v0.6 omits

v0.6 §4A.12: "the top-10 analogs' actual cum12 IQR must bracket the subject's actual at
stated rates". The rate is never stated anywhere in v0.6, yet P3's exit criterion is "4A.12
green" (v0.6 §7.1) — an exit gate that cannot fire (§16 ER-05). Pinned:

```
For a sample of held-out subject wells (TEST, ≥ 300 subjects, seeded sample):
    A(s)        = top-10 analogs of s, drawn from TRAIN ∪ CAL at as_of(C)
    [Q1, Q3](s) = interquartile range of { actual cum12(a) : a ∈ A(s) }
    bracket(s)  = 1 if actual cum12(s) ∈ [Q1, Q3](s) else 0

    bracket_rate = mean(bracket)
    PASS iff |bracket_rate − IQR_BRACKET_TARGET| ≤ 0.10       (i.e. 0.40 ≤ rate ≤ 0.60)
```

**The target is 0.50, and that is the whole subtlety.** An interquartile range covers half
the mass of the distribution it is drawn from, so a *well-behaved* analog set brackets the
subject about half the time. This makes the check genuinely two-sided:

- `bracket_rate` **well below 0.50** → the analogs are not analogous; the subject falls
  outside their central half more often than chance, so the metric or the feature space is
  wrong.
- `bracket_rate` **well above 0.50** → equally a failure, and the one everybody misses. It
  means the analogs are *diffuse*: their outcomes are spread so widely that their IQR
  swallows almost anything. High bracketing is not high quality; it is an uninformative set
  passing itself off as a precise one.

Reported alongside, so the rate is interpretable rather than a lone number:

- **Median IQR width** relative to the population IQR — the sharpness counterpart to the
  bracket rate, exactly as interval width is to coverage (§4.6). A bracket rate of 0.50 with
  an IQR as wide as the whole basin is a failure that the rate alone cannot express.
- Median absolute feature distance to the 10th analog, and its distribution.
- Bracket rate **by slice** (formation, length bucket, vintage), so 4A.12 is "reported like
  calibration" as v0.6 §4A.12 requires — same slice taxonomy, same Clopper–Pearson CIs.

Failure response: 4A.12 red blocks P3 exit and blocks promotion of the index. The first
remediation is family weighting (§6.2), the second is the OQ-8 learned-metric arm; neither
is "widen until it passes".

### 6.5 `training_support` — pinned so the 4D gates can fire

v0.6 §4A.10 requires `training_support` on every prediction "on a stated 0–1 scale with its k
and metric declared", and 4D.2/4D.3 gate inventory on it — but v0.6 never states the scale,
so the gate is untestable as written (§16 ER-06). Pinned:

```
k              = KNN_K = 25
metric         = Euclidean on the §6.2 standardized, family-weighted space
d̄(x)           = mean distance from x to its k nearest TRAIN wells
d_ref          = the 90th percentile of d̄ over TRAIN wells (leave-one-out), stored on the index

training_support(x) = clip( 1 − d̄(x) / d_ref , 0, 1 )
```

Properties, all deliberate:

- **0 means "outside the training data's reach"**, not "no neighbours" — a well beyond the
  90th percentile of the training population's own neighbour distances scores 0. That is a
  conservative and legible definition.
- **Scale-free across basins** because `d_ref` is computed per index from the training
  population itself, so ND and Permian supports are comparable in meaning even though the
  populations differ.
- `k`, `metric`, `d_ref` and the index id are **declared on every prediction**, per 4A.10 —
  the number is never served bare.

`training_support` is reported as a distribution, never as a mean, wherever it describes a
set (4D.3: inventory rollups always state the support distribution). A mean support of 0.6
over a township could be 0.6 everywhere or half zeros and half ones, and those are different
inventories.

---

## 7. Benchmark harness (E4 / S4)

The only sanctioned producer of accuracy claims in the system (v0.6 §3.2 C9). If a number
describing model accuracy appears anywhere — UI, notebook, capability matrix, README — it
came from a benchmark artifact or it is a defect.

### 7.1 Identical holdout — enforced, not promised

S4's wording is "type curve vs ML on an identical temporal holdout". Identical is made
mechanical:

- One **split object** per (basin, origin), content-addressed as `split_id`, materialized
  once and read by every arm.
- Every arm's derivation records `split_id` in `params`; the harness **asserts equality
  across arms before computing any metric** and fails the run otherwise.
- CI asserts the same, on the fixture (§11.5 `test_typecurve_uses_same_split_id`).
- The subject set is the intersection of arms that produced a forecast, and the
  **`control_unavailable_share` is reported** (§5.4) — the intersection is never taken
  silently, because dropping the subjects the control could not handle is how a benchmark
  gets quietly rigged toward ML.

Arms per run: `ml_cqr`, `typecurve_per_kft`, `typecurve_absolute`, `naive_median`, plus any
declared ablation arms (§7.6).

### 7.2 Metrics

| Metric | Role | Note |
|---|---|---|
| **Interval score (Winkler) at 80%** | **primary** | Proper, penalizes width and miscoverage jointly; the one number that cannot be gamed by widening or by sharpening |
| Pinball loss at P10, P50, P90 | primary, per quantile | Directly the fitted objective; comparable across arms because the control's quantiles are empirical |
| Empirical coverage, central and per tail, with Clopper–Pearson CIs | primary | §4.6 |
| MAE on P50, in absolute bbl/mcf | secondary | Interpretable in the unit the industry uses |
| **Median** absolute percentage error on P50 | secondary | Median, not mean: MAPE is unstable near zero and unbounded above, and cum12 has both small wells and a long tail. The asymmetry of MAPE is stated wherever it is shown |
| Month 1–3 cumulative error | secondary | The measured cost of the hierarchical shape decision (§2.2) |
| Bias (mean signed error on P50) | secondary | A model can have good MAE and be systematically high |

**Comparison statistics: paired bootstrap CIs, no p-values.** For each slice, resample
subjects with replacement `BOOTSTRAP_B = 2000` times, recompute the arm difference, report
the 2.5/97.5 percentiles of the difference. With ~40 slices, per-slice significance testing
would be a multiple-comparison exercise that invites over-claiming; **the artifact reports
intervals and says nothing about significance.** A slice whose difference CI spans zero is
reported as a tie, in those words.

### 7.3 Slicing (4A.9)

Slices: `operator` · `completion vintage (year)` · `formation_group` · `area` (county / RRC
district) · `lateral_length_bucket` · `training_support` decile · `censored_share` band ·
`calibration_group fallback level` · `stream` × `horizon`.

- Slices with `n < SLICE_MIN_N` (50) are reported as **`insufficient_n`** with their n, never
  dropped and never merged silently.
- Slices with `n < 200` are reported but do not participate in promotion gating (§10.2) —
  the gate needs enough n to mean something.
- The `training_support` decile slice is the most product-relevant one: it answers "where
  does the model know what it is doing", which is what 4D and the scenario card actually
  need, and it is the slice most likely to show ML losing (low support) — which is why it is
  mandatory rather than optional.

### 7.4 Artifact schema

`benchmark_id` is content-addressed. The artifact is D1, has a recipe, and is regenerable
with a matching hash (v0.6 §5 E4 acceptance).

```json
{
  "benchmark_id": "bmk_…", "recipe_id": "rcp_…", "derivation_id": "drv_…",
  "basin": "nd", "origin": "2024-01", "split_id": "spl_…",
  "knowledge_cutoff": "2025-04-01", "eval_vintage": "2026-08-01",
  "feature_version": "fv1.3", "feature_set_hash": "sha256:…",
  "arms": [
    {"arm": "ml_cqr", "model_ids": {"oil.cum12": "mdl_…"}},
    {"arm": "typecurve_per_kft", "type_curve_spec": {...}},
    {"arm": "typecurve_absolute", "type_curve_spec": {...}},
    {"arm": "naive_median", "spec": {...}}
  ],
  "population": {"n_train": 0, "n_cal": 0, "n_test": 0,
                 "n_reassigned_by_group_rule": 0,
                 "censored_share": 0.0, "withheld_share": 0.0,
                 "late_report_share": 0.0, "control_unavailable_share": 0.0},
  "results": [
    {"stream": "oil", "horizon": 12, "slice": {"dim": "overall", "value": null}, "n": 0,
     "by_arm": {"ml_cqr": {"interval_score": 0.0, "pinball": {"p10": 0.0, "p50": 0.0, "p90": 0.0},
                           "coverage": {"central": 0.0, "lower_tail": 0.0, "upper_tail": 0.0,
                                        "ci_lo": 0.0, "ci_hi": 0.0},
                           "sharpness_bbl": 0.0, "mae_bbl": 0.0, "medape": 0.0, "bias_bbl": 0.0}},
     "ml_advantage": {"metric": "interval_score", "delta": 0.0, "delta_pct": 0.0,
                      "ci_lo": 0.0, "ci_hi": 0.0, "verdict": "ml_better|tie|control_better"}}
  ],
  "slices_where_ml_loses": [ {"stream": "oil", "horizon": 12, "dim": "training_support_decile",
                              "value": "d1", "n": 0, "delta": 0.0, "ci_lo": 0.0, "ci_hi": 0.0} ],
  "reader_summary": "generated from the numbers above, never hand-written",
  "plausibility_flags": ["no_losing_slices"]
}
```

`ml_advantage.delta` is **signed** and may be negative. `verdict` is derived from the CI, not
from the point estimate.

### 7.5 Honest-loser reporting (DIR-1)

Three mechanisms, because "we will be honest" is not a mechanism:

1. **`slices_where_ml_loses` is a mandatory field**, and the schema test asserts its presence
   (§11.5). It may be empty, but it must exist and be computed.
2. **The plausibility flag.** A benchmark with **no** losing slices across ~40 slices and
   three arms raises `no_losing_slices`. That result is possible but improbable, and it is
   more often a sign of leakage or of arms sharing state than of a dominant model. The flag
   does not block the run — it forces an explicit look, and it appears on the artifact so a
   reader sees the same prompt the author saw.
3. **`reader_summary` is generated from the numbers**, never authored. A hand-written summary
   is where a losing slice goes to be described as "broadly comparable". The generator names
   the worst slice for ML by CI, always, in every summary.

F2 (v0.6 §2.4) is "can quantify the ML advantage honestly, **including the cases where it is
zero**". These three mechanisms are what make F2 answerable rather than aspirational.

### 7.6 Ablation arms

Declared ablations run as additional arms on the same split, so their results are directly
comparable and land in the same artifact:

| Ablation | Question it answers |
|---|---|
| `no_depletion` (spacing family dropped) | OQ-4: how much does parent-child encoding carry? Also the answer to "is your lift just neighbour performance?" |
| `no_geology` / `with_tops` (TX only in v0) | OQ-2: what would the $500 Premium tops tier buy? |
| `depletion_count` vs `depletion_distance` vs `depletion_decay` | OQ-4's three encodings, head to head |
| `log_target` | §2.3's rejected transform, quantified rather than asserted |
| `no_monotone` | §4.1's constraint cost |
| `symmetric_cqr` | §4.3's score choice, quantified per tail |
| `marginal_conformal` | §4.4's Mondrian choice, shown as the slice-coverage table it would have produced |
| `learned_analog_metric` | OQ-8, once E3 is stable |

Every ablation in this table is a v0.6 open question or a decision made in this document.
Running them as arms means the open questions close with numbers from the same harness that
produces the headline, rather than from a side experiment nobody can reproduce.

---

## 8. Forecast ledger (E13 / S7)

The ledger is the only artifact in this system that cannot be back-filled. It is worth
building even in a phase where nothing consumes it, because a track record that starts today
is worth more than a perfect one designed later — and because v0.6 §4E.5's logic (history not
captured cannot be reconstructed) applies to forecasts exactly as it does to vintages.

### 8.1 Write-at-forecast-time

A ledger entry is written by the `forecast.batch` job at publication, one per
`(api10, stream, horizon, bundle_model_id, as_of_vintage)`, content-addressed so a re-run of
the same publication is idempotent.

**Two write rules that are anti-gaming controls, not bookkeeping:**

1. **An entry is only valid if the outcome is unknown at publication.** If the well already
   has ≥ H producing months at `as_of_vintage`, no ledger entry is written — that would be a
   hindcast wearing a forecast's clothes, and a ledger stuffed with hindcasts would show
   excellent accuracy and mean nothing. Enforced by a test (§11.6).
2. **Scenario forecasts are never ledger entries.** A scenario is a hypothetical well; it has
   no actual and can never be graded. Ledger entries exist only for real API-10s. This also
   keeps the ledger's denominator honest — a system could otherwise inflate its track record
   with thousands of ungradeable rows.

Entry contents: `predicted_p10/p50/p90`, `bundle_model_id`, member model ids, `feature_version`,
`feature_set_hash`, `as_of_vintage`, `training_data_vintage` (copied from the registry at
write time), `horizon_months`, `anchor_date`, `training_support`, `calibration_group_used`,
`calibration_n`, `published_at`, `derivation_id`.

### 8.2 Append-only, and no silent withdrawal

The ledger is append-only under the same role grants as the audit stream (SB-07 §5.1). Three
consequences stated because each blocks a specific way of flattering a track record:

- **A forecast is never edited.** A better forecast for the same well is a *new* entry with a
  new `bundle_model_id` and `as_of_vintage`; both are graded and both are reported.
- **No entry is ever deleted or hidden.** Retiring a model (§10.4) does not retire its ledger
  entries — they are the evidence for why it was retired.
- **The reported track record is over all entries, not a selected subset.** Any filter
  applied to a served ledger view (by model, by cohort) is echoed in the response, so
  "accuracy" is never shown without stating whose entries it covers.

### 8.3 Graded-cycle mechanics (4A.14, DIR-2)

A monthly `ledger.grade` job. For each open entry, if the well now has H producing months:

```
V_first = the earliest report_vintage at which the H-th producing month was published
V_now   = the latest published vintage at grading time

Emit TWO grade rows (SB-07 §3.5's "re-grading appends" pattern, no schema change):
  row A:  graded_against_vintage = V_first    ← "as of the forecast's own grading vintage"
  row B:  graded_against_vintage = V_now      ← "against current actuals"
Both carry trained_on_vintage, copied from the model registry.
```

v0.6 §4A.14 requires exactly these two reports. SB-07 §3.5 already models re-grading as
appended rows with `trained_on_vintage` and `graded_against_vintage` — so this consumes the
spine as written, with no new columns and no `basis` flag: the two rows are distinguished by
their `graded_against_vintage`, which is the honest discriminator anyway.

**Restatement-drift decomposition.** `Δ = metric(row B) − metric(row A)` attributes movement
to the actuals moving rather than the model being wrong. SB-07 §3.5 recommends this become a
scorecard row and hands the scheduling decision back (SB-07 §15). **SB-02 accepts it**:
`ledger_restatement_drift` is a published scorecard metric per basin per cohort. It is the
direct evidence for F11 (v0.6 §2.4) and it converts v0.6 §8.2 R-04 from a risk into a
measurement.

Re-grading is idempotent per `(entry_id, graded_against_vintage)`; a later restatement
produces a *third* row at a new vintage, never an update.

### 8.4 Grade metrics

Identical to §7.2 — interval score, pinball, coverage, MAE, median APE, bias — so the ledger
and the benchmark are **commensurable**. This matters more than it sounds: the benchmark is a
retrospective simulation of deployment and the ledger is deployment. If the two use different
metrics, the most interesting question in the system ("did the retrospective benchmark
predict live performance?") cannot be asked. With shared metrics it becomes one subtraction,
and it is reported per cohort as `benchmark_to_ledger_gap`.

Additionally per publication cohort: coverage over time (calibration drift), and
`training_support` distribution of the graded population.

### 8.5 What "one graded cycle" means (S7)

v0.6 §2.4 S7 requires "one graded cycle complete" and never defines it, so P8's exit gate is
untestable (§16 ER-15). Pinned:

> **One graded cycle** = a cohort of at least `LEDGER_CYCLE_MIN_N` (100) ND oil cum12 entries
> published at a single `as_of_vintage`, of which every entry has reached H producing months
> and has been graded, with **both** grade rows emitted, the coverage CI computed, and the
> restatement-drift decomposition published.

100 is chosen so a coverage estimate has a Clopper–Pearson half-width of roughly ±8
percentage points at 80% — wide, but wide enough to detect a gross calibration failure,
which is what the first cycle is for. The number is on the artifact so a reader can judge it
rather than infer it.

Elapsed time, not effort, bounds this (v0.6 §7.2). Entries written from P5 onward with H = 12
mature roughly 12 producing months plus reporting lag later, which is why v0.6 §7.1 puts the
graded cycle in P8 and why the write path must start in P5 rather than when the ledger
surface is built.

---

## 9. Transfer test (E14 / F7)

E14 is first in the cut order (v0.6 §7.4). The design exists anyway, for two reasons: if it
survives it must not be improvised, and F7 ("can state whether a model transfers across
basins and precisely what breaks") is listed as an unconditional fluency outcome while its
only vehicle is the first thing cut (§16 ER-11).

### 9.1 Target basin: New Mexico, not Texas

Train ND, apply to the **NM Delaware** well-level spine — not TX. Defence, and it is the same
argument as v0.6 §8.1 D-20: TX production is lease-level, so a TX transfer test would measure
transfer degradation **plus** allocation error and could not separate them. NM is well-level
(`ad:287`), so the transfer measurement is clean. Using TX would produce a number that
answers no question.

### 9.2 Three arms and a decomposition

| Arm | What it is | What its gap measures |
|---|---|---|
| **(a) cold** | ND-trained bundle applied to NM features, ND calibrator unchanged | Total transfer degradation |
| **(b) recalibrated** | ND-trained quantile models, **conformal calibration refit on an NM calibration set**; no retraining | Gap (a→b) = **calibration transfer failure** — the model's ranking is fine, its uncertainty is not |
| **(c) native** | NM-only model, same protocol, small-n | Gap (b→c) = **conditional-function transfer failure** — the learned response surface itself does not carry over |

This decomposition is the deliverable. "The model transfers" and "the model transfers if you
recalibrate" are different findings with different product consequences, and a single
degradation number cannot distinguish them. Arm (b) is cheap — refitting a conformal
calibrator is an order statistic over a few hundred rows — so the decomposition costs almost
nothing beyond arm (a).

### 9.3 What breaks — the measurement, not the anecdote

Reported as a table, one row per feature, plus the aggregate:

| Measurement | Method |
|---|---|
| **Covariate shift per feature** | Wasserstein-1 distance between ND-train and NM-test on the standardized scale (comparable across features by construction) |
| **Out-of-support share** | Share of NM rows outside ND-train's [1st, 99th] percentile per feature, and jointly via `training_support` under the ND index |
| **`training_support` distribution of NM wells under the ND index** | The honest headline: if most NM wells score near 0, the model is extrapolating and every downstream number should say so. Measured *before* any accuracy claim is made |
| **Feature-availability differences** | Which ND features have no NM counterpart or a different meaning — spacing-unit semantics differ by state, ND tops are paywalled while TX ships them free (`ad:209`), FracFocus coverage differs by operator population. Enumerated as a table, not prose |
| **Degradation attribution** | Feature-family ablation on the transferred model: the family is **dropped and the model retrained without it** (family-mean substitution is not used — it would measure the imputation, not the family) |
| **Target-scale shift** | Ratio of NM to ND median cum12 per 1,000 ft by formation group; a level shift with an intact ranking is a recalibration problem, not a transfer failure |

### 9.4 Pre-registration

**The pass/fail thresholds are written into the notebook memo before the test runs**, with a
timestamped audit event. Specifically: "transfer works" is stated as a bound on arm (a)'s
interval score relative to arm (c)'s, and "recalibration is sufficient" as a bound on arm (b)
relative to arm (c).

This is a small ceremony with a large effect. E14's result is the single most quotable
finding in the project (v0.6 §1.2 Q7), and a threshold chosen after seeing the numbers is not
a threshold. Pre-registration costs one memo and makes the finding defensible to the audience
DIR-1 names.

### 9.5 If E14 is cut

Per §16 ER-11, the cut must be recorded the way v0.6 §2.4 already records S12's: F7 is marked
conditional, and the E16 capability matrix carries a **transfer** row tagged
*effort-unreachable* with the cut decision cited. Silently forfeiting a fluency outcome is the
failure mode v0.6 §2.4's conditionality clause exists to prevent.

---

## 10. Model registry usage (4A.13 / C24 / SB-07 §7)

SB-07 §7 owns identity and lineage. SB-02 owns what goes in and what is allowed out.

### 10.1 Division of labour

| SB-07 provides | SB-02 supplies |
|---|---|
| `register_model()`, `promote_model()`, `resolve_model()` | Every field in the model row: `training_window`, `training_data_vintage`, `holdout_def`, `hyperparams`, `seeds`, `probe_set_ref`, `probe_tolerance`, `calibration_report_ref`, `feature_version`, `feature_set_hash` |
| Immutability of model rows except `promotion_status` and timestamps | The gate that decides when `promotion_status` may change (§10.2) |
| "A forecast may not be served from a non-promoted model unless flagged `shadow`" | The shadow-mode operating procedure (§10.3) |
| `supersedes_model_id` chains | The retraining cadence and triggers (§10.5) |

`holdout_def` is not decoration: it carries `split_id`, `B`, `C`, `CAL_WINDOW_MONTHS`,
`EMBARGO_MONTHS`, the pad-group parameters and the per-source reporting lags, which together
let a reader reconstruct §3.3 exactly.

### 10.2 Promotion gate

A candidate becomes `promoted` **only if every one of these passes**, checked mechanically by
the promotion job, with the results recorded on the `model.promoted` audit event:

| # | Gate | Threshold |
|---|---|---|
| 1 | A benchmark artifact exists for this bundle on the **current** split object | `split_id` match, not "a recent benchmark" |
| 2 | Pooled central coverage inside `COVERAGE_PASS_BAND` | [0.72, 0.88] |
| 3 | Per-slice coverage inside `COVERAGE_SLICE_BAND` for every slice with n ≥ 200 | [0.65, 0.92]; a single breach blocks |
| 4 | Per-tail coverage each within [0.85, 0.95] against nominal 0.90 | asymmetric calibration must work on both ends |
| 5 | `crossing_rate` ≤ `CROSSING_RATE_MAX` | 0.02 |
| 6 | Determinism check green (SB-07 §10 Check 8) | artifact hash equality + probe equality |
| 7 | Every leakage guard test green (§11.4) | any red blocks; no override |
| 8 | 4A.12 analog check green if the bundle ships a new index | §6.4 |
| 9 | **Non-inferiority to the incumbent promoted bundle** on interval score, pooled | the 95% paired-bootstrap CI of (candidate − incumbent) must not lie entirely above zero |
| 10 | No slice with n ≥ 200 degrades by more than 10% in interval score versus the incumbent | prevents a pooled win that hides a slice collapse |
| 11 | `training_support` distribution over the serving population not materially shifted | 10th percentile within 0.05 of the incumbent's |
| 12 | `feature_set_hash` recorded and resolvable in the feature registry | §1.6 |

Gate 9 is **non-inferiority rather than superiority on purpose**: a retrain on fresher data
that is statistically indistinguishable from its predecessor is a legitimate promotion, and
requiring a measured improvement every cycle would create pressure to find one.

A candidate that fails any gate stays `candidate` forever — rows are never deleted (SB-07
§7) — and the failing gate is on the audit event, so "why was this not promoted" is answerable
a year later.

### 10.3 Shadow mode

Between `candidate` and `promoted` sits `shadow`. A shadow bundle:

- runs on the same schedule as the promoted bundle and **writes ledger entries flagged
  `shadow`**, accumulating a real, gradeable track record before it serves anything;
- never appears in an unflagged API response — `resolve_model()` enforces this (SB-07 §7);
- is compared to the promoted bundle on the same graded entries, which is a stronger test
  than the retrospective benchmark because it is live.

Minimum shadow period before promotion is **one grading cycle** for a MAJOR feature-version
change or an algorithm change. A routine retrain on a new data vintage with an unchanged
`feature_set_hash` may promote directly on the §10.2 gates.

### 10.4 Rollback

`promoted → retired` requires a recorded trigger and emits `model.retired` (SB-07 §5.2). The
triggers are pinned so rollback is a procedure, not a judgement call:

| Trigger | Detection |
|---|---|
| Live coverage breach | Ledger coverage over a rolling 3-cycle window falls outside `COVERAGE_PASS_BAND` with a CI excluding the band |
| Ledger degradation versus the prior bundle | Interval score worse by a CI-excluded margin on shared cohorts |
| A leakage regression found post-hoc | Any §11.4 test that starts failing against the model's recorded feature version |
| An upstream conformance-rule correction invalidating the training features | SB-07 §6.5 returns the affected derivations; if the bundle's features are in the closure, it is retired pending retrain |

**Rollback never rewrites history.** Retiring a bundle does not withdraw the forecasts it
produced: they remain valid at their own `model_id` and `as_of_vintage`, which is the entire
purpose of 4A.13's "retraining is additive; a published model is never overwritten". What
changes is what serves *next*. Ledger entries from a retired bundle stay in the track record —
removing them would be the exact dishonesty the ledger exists to prevent — and the retirement
reason is joined to them in the ledger view so a reader sees why the cohort ends.

The rollback target is the previous `promoted` bundle in the `supersedes_model_id` chain,
whose `artifact_sha256` is re-verified before it serves again.

A rollback also writes a notebook memo (v0.6 §5 E15) at the moment it happens. A rollback
reconstructed from git history six months later is not a learning instrument.

### 10.5 Retraining cadence and triggers

- **Scheduled**: quarterly per basin, or when a new production vintage adds ≥ 5% new labelled
  wells to the training population — whichever comes first.
- **Event-driven**: a MINOR feature addition, a conformance-rule correction in the feature
  closure, or a MAJOR feature version.
- **Never**: because a metric looked bad this week. Retraining in response to one cohort's
  noise is how a model gets fitted to its own ledger.

One training job runs system-wide at a time (v0.6 §3.7.3); C26 enforces it and SB-02 assumes
nothing about parallelism.

---

## 11. Test strategy (DIR-10)

TDD as directed: tests are written with or before the implementation of each unit, not
backfilled, and every phase exit criterion includes its tests passing. The suite lives under
the existing `tests/` scaffold and uses the markers already declared in `pyproject.toml`
(`unit`, `integration`, `contract`), plus one addition — **`determinism`**, for the
train-twice checks that are too slow for the default run.

### 11.1 Layout

```
tests/unit/
  test_feature_registry.py        registry schema, member_of sets, unit declarations
  test_leakage_guards.py          §11.4 — the whole leakage class
  test_targets.py                 producing-month definition, censoring, cum arithmetic
  test_split.py                   boundary, groups, disjointness, inner-split containment
  test_conformal.py               §11.3 — property tests on the calibrator
  test_typecurve.py               §11.5 — aggregation traps
  test_analog.py                  standardization, tie-breaking, IQR-bracket check
  test_ledger.py                  §11.6 — write rules and grading
  test_benchmark_artifact.py      schema, honest-loser fields, slice min-n behaviour
tests/integration/
  test_training_smoke.py          end-to-end on the tiny fixture against ephemeral stores
  test_registry_roundtrip.py      register → promote → resolve → refuse-on-hash-mismatch
tests/determinism/
  test_model_determinism.py       train twice; hash + probe equality (SB-07 §10 Check 8)
tests/support/
  synth.py                        the seeded synthetic basin generator (§11.2)
```

### 11.2 Deterministic tiny-data training tests

Two fixtures, each doing a job the other cannot:

**(a) `make_synthetic_basin(n=400, seed=SEED)`** — a known data-generating process:
`cum12 = f(lateral_length, proppant_per_ft, x, y) + heteroscedastic noise`, with a planted
parent-child depletion effect and a planted pad-group structure. Trains in under two seconds
on one core.

Because the DGP is known, the tests assert *behaviour*, not just "it ran":

- P50 response to `lateral_length` is monotone increasing (the §4.1 constraint holds).
- Recovered feature importance ranks the planted signal features above the planted noise.
- Conformal coverage on a held-out exchangeable sample lands inside its theoretical bounds
  (§11.3).
- The planted depletion effect is detected by the `no_depletion` ablation arm — a test of the
  *harness*, proving the ablation machinery can find an effect known to be there.

**(b) The real micro-fixture** — the ~200 ND wells, ~50 TX leases and ~30 NM wells already
specified for SB-07 §10's CI database. SB-02 reuses it rather than building a second fixture
set. Its job is schema realism: nulls, withheld months, `mod_dte` churn, a restated month, a
multi-wellbore quarantine. Synthetic data cannot produce those and real data cannot produce a
known ground truth, so both exist and neither pretends to be the other.

Budget: the `unit` suite runs in **under 60 seconds**; `test_training_smoke.py` under 30
seconds; `determinism` is excluded from the default run and gated in CI. A suite nobody can
afford to run is not a gate (SB-07 §10).

### 11.3 Calibration property tests

The conformal guarantee is a *theorem*, so it can be tested as a property with a tight
two-sided bound rather than a smoke test. Using `hypothesis` over seeds and sample sizes, on
synthetic **exchangeable** data:

| Test | Assertion |
|---|---|
| `test_conformal_coverage_bounds_on_exchangeable_data` | For n calibration points at nominal `1 − α`: coverage ≥ `1 − α` **and** ≤ `1 − α + 1/(n+1)`. Both bounds — the upper one catches an over-conservative implementation that would otherwise look "safe" |
| `test_conformal_quantile_index_formula` | The order statistic is exactly `⌈(n+1)(1−α)⌉`; an off-by-one is invisible at n = 10⁴ and fatal at n = 100 |
| `test_infinite_band_when_k_exceeds_n` | When `⌈(n+1)(1−α)⌉ > n` the interval is unbounded on that side rather than silently clipping to the max score |
| `test_mondrian_fallback_records_group_and_n` | Every prediction carries the group actually used and its n; a fallback is never silent |
| `test_mondrian_groups_are_disjoint_and_exhaustive` | The taxonomy partitions the space; no row lands in two groups or none |
| `test_quantiles_do_not_cross_after_rearrangement` | p10 ≤ p50 ≤ p90 for every row, always |
| `test_interval_width_monotone_in_alpha` | Tightening α never narrows the interval |
| `test_calibrator_is_deterministic_under_tie` | Duplicate scores produce identical calibrators across runs (the stable-sort tie-break, §4.3) |
| `test_asymmetric_matches_symmetric_on_symmetric_data` | On symmetric noise the two scores agree within tolerance — a sanity check that the asymmetric path is not simply wrong |

### 11.4 Leakage regression tests — including one that fails on a future-dated feature

This is the class the whole modeling section stands on. Each test names the failure it
prevents.

| Test | Fails when |
|---|---|
| **`test_feature_invariance_to_future_production`** | **Parameterized over every feature in the registry.** Build the matrix; append synthetic production rows dated **after** each well's anchor (and after its offsets' anchors); rebuild; assert every feature value is **byte-identical**. A feature that moves has leaked, whatever its registry row claims. Class-level: a newly added feature is in scope automatically, with no test to remember to write |
| **`test_poisoned_feature_is_rejected`** | Inject a registry row whose computed `knowable_at` is `anchor + 1 day` and build. Assert `FeatureLeakageError` is **raised** — not logged, not warned. This is the explicit "fails if a future-dated feature enters", and it fails loudly the moment the guard is removed or downgraded |
| `test_availability_date_never_exceeds_anchor` | Over the full fixture matrix: `max(knowable_at) ≤ anchor` per (well, feature) |
| **`test_label_read_vintage_le_cutoff`** | Reads the **lineage record**, not process memory: every `derivation_inputs` edge on the training derivation carries `as_of_vintage ≤ C` (SB-07 §1.4). The C2 guard — checking it through the derivation graph catches a code path that bypasses `as_of()` even when it produces plausible numbers |
| `test_no_canonical_read_outside_as_of` | Static check plus runtime assertion: the training package contains no direct canonical read |
| `test_split_groups_do_not_span_boundary` | Any `pad_group_id` appears in more than one of TRAIN/CAL/TEST |
| `test_train_cal_test_are_disjoint` | Three-way `api10` intersection non-empty; also asserts the inner hyperparameter split is contained in TRAIN |
| `test_test_labels_never_touch_a_fitted_object` | The TEST label array is a read-only view; any fit call receiving it raises |
| `test_typecurve_peers_exclude_test_and_own_pad` | The control's peer group intersects TEST, or contains the subject's own pad-mates |
| `test_analog_index_respects_as_of` | An analog is returned whose cum12 completed after the query's `as_of` |
| `test_standardization_stats_from_train_only` | Index statistics are computed over more than TRAIN |
| `test_excluded_features_absent_from_matrix` | Any §1.4 exclusion (IP90, target encodings, `first_production_month`, status, well name) appears as a column |
| `test_league_expectation_set_excludes_operator_and_design` | The `rock_location_only` membership admits an operator or design feature — D-17's claim made mechanical |

The first two are a pair. `test_poisoned_feature_is_rejected` proves the guard exists;
`test_feature_invariance_to_future_production` proves the guard is *sufficient*, because it
does not trust the declaration at all — it re-derives the answer from the data. A system with
only the first has a guard it cannot verify.

### 11.5 Harness and control tests

| Test | Fails when |
|---|---|
| `test_typecurve_cum_quantiles_not_summed_from_monthly` | The cumulative quantile equals the cumsum of monthly quantiles on a fixture where the two provably differ (§5.4 trap 2) |
| `test_typecurve_reports_n_per_month` | A month is emitted without its peer count, or a month below `TC_MIN_N` is drawn rather than marked insufficient |
| `test_typecurve_fallback_level_recorded` | A fallback ladder step is taken without recording the level |
| `test_typecurve_uses_same_split_id` | Any arm's derivation carries a different `split_id` from the ML arm |
| `test_benchmark_asserts_split_equality_before_metrics` | The harness computes a metric when arms disagree on `split_id` |
| `test_benchmark_artifact_has_losing_slices_field` | `slices_where_ml_loses` is absent (empty is legal, missing is not) |
| `test_benchmark_flags_no_losing_slices` | A fixture run where ML wins everywhere does not raise the `no_losing_slices` plausibility flag |
| `test_reader_summary_is_generated_not_stored` | `reader_summary` does not reproduce byte-identically from the numbers |
| `test_slice_below_min_n_reported_not_dropped` | A small slice vanishes instead of appearing as `insufficient_n` |
| `test_control_unavailable_share_reported` | Subjects with no control are silently dropped from the intersection |
| `test_analog_iqr_bracket_rate_within_band` | On a fixture with a known bracket rate the computed rate is outside tolerance — and separately, that an artificially **diffuse** analog set (rate ≈ 0.9) **fails** the check, proving §6.4's two-sidedness |

### 11.6 Ledger tests

| Test | Fails when |
|---|---|
| `test_ledger_entry_rejected_when_outcome_already_known` | An entry is written for a well already at ≥ H producing months (§8.1 rule 1) |
| `test_no_ledger_entry_for_scenarios` | A `scenario_id` reaches the ledger |
| `test_regrade_appends_and_preserves_prior` | A second grading updates a row instead of appending |
| `test_two_grade_rows_per_cycle` | Only one of `V_first` / `V_now` is emitted (4A.14 requires both) |
| **`test_restatement_changes_current_grade_not_asof_grade`** | Restating an actual moves the `V_first` row's metric. The most important ledger test: the mechanical statement of "a track record graded against a moving target is not a track record" |
| `test_ledger_is_append_only_by_grant` | `UPDATE`/`DELETE` as the pipeline or API role succeeds (mirrors SB-07 §10 Check 9) |
| `test_retired_model_entries_remain_in_track_record` | Retiring a bundle removes or hides its entries |

### 11.7 Registry and determinism tests

`test_registry_roundtrip.py`: register → promote → resolve; `resolve_model()` **refuses** a
feature matrix whose `feature_set_hash` differs; a non-promoted bundle cannot serve unflagged;
`supersedes_model_id` chains resolve.

`test_model_determinism.py` (marker `determinism`): train the fixture bundle twice in the
pinned environment; assert artifact `sha256` equality and probe-prediction equality within
`probe_tolerance`; assert the calibrator is byte-identical given identical scores; assert any
recorded `DeterminismViolation` fails the build (SB-07 §1.3).

### 11.8 What is deliberately not tested

Full-population training accuracy (that is the benchmark, not a test), LightGBM's own
correctness, and metric implementations against a second library — instead, metrics are tested
against hand-computed values on three-row fixtures, which catches the errors that matter
(sign, weighting, quantile index) without importing a comparison dependency.

---

## 12. Non-functional budgets

Against v0.6 §3.7.8, with the measurement that turns each into a test:

| Budget | v0.6 | SB-02 position |
|---|---|---|
| Three-stream model training < 20 min | §3.7.8 | **In tension with `byte_exact` single-threaded artifact production (v0.6 §4C.5) and with 4 rolling origins.** Measured at P3 as `training_wall_clock_by_config`; the tension is §16 ER-12. If the measurement exceeds the budget, the honest options are to widen the budget or to declare model artifacts D2-with-thread-pin (which SB-07 §4.2 already does) — not to quietly drop determinism |
| Analog index rebuild < 5 min | §3.7.8 | Comfortable: exact brute-force KNN at ND scale is seconds; the budget is dominated by feature assembly |
| Scenario forecast p95 < 3 s (S3) | §2.4 | SB-02's contribution is inference only — a loaded bundle predicting one row is sub-millisecond. The budget is spent in feature assembly and PostGIS spacing computation, which SB-01/SB-03 own |
| Benchmark run | not budgeted | Bounded by `ROLLING_ORIGINS × arms × slices`; runs as a job under `202 Accepted` (v0.6 §3.6.7), never interactively |
| One training job system-wide | §3.7.3 | Assumed, not managed here |

---

## 13. Interfaces

| Counterparty | SB-02 consumes | SB-02 emits |
|---|---|---|
| **SB-07 lineage spine** | `derive()`, `as_of()`, `register_model()`, `promote_model()`, `resolve_model()`, recipes, determinism classes, probe-set helpers, `figure()` | Registry rows with the §10.1 fields; `model.train` / `model.calibrate` / `forecast.batch` / `forecast.scenario` / `analog.index` / `ledger.grade` derivations with `output_sha256`; `as_of_vintage` on every training input edge; two grade rows per cycle |
| **SB-01 data platform** | Canonical production, completion events, spatial features, `formation_aliases`, `operator_aliases`, quarantine state | Feature-registry rows; `features.well_features` partitions keyed `(feature_version, as_of_vintage)`; the conformance rules the feature closure depends on |
| **SB-03 econ / scenarios / inventory** | — | A forecast object carrying P10/P50/P90 **together** (v0.6 §4B.7), absolute-normalized (§2.3), with `bundle_model_id`, `feature_version`, `training_support`, `calibration_group_used`, `report_vintage`, and a monthly series that sums exactly to the cumulative (§2.2) |
| **SB-04 API / agent** | Envelope helpers; the OpenAPI-example discipline | Response shapes for `/models`, `/benchmarks`, `/typecurves`, `/analogs`, `/ledger`; the fields that must never be omitted: `training_support`, `calibration_n`, `normalization`, `censored_share`, `granularity`, `basis` |
| **SB-05 map / UI** | — | Tile attribute values (`p50 cum12 per 1,000 ft`) each carrying its own handle — a model-styled map is otherwise a field of naked numbers (`ab:763`); the visual-break requirement for extrapolated series (4A.9) |
| **SB-06 infrastructure** | `/data/models` path, `lineage.environments` rows, thread pinning, the CI runner and its 5-minute budget | Training job unit definitions; the single-training-job concurrency requirement |
| **SB-00 v0.6 consolidation** | — | The fifteen errata in §16, and glossary rows (DIR-8) for *CQR, pinball loss, interval score, Mondrian calibration, exchangeability, pad group, rolling origin, anchor date, knowledge cutoff, label vintage, bracket rate, shadow model, honest loser* |

---

## 14. Rejected alternatives

- **Neural networks / any deep tabular model.** Worse on this data shape, far worse
  determinism story, unexplainable to the audience that has to trust the number. DIR-4's
  "boring and auditable beats contrarian" applies directly.
- **A second learner (XGBoost, CatBoost) as an ensemble.** Doubles the determinism and
  dependency surface for a small metric gain; the benchmark is not a learner bake-off.
- **Bayesian hierarchical model.** Attractive for spatial pooling and honest uncertainty, but
  its intervals are model-based rather than distribution-free — weakening exactly the claim
  (measurable coverage) that v0.6 §8.1 D-1 chose conformal for.
- **Random or K-fold cross-validation.** Prohibited by v0.6 §4A.3, and correctly: it leaks
  vintage, operator behaviour and price environment at once.
- **A random split with a group constraint.** Still a random split. Grouping supplements the
  temporal split; it never substitutes for it.
- **Symmetric CQR score.** §4.3 — one correction for two very different tails on a
  right-skewed target, and it corrupts P10 to fix P90.
- **Marginal (non-Mondrian) conformal.** §4.4 — would ship a slice-coverage table known in
  advance to fail.
- **Weighted / adaptive conformal for temporal shift.** Genuinely relevant, and cut: it adds a
  weighting scheme whose own parameters need validation, for a shift whose magnitude has not
  been measured yet. Measure first (§4.6), then revisit.
- **Per-kft training target.** §2.3 — bakes in a false proportionality.
- **Log-target training.** §2.3 — retained as an ablation arm, not a default.
- **Imputing missing design fields.** §1.7 — invents observations.
- **Target / mean encoding of categoricals.** §1.4 exclusion 3.
- **A feature store product.** The feature registry is fifteen columns and a partition scheme;
  a product adds a service to operate on one VM for no gain.
- **MLflow / Weights & Biases.** SB-07 §7 is the registry and the audit stream is the
  experiment log; a second system of record is a second source of truth.
- **Optuna / Bayesian hyperparameter search.** §3.6 — a fixed grid is reproducible by
  construction.
- **Approximate nearest neighbours (faiss, annoy, HNSW).** §6.2 — exact brute force is fast
  enough here and is deterministic.
- **A learned analog metric as the default.** §6.2 — it makes the analog panel a restatement
  of the model rather than an independent view; kept as the OQ-8 comparison arm.
- **Direct multi-horizon monthly models.** §2.2 — incoherent with the cumulative forecast.
- **EUR as a target.** Already excluded by v0.6 §4A.2; restated because it is the most
  commonly requested addition and the answer is standing.
- **Grading only against current actuals.** Defeats DIR-2 and S7; §8.3 emits both bases.

---

## 15. Cut as gold-plating

Designed, then dropped, so the cut is a decision rather than an omission:

1. **The history-conditioned prediction regime** (§1.1) — a second estimand, a second control
   problem, and no consumer in v0.6 §2.2 that DCA does not already serve.
2. **A joint oil/gas/water distribution model** (copula or multi-output) that would license a
   band on GOR and water cut (§2.5). No success criterion asks for it.
3. **A well-specific monthly shape model** (§2.2). The peer-group shape is coherent and its
   error is measured; a per-well shape is a later experiment once the measurement says it
   matters.
4. **Weighted / adaptive conformal under temporal shift** (§14). Measure the shift first.
5. **Learned analog metric as default** (§6.2) — OQ-8 arm only.
6. **Hyperparameter search beyond the fixed grid** (§3.6).
7. **Per-well conditional coverage claims.** Not attainable distribution-free; not claimed.
8. **A model-monitoring dashboard.** The scorecard (C18) and the ledger already carry every
   number one would show, and the failure mode being defended against is silence, not a lack
   of charts (v0.6 §3.7.7).
9. **Automatic retraining on metric degradation** (§10.5) — fits the model to its own ledger
   noise.
10. **A bootstrapped band on the type-curve control.** Defensible, and buys nothing the
    interval score does not already capture.

---

## 16. v0.6 errata

Defects found in `blueprint-v0.6-draft.md` while writing this SB, each with a severity, the
concrete consequence, and proposed amendment text. **Nothing in this document diverges from
v0.6 silently** — where SB-02 makes a choice v0.6 does not license, it is here.

| # | Severity | Section | Defect | Proposed amendment |
|---|---|---|---|---|
| **ER-01** | **MAJOR** | §4A.2 | Targets are "reported both absolute and per 1,000 ft" but the **trained** normalization is never stated. Training per-kft imposes exact proportionality between recovery and lateral length — empirically false, and invisible in per-kft metrics because the metric shares the assumption | Add **4A.2a**: "Models are trained on absolute cumulative volume with lateral length as a feature; per-1,000-ft figures are a post-hoc division of the served absolute value. Per-kft training is prohibited because it imposes a proportionality the data does not support." |
| **ER-02** | **MAJOR** | §3.1 (Modeling row), §8.1 D-1, §4A.7 | Conformal is described as giving "distribution-free coverage guarantees" with no qualifier. The guarantee holds **under exchangeability**, which a temporal holdout violates by construction. Same class of overclaim SB-07 §4.6 corrected for "byte-for-byte", and a DS reviewer tests it first | Amend to: "…conformal calibration, which provides distribution-free coverage **under exchangeability of the calibration and test populations**. Because the holdout is temporal, exchangeability is not assumed: empirical coverage is measured per slice, published with a confidence interval, and a miss is reported as a miss." |
| **ER-03** | **MAJOR** | §4A.3 | Temporal split with no group constraint. Wells from a common pad in a common campaign are near-duplicates; splitting a pad across the boundary leaks **asymmetrically** — ML can exploit it, the type-curve control cannot — inflating the S4 advantage in the one direction that discredits it | Add **4A.3a**: "Wells sharing a pad group (surface holes within 150 m and completions within 180 days, computed in the basin's projected CRS) are assigned wholly to one side of the split. The count of wells reassigned by this rule is reported with every benchmark." |
| **ER-04** | **MAJOR** | §4A.5 + OQ-3 | The control is "the peer-group type curve" but no peer group is pinned, and OQ-3 leaves it open. S4 is therefore not reproducible across runs — and the control is what an adversary attacks first | Add to 4A.5: "The benchmark control's peer group is pinned (formation group × area × lateral-length bucket × 36-month vintage window, min n = 20, with a recorded fallback ladder) and recorded verbatim on the artifact. OQ-3's user-controlled filter set governs the product builder, not the control." |
| **ER-05** | **MAJOR** | §4A.12 vs §7.1 | 4A.12 requires the analog IQR to bracket "at stated rates" — and no rate is stated anywhere — yet P3's exit criterion is "4A.12 green". The gate cannot fire. The correct target is also counterintuitive (an IQR brackets ~50% by construction, so a *high* rate is a failure) and will be got wrong by default | Add: "Target bracket rate 0.50 ± 0.10. Rates materially above target indicate diffuse, uninformative analogs and fail equally. Median IQR width relative to the population IQR is reported alongside, and the check is sliced like calibration." |
| **ER-06** | **MAJOR** | §4A.10 vs §4D.2, §4D.3 | `training_support` must be "on a stated 0–1 scale with its k and metric declared", but v0.6 never states the scale — while 4D.2/4D.3 make it a hard gate on every inventory slot and every scenario. The gate is untestable as written | Pin the default: k = 25, Euclidean on standardized family-weighted features, `support = clip(1 − d̄/d_ref, 0, 1)` with `d_ref` the 90th percentile of training leave-one-out mean k-distance; k, metric and `d_ref` declared per prediction |
| **ER-07** | **MAJOR** | §3.4.4 (`models`, `calibration_sets`) | `models` has singular `quantile` and `target_stream`, so one forecast maps to three rows — yet 4A.13 requires each forecast to cite **a** `model_id`. There is also no schema home for the calibrator's parameters (`calibration_sets` holds the coverage *report*, not per-group `Q_lo`/`Q_hi`), and SB-07 §7 has neither a quantile column nor a calibrator artifact. **A forecast's model citation is ambiguous today** | Introduce a **bundle** identity: one registry row per (stream, horizon), `algo = "cqr_bundle"`, content-addressed over member model ids + calibrator hash + `feature_set_hash` + `conformal_alpha` + taxonomy. Forecasts cite the bundle. Add a calibrator artifact reference to `calibration_sets` |
| **ER-08** | **MODERATE** | §4A.11, §3.6.12 ep. 6, §6.1 | GOR and water cut are "derived surfaces, never targets" with nothing said about their uncertainty. A ratio of independently fitted marginal quantiles has no quantile interpretation, so any band on a GOR forecast would be fabricated — which the anti-story list forbids as firmly as it forbids naked numbers | Add **4A.11a**: "Derived ratio surfaces (GOR, water cut) are served as the ratio of P50 forecasts, labelled `modelled` with `method = derived_ratio`, and carry no band. Historical GOR and water cut computed from actuals are a distinct `observed` object and are never plotted in the same series without a visual break." |
| **ER-09** | **MODERATE** | §4A.4 | Two load-bearing details missing: "producing month" is never defined (days-produced? non-zero volume? shut-in? withheld?), and nothing says whether censored wells may serve as **feature inputs** to other wells. They must — a censored parent still depletes its neighbours — and the omission invites dropping them, silently understating depletion for the newest infill wells | Add the producing-month definition (§2.2 here) and: "Censored wells are excluded as training labels and retained as feature inputs to other wells, as type-curve members up to their last producing month, and in the reported denominator." |
| **ER-10** | **MODERATE** | §7.1 P7 exit vs §7.3 | §7.3 maps S4 to "P3 (ND), P7 (Permian)", but P7's exit criteria list S6, S8, U13, U21, quarantine rate, oil-lease share and the NM-ordering validation — **not S4**. The Permian benchmark has no exit gate, so the criterion that legitimizes every Permian accuracy claim can be skipped without failing a phase | Add "S4 artifact for the Permian, sliced, with the type-curve control on the identical split" to P7's exit criteria |
| **ER-11** | **MODERATE** | §2.4 vs §7.4 | E14 (transfer) is **first in the cut order**, while F7 ("whether a model transfers and precisely what breaks") sits among the fluency outcomes with no conditionality — though §2.4 went to the trouble of making S12 explicitly conditional on E17. Cutting E14 silently forfeits F7 and answers §1.2 Q7 with nothing | Extend §2.4's conditionality clause: "F7 is conditional on E14 surviving the cut order. If E14 is cut, the E16 capability matrix records basin transfer as *effort-unreachable* with the cut decision cited." |
| **ER-12** | **MODERATE** | §3.7.8 vs §4C.5 | "Three-stream model training < 20 min" sits alongside a `byte_exact` requirement pinning `num_threads=1`, `deterministic=true`, `force_row_wise=true`. Single-threaded training across 3 streams × 2 horizons × 3 quantiles × 4 rolling origins, plus calibration and two league expectation models, is plausibly over budget — and neither clause references the other | Either widen the budget with the determinism cost stated, or record that model artifacts are **D2 with a pinned thread count** (which SB-07 §4.2 already specifies) rather than D1 single-threaded. Make `training_wall_clock_by_config` a P3 exit deliverable so the resolution is evidence-based |
| **ER-13** | **MINOR** | §3.3 R5 vs §4A.9 vs SB-07 §9.1 | Three `granularity` vocabularies coexist: R5's `observed \| allocated \| modelled \| assumed`; 4A.9's `extrapolated` used as though it were a granularity; SB-07 §9.1's `well_observed \| lease_allocated`. A field with three vocabularies cannot be CI-checked, and the naked-number harness checks this field | Adopt R5's four-value enum as the single `granularity` vocabulary; record SB-07 §9.1's pair as its production-figure **subset**; move `extrapolated` to a separate `method` field alongside `derived_ratio` |
| **ER-14** | **MINOR** | §4A, §8.1 D-17 | D-17's league expectation models serve numbers through endpoint 22, so 4A.13 applies — but §4A never mentions them, so nothing binds them to the split, censoring, leakage or calibration protocol they must obey | Add to 4A.13: "Expectation models used for residual metrics are models under this protocol: same split, same censoring, same leakage constraints, registered, and cited by `model_id` on every league row." |
| **ER-15** | **MINOR** | §2.4 S7 | "One graded cycle complete" is never defined — no cohort size, no completeness condition — so P8's exit gate is unfalsifiable | Define: "≥ 100 entries published at a single `as_of_vintage`, all matured to the horizon and graded, with both grade bases emitted, the coverage CI computed, and the restatement-drift decomposition published." |

**Consolidated ask of SB-00.** ER-01 through ER-07 are change-controlled (v0.6 §10 covers §4
protocols and §3.x) and should land **before P3 opens**: each is either a gate that cannot
fire, a gate that would fire on the wrong number, or — ER-07 — a schema ambiguity that blocks
the first forecast that has to cite a model. ER-08 through ER-15 are corrections that can
travel with the next consolidation pass.

---

## 17. Open items handed back

| Item | Owner | Why it is not decided here |
|---|---|---|
| Ratify the fifteen errata in §16; add the DIR-8 glossary rows from §13 | SB-00 | §4 protocols are change-controlled (v0.6 §10) |
| Whether `NDOGD_Surveys` carries station-level MD/INC/AZI or headers only (`ad:97`) | SB-01, **before P3 feature work** | Decides whether ND gets `landing_tvd_ft` and `structural_residual_ft` at all |
| OQ-2: whether NDIC Premium tops ($500/yr) are bought | Owner, after the §7.6 `with_tops` ablation | The ablation is the input to the decision; the decision is not SB-02's |
| OQ-1: when cum24 joins cum12 as a headline | SB-02 + owner, after P3 | Depends on measured ND history depth at the rolling origins |
| OQ-7: final confidential / withheld policy | SB-02, after `withheld_share_by_completion_cohort` is measured in P3 | The interim policy is stated (§2.6); the final one needs the number |
| OQ-4: which parent-child encoding wins | SB-02, from the §7.6 ablation arms | Answered by the harness, not by argument |
| OQ-8: Euclidean versus learned analog metric | SB-02, once E3 is stable | Comparison arm designed (§6.2); result pending |
| Per-basin reporting lags used in `holdout_def` | SB-01 | Ingest cadence is SB-01/SB-06 (v0.6 §3.7.4) |
| Whether `ledger_restatement_drift` is published on the scorecard | E11 / SB-04 | SB-02 computes it and accepts ownership (§8.3); placement is the scorecard's |
| TX allocated-label training experiment | SB-02, after 4F.5 error bounds exist | Blocked on the allocation study (v0.6 §4F.4) |
| Whether E14 survives the cut order | Owner | v0.6 §7.4; §9.5 states what must be recorded either way |
