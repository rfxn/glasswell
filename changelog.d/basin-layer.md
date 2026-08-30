- [New] tiles: basins and plays are served tile layers over marts.basin_boundaries_tile —
      32 EIA sedimentary basin outlines and 16 individual play boundaries for the lower 48,
      each with a label anchor point owned by exactly one tile, so the map has a geological
      frame of reference instead of an undifferentiated field of well points
- [New] ingest: eia_boundaries loads both EIA archives as plain HTTPS zips through the
      existing strict-.prj shapefile reader — one manifest per archive, twelve boundary
      shapefiles selected out of the play bundle by a declared stem marker so the elevation
      and isopach contours beside them are never read
- [New] canonical: basin_boundaries holds one published boundary per row under a minted key
      — EIA publishes no feature id — discriminated by boundary_kind, append-only, with the
      publisher's own Basin string kept verbatim beside the resolved link
- [New] seed: eight code_ref and datum conformance rules record the boundary decisions —
      whose interpretation is drawn, that a basin and a play are different objects, how a
      play links to its basin, that overlap is served rather than arbitrated, how an invalid
      published ring is repaired, whose area is served, how a well is judged inside a
      boundary, and that both archives ship WGS 84
- [New] conformance: cr_eia_basin_link_1 links a play to its basin by case-folded exact name
      and to nothing otherwise; four of sixteen plays do not resolve and the rule records why
      each near match is refused, because a join right twelve times and quietly wrong twice
      is worse than one that reports four unresolved links
- [New] conformance: cr_eia_geometry_repair_1 repairs the two invalid published rings —
      Bakken and Three Forks, both ring self-intersections, both Williston — by ST_MakeValid
      with polygonal extraction, records each as an invalid_geometry reject and then releases
      it under the rule with the promotion derivation, so the repair is a ledger fact rather
      than a silent edit; a repair that yields no polygon is refused outright
- [New] conformance: cr_eia_well_membership_1 defines basin membership as surface-hole
      intersection with the served boundary, states that membership is a set and that a well
      inside none is unassigned, and records that canonical.wells.basin is a declared
      per-source constant and not this geometric claim
- [New] quarantine: invalid_geometry joins the reject vocabulary
- [Change] tiles: TILE_LAYERS composes BASIN_LAYERS, so the proxy allowlist, the martin
         config assertion and the wire-type audit cover the two new layers on the day they
         are declared
