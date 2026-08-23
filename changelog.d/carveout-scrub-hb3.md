- [Fix] source comments in the land-grid thematics, the layer registry, the land
      metrics mart, its unit test and migration 034 carried research provenance
      from the blueprint 8.2 carve-out corpus, which is git-excluded — the
      pointers dangled as well as leaked; the properties they justified are
      restated in the project's own voice, with no behaviour change
- [Change] migration 034's comment scrub changes the file's sha256, which
         `public.schema_migrations` records; an environment that already applied
         034 needs its recorded sha updated or `glasswell-migrate` refuses the
         run, by design — no DDL changed and no re-run is required
- [New] the `collateral` CI job rejects carve-out material in tracked source,
      beside the AI-attribution check; the token list is deliberately narrow to
      stay false-positive free and carries a note on extending it
