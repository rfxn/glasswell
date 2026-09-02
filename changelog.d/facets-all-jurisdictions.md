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
