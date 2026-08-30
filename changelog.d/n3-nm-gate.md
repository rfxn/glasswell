- [New] `scripts/ops/nm_reregister_manifests.py` re-registers a sealed raw-zone artifact
      from its sidecar into an index that does not carry it yet; no socket is opened and
      the operation is idempotent on the sha256 within a slot
- [New] `--dry-run` validates every sidecar, resolves each against the live index and
      reports the manifest ids it would create on a read-only connection, so committing
      nothing is enforced by the server rather than by the code path
- [Fix] the manifest re-registration tool existed only at `/data/scratch/d1-p4/reregister.py`
      on the app VM, inside a disposable tree, while the status file that directs an
      operator to it named a `work-output/experiments` path that does not exist; it now
      names its target database on every run, reports registered against already-present
      per sidecar, and exits 1 on a slot conflict instead of tracebacking
- [Fix] `status/collector.py` aggregated `canonical.production_monthly` with no state filter
      and served the result under a hardcoded North Dakota jurisdiction, so the first New
      Mexico promotion would have published 24.8M rows and ~93,958 wells under the wrong
      state within fifteen minutes, on a timer, over rows with no well header
- [Change] the inventory splits into `canonical.production_monthly/nd` and `/nm`, matching
         the state-qualified convention every sibling dataset in the file already follows,
         including the `well_completions/nm` entry that already serves zero
- [Change] the status contract test seeds two states rather than one — the defect was
         invisible to a single-state fixture — and asserts the two datasets partition the
         table, so a third population would fail rather than vanish from a served figure
- [New] `docs/runbook-nm-promotion.md`: the four New Mexico production steps with their
      preconditions, abort conditions, expected counts, verification gates and the rollback
      each step actually has — which for three of the four is none, stated in terms designed
      to stop an operator improvising a delete
- [New] `tests/integration/test_nm_promotion_gates.py` pins the index the deployed G7-2 gate
      names: `production_monthly_api10_idx` exists, leads on `api10`, and both the served
      query and the `_latest` view resolve to it once a sequential scan stops being free
- [Change] `055_state_parameterised_neighbors.sql`: `nd_neighbor_subjects.api10` and both
         `nd_neighbor_edges` endpoints accept any ten-digit API-10 rather than only `^33`,
         while a new constraint keeps an edge intra-state because the pair-local UTM zone
         selection is undefined across an arbitrary state pair
- [Change] `marts/neighbors.py`: `STATE_CODE` becomes the `STATE_CODES` tuple the refresh
         binds through `= any(...)`, so a second state is a data change rather than an edit;
         New Mexico is deliberately not in it, because neither NM source ships a lateral
- [New] `seed/conformance_nm_wells.py`: ten conformance rows covering New Mexico's header
      identity, effective dating, status and well-type domains, the NAD83 datum transform, the
      coordinate policy, geometry provenance and scope, the pool grain and the cross-source
      header precedence; `056_nm_gate_rule_publications.sql` registers their publication
      evidence, which migration 049 makes a precondition for the insert
- [New] `cr_nm_wellhistory_coordinate_1` records the measurement behind the policy: 318,720 of
      321,510 records carry a usable coordinate pair, 897 carry a zero ordinate and 1,893 a nil
      one, giving 141,778 of 142,000 wells a point — three counted populations that sum to the
      record count rather than two counted and one subtracted
- [New] `cr_nm_wellhistory_status_vocab_1` records the fifteen-value status domain and asserts
      no canonical status: the OCD publishes no codebook, so a New Mexico well carries its
      letter in `status_reported` and null in `status_canonical`, and the served unmapped count
      has a rule behind it
- [New] `cr_nm_wellhistory_geometry_scope_1` states that no in-scope New Mexico source ships a
      lateral or a bottomhole, so the 43,409 horizontal and 3,265 directional wells the header
      table names must never be read as carrying a path
- [New] `cr_nm_wcproduction_pool_rollup_1` gives New Mexico's pool grain a New Mexico rule to
      cite instead of North Dakota's, and says the opposite of what North Dakota's says: all
      17,597,960 promoted rows are `well_completion_pool` with a null aggregation and there is
      no well-level row among them, so a New Mexico well's well-level series is absent rather
      than zero
- [New] `057_nm_well_headers.sql`: `coordinate_sentinel` and `coordinate_absent` join the
      quarantine reason vocabulary, so a zero ordinate and a nil one are quarantined under
      distinct codes rather than dropped or collapsed, and `wells_state_effective_idx` supports
      the per-state newest-effective-row scan the tile marts run
- [Change] `canonical.wells` and `canonical.well_spatial` need no widening for API prefix 30 —
         neither carries a state constraint and `geom_type` already admits `surface` — and a
         test now guards that against a future state check
- [New] `ingest/nm_wells.py` promotes `staging.stg_nm_ocd_wellhistory__records` into
      `canonical.wells` and `canonical.well_spatial`, keyed by the registry's own per-segment
      API-10 composition rule and carrying no state-code literal. This is the row that opens the
      serving gate: the spine is rooted on `canonical.wells`, so every New Mexico figure becomes
      servable here and nowhere earlier
- [New] the OCD FTP header table ships latitude, longitude and NAD83 datum — 318,720 usable
      pairs of 321,510 records and 141,778 of 142,000 wells — so New Mexico geometry needs no
      new source; the earlier "no coordinates" finding was scoped to `wcproduction`
- [New] the coordinate policy is a pair rule, not a latitude rule: either ordinate nil
      quarantines as `coordinate_absent` and either ordinate zero as `coordinate_sentinel`, nil
      taking precedence. Four records carry a good latitude with a zero longitude, and a
      latitude-only check would have given them a valid point in the Gulf of Guinea in an
      append-only table
- [New] `tests/fixtures/nm_ocd/nm_wellhistory_headers.xml`, cut from the sealed artifact by
      truncation and selected rather than taken from the head, so all six coordinate
      populations are present — three of them hold fewer than five records in 321,510
- [Change] neither refusal suppresses the well header, and two reconciliations close on counted
         populations rather than on subtraction: records equal headers plus unkeyed plus
         undated, and headers equal points plus coordinate refusals
- [New] `marts/land_metrics.py` counts unassigned wells a third way — those outside the states
      the PLSS grid covers at all — so the scope New Mexico's 141,778 surface points fall
      outside is stated explicitly rather than inferred from a total
- [Change] `058_land_grid_state_scope.sql` and `seed/conformance_land.py` supersede
         `cr_land_agg_membership_1` with `_2`, carrying the third counter and the measured
         populations; the membership itself is unchanged, which is why this is a superseding
         row rather than the code change its own contract_note forbids
- [Fix] the membership universe is not filtered by state: 355,463 Texas surface points are in
      it today and a scope filter would have collapsed a served figure to zero while a fixture
      with one state in it reported no change
- [Change] the production CTE is restricted to the wells membership actually joins, which is
         output-identical — asserted by running both shapes side by side — and removes a full
         scan of a view that spans 24.8M rows after the New Mexico promotion
- [New] `marts/nm_wells.py`: a point-only New Mexico tile mart on the same shape as the ND and
      TX marts — reads canonical only, rebuilds rather than appends, one content-addressed
      derivation per refresh — and `059_nm_marts.sql` creates `marts.nm_wells_tile` with its
      grants and registers the GIS layer's poll cadence
- [New] the tile carries `status_reported` beside `status_canonical`, because every New Mexico
      `status_canonical` is null by `cr_nm_wellhistory_status_vocab_1` and the reported letter
      is what a legend has to work with
- [Change] there is no `nm_laterals` layer and a test guards against one, asserted against the
         tile proxy's own allowlist rather than the mart module's constant: no in-scope New
         Mexico source ships a lateral, and a layer would imply a footprint nobody filed
- [Fix] `api/routers/production.py`: the pool-rollup link was pinned to `cr_nd_pool_rollup_1`
      and served on the pool endpoint unconditionally, so every New Mexico pool series would
      have cited a North Dakota rule; the link now resolves per jurisdiction and cites
      `cr_nm_wcproduction_pool_rollup_1`, which says New Mexico rolls nothing up
- [Fix] `api/routers/production.py`: `ND_LIQUIDS_BASIS` was served as the mandatory `_basis`
      sidecar on every liquids figure regardless of state, so every New Mexico oil figure would
      have carried North Dakota's liquids policy; the basis is resolved per figure and New
      Mexico's is `oil`, because `cr_nm_wcproduction_liquids_1` measured 3,398 condensate
      filings and ruled that condensate is its own stream
- [New] a New Mexico well whose production is filed at pool grain now says so on its
      well-level series instead of rendering an empty chart: all 17,597,960 promoted rows are
      `well_completion_pool` and nothing rolls up, so the series is absent rather than zero
- [Fix] `api/routers/wells.py`: `STATUS_VOCABULARY_RULES` had no prefix-30 entry, so a New
      Mexico well served a null `status_vocabulary_rule` and a spurious warning; geometry
      provenance likewise resolved to the North Dakota rule for every state, and five served
      field descriptions enumerated North Dakota and Texas in prose where they now name the
      per-jurisdiction mapping
- [Change] `status/collector.py` reports New Mexico in the `canonical.wells_latest` inventory
         and publishes `marts.published_map_layers/nm`, so the status surface stops enumerating
         two states out of three
- [New] `web/src/map`: the `nm_wells` point layer, its registry provenance entry citing
      `marts.nm_wells_tile`, and its status-count block — which is empty, and says why: every
      New Mexico `status_canonical` is null under `cr_nm_wellhistory_status_vocab_1`, so the
      whole state draws in the unmapped class rather than a guessed one
- [Change] no `nm_laterals` layer is added and no struck sibling: no in-scope New Mexico source
         ships a lateral, and the strike marks a status class New Mexico can never carry
- [Change] the default Williston centring is left alone; re-centring for a second basin is an
         owner decision and is routed to the register rather than taken here
- [New] the `nm_wells` mart joins the ingest unit's refresh sequence, and the unit description
      stops claiming it is ND-only; that unit runs monthly on day 5, not nightly
- [New] a smoke check asserts the New Mexico spine — a well header with a geometry provenance
      and a New Mexico status vocabulary rule — rather than a row count, and skips cleanly
      where the gate is not open
- [Change] no timer is added for `nm_ocd`, `nm_dims` or `nm_wells`: those sources are
         registered owner-triggered and the FTP pull is a once-ever event; the measured cost of
         a recurring promotion — 89 minutes and 9.9 GB, which does not fit the ingest unit's
         `TimeoutStartSec` — is recorded in `SMOKE.md` for the decision, along with a weekly
         recommendation for the daily-refreshed GIS layer
- [New] `ingest/nm_wells_gis.py`: one ordered walk of the OCD Wells_Public FeatureServer layer,
      ordered by the unique `id` rather than `OBJECTID`, into one checksummed artifact, one
      manifest and one staging load; the host is already allowlisted so no blueprint amendment
      is required, and `060_nm_wells_gis.sql` creates the staging table and registers the rule
      publications
- [New] `cr_nm_wells_gis_parity_1` records the agreement between two independently produced New
      Mexico well populations — 141,916 GIS features against 142,000 FTP header API-10s, a
      0.06% difference — as a prohibition rather than a tolerance band: the per-well distance
      distribution is not measured, so no rule can yet say which source wins where they differ
- [Change] the module stops at staging on purpose: the parity measurement decides how it
         promotes, and promoting first would make the rule a rationalisation rather than a
         finding. `cr_nm_wellhistory_header_precedence_1` accordingly still names the FTP
         archive as sole authority, and no superseding row is seeded ahead of the evidence
- [Fix] `STATUS.md` conflated the production database with the deployed host, so it reported
      New Mexico as unpopulated while 79 conformance rules, 10 sources and 71,447 staging rows
      were resident and a full 17.6M-row spine sat in a scratch database on the same machine
- [Fix] `STATUS.md` overstated `tx_pdq_dsv`: it has a poll-cadence row on a table with no
      foreign key to `lineage.sources`, and a test fixture — not a seeded source registration,
      not conformance rules and not an ingest module
- [Change] `ROADMAP.md` N3 says surface geometry rather than lateral geometry, and New Mexico
         lateral geometry is tagged `data-unreachable`: neither the OCD FTP header table nor
         the OCD public wells layer ships a lateral or a bottomhole, measured in both, with
         43,409 horizontal wells named and no path filed for any of them
- [Change] `ARCHITECTURE.md` names the New Mexico tile mart and the two staging termini that
         are termini by design rather than by omission
- [Change] the promotion runbook asserts the Wave-1 `glasswell-repromote` units are **absent**
         rather than masking them: T6 removed them from VM 111 on 2026-08-30 and `verify.sh`
         now asserts host against tree, so masking a unit that does not exist is not the check
         the condition wants. The armed-timer framing is corrected with the measurement that
         settles it — `Persistent=` catch-up needs a calendar occurrence after the base time,
         and `systemd-analyze calendar '2026-08-21 00:30:00 UTC'` returns `Next elapse: never`
- [Change] the dump precondition says what it does not give: `verify.sh` gates its schema-head
         comparison on a drill completing after `max(applied_at)`, and the drill is weekly, so
         between this deploy and the next Sunday the newest restore proof covers the previous
         schema
- [Fix] `cr_nm_wellhistory_effective_1` legislated a translation of the `9999-12-31` sentinel
      into a null `effective_to`, and `canonical.wells` has no `effective_to` column and the
      promoter never read `rec_termn_dte`; the row now states what the code does, the promoter
      reads the field name and the reason code from the spec, and the ranking question the old
      text hid is measured — 142,000 open headers against 142,000 wells and zero wells whose
      newest row is retired
- [New] `cr_nm_wellhistory_basin_scope_1` records that New Mexico headers carry no basin and
      why: its wells sit in the Permian and the San Juan and this build delineates neither, so
      a default would be a claim about geography wrong for every San Juan well
- [Fix] `marts/producing.py` filtered `entity_type = 'well'` and served every New Mexico well
      `producing: unknown` under a field description offering three causes, none of which
      applied; the states with no well-level series now resolve from the registry for either
      recorded reason, and the well card discloses which with the rule that decided it
- [Change] the New Mexico smoke check keys its branch on `/v1/status` rather than on the
         endpoint under test, so a regression that drops New Mexico from the spine fails
         instead of converting the assertion into a skip
- [Change] `scripts/ops/nm_reregister_manifests.py` gains `--expect-database`, turning an
         operator rule into a refusal; `test_martin_publishes` suffixes its container name, so
         two worktrees sharing a Docker daemon stop manufacturing false reds
