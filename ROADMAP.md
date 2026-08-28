# Roadmap

Nine phases, each exiting on a stated criterion rather than on a feeling. The cut
order under compression is decided in advance, and some things are never cut.

<p align="center"><img src="assets/roadmap.svg" alt="Build phases P0 through P8 with exit criteria, the pre-committed cut order, and the never-cut list" width="1000"></p>

The phase model here is the nine-phase P0–P8 set in
[`blueprint-v0.6-draft.md`](blueprint-v0.6-draft.md) §7. [`blueprint.md`](blueprint.md)
is still the committed contract at v0.5 and still carries the earlier eight-phase
numbering; its §10 governs when that changes.

## Where it stands

41 tagged releases, v0.20 through v0.60, cut from 2026-08-21 through 2026-08-28, run
the North Dakota production slice and North Dakota/Texas map on one VM. The concise
evidence ledger is [`STATUS.md`](STATUS.md); status here is per phase and stated against
the exit criteria below, not against a feeling of progress:

| Phase | Where it stands |
|-------|-----------------|
| **P0** Scaffold and contracts | **Met.** Envelope and error model frozen and contract-tested; OpenAPI snapshot committed with a diff test; naked-number and glossary-coverage checks blocking; `lineage.audit_events` append-only as enforced, by grant and by trigger; registry and glossary seeded with evidence and served. No `/v1/audit` read endpoint yet, which P0's exit does not ask for |
| **P1** ND spine | **Met with named deferrals.** Ingest, promotion with conformance references and bitemporal vintages, and a live quarantine with a measured share, across the monthly production report, DMR GIS layers and PLSS grid. The 125-workbook XLSX back-load is complete: canonical holds 131 distinct months from 2015-05-01 and 7,223,544 rows. The PDF era remains deferred by design. FracFocus disclosure-header ingest now supplies P3 completion anchors; chemistry remains unparsed |
| **P2** Serving and map | **Substantially met.** Thirty-four snapshot-pinned operations, thirty-three under `/v1`; tiles from PostGIS with the layer allowlist asserted in CI; URL-backed Map, Explore, and Status surfaces; well card, lineage drawer and glossary tooltip shipped; the frame-rate budget codified in the perf harness. Source-observed completion events, pool-to-formation mappings and current ND physical neighbours are separate API/card sections. Neighbours use current lateral geometry, strict earlier-completion cutoffs, exact query lineage and an explicit non-analog warning; retrospective geometry is unavailable rather than inferred. Completion-design measurements remain unpromoted. Permits, land units, spacing units, GOR and water-cut remain |
| **P3** Forecasting and benchmark | **Pinned control accepted; modeling remains.** Publication `p3pub_8b434525d8c621762e31b06ca660bfcd` advances the evaluation vintage to 2026-08-28 without changing `fv2.0`, `mdv1.4`, `tcv1.0`, or split set `sset_c7bbb9a6932db76b`. Two full builds reproduce all eight artifacts and all eight split files byte-identically; an independent read rehashes every file against the receipt. Control unavailability is 1.0798% (230 / 21,300), below the 5% ceiling, with source-absent laterals retained rather than inferred. No model, calibration, persisted analog index or benchmark runner exists, and the model registry remains DDL with no writer |
| **P4** Dollars and scenarios | **Not started.** No deck, DCF, breakeven, payout or scenario loop. `econ.value` and `econ.sensitivity` exist in the derivation-kind vocabulary and nothing emits them |
| **P5** Intelligence, agents and alerts | **Not started.** No agent gateway and no curated tool surface; no league table, AOIs or digests; `lineage.forecast_grades` is DDL with no writer |
| **P6** Hardening and glass-box proof | **Partial.** Six CI jobs are branch-protection-required — `python`, `web`, `e2e-guards`, `shell`, `collateral`, `map-chrome` — with the tile allowlist asserted and conformance exercised end to end. Deployed `v0.60+be8e234` at schema head 51 adds independently committed source-poll outcomes aligned to actual recurring timers, nine fail-closed selector-output contracts, two-clock conformance, a bounded viewport rate window, and a sandboxed nightly retention unit; release CI, 111 host checks and 20 API smoke checks pass. Fetch-attempt history begins empty until each source next polls. The recurring logical restore has passed against the latest schema-47 backup with exact critical counts, six reads, durable evidence and scratch cleanup; schema 51 has not yet reached that scheduled proof. Full VM/raw-zone recovery remains open, as do broader rate policy, remote-copy evidence, tunnel/Access, outsider guest exercise, broader determinism and tool-equivalence gates |
| **P7** Permian — NM first, then TX | **Started, unpromoted.** NM ingest and promotion code exist and the sources are registered, but no NM row is resident — they read `pending` until the promotion deploy. TX carries wells and wellbore identity on the map. TX lease production, allocation v0 and its two validators are unbuilt P7b scope |
| **P8** Living systems | **Not started.** |

## Phases

| Phase | Contents | Exit criteria |
|-------|----------|---------------|
| **P0** Scaffold and contracts | Repo layout with the staging / canonical / marts split; derivation capture written before the first transform, not retrofitted after it; DDL for manifests, fetch log, quarantine, derivations, recipes, audit events, `conformance_rules`, `crs_registry`, `glossary_terms` and `land_units`; registry seeded from evidence already in hand — datum and CRS transforms, per-basin compute CRS, the liquids policy of oil plus condensate, API-number formatting, unit policy; API skeleton with the envelope, error model, pagination, `as_of` and an auth stub | Audit stream live and append-only as enforced — grants revoked, trigger behind them, one writing role; first conformance and glossary rows committed with evidence URLs; envelope and error model frozen; a trivial endpoint passes the naked-number and glossary-coverage checks; one recipe replays byte-identical |
| **P1** ND spine | The identity question first — whether the free monthly production report keys on API-10 or only on the state file number, and the crosswalk built before anything else if it does not; fetchers on the free NDIC and DMR GIS paths, with no subscription on the critical path; XLSX, shapefile and file-geodatabase parsers; staging load with quarantine live; promotion to canonical with conformance references and bitemporal vintages; PostGIS load of well points, laterals, PLSS sections and townships, spacing units and pre-spud permits; FracFocus completion design. The PDF era, 2003-01 → 2015-04, is deferred inside this phase | Every ND production row explains to a manifest and cites the rules that shaped it; the identity decision is a committed conformance rule with its evidence; the quarantine path is exercised by an injected fixture and its share is measured, whatever it turns out to be — exiting on a non-zero share would reward manufacturing rejects; re-fetching an unchanged file is a logged no-op; a synthetic restatement produces a new vintage without touching prior rows |
| **P2** Serving and map | API v1 over wells, production, completions, neighbours, permits, land units, spacing units, formations, manifests, conformance, quarantine and glossary; geometry tiles from PostGIS behind the tile proxy, with attribute bundles joined client-side; map application, well card with GOR and water-cut charts, the lineage drawer, and the glossary tooltip component | 20k+ laterals at interactive frame rates; the glass box demonstrated on a served production number; glossary coverage for the surfaces that exist; the tile-layer allowlist checked in, with CI asserting the served source list equals it; every UI figure has a reproducing endpoint |
| **P3** Forecasting and benchmark | Entry is the production back-load, without which not one rolling origin is reachable. The v0.6-rc4 amendment resolves the old arithmetic: 2015-05 → 2025-09 is 125 monthly workbooks and 336.6 MB measured; all 125 landed, leaving 131 distinct canonical months from 2015-05-01 and meeting the entry gate. Feature builder with declared availability dates; type-curve baseline; three-stream gradient-boosted quantile models; split-conformal calibration; model registry; persisted analog index; benchmark harness | Entry gate: ≥ 120 distinct production months in canonical with the earliest at or before 2016-01. Then calibration green and the analog check measured against its bracket rather than asserted — an inconclusive interval blocks exit exactly as a failure does; the pinned type-curve control on the identical split; per-slice empirical coverage published with its interval; the determinism check green; every forecast citing a registered artifact, and no number served from an unregistered one |
| **P4** Dollars and scenarios | Decks and assumptions with water opex and per-state tax defaults; DCF, breakeven and payout; sensitivities and tornado; the scenario loop; type-curve builder in the UI; analog panel on the scenario card | A scenario returns forecast plus NPV in under three seconds; the type-curve builder is live; the tornado is hand-checked directionally; every valuation reports P10, P50 and P90 together |
| **P5** Intelligence, agents and alerts | Activity surfaces and the DUC proxy; operator league table on the residual metric, with operator aliasing and a stated rollup mode; areas of interest and weekly digests; well sets and rollups; agent gateway over curated tools; the forecast ledger starts writing | The ten-question suite passes through the public tools; the tool-equivalence report is clean; an AOI digest is correct against a manual diff, with its freshness window stated |
| **P6** Hardening and glass-box proof | Naked-number, glossary-coverage, tile-allowlist, conformance, contract, tool-equivalence and determinism checks all wired and blocking; determinism pinning across the artifact path; tunnel and Access with all three scopes and a non-interactive guest-key class; the two-user database split landed before the first guest key; rate limits; backup and a live restore drill; observability and the weekly self-report; non-functional budgets converted to tests | A stranger with a guest key reproduces every number in the UI; the restore drill completed from backup to a working system; the glass-box, performance, scenario, agent, conformance, glossary and as-of criteria all green |
| **P7** Permian — NM first, then TX | **NM first.** OCD fetch with address re-resolution; XML full-table parsers; production, well and completion history, spacing units and the well-completion crosswalk; change detection; a well-level Permian spine, which is the allocation variable removed. **Then TX.** RRC identifier resolution with rotation monitoring; lease production and the in-dump well-to-lease crosswalk; the wellbore master; completion feed and permits, incremental; county GIS layers with the NAD27 transform recorded as a derivation; allocation v0 with both validators; abstracts loaded as land units. TX directional survey stations stay out — see the two reasons under **Out of scope** | Allocation error bounds published from both validators; the quality scorecard published; the Texas user stories passing on TX data; quarantine rate reported by basin against the per-basin trigger; the oil-lease share of allocation measured and published; a Permian benchmark artifact, sliced, against the type-curve control on the identical split; the NM-before-TX ordering validated — the well-level spine de-confounded the allocation error measurement, or it is documented why it did not |
| **P8** Living systems | One graded forecast-ledger cycle, bounded by elapsed time; inventory v0, ND-scoped — geometrically admissible undrilled locations at an assumed spacing, each carrying a training-support score, and never reserves; basin transfer as a stretch; capability matrix with attribution checked; the notebook write-up and the fluency outcomes; publish decision against IP-carve-out status | One graded cycle complete, the capability matrix published, and the township inventory demo recorded (conditional); every honest gap tagged `data-unreachable` or `effort-unreachable`; the publish decision recorded either way |

Epics E1–E16 and user stories U1–U15 are defined in blueprint v0.4 §5 and §6; the
v0.5 amendments, E17 (inventory) and U16–U21 are in [`blueprint.md`](blueprint.md)
§5 and §6; E18 (glossary-as-data) and U22 are new in
[`blueprint-v0.6-draft.md`](blueprint-v0.6-draft.md) §5 and §6.

## Timebox

Rough, and deliberately stated in weekends rather than sprints, at 12–16 productive
hours per weekend, solo:

| Phase | Weekends | Note |
|-------|----------|------|
| P0 Scaffold and contracts | 2 | Higher than instinct: derivation capture and the envelope are contracts, and contracts frozen late are the most reliable source of rework |
| P1 ND spine | 4 | Six source families, three file formats, bitemporal promotion, quarantine |
| P2 Serving and map | 4 | Tiles, attribute bundles, card, drawer and the whole glossary system, plus the tuning loop against the frame-rate budget |
| P3 Forecasting and benchmark | 4 | Features, three streams, conformal calibration, registry, harness, determinism |
| P4 Dollars and scenarios | 3 | |
| P5 Intelligence, agents and alerts | 3 | The agent suite is the long pole, not the league table |
| P6 Hardening and glass-box proof | 3 | Seven checks, three scopes, a real restore drill |
| P7 Permian (NM 2, TX 4) | 6 | TX carries the heaviest parse work in the project |
| P8 Living systems | 3 + elapsed | The graded cycle is bounded by calendar time, not effort |
| **Total** | **~32 weekends** | About seven to eight months of weekends |

The earlier estimate — roughly 17 to 19 weekends — did not survive inspection. The
same span had to carry ND ingest across six source families, promotion, PostGIS,
tiles and a map UI, three-stream models with conformal calibration, a benchmark
harness, analogs, economics, scenarios, a builder UI, alerting, the ledger write
path and an agent gateway, plus hardening. The increase is not scope creep: it is
the cost of what the earlier figure assumed rather than budgeted — capture written
first, bitemporal ingest, determinism pinning, seven checks, an auth model, a
restore drill, and the honest parse cost of delimited, XML, fixed-width and
text-layer formats. It is better for the number to be bigger and true.

## Traceability

Every success criterion maps to at least one epic and to the phase that proves it:

| Criterion | Epics | Proven in |
|-----------|-------|-----------|
| S1 stranger reproduces every number | E9, E10 | P6 |
| S2 20k+ laterals at frame rate | E7 | P2, re-verified P6 |
| S3 scenario under three seconds | E6 | P4 |
| S4 benchmark artifact per basin | E4 | P3 (ND), P7 (Permian) |
| S5 agent ten-question suite | E9 | P5, re-verified P6 |
| S6 allocation with both validators | E12 | P7, Texas half |
| S7 ledger with a graded cycle | E13 | P8 |
| S8 quality scorecard published | E11 | P7 |
| S9 glass box holds | E10 | P2 first proof, P6 full |
| S10 capability matrix | E16 | P8 |
| S11 conformance registry served | E11 | P6 |
| S12 inventory demo *(conditional)* | E17 | P8 |
| S13 glossary coverage | E18 | P2 partial, P6 full |
| S14 as-of reproducibility | E1, E10 | P6 |
| F1–F11 fluency | E15 | Continuous, written up in P8 |

## Cut order under compression

First cut on the left:

**E14 transfer → inventory (E17) → alerts and league table → activity (E8) →
map-UI polish (E7) → field-notes UI**

The memos still get written when the last one goes; only the reader is cut.
Deciding this in advance is what stops a schedule slip from quietly eating the
load-bearing work.

### Never cut

- **E1** and **E2** — the ingest and canonical spine. There is no product without it.
- **E4** — the benchmark. It is the control group; without it every accuracy claim is marketing.
- **E5** — economics. Without dollars there is no loop.
- **E10** and **E11** — glass-box lineage and quality. They are the thesis.
- **E12 validators** — the allocation error bounds. Allocation without measured error is a guess with a decimal point.
- **Derivation capture** — retrofitting lineage is not a thing that happens.
- **The conformance registry** — cheap, and load-bearing. Without it, no cross-source number can cite the rules that shaped it.
- **E18's glossary** — cheap, load-bearing for coverage, and the only thing that makes the teaching claim concrete rather than aspirational.

Cutting E17 forfeits the inventory demo, which is already conditional. Nothing else
in the cut order costs a success criterion.

## Deferred until after P8

Canada · NGL three-stream economics beyond simple gas pricing · fault-aware
geology · additional basins · TX inventory geometry · a public hosted demo and capability
matrix (IP-gated, see [`blueprint.md`](blueprint.md) §8.2). The source repository is public;
its proprietary license and data-redistribution limits are unchanged.

## Out of scope

Not deferred — out, until the blueprint changes:

Mineral ownership and title · daily production · multi-tenant SaaS auth
(single-tenant key auth is in) · distributed infrastructure · mobile · lineage
ontology platform · rig and frac-crew tracking (a documented moat item) ·
interpreted maturity mapping (moat item) · news and research layer.

**TX directional survey station data** is out for two different reasons, and they
are not one reason: filings before 2021-01-01 are `data-unreachable` — scanned
images with no free machine-readable index over them — and filings from that date
are `effort-unreachable` — reachable nightly, but behind per-well vendor-format PDF
parsing. Anything ever built on them states its coverage start.

## Open questions

Carried forward, to be resolved with evidence rather than preference:

1. **Headline target horizon** — cum12, cum24, or an EUR-style extrapolation? Start with cum12 oil: data-supported for recent vintages, and a short feedback loop for the ledger. EUR stays out of the target set.
2. **Feature-set boundary** — how much geology against design and location alone? Bulk ND tops are paywalled while TX formation data ships free, so the honest start is design-plus-location with geology as an ablation.
3. **Bulk formation tops behind the paid ND tier** — owner-parked, and worth buying only if that ablation shows geology carries real lift. Bounded to a one-time bulk pull if it ever happens.
4. **Type-curve peer-group definition** — geography, formation, vintage window, operator, or a learned neighbourhood? Start with an explicit filter set the user controls, which is also the builder UI. This governs the product builder only: the benchmark control's peer group is pinned, because a control that moves between runs is not a control.
5. **Parent-child depletion encoding** — offset count within a radius, time-weighted cumulative production, or a distance-decayed pressure proxy? All three are computable; the choice needs an ablation, and it is likely the highest-value feature family in the Bakken.
6. **Extrapolation form** — an interpretable decline form that imposes assumptions, or direct multi-horizon models that make fewer but extrapolate worse? Currently the former; revisit with ledger evidence.
7. **Price deck source and default** — no free, redistributable forward strip is in hand. Currently a flat default deck with its provenance stated. This one is an honest gap, and it belongs in the capability matrix tagged `data-unreachable`.
8. **Confidential and tight-hole handling** — exclude, censor, or impute? Currently censored, but the confidential period systematically hides new wells, which is exactly the population inventory and scenarios care about.
9. **Analog distance metric** — plain Euclidean on standardised features, or learned? Start Euclidean; compare once forecasting is stable.
10. **Inventory spacing assumption** — a single user input, or per-operator inferred from recent development? Start with user input; inferred spacing is a P8 experiment.
11. **TX inventory geometry** — with no PLSS, what is the unit: the operator's unit polygon, the lease, the abstract, or a synthetic grid? The land-unit abstraction keeps this a design question rather than a migration.
12. **Attribute-bundle size ceiling** — the client-side join is measured at ND scale and the Permian is an order of magnitude larger. The declared feature cap turns this into an instrument that fires on real traffic rather than a measurement someone must remember to take.
13. **Rule-change re-promotion cost** — at what rule-change frequency does re-vintaging become the dominant compute cost, and does a rule change ever justify a rebuild instead?

Two further questions — league-table normalisation, and whether upstream bandwidth
would carry a public demo — are closed, and are kept on the record in
[`blueprint-v0.6-draft.md`](blueprint-v0.6-draft.md) §8.3 rather than deleted, so
their resolution stays traceable.

## Known risks

| Risk | Mitigation |
|------|------------|
| **IP carve-out** (top item, time-sensitive) | The source repository became public on 2026-08-28 under its existing proprietary license. That does not publish the hosted app, regulator artifacts, capability matrix or vendor-comparison corpus; those remain separately gated before a public URL or matrix row |
| **Source redistribution rights** — a different legal question from competitor IP, and easy to conflate with it | Per-source licence status tracked with evidence URLs, and the absence of an affirmative grant recorded honestly rather than assumed; a per-source re-read gates any public artifact. The exposure is live, not theoretical: one RRC field, the coordinate-source provenance, is already withheld pending an open licence question while the rest of the TX stack is served. It is a review item over that stack, and it is not the reason any particular dataset is unbuilt |
| **Solo-builder bandwidth** — ~32 weekends is a long single-threaded run | The cut order is pre-decided, so compression is a lookup rather than a negotiation; phases are ordered so each ends with something demonstrable |
| **Source access drift** — identifiers rotate without notice, page structure changes | Identifier resolution is a monitored step; every poll writes an independently committed attempt before network access and finalizes as new, unchanged or failed only after manifest visibility. Status applies the registered source cadence, and one failed/open source key cannot be hidden by another key's success |
| **Conformance registry rot** — rules drift from code and the registry becomes decoration | Three rule kinds plus coverage, execution and binding checks; the documented share is itself a tracked scorecard metric |
| **Datum mishandling** — silent ~100 m position errors corrupt spacing and inventory | Datum rules per file vintage; the CRS service is the only transform path; a fixed set of TX wells with published positions asserted in CI |
| **Public-data quality bias** — withheld wells, trade-secret fields, missing quantities | Withheld is a distinct state, never collapsed to missing; the share is a scorecard metric and its own censoring class in the model |
| **Allocation error too large to be useful** | Measure early on the Texas half and report the oil-lease share; if the bounds are wide, ship them wide and say so — a labelled bad number is content, an unlabelled one is a defect |
| **Single VM, irreplaceable raw zone** | Nightly and weekly off-box copies, and a live restore drill as a P6 exit item |
| **Glass-box tax collapses velocity** | Capture is a decorator and a context manager, not a per-call-site chore, and it is built in P0 so the cost is paid once. If it does slow the build, that measurement is itself an answer worth writing up |
| **Harvest scope creep** — small features quietly become medium ones | Each harvested feature is capped at its stated acceptance; anything beyond it is a new blueprint version |
| **Inventory misuse** — slot counts read as reserves | The 4D statements are mandatory in every rollup, response and export |

---

> Copyright (C) 2026 Ryan MacDonald &lt;ryan@rfxn.com&gt; &#183; All rights reserved
