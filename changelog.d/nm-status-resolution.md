- [New] `cr_nm_wellhistory_status_vocab_2` supersedes `_1` and maps the OCD well-header
      status letters to the canonical vocabulary from the regulator's own data dictionary
      (sheet "consolidated code list", sha256 `b95c45d3…`), corroborated per well against
      OCD's live `Wells_Public` layer. Ten of fourteen codes reach a canonical class; `I`,
      `J`, `Q` and `Z` — reclamation-fund and zone-plugged — carry the new registered class
      `documented_unmapped`, because forcing them into `plugged` would strike 507 wells
      through on a claim the regulator never made and collapsing them into the absence class
      would erase that it said anything. The dictionary transposes `I` and `J` against both
      live services; the services win, per well
- [New] `lineage.nm_wellhistory_status_map` and `canonical.status_resolution` (migration
      `071_nm_status_resolution.sql`) resolve the class at read time. `marts.tile_nm_wells`,
      `/v1/wells`, `/v1/wells/{api10}`, `/v1/wells/status-summary` and `/v1/wells/facets`
      all read the one view, so the map and the well card cannot answer differently about
      the same well. `canonical.wells.status_canonical` stays null for New Mexico: the table
      is append-only and a backfill would have to invent a valid time the OCD never filed
- [New] `nm-wells-struck` draws the strike over plugged New Mexico wells, which had no
      struck style layer because no New Mexico well could previously carry a terminal class
- [Change] New Mexico's 141,778 mapped wells stop painting as one unmapped swatch: 54,325
           active, 50,935 plugged, 18,161 permitted, 17,056 expired, 779 temporarily
           abandoned, 507 documented-without-an-equivalent and 15 dry. The legend census
           counts them, the map key lists them and the flyout carries the class beside the
           filed letter. `unmapped_action` is `passthrough` and not the `quarantine` North
           Dakota and Montana use, because the header table is the identity spine production
           joins to and quarantining would drop 2,211 records from it
- [New] `/v1/wells` and `/v1/wells/{api10}` serve `status_vocabulary_rule` beside the class,
      and the record links it at `/v1/conformance/{rule_id}`. New Mexico is the first state
      whose served class is decided by a rule its own row derivation does not cite — the
      promotion still cites the superseded `_1` — so without this a reader resolving the
      handle behind an NM `active` reached the rule that refuses the mapping
- [Fix] The `status` filter description and the `gt_well_status` glossary term said an
      unmapped code is always quarantined, which stopped being true when
      `cr_nm_wellhistory_status_vocab_2` registered the repository's first `passthrough`.
      Both now name the two actions and which jurisdiction chooses which, and the glossary
      enumerates `service` and `documented_unmapped`
