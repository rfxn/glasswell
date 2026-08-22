- [Fix] the three remaining same-day vintage-ledger upsert-without-accumulation
      sites route through record_vintage_day: the NM dimension close, TX GIS county
      loads and TX wellbore exports now sum counters and union manifest ids onto the
      one (source, day) row instead of overwriting the pass that did the work; the
      no-op guard holds at all three (DR-85, class from gate-a1b claim 3)
- [Change] ingest.base record_vintage_day returns the written VintageRecord — None
         when the no-op guard leaves the row alone — so a caller can cite the
         vintage_id it wrote instead of reconstructing it
