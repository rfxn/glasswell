- [Change] status collector: canonical.production_monthly is inventoried by one bounded query
           per registered source instead of one multi-arm filtered aggregate over the whole
           table; measured 60,571 ms to 3,474 ms at 29,580,309 rows, with the whole-table sort
           (1.88 GB spilled to temp files) removed rather than made cheaper
- [New] migration 069: production_monthly (source_id, entity_key) and
      (source_id, created_at desc) indexes, so the per-source arms run index-only with no heap
      fetch; max(created_at) was the column that forced the heap, costing 25,934 ms for one
      source against 596 ms without it
- [New] cr_nd_inventory_jurisdiction_1, cr_nm_wcproduction_inventory_jurisdiction_1,
      cr_mt_inventory_jurisdiction_1 and cr_mt_pru_inventory_jurisdiction_1 register which
      jurisdiction each source's production rows are counted under (R8); a new state registers
      a source and a rule and is inventoried without editing the collector
- [Change] production inventory counts distinct entity_key rather than distinct api10, so the
           Montana PRU lease grain is counted on the identity it carries; an API-10 prefix
           predicate reached none of its 4,808,814 rows
- [Change] New Mexico's production entity metric is labelled as completion-pool entities rather
           than wells, because that is the grain the source files and glasswell rolls none of it
           up to the well
