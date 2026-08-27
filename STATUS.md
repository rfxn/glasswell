# Current status

Reconciled on **2026-08-27** against the v0.58 release line, the checked-in OpenAPI
snapshot, and current `main` history. This is the short current-state ledger;
[`ROADMAP.md`](ROADMAP.md) owns phase scope and exit criteria, while
[`blueprint.md`](blueprint.md) remains the committed v0.5 contract and
[`blueprint-v0.6-draft.md`](blueprint-v0.6-draft.md) is the rc4 amendment set.

## Shipped baseline

- **Release line:** 39 tagged releases, v0.20 through v0.58, cut 2026-08-21 through
  2026-08-27.
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
- **Serving surface:** the frozen snapshot contains 34 operations, 33 under `/v1`, covering
  health, operational status, wells, ND production, source-observed completion context,
  current ND physical neighbours, canonical formations with alias counts, lineage, manifests,
  conformance, quarantine, glossary, keys, and tiles. Forecast,
  valuation, scenario, agent, and inventory operations are not served.
- **Frontend:** URL-backed Map, Explore, and Status surfaces; MapLibre ND/TX layers; a well
  card with independent completion-event, pool-to-formation and current physical-neighbour
  sections, production chart, lineage drawer, glossary, explorer, satellite/hybrid modes, and
  searchable layer panel ship. The neighbour card explicitly separates proximity from analogs.

## Phase ledger

| Phase | Status | Remaining boundary |
|-------|--------|--------------------|
| **P0** Scaffold and contracts | Met | `/v1/audit` is not served, but is not a P0 exit requirement |
| **P1** ND spine | Met with named deferrals | PDF-era production and FracFocus chemistry remain absent; the disclosure-header anchor path is built |
| **P2** Serving and map | Substantially met | Completion context, formations and current ND physical neighbours are served and visible on eligible well cards without promoting staging-only design measurements or treating proximity as an analog. Neighbours use current lateral geometry, strict earlier-completion cutoffs and exact query lineage; retrospective geometry remains explicitly unavailable. Permits, land/spacing units, GOR and water-cut remain |
| **P3** Forecasting and benchmark | Pinned control and publication gate built; resident gate red | Immutable `fv1.0`, semantic-major `fv2.0`, `mdv1.4`, and control-major `tcv1.0` remain separate identities. The immutable resident artifact still records 12.9484% unavailability. A rollback-only migration rehearsal restored all 318 TEST formation gaps through same-manifest source rows, left the 38 source-absent laterals uninferred, replayed unchanged `tcv1.0` byte-identically on all eight exact split hashes, and measured 230 / 21,300 unavailable instances (1.0798%). A fail-closed publisher now pins deployed code and lock identity, verifies two byte-identical builds and persists an immutable family receipt, but a new-vintage live artifact is not yet published. Models, calibration, the model-registry writer, analog index, and harness remain |
| **P4** Dollars and scenarios | Not started | Entire phase |
| **P5** Intelligence, agents and alerts | Not started | Entire phase |
| **P6** Hardening and glass-box proof | Partial | A sanitized timed Status snapshot observes core services, bounded probes, storage, scheduled jobs, exact-grain dataset inventory and source artifact age. Nightly dumps now carry exact-vintage manifests, and a weekly logical restore drill validates freshness, schema, counts, representative reads and scratch cleanup. The first v0.57 live drill completed those database checks but exposed a state-directory permission defect before durable evidence could be published; the corrective isolated state directory is built and awaits replay. Completion and neighbour lineage selectors are checked against persisted derivation outputs, but that enforcement is not universal. This does not prove full VM/raw-zone recovery. Still add durable source-check/cadence evidence, tunnel/Access, outsider guest exercise, full-system recovery, determinism and tool-equivalence gates |
| **P7** Permian | Started, unpromoted/incomplete | NM deployment; TX production, allocation, and validators |
| **P8** Living systems | Not started | Entire phase |

## Immediate gaps

1. Deploy the source-faithful context and receipt migrations, then publish unchanged `tcv1.0`
   at a new evaluation vintage with the same eight split hashes and ≤5% unavailability.
2. Populate the current ND physical-neighbour mart on the release host and verify card,
   pagination, exact lineage and Status inventory against the resident data.
3. Deploy the corrective restore-result state directory, then replay and record the weekly
   logical restore drill from the fresh exact-vintage dump; retain full VM/raw-zone recovery as
   a separate P6 exit requirement.
4. Extend `/explain` selector-output validation beyond the completion and physical-neighbour
   datasets, retaining strict URL-safe base64 decoding for encoded identities.
5. Add immutable conformance-rule publication time distinct from `effective_from`, then
   make historical rule lookup honor both clocks; today a newly inserted backdated rule can
   alter a replay despite append-only storage.
6. Promote New Mexico before implementing Texas lease allocation so the well-level
   Permian spine can act as the intended control.
7. Resolve the owner-gated v0.6 §11 review and public IP carve-out decision separately
   from implementation work.

## Verification state

- The full locked Python suite passes **2,666 tests with 2 explicit skips**, including the
  Docker-backed integration and contract tiers; Ruff passes.
- The web suite passes **1,184 tests across 79 files**; typecheck and production build pass.
- Browserless E2E guards, shell checks, collateral checks, changelog lint, and the
  headless-Chromium gates pass locally: 35 Map assertions and 82 Status assertions.
- The dependency lock exactly matches the installed environment and the generated OpenAPI
  snapshot reports current.
- Hosted CI evidence for this implementation-review head is recorded on its pull request;
  release claims do not inherit a prior head's run.
