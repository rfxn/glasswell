- [Fix] canonical.production_monthly_latest re-ranked the whole table for a one-well read
      (73 s warm / 156 s cold at 17.6M rows) because api10 was not in its PARTITION BY;
      migration 031 adds it, so an api10 predicate now prunes to the index — no output
      row changes, a well's entity_key is its api10 by 020's trigger (DR-79)
- [Fix] A second same-day ND run understated the vintage ledger: repromote, monthly
      ingest and every GIS layer wrote one run's totals under an upsert keyed per
      vintage-day; counters now accumulate onto the day's row and a no-op run leaves it
      alone, the shape NM's D2 fix set (DR-78)
- [New] ND completion rows are pinned to the month grain: a guard test asserts every
      nd_mpr well_completions row carries a production_month and no effective_from
      under migration 029's two-grain CHECK (DR-80, gate-nm-p5 round-2 O1)
