- [New] ND directional-survey traces (M1-5): source `nd_gis_directionals` registered
      against OGD_Directionals.zip (3.4 MB, 52,579 stations) with the publisher's own
      disclaimer quoted verbatim; staging.nd_gis_directionals,
      canonical.well_survey_stations at station grain, and a `survey_trace` geometry in
      canonical.well_spatial keyed by API-10 the way laterals are
- [New] marts.nd_survey_traces_tile and the `nd_survey_traces` tile layer, publishing
      station_count, deepest measured depth and TVD, wellbore segment and a
      geometry_provenance column that tells a surveyed path from a GIS bore line;
      simplified like the laterals, not thinned — 586 traces statewide is not overplot
- [New] six R8 rule rows for the survey source: API-14 to API-10 on ND's own published
      rationale, the well_sub vocabulary, the ascending-measured-depth assembly with its
      tie-break, per-field physical bounds that withhold the value and keep the position,
      a two-station floor, and the unstated azimuth north reference recorded as a gap
- [Change] canonical.well_spatial.geom_type admits `survey_trace`; quarantine reason
           vocabulary admits `insufficient_stations`
- [Fix] ND GIS layer selection is declared rather than incidental: OGD_Directionals.zip
      ships two shapefiles and the loader now names the stem it reads
