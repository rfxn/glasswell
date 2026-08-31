- [New] `GET /v1/wells/facets` counts wells by a dimension for one state — operator, county,
      status, well type or completion year — ranked, searchable and sortable, with every
      bucket count, the truncation remainder, the named absence bucket and the scoped total
      served as figures carrying derivation handles that `?explain=true` resolves
- [New] The explorer's wells dataset carries a "Wells by …" panel above the grid: the leading
      values with counts and proportion bars, a caption stating what the list is a cut of, and
      a bucket click that narrows the grid beside it to exactly that bucket
- [New] Truncation is counted rather than implied: `remainder` states how many values fall
      below the cut and how many wells they hold, `distinct_values` states how many the state
      holds in total, and with no search in force `buckets` + `remainder` + `absence` sum to
      `wells`; under a search the absence bucket stays outside it, so `buckets` + `remainder`
      sum to `matched_wells` and the served description says which reconciliation applies
- [New] Wells whose dimension has no value are their own named bucket, outside the ranking and
      outside the search — on the current Texas load 70,039 wells report no operator, more
      than any real operator holds, so ranking it would have put a non-operator at the top and
      dropping it would have broken the sum
- [New] `cr_tx_operator_absence_1` registers what a missing Texas operator means: not reported,
      never withheld and never imputed, measured at 39,390 wells whose EWA wellbore record
      carries an empty operator field and 30,649 that reach canonical from a county GIS layer
      with no EWA record at all; Montana's `cr_mt_operator_absence_1` already stated the same
      for its source and is cited beside it
- [New] `/v1/wells` accepts `state`, an exact API state-code filter, so a facet bucket's link
      narrows to the state the bucket was counted in
- [New] Migration 070 adds `wells_facet_dimensions_idx`, a covering index over
      `canonical.wells` that answers the facet aggregate index-only with no heap fetches;
      measured on the deployed database the top-15 Texas operator facet falls from 269,438
      shared buffers and 459 ms to 5,717 buffers and 354 ms
- [Change] Scope is one state and is required. Operator names arrive per source and
           `lineage.operator_aliases` carries no row for any state served, so summing a company
           across a state border would be an aliasing decision no conformance rule has made
- [Change] A state the spine holds no wells for is refused with the loaded states named, rather
           than answered with an empty list — New Mexico's promotion is gated, and "no wells
           loaded" is a different fact from "no operators found". The refusal carries the state
           list as an RFC 9457 extension member so the picker survives it
- [Change] Search runs over every value in the state before the ranking, not over the served
           page: with 9,369 Texas operators a page-scoped search would answer "no such
           operator" for the 9,354 it never loaded
- [Change] Explorer route bundle budget re-measured 71,500 → 75,000 B gzipped for the panel,
           which is on the route rather than split behind a dynamic import because it renders
           on the dataset the explorer opens on
- [Fix] An empty string in a facet dimension is treated as an absent value rather than a bucket
      with no name, which would have ranked among the real values and minted a handle whose
      selector the grammar cannot address
