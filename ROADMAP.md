# Roadmap

Eight phases, each exiting on a stated criterion rather than on a feeling. The cut
order under compression is decided in advance, and some things are never cut.

<p align="center"><img src="assets/roadmap.svg" alt="Build phases P0 through P7 with exit criteria, the pre-committed cut order, and the never-cut list" width="1000"></p>

**Current status: pre-build.** Nothing in P0 has started. This repository holds the
blueprint and the collateral derived from it.

## Phases

| Phase | Contents | Exit criteria |
|-------|----------|---------------|
| **P0** Scaffold | Repo layout with the staging / canonical / marts split; audit stream and derivation plumbing; `conformance_rules` and `crs_registry` schema | Audit stream live; first conformance rows committed — datum, CRS, liquids policy |
| **P1** ND spine and map | ND ingest; parsers write staging; promotion step emits conformance references; vector-tile map | Every production row explains to a manifest and cites the rules that shaped it |
| **P2** Forecasts and benchmark | Quantile model with conformal calibration; three-stream targets; analog index; type curve as the control group | 4A.11 and 4A.12 green for ND — calibration holds, analog check passes |
| **P3** Dollars and scenarios | DCF economics at a named deck; tornado sensitivities; analog panel on the scenario card; type-curve builder in the UI | U17 and U18 pass; builder live; a scenario returns forecast plus NPV in under three seconds |
| **P4** Intelligence and agents | Operator league table; AOI alerts; agent gateway over curated tools; forecast ledger starts writing | U16 passes; the agent passes the ten-question suite with every figure traceable |
| **P5** Hardening | Naked-number CI across every endpoint, with `/conformance` inside its scope; performance work at 20k+ laterals | S1–S5, S9 and S11 green |
| **P6** Permian | TX RRC and NM OCD ingest; allocation v0 with two validators; datum transforms recorded as derivations; OSDU mapping memo | S6 and S8; U13 and U21 pass on TX data; a TX spacing value explains through its datum transform |
| **P7** Living systems | One graded forecast-ledger cycle; inventory v0; capability matrix | S7, S10 and S12; township inventory demo recorded; publish decision taken against IP status |

Epics E1–E16 and user stories U1–U15 are defined in blueprint v0.4 §5 and §6; the
v0.5 amendments and the new E17 (inventory) and U16–U21 are in
[`blueprint.md`](blueprint.md) §5 and §6.

## Timebox

Rough, and deliberately stated in weekends rather than sprints:

| Span | Estimate |
|------|----------|
| P1–P5 | ~10–11 focused weekends (the v0.5 feature harvest adds one to two) |
| P6 | 3–4 |
| P7 | 2, plus waiting for actuals to grade the ledger cycle |

## Cut order under compression

First cut on the left:

**E14 → inventory (E17) → alerts and league table → activity (E8) → map-UI polish (E7) → field-notes UI**

Deciding this in advance is what stops a schedule slip from quietly eating the
load-bearing work.

### Never cut

- **E4** and **E5** — forecasting and economics. Without dollars there is no loop.
- **E11** — the quality scorecard. An unmeasured system cannot make an honest claim.
- **E12 validators** — the allocation error bounds. Allocation without measured error is a guess with a decimal point.
- **Derivation capture** — retrofitting lineage is not a thing that happens.
- **The conformance registry** — cheap, and load-bearing for S11. Without it, no cross-source number can cite the rules that shaped it.

## Deferred until after P6

Canada · NGL three-stream economics beyond simple gas pricing · fault-aware
geology · additional basins · public release (IP-gated, see
[`blueprint.md`](blueprint.md) §8.2).

## Out of scope

Not deferred — out, until the blueprint changes:

Mineral ownership · daily production · multi-tenant auth (design only) ·
distributed infrastructure · mobile · lineage ontology · rig and frac-crew tracking
(a documented moat item) · interpreted maturity mapping (moat item) · news and
research layer.

## Open questions

Carried forward, to be resolved with evidence rather than preference:

1. **Analog distance metric** — plain Euclidean on standardised features, or learned (model leaf co-occurrence)? Start Euclidean; compare once E3 is stable.
2. **Inventory spacing assumption** — single user input, or per-operator inferred from recent development? Start with user input; inferred spacing is a P7 experiment.
3. **League table normalisation** — cum12 per 1,000 ft alone, or a residual metric (actual minus model expectation) that adjusts for rock quality? The residual version is more honest and more interesting; decide after E3.

Items 1–7 from blueprint v0.4 §8.3 also remain open.

## Known risks

| Risk | Mitigation |
|------|------------|
| **IP carve-out** (top item, time-sensitive) | Public release stays gated until resolved; positioning language is reviewed before anything goes public |
| **Conformance registry rot** — rules drift from code and the registry becomes decoration | The promotion step reads rules from the table at run time where feasible; CI asserts every canonical field maps to at least one rule |
| **Datum mishandling** — silent 100 m position errors corrupt spacing and inventory | Datum rules per file vintage; a fixed test set of known TX wells with published NAD83 positions asserted in CI |
| **Harvest scope creep** — seven small features quietly become seven medium ones | Each harvested feature is capped at its stated acceptance; anything beyond it is a new blueprint version |
| **Inventory misuse** — slot counts read as reserves | 4D statements mandatory in every rollup and every export |

---

> Copyright (C) 2026 Ryan MacDonald &lt;ryan@rfxn.com&gt; &#183; All rights reserved
