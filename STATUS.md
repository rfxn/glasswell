# Current status

Reconciled on **2026-08-28** against the v0.59 release line, the checked-in OpenAPI
snapshot, and current `main` history. This is the short current-state ledger;
[`ROADMAP.md`](ROADMAP.md) owns phase scope and exit criteria, while
[`blueprint.md`](blueprint.md) remains the committed v0.5 contract and
[`blueprint-v0.6-draft.md`](blueprint-v0.6-draft.md) is the rc4 amendment set.

## Shipped baseline

- **Release line:** 40 tagged releases, v0.20 through v0.59, cut 2026-08-21 through
  2026-08-28.
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
| **P6** Hardening and glass-box proof | Partial | A sanitized timed Status snapshot observes core services, bounded probes, storage, scheduled jobs, exact-grain dataset inventory and source artifact age. Nightly dumps now carry exact-vintage manifests, and a weekly logical restore drill validates freshness, schema, counts, representative reads and scratch cleanup. The v0.57 live drill completed the database checks but could not publish into shared state; v0.58 isolated the result and persisted the next failure honestly, exposing that an explicit redundant root identity blocked the sandbox's required PostgreSQL credential transition. The exact corrected implicit-root sandbox then restored the 1,493,232,492-byte dump in 863 seconds, matched schema 46, all four critical counts and all six representative reads, removed the scratch database, and persisted a `root:glasswell` `0640` pass receipt. The tagged recurring unit still needs deployment. Completion and neighbour lineage selectors are checked against persisted derivation outputs, but that enforcement is not universal. This does not prove full VM/raw-zone recovery. Still add durable source-check/cadence evidence, tunnel/Access, outsider guest exercise, full-system recovery, determinism and tool-equivalence gates |
| **P7** Permian | Started, unpromoted/incomplete | NM deployment; TX production, allocation, and validators |
| **P8** Living systems | Not started | Entire phase |

The v0.58 deployment also exposed an operational defect in the first live neighbour replay:
the reverse subject foreign key had no supporting edge index, so deleting 22,263 subjects
repeatedly scanned 7,958,550 directed edges. The transaction was cancelled and rolled back
without changing the resident mart. The corrective migration and transactional full-replacement
path are now release-gated before any further live replay; row deletes remain transactional so
readers retain their prior MVCC behavior while the replacement is prepared.

## Immediate gaps

1. Publish unchanged `tcv1.0` at a new evaluation vintage with the same eight split hashes and
   ≤5% unavailability; the source-faithful context and receipt migrations are already resident.
2. Deploy the reverse-FK index, replay the populated ND physical-neighbour mart safely, and
   verify unchanged card, pagination, exact-lineage and Status results against resident data.
3. Deploy the corrected implicit-root recurring restore unit and confirm it preserves the exact
   live sandbox pass; retain full VM/raw-zone recovery as a separate P6 exit requirement.
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

- The full locked Python suite passes **2,668 tests with 2 explicit skips**, including the
  Docker-backed integration and contract tiers; Ruff passes.
- The web suite passes **1,184 tests across 79 files**; typecheck and production build pass.
- Browserless E2E guards, shell checks, collateral checks, changelog lint, and the
  headless-Chromium gates pass locally: 35 Map assertions and 82 Status assertions.
- The dependency lock exactly matches the installed environment and the generated OpenAPI
  snapshot reports current.
- Hosted CI evidence for this implementation-review head must be recorded on its pull request;
  release claims do not inherit a prior head's run.
