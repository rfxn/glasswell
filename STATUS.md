# Current status

Reconciled on **2026-08-26** against the v0.50 release line, the checked-in OpenAPI
snapshot, and current `main` history. This is the short current-state ledger;
[`ROADMAP.md`](ROADMAP.md) owns phase scope and exit criteria, while
[`blueprint.md`](blueprint.md) remains the committed v0.5 contract and
[`blueprint-v0.6-draft.md`](blueprint-v0.6-draft.md) is the rc4 amendment set.

## Shipped baseline

- **Release line:** 32 tagged releases, v0.20 through v0.51, cut 2026-08-21 through
  2026-08-26.
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
  are on the map. Lease production, well allocation, and its validators are not built.
- **New Mexico:** ingest and promotion code exist, but promotion remains deployment- and
  owner-gated; no resident NM production is claimed here.
- **Serving surface:** the frozen v1 snapshot contains 30 operations covering health,
  wells, ND production, lineage, manifests, conformance, quarantine, glossary, keys, and
  tiles. Forecast, valuation, scenario, agent, and inventory operations are not served.
- **Frontend:** MapLibre map, ND/TX layers, well card, production chart, lineage drawer,
  glossary, explorer, satellite/hybrid modes, and searchable layer panel are shipped.

## Phase ledger

| Phase | Status | Remaining boundary |
|-------|--------|--------------------|
| **P0** Scaffold and contracts | Met | `/v1/audit` is not served, but is not a P0 exit requirement |
| **P1** ND spine | Met with named deferrals | PDF-era production and FracFocus chemistry remain absent; the disclosure-header anchor path is built |
| **P2** Serving and map | Substantially met | Missing completions, neighbours, permits, land/spacing units and formations routes; no GOR/water-cut card |
| **P3** Forecasting and benchmark | Data seam resident; first matrix pending | The `fv1.0` declaration and two-clock D1 materializer are built. The 2026-08-26 resident load assigns all 43,817 ND wells to Williston and preserves 18,665 valid FracFocus events across 17,563 API-10s; 26,254 uncovered wells remain explicitly null. Single-pool completion observations and 40 reviewed formation aliases are resident. The first live matrix, type-curve control, models, calibration, model-registry writer, analog index, and harness remain |
| **P4** Dollars and scenarios | Not started | Entire phase |
| **P5** Intelligence, agents and alerts | Not started | Entire phase |
| **P6** Hardening and glass-box proof | Partial | Tunnel/Access, outsider guest exercise, live restore drill, determinism and tool-equivalence gates |
| **P7** Permian | Started, unpromoted/incomplete | NM deployment; TX production, allocation, and validators |
| **P8** Living systems | Not started | Entire phase |

## Immediate gaps

1. Materialize the first live `fv1.0` matrix, publish coverage and missingness, then
   implement the type-curve control before model code.
2. Close the highest-value P2 serving gaps or explicitly defer them before adding another
   UI surface.
3. Prove P6 operationally: execute and record the restore drill, then exercise a
   non-interactive guest path with an outsider.
4. Promote New Mexico before implementing Texas lease allocation so the well-level
   Permian spine can act as the intended control.
5. Resolve the owner-gated v0.6 §11 review and public IP carve-out decision separately
   from implementation work.

## Verification state

- The full locked Python suite passes **2,448 tests with 2 explicit skips**, including the
  Docker-backed integration and contract tiers; Ruff passes.
- The web suite passes **1,149 tests across 77 files**; typecheck and production build pass.
- Browserless E2E guards, shell checks, collateral checks, changelog lint, and the
  35-assertion headless-Chromium map-chrome gate pass locally.
- The dependency lock exactly matches the installed environment and the generated OpenAPI
  snapshot reports current.
- Hosted pre-release `main` CI run `32779964976` passed all six jobs on 2026-08-24 at
  merge commit `9fe2712`, before the v0.48 train added four release and deterministic-fixture
  tests: 2,430 passed, 2 explicitly skipped, and zero annotations.
