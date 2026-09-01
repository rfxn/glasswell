- [Fix] `README.md` claimed 34 operations in the frozen snapshot, 33 under `/v1`; the
      snapshot holds 49 across 44 paths, 48 under `/v1`. The listing gains
      `/v1/wells/facets`, the glossary and quarantine members, the derivations, manifests
      and vintages collections, and a line naming the session, user and key write paths
- [Fix] `README.md` described the deployment as a North Dakota production slice with a
      North Dakota/Texas map. It is four states at four depths: North Dakota end to end,
      Montana with both production grains promoted, Texas geometry-only, and New Mexico's
      spine behind a closed gate
- [Fix] `README.md` carried a v0.60 paragraph stating schema head 52, 111 host checks and
      20 smoke checks, and a P3 block of coverage percentages, row counts and a
      publication id. Volatile figures now live in `STATUS.md` and the P3 docs, which the
      README defers to rather than restating
- [Change] `README.md` marks the Texas and New Mexico source rows for what is ingested
           against what is designed, lists the five console scripts it omitted
           (`glasswell-nm-wells`, `-nm-tiles`, `-basin-boundaries`, `-eia-boundaries`,
           `-owner-reset`), and points each multi-step load at its runbook
- [Fix] `assets/architecture.svg` named no Montana source or staging table though the
      state is promoted and on the map; the source band gains `MT BOGC — well · lease
      production` and the staging band re-pitches to six for `mt_bogc_* · mt_gis_*`
- [Fix] `assets/architecture.svg` named `TX RRC — PDQ lease production` in the source
      band, which is not a registered source and has no ingest module; the box now reads
      `TX RRC — GIS wells · wellbore export`, which is what Texas actually contributes
