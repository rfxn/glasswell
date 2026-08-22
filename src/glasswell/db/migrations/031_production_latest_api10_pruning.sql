-- DR-79: a predicate on api10 could not be pushed below the WindowAgg because api10 was not
-- in the PARTITION BY, so a one-well read re-ranked the whole table (73 s warm / 156 s cold
-- at 17.6M rows on glasswell_d1; d1-p5-status.md §7). api10 is fixed within every
-- (entity_type, entity_key): a well's entity_key IS its api10 (020's trigger), a pool
-- entity's key embeds it, and a lease row's is null — so adding it splits no partition and
-- changes no output row, while letting the planner prune to production_monthly_api10_idx.

create or replace view canonical.production_monthly_latest as
select api10, production_month, stream, source_id, report_vintage, volume, unit, days_produced,
       granularity, value_hash, source_manifest_id, derivation_id, created_at, null_semantics,
       entity_type, entity_key, reporting_level, well_completion_pool, aggregation
  from (select p.*,
               row_number() over (
                   partition by api10, entity_type, entity_key, production_month, stream,
                                source_id
                   order by report_vintage desc) as vintage_rank
          from canonical.production_monthly p) ranked
 where vintage_rank = 1;
