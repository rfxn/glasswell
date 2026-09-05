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
- [Fix] the rule's served evidence names both blank columns the header archive measures —
      Well_Class (1,176) and Loc_Qual (62) — rather than only the one a gate caught
      (gate-cofix M-3)
- [Fix] an empty value on /v1/wells is no filter rather than a selector for the rows the
      spine reads as absent: `?well_type=`, `?county=`, `?operator=`, `?q=`, `?status=` and
      `?geometry_provenance=` now answer the unfiltered population, and every text predicate
      addresses the value the response serves rather than the column beneath it (gate-cofix
      M-4)
- [New] a standing post-promotion sweep: every non-key attribute is planted blank in staging
      and no text column of canonical.wells may hold an empty string afterwards, so the
      class claim holds at the write path and not only at the selector (gate-cofix L-4)
