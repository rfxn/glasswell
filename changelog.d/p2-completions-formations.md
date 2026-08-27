- [New] `GET /v1/wells/{api10}/completions` serves FracFocus completion events separately
      from regulator completion-pool entities, source-scoped formation mappings, explicit
      null semantics, as-of guards, and derivation handles without joining unrelated keys
- [New] `GET /v1/formations` aggregates current source-scoped aliases into canonical
      formations with alias counts, basin and free-text filters, cursor pagination, and
      reviewed peer groups
- [New] Well cards show completion events and pool-to-formation context with independent
      loading, empty, and unavailable states; staging-only design measurements and formation
      tops remain explicitly unserved
- [Fix] Formation-alias uniqueness now includes the source namespace; historical well rows,
      geometry, completion context, and formation aliases honor their available knowledge,
      effective, and release dates without leaking future or unvintaged observations
