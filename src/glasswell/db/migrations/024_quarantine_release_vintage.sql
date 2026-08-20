-- Three corrections from gate-a1b-fp, none of which edits a migration that has already run.
--
-- 1. The ledger was not bitemporal. `supersede_pool_collisions` sets `state` in place and the
--    serving query filters `state = 'open'` with no as-of predicate, so an as-of read of a
--    vintage that predates the release stopped disclosing a withholding that was disclosed on
--    that date — it answered with an affirmative regulator zero instead. `released_at_vintage`
--    is knowledge time for the release, so a read before it still sees the row as open.
--
-- 2. Migration 020's `_latest` view ordered `report_vintage desc, derivation_id desc`. The
--    tiebreak is unreachable: the primary key contains every column the window partitions and
--    orders on, so `report_vintage` cannot tie inside a partition. Believing otherwise is what
--    made a same-vintage re-promotion look safe. The order is now the reachable one, and the
--    unreachable claim is gone rather than left as decoration.
--
-- 3. Nothing tied `entity_type` to `reporting_level`, so a lease row could assert it was
--    observed at the well. Latent today - every row is consistent - and load-bearing at P7a.

alter table lineage.quarantine_rows add column released_at_vintage date;

comment on column lineage.quarantine_rows.released_at_vintage is
    'Knowledge time of the release, so an as-of read before it still sees the row as open'
    ' (DIR-2). Null while the row is open.';

create index quarantine_rows_release_idx
    on lineage.quarantine_rows (source_id, reason_code, released_at_vintage);

create or replace view canonical.production_monthly_latest as
select api10, production_month, stream, source_id, report_vintage, volume, unit, days_produced,
       granularity, value_hash, source_manifest_id, derivation_id, created_at, null_semantics,
       entity_type, entity_key, reporting_level, well_completion_pool, aggregation
  from (select p.*,
               row_number() over (
                   partition by entity_type, entity_key, production_month, stream, source_id
                   order by report_vintage desc) as vintage_rank
          from canonical.production_monthly p) ranked
 where vintage_rank = 1;

alter table canonical.production_monthly
    add constraint production_monthly_entity_level_check
        check ((entity_type = 'well'
                and reporting_level in ('well', 'well_completion_pool'))
            or (entity_type = 'well_completion_pool'
                and reporting_level = 'well_completion_pool')
            or (entity_type = 'lease' and reporting_level = 'lease'));

comment on constraint production_monthly_entity_level_check on canonical.production_monthly is
    'A well row may report at pool level - that is the sum_over_pools case - but no other'
    ' pairing is meaningful, and a lease row can never claim a well observation (S-B, DIR-3).';
