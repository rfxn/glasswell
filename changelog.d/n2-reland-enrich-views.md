- [New] GET /v1/wells/{api10}/cumulatives: per-well cumulative oil, gas and water,
      each a figure carrying its unit, its liquids basis and the mart snapshot
      vintage it was built at, beside four month counts per stream that reconcile
      to the span; reported, reported_zero, no_report and withheld stay four
      distinct served facts and only the first two enter a total
- [New] a well that has never filed anything is served with a null cumulative and
      coverage_outcome never_reported rather than a zero or a 404, and a well
      outside the mart's states is refused by name rather than served an empty
      total that would read as no production
- [New] a cumulative_behind_series warning naming both vintages and the month
      count wherever canonical already holds filings the snapshot has not
      absorbed, so a reader summing the live series is not left to find the gap by
      arithmetic
- [New] GET /v1/wells/vintage-cohorts: wells, the wells whose record admits a month
      into those totals, and cumulative volumes per cohort, all three keyed by
      cr_nd_vintage_cohort_1 - which rules the support measure as well as the
      cohort key, so neither is decided in a query - on the spud year with
      its measured rationale and its rejected alternative served at
      /v1/conformance; the no-spud-date cohort is its own, never folded into a
      year, and the Montana truncation is stated inside data rather than only in a
      warning a copied payload would lose
- [New] Protocol 4D on the cohort rollup: spacing_assumption is stated as
      inapplicable with its reason, and support_distribution uses cohort-scale
      bands because the PLSS section scale puts 73 of the 94 measured ND cohorts
      in one class
- [New] canonical.well_completion_design promotes the FracFocus base water volume
      under cr_ff_base_water_units_1 and cr_ff_design_promote_1: a blank promotes
      as no_report rather than as a zero, and a non-numeric literal, a duplicate
      disclosure or a volume above the measured 50,000,000 gal bound is
      quarantined with a reason rather than dropped
- [New] fluid intensity per lateral foot on /v1/wells/{api10}/completions under
      cr_ff_fluid_intensity_1, which declares a 1,000 ft divisor floor and a 5,000
      gal/ft ceiling; no ND well has a zero summed lateral, so a divide-by-zero
      guard would fire on nothing while the measured 0.24 ft minimum would serve
      26 M gal/ft as a handled figure. An absent numerator is reported as the
      source classified it, so a withheld volume yields a withheld intensity and
      never an undisclosed one
- [New] marts.well_cumulatives and marts.well_withholding carry no state regex and
      an explicit state_code, so a second jurisdiction widens a Python constant
      rather than altering shipped DDL
- [New] glasswell-fracfocus --promote-design promotes completion design from
      staging already resident on the host with no fetch, and states its outcome
      rather than failing where the 440 MB archive has never been pulled
- [New] deploy.sh populates the cumulative marts and backfills completion design
      before verify.sh and smoke.sh run, and verify.sh asserts both marts are
      non-empty; the design check reports pending rather than failing on a host
      with no staged ND disclosures
- [Change] design_availability reads promoted. It is a statement about the
         release, not about the well: per-well absence is design null with
         design_null_semantics, which is the right grain for a per-well fact
- [Change] the per-well cumulative has one definition. marts.cumulatives owns it
         and land_metrics reads it rather than its own copy; the predicate names
         what the total admits instead of relying on a NOT NULL column's fill
         value staying zero. per_well_cumulative_cte takes the membership CTE to
         bound its scan, so the land grid keeps the restriction that stops it
         reading 24.8M rows it discards
- [Fix] the well card rejected any design_availability other than not_promoted and
      replaced the whole completion panel with 'unavailable', so promoting the
      design server-side would have removed the panel from every card
- [Change] a saved handle from a cumulative, cohort or intensity figure resolves
         through an api.respond derivation, which lineage.sweep_ephemeral_derivations
         deletes once unreferenced and older than 90 days; the same inherited
         behaviour as the existing well-detail and status-summary figures
- [Change] the N2 migration lands as 072_n2_enrich_views.sql. The track branched
         at v0.64 and main's head migration is 070; discover_migrations refuses a
         duplicate version as well as a gap
- [Change] the completion-design and fluid-intensity sections are re-expressed
         inside the well flyout's section grammar rather than the panel they were
         written against: short empty states, a scope line of dense facts, and no
         prose paragraph where the flyout carries none
- [New] the well flyout carries a cumulative row under monthly production: oil, gas
      and water as three figures, each with its own derivation handle, over a scope
      line stating the window, the months admitted and the mart snapshot; a stream
      with no admitted month reads withheld or no report and never a zero, and a
      well that never filed reads as such rather than as three zeroes
- [New] /v1/wells/{api10} links to cumulatives only where the mart holds a total, so
      a client reads the link rather than testing the API prefix itself and a
      jurisdiction outside the mart is never rendered as a well that produced nothing
