- [New] Montana reaches the API and the map: marts.mt_wells_tile and marts.mt_paths_tile
      rebuilt by glasswell.marts.mt_wells, mt_wells and mt_paths published as tile layers
      and martin function sources, and a Wells (MT) and Well paths (MT) row in the layer
      registry drawn from the same status expressions as North Dakota and Texas
- [New] every served Montana path carries geometry_class map_stick and its vertex_count as
      tile properties, so cr_mt_paths_geometry_class_1's requirement that the distinction
      be stated wherever the geometry is served holds for a client that reads no docs
- [New] cr_mt_paths_length_scope_1: no lateral length is served for a Montana well, and the
      response carries the rule in the figure's place with a length_not_served warning and
      a links.length_rule handle
- [New] glasswell-mt-bogc and glasswell-mt-gis console scripts, the Montana mart refresh on
      the ingest timer, and docs/runbook-mt-load.md — the production load with its expected
      counts, tolerances, success-versus-partial cut and its undo
- [New] /status reports current Montana wells and published Montana map layers, each stating
      the rule behind what it counts
- [Fix] mt_gis: rejected rows reach lineage.quarantine_rows instead of only a counter — on
      the 2026-08-18 Wells.zip that is 1,400 wells whose MBOGC status cr_mt_gis_status_vocab_1
      does not promote, plus one unparseable API-10, recoverable with their payloads rather
      than reconstructable by subtracting two printed totals
- [Fix] the well card served a Montana lateral length of 6,120.87 ft under North Dakota's
      cr_nd_compute_crs rule: lengths.length_rule_source answers nd_gis_horizontals_line for
      any well with no basin, and cr_mt_basin_scope_1 leaves every Montana well untagged
- [Change] the frozen WellDetail schema documents what it now serves: length_method reads
           not_served where a rule withholds the length, compute_crs and lateral_length_ft are
           null there, and links.length_rule names the rule; descriptions only, no structural
           change, snapshot regenerated with scripts/regen-snapshot.py
- [Change] /status inventories Montana production on both grains MBOGC files, bucketed by
           source rather than by API-10 prefix: the lease grain carries a lease entity_key and
           no api10, so a prefix filter reaches none of it and would report 72% of the state
           under a label saying Montana
- [Change] PROVENANCE_RULES maps state 25 to cr_mt_paths_geometry_class_1 rather than
           falling through to North Dakota's cr_nd_geometry_provenance_1, which would have
           cited a survey-derived classing rule for a cartographic centreline
