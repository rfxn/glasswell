- [New] Colorado is resident, and it arrived as a registration rather than as a project: one
      `lineage.jurisdictions` row with prefix `05`, thirteen `jurisdiction_rules` decisions
      and twenty-two conformance rules with published ECMC evidence, and no edit to
      `api/routers/wells.py`, `facets.py`, the legend census constants or the status collector
- [New] `cr_co_wells_status_vocab_1` maps the thirteen published ECMC Well Status codes:
      eleven to a canonical class and `SO` and `UN` to `documented_unmapped`, resolved at read
      time through a Colorado arm on `canonical.status_resolution`. The shapefile's in-band
      legend is the stale one, and the rule says which of the three published legends governs
- [New] `cr_co_wells_location_qualifier_1` and `canonical.well_spatial.location_qualifier`:
      how good a coordinate is, on the row that holds the coordinate and on a separate axis
      from `geometry_provenance`. 44.67% of Colorado's served points are permit locations
      rather than surveys, 27,976 of them on wells that carry a spud date
- [New] Colorado production at completion grain with North Dakota's dual write beside it: one
      row per completion plus one `sum_over_pools` well row per month and stream, so
      `/v1/wells/{api10}/production` renders and a reader can tell a two-completion month from
      a one-completion one. Liquid means oil plus condensate, because ECMC files one liquid
      stream and no condensate column exists
- [New] `marts.co_wells_tile` and the `co_wells` layer, from a `MartProfile` row in the
      parameterised engine. There is no `marts/co_wells.py`: Colorado is the first state added
      without a module of its own
- [New] Colorado's six jobs are `scheduled_jobs` rows seeded `launch_mode = 'launch'`, so the
      scheduler runs the first load in dependency order. It installs no systemd unit, which is
      what makes launching admissible: nothing an installed timer drives shares an entry point
- [Change] The cumulative mart's population is a `cumulatives_scope` registry dimension rather
           than a tuple in `marts/cumulatives.py`; North Dakota and Colorado each carry a row
           naming the rule that decides whether they write a well-grain row at all. The mart's
           derivation address moves from `states 33` to `states 05,33`, because a total over a
           different population is a different figure; North Dakota's own totals are unchanged
- [Change] The scheduler's launch gate asserts the invariant it was standing in for rather
           than the posture: no launching row carries a legacy unit or shares an entry point
           with an installed timer, and something must launch for the gate to pass at all
- [Fix] `test_no_other_states_letters_are_resolved_through_the_new_mexico_map` asserted the
      read-time resolver answered for one jurisdiction, which a second read-time jurisdiction
      would have reddened without any defect; it now asserts each codebook reaches only its own
      registered prefix
