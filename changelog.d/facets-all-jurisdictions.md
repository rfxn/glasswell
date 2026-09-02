- [New] `/v1/wells/facets` counts across a set of jurisdictions: repeat `state`,
      comma-separate the codes, or send `all` for every registered jurisdiction the
      spine carries wells for, resolved from the registry at request time
- [New] `/v1/wells/facets` serves `jurisdictions`: the set the counts were taken
      over, each one's wells, and whether it carries the dimension, reports none of
      it under a registered rule, or reports none with nothing registered (R8)
- [New] the Wells-by panel offers `All jurisdictions` and takes several at once on
      Explore and on the map sheet; `wb.state` carries `all` or a comma list, and a
      jurisdiction that reports nothing at all is named under the ranking with its
      wells and the rule that took them out of the "not reported" bucket
- [Change] `/v1/wells` accepts the same `state` set grammar, so a facet bucket link
         narrows the collection to exactly the jurisdictions the bucket was counted
         over; a single code behaves as it did, and the page cursor is fingerprinted
         over the normalised set so two spellings of one scope are one traversal
- [Change] the facet scope is deduped per (state_code, api10), the order
         `wells_facet_dimensions_idx` answers index-only over a set: measured on the
         deployed 585,864 wells at 12,780 buffers and 592 ms against 279,288 and
         1,031 ms for the api10-only partition (web/PERF.md §7)
- [Fix] a jurisdiction contributing no well to the scope is served as
      `no_wells_in_scope` rather than `absent_by_rule`: under an `as_of` before its
      promotion the emptiness is the knowledge cut's, and blaming a conformance rule
      for it is a claim with no row behind it
- [Change] `canonical.status_resolution` is registry-driven: it resolves every
         jurisdiction whose status-vocabulary rule says `resolved_at: read_time`,
         reading the mapping table and its key and value columns out of that rule's own
         spec, so a later jurisdiction registers rows rather than redefining the view
- [Change] `wells_facet_dimensions_idx` carries `status_reported`, and
         `canonical.status_resolution` is backed by a relation keyed on (state, reported
         code) rather than a view; the status facet over a set of states goes from an index
         scan with a heap visit per row to an index-only scan with a keyed resolver lookup,
         measured at 809,191 rows as 32,598 buffers and 1,285 ms against 12,484 and 818 ms
