- [New] `glasswell-nm-wells` and `glasswell-nm-tiles` console scripts for the New Mexico
      Tier 2 pair — the header and surface-geometry promotion, and the tile mart refresh.
      Both modules already had a `main()` and neither had an operator entry point, so the
      runbook commands were module invocations; `scripts/deploy.sh` reinstalls the project
      editable on every deploy, so the table and the host move together
- [New] `docs/runbook-nm-tier2.md`: the four production steps that open the New Mexico gate,
      scoped as Tier 2 and explicitly not the production-history load. Every expected figure
      carries its provenance — sealed 2026-08-20 measurement, estimate by analogy, or record
      it — so no fixture count is mistaken for a forecast
- [New] `tests/integration/test_nm_tier2_end_to_end.py` runs the operator's chain on one
      database — stage, promote, refresh, serve — and decodes a fixed zoom-9 southeastern New
      Mexico tile off the wire; the promotion and the mart each had their own suite and
      nothing measured the seam between them
- [New] the gate assertion is red then green on the same API-10: the first promotion is
      rolled back so the 404 and the 200 are the same key on the same database, which is the
      only ordering that proves the header row is what changed the answer
- [New] `tests/unit/test_console_scripts.py` pins the New Mexico pair to the launcher
      contract and fails if `nm_ocd` or `nm_dims` ever acquires a script of its own: an entry
      point is a form of encouragement, and the production-history load needs a runbook and a
      named authorisation instead of a shorter spelling
- [New] `canonical.wells.operator_name_reported` is decided at promotion time and is not one
      of the attributes the divergence check compares, so a re-run once
      `lineage.operator_aliases` exists appends nothing and leaves every name null — measured,
      then pinned by a test pair covering both orderings. The runbook makes it an abort
      condition with an owner decision rather than a default
- [Change] `infra/README.md` gains an operator entry-point table, and records why the Tier 1
         production-history load keeps its `python -m` spelling: an entry point is a form of
         encouragement, and that load needs a runbook and a named authorisation instead
- [Change] `infra/martin/README.md` lists `nm_wells` with its refresh command, states that
         New Mexico publishes a point layer and no lateral, and stops claiming a layer count
         the roster outgrew
- [Change] `README.md`'s project-docs table gains both New Mexico runbooks; the Tier 1 one
         has never been listed there and the pair only reads correctly together
