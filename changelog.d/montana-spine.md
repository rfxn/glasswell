- [New] seed: conformance_mt.py registers 45 Montana rules across four MBOGC sources — the
      API-14 to API-10 slice on state code 25, the end-of-month report convention, the -999
      Lease_Unit sentinel, the pre-applied oil-plus-condensate liquids basis, the formation
      rollup, the lease grain's reporting level, the fifteen disposition columns that stage
      but never promote, the cp1252 DBF encoding, the twinned-layer selection, and the
      map-stick-not-survey class on well paths; every row carries a rationale, an evidence
      URL and a figure measured by full streaming pass rather than sampled
- [New] seed: four MBOGC sources registered with an UNVERIFIED licence note — the listing
      root answers 403, so bulk paths are pinned constants and no filename is ever derived
      from an index
- [New] db: 057_mt_registry.sql adds the Montana poll cadences, lineage.mt_stream_map and
      lineage.mt_status_map with their promoted views, and the first-publication evidence
      migration 049 requires before any cr_mt_ rule may be seeded
- [Fix] ingest: ZippedShapefile takes an optional encoding. The MBOGC DBF declares Windows-1252
      at language-driver byte 0x59 and pyshp's strict UTF-8 default raised partway through
      iteration on a well named Blasé; the default is unchanged, so ND, TX and NM read exactly
      as before
- [Fix] tests: the source-poll cadence guard scans every migration for its insert rather than
      opening 050 by name — migrations are immutable, so a source registered later can only be
      given a policy in a later file, and the guard was blind to precisely that case; its
      statement terminator now tolerates a semicolon inside a cadence string
- [New] ingest: mt_bogc.py stages and promotes both MBOGC grains from one archive and one
      manifest — the well grain at well and well_completion_pool over ST_FMTN_CD with a
      sum_over_pools rollup whose days take the maximum, and the lease grain at
      lease_reported. Staging streams from the zip member and promotion reads one production
      month at a time, so a 573 MB file is never extracted and never held in memory
- [New] ingest: mt_gis.py loads the surface points and well paths, selecting the geographic
      layer of each twinned archive by stem and keying a lateral on WellSub within its API-10;
      the promotion derivation records is_directional_survey false, so a consumer reading
      provenance learns the map-stick class from the ledger rather than from prose
- [New] ingest: promote.py carries the source-parameterised bitemporal append — change-only
      heads, scoped head reads and same-vintage divergence refusal — so a second state does
      not restate them as literals bound to one source id
- [New] db: 058_mt_staging.sql adds the four Montana staging tables, text-faithful including
      the -999 sentinel and the fifteen unpromoted disposition columns
- [New] seed: 057 seeds all nineteen published MBOGC status values with their measured counts;
      six are deliberately unpromoted and quarantine as unknown_status rather than being forced
      onto a canonical state the source does not claim
