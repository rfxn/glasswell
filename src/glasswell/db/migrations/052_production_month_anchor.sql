-- The producing classes are judged over a window anchored on the newest filed month, so every
-- request that serves one asks `max(production_month)` first. No index led with that column:
-- the api10 index leads with api10 and the vintage index with report_vintage, so the anchor
-- was a full scan — 288 ms warm at 7.2M rows on the deployed instance, before any well was
-- classed. Leading with the month makes it a one-row descending index scan.
--
-- The window scan reads the same index from the anchor forward, which is the newest end.

create index if not exists production_monthly_month_idx
    on canonical.production_monthly (production_month desc);

-- Migration 049 made publication evidence a precondition for every conformance rule, so the
-- three producing rules register theirs before the seeder inserts them. v0.61 is the first tag
-- to contain these rule ids; the commit is the `main` head they were written against, because
-- the commit that introduces a rule cannot cite its own hash.
insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
select rule_id, date '2026-08-28', 'v0.61',
       'b4b81767cbd31b9bd2d9fdde22441c40af285884'
  from unnest(array[
       'cr_producing_window_1', 'cr_producing_streams_1', 'cr_producing_evidence_1'
  ]) as rule_id
    on conflict (rule_id) do nothing;
