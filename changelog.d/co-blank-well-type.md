- [Fix] a blank ECMC attribute is an absence, not an empty string: the three Colorado GIS
      archives stage every text column under cr_co_wells_shp_blank_is_absent_1,
      cr_co_directional_bh_blank_is_absent_1 and cr_co_directional_lines_blank_is_absent_1,
      which promote it as NULL; the 124,392 headers already promoted are read under the same
      rule rather than restated, since canonical.wells is keyed on ECMC's own Stat_Date
- [New] blank_is_absent is a registry decision: lineage.jurisdiction_rules carries it for
      Colorado at cr_co_wells_shp_blank_is_absent_1, and the three reads that apply it —
      the wells spine, the well card and /v1/wells/status-summary — cite it in their
      derivations and link it, per jurisdiction, so no Texas or North Dakota response names
      a rule about ECMC's blanks (R8)
- [Fix] the model context reads its `area` control feature under the same rule; a blank
      county there is a category of its own and would split one county's peers into two
      cohorts (gate-cofix M-1)
- [Fix] a status class the read-time resolver maps onto an empty string is the absence class
      rather than a second bucket beside the real ones: /v1/wells/status-summary and the wells
      spine wrap the resolved status the way facets.py already does, so two selectors can no
      longer collide on status_null=1 (gate-cofix M-2)
