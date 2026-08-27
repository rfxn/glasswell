# Current status

Reconciled on **2026-08-26** against the v0.54 release line, the checked-in OpenAPI
snapshot, and current `main` history. This is the short current-state ledger;
[`ROADMAP.md`](ROADMAP.md) owns phase scope and exit criteria, while
[`blueprint.md`](blueprint.md) remains the committed v0.5 contract and
[`blueprint-v0.6-draft.md`](blueprint-v0.6-draft.md) is the rc4 amendment set.

## Shipped baseline

- **Release line:** 35 tagged releases, v0.20 through v0.54, cut 2026-08-21 through
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
- **Serving surface:** the frozen v1 snapshot contains 32 operations covering health,
  wells, ND production, source-observed completion context, canonical formations with alias
  counts, lineage, manifests, conformance, quarantine, glossary, keys, and tiles. Forecast,
  valuation, scenario, agent, and inventory operations are not served.
- **Frontend:** MapLibre map, ND/TX layers, well card with independent completion-event and
  pool-to-formation sections, production chart, lineage drawer, glossary, explorer,
  satellite/hybrid modes, and searchable layer panel are shipped.

## Phase ledger

| Phase | Status | Remaining boundary |
|-------|--------|--------------------|
| **P0** Scaffold and contracts | Met | `/v1/audit` is not served, but is not a P0 exit requirement |
| **P1** ND spine | Met with named deferrals | PDF-era production and FracFocus chemistry remain absent; the disclosure-header anchor path is built |
| **P2** Serving and map | Substantially met | Completion context and formations are served and visible on the card, without pretending staging-only design measurements or formation tops are canonical. Neighbours, permits, land/spacing units, GOR and water-cut remain |
| **P3** Forecasting and benchmark | Pinned control built; resident gate red, repair rehearsal green | Immutable `fv1.0`, semantic-major `fv2.0`, `mdv1.4`, and control-major `tcv1.0` remain separate identities. The immutable resident artifact still records 12.9484% unavailability. A rollback-only migration rehearsal restored all 318 TEST formation gaps through same-manifest source rows, left the 38 source-absent laterals uninferred, replayed unchanged `tcv1.0` byte-identically on all eight exact split hashes, and measured 230 / 21,300 unavailable instances (1.0798%). A new-vintage live artifact is not yet published. Models, calibration, the model-registry writer, analog index, and harness remain |
| **P4** Dollars and scenarios | Not started | Entire phase |
| **P5** Intelligence, agents and alerts | Not started | Entire phase |
| **P6** Hardening and glass-box proof | Partial | Enforce selector identity/cardinality in `/explain`; add independent knowledge-publication time to conformance rules; tunnel/Access, outsider guest exercise, live restore drill, determinism and tool-equivalence gates |
| **P7** Permian | Started, unpromoted/incomplete | NM deployment; TX production, allocation, and validators |
| **P8** Living systems | Not started | Entire phase |

## Immediate gaps

1. Deploy the source-faithful context migration, then publish the unchanged `tcv1.0` replay
   at a new evaluation vintage with the same eight split hashes and ≤5% unavailability.
2. Choose the next honest P2 slice: neighbours, permits, land/spacing units, or the canonical
   completion-design promotion required before design measurements can serve.
3. Prove P6 operationally: execute and record the restore drill, then exercise a
   non-interactive guest path with an outsider.
4. Enforce every `/explain` selector against its derivation output, including `_b64`
   completion identities, so a valid derivation cannot appear to support a nonexistent row.
5. Add immutable conformance-rule publication time distinct from `effective_from`, then
   make historical rule lookup honor both clocks; today a newly inserted backdated rule can
   alter a replay despite append-only storage.
6. Promote New Mexico before implementing Texas lease allocation so the well-level
   Permian spine can act as the intended control.
7. Resolve the owner-gated v0.6 §11 review and public IP carve-out decision separately
   from implementation work.

## Verification state

- The full locked Python suite passes **2,550 tests with 2 explicit skips**, including the
  Docker-backed integration and contract tiers; Ruff passes.
- The web suite passes **1,158 tests across 77 files**; typecheck and production build pass.
- Browserless E2E guards, shell checks, collateral checks, changelog lint, and the
  35-assertion headless-Chromium map-chrome gate pass locally.
- The dependency lock exactly matches the installed environment and the generated OpenAPI
  snapshot reports current.
- Hosted PR CI run `33013817153` passed all six jobs on 2026-08-26 at implementation-review
  head `978e2fc`: 2,494 passed, 2 explicitly skipped, and zero annotations.
