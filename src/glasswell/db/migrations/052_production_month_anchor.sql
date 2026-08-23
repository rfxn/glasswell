-- The producing classes are judged over a window anchored on the newest filed month, so every
-- request that serves one asks `max(production_month)` first. No index led with that column:
-- the api10 index leads with api10 and the vintage index with report_vintage, so the anchor
-- was a full scan — 288 ms warm at 7.2M rows on the deployed instance, before any well was
-- classed. Leading with the month makes it a one-row descending index scan.
--
-- The window scan reads the same index from the anchor forward, which is the newest end.

create index if not exists production_monthly_month_idx
    on canonical.production_monthly (production_month desc);
