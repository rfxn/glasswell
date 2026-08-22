- [New] observed rollups on the land grid (M2-3): well counts and cumulative liquid, gas
      and water summed per PLSS section and township into marts.land_metrics_tile, served
      as two tile layers with a support-aware amber choropleth (support modulates the ink,
      unobserved cells stay unpainted, never interpolated); percentile bins are cut at
      refresh and ride the tile with their edges, population and derivation handle, and
      the on-canvas key restates exactly that frame; liquid means oil plus condensate
      (cr_nd_liquids_policy_1) and says so wherever the number appears
- [New] cr_land_agg_membership_1, the section-membership decision as a conformance row:
      a well belongs to the section holding its lateral midpoint, else its surface hole —
      chosen against measured evidence (84.9% of ND laterals cross 2+ sections; 57.33% of
      well-reported ND liquid sits on wells whose midpoint and surface sections differ);
      the newest filing wins with geom_key breaking ties, grid-edge midpoint orphans
      (163 wells, 2.07M bbl) fall back to the surface hole rather than vanishing, ND
      bottomhole is ruled out by absence, and apportionment is deferred to a superseding
      rule with its Protocol 4D obligations
- [Fix] polygon labels no longer duplicate at tile seams: the land-grid and spacing-unit
      tile functions emit one anchor point per unit in the one tile that owns it, and the
      symbol layers bind to that `_label` sublayer instead of the polygon fragments
- [Fix] the land-grid panel row quotes its counts as published by BLM, so the register no
      longer presents staged totals as what was promoted
