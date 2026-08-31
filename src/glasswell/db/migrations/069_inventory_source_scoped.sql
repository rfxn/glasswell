-- The status collector counted canonical.production_monthly with one multi-arm filtered
-- aggregate per table. A FILTER clause is evaluated above the scan, so every arm read every
-- row: at 29,580,309 rows the production arm seq-scanned 7.6 GB and sorted all of it by api10
-- to answer count(distinct), spilling 1.88 GB to temp files. Measured 60,571 ms. Each new
-- state added arms to the same aggregate, so the cost grew with the union of all states rather
-- than with the state being counted.
--
-- The replacement asks one bounded question per registered source. That only pays if each
-- question is answerable from an index without touching the heap, which needs two more:
--
--   (source_id, entity_key)      count(distinct entity_key) from presorted index order, so the
--                                sort disappears rather than moving.
--   (source_id, created_at desc) max(created_at) as a one-row backward scan. This column is the
--                                reason the whole arm was expensive: no existing index carries
--                                it, so asking for it alongside the others turned an index-only
--                                scan into a bitmap heap scan over 233,018 pages — measured
--                                25,934 ms for one source, against 596 ms for the same query
--                                without it.
--
-- (source_id, production_month) already exists from migration 028 and answers count(*),
-- count(distinct production_month) and the valid-time bounds. Together the three cover the
-- inventory without a heap fetch. Sizes at 29.6M rows: 203 MB and 202 MB, against a 7,643 MB
-- table — btree deduplication carries them, because both lead with a column of three values.

-- `if not exists` so an operator can build both CONCURRENTLY ahead of the migrate and have this
-- no-op: migrate.py runs each migration inside one transaction, which CONCURRENTLY cannot join,
-- and a plain build holds a SHARE lock against writes to a 7.6 GB table for its whole duration.

create index if not exists production_monthly_source_entity_idx
    on canonical.production_monthly (source_id, entity_key);

create index if not exists production_monthly_source_created_idx
    on canonical.production_monthly (source_id, created_at desc);

comment on index canonical.production_monthly_source_entity_idx is
    'Distinct reporting entities per source without a heap fetch. entity_key, not api10: the'
    ' Montana PRU grain carries a lease key and no API-10 at all, and a prefix filter reaches'
    ' none of its rows.';
comment on index canonical.production_monthly_source_created_idx is
    'Latest knowledge time per source as a one-row backward scan.';

-- Which jurisdiction a production row belongs to stops being a predicate in the collector and
-- becomes the registered jurisdiction of the source that filed it. That is a cross-source
-- mapping decision under R8, so it is a rule per source rather than a literal in Python, and
-- the next state registers a row instead of adding an arm.
--
-- Publication evidence is a placeholder until the merge train repoints it. The tag below reads
-- UNRELEASED and the commit is forty zeros — the repository's agreed placeholder literals — and
-- `make release-check` refuses while they stand. Naming them here is safe because the guard
-- scans for the quoted SQL literals, not the bare words. `published_vintage` is NOT
-- placeholdered: it has no placeholder form, and migration 049 defines knowledge time as the
-- day the tag is cut.
--
-- REPOINT CHECKLIST (integrator, at the merge train):
--   1. evidence_tag -> the tag that first carries the four rule ids below
--   2. evidence_commit -> the first commit on main that contains these rules, which is the
--      merge commit and not the head this branch was written against: the tag has to contain
--      what evidence_commit names, and `make release-check` says so in those words
--   3. published_vintage -> confirm it is the date that tag is cut, or correct it
-- The rule ids themselves are immutable and must not change during the repoint.
insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
select rule_id, date '2026-08-31', 'UNRELEASED',
       '0000000000000000000000000000000000000000'
  from unnest(array[
       'cr_nd_inventory_jurisdiction_1', 'cr_nm_wcproduction_inventory_jurisdiction_1',
       'cr_mt_inventory_jurisdiction_1', 'cr_mt_pru_inventory_jurisdiction_1'
  ]::text[]) rule_id
on conflict (rule_id) do nothing;
