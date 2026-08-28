- [New] Publish accepted P3 receipt `p3pub_8b434525d8c621762e31b06ca660bfcd` with
      unchanged `fv2.0`, `mdv1.4`, `tcv1.0` and split hashes, two byte-identical builds,
      independent receipt rehashing and 1.0798% control unavailability against the 5% ceiling
- [New] Validate every current selector-bearing API figure against a fail-closed persisted-output
      registry, with dedicated response derivations for computed well and viewport aggregates
- [New] Give conformance rules and lookup rows immutable publication evidence independent of
      valid time, and expose both clocks without hiding known historical rule versions by default
- [New] Persist source polls independently of ingest transactions with explicit new, unchanged,
      failed and interrupted outcomes and one source-specific cadence registry
- [New] Sweep successful unreferenced ephemeral lineage after 90 days from an always-armed,
      sandboxed nightly unit while retaining failed, permanent, recent and referenced derivations
- [Change] Show attempt outcome, next expected poll, cadence, retrieval and declared vintages,
         latest artifact identity, and bounded freshness reasons on Status and health surfaces
- [Change] Use the first published routing/rule set as the explicit baseline for source-data
         vintages that predate Glasswell, without admitting later backdated corrections
- [Fix] Prevent another source key's success from hiding a failed or interrupted key, and keep
      failure evidence bounded, redacted, database-safe and append-only
- [Fix] Keep response values outside derivation identity so a repeated request with different
      output hits the determinism gate instead of minting a second derivation
- [Fix] Keep retention progress safe around every foreign-key-owned ephemeral artifact, bind
      directly applied summary rules, and cap viewport provenance writes per principal
- [Fix] Align freshness cadence with the recurring units, treat unscheduled sources as explicitly
      owner-triggered, and refuse deployments that intentionally skip required migrations
