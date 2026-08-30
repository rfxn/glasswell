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
