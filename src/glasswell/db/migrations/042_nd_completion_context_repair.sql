-- Migration 040 could only backfill ND completion entities from production rows that already
-- carried well_completion_pool. Historical single-pool rows predate that field, even though
-- their source-faithful pool remains in staging.nd_mpr_oil. Repair only when the staged row and
-- canonical well-month cite the same manifest and API-10. The production month, knowledge
-- vintage, and derivation all come from that canonical observation; no pool, date, or identity
-- is inferred from another filing.

with staged_pools as materialized (
    select distinct s.manifest_id,
           left(s.api_wellno, 10) as api10,
           btrim(s.pool) as pool_reported
      from staging.nd_mpr_oil s
     where s.api_wellno ~ '^[0-9]{10,14}$'
       and nullif(btrim(s.pool), '') is not null
), source_observations as materialized (
    select distinct on (
               p.source_manifest_id, p.api10, s.pool_reported, p.production_month,
               p.report_vintage
           )
           p.source_manifest_id, p.api10, s.pool_reported, p.production_month,
           p.report_vintage, p.derivation_id
      from canonical.production_monthly p
      join staged_pools s
        on s.manifest_id = p.source_manifest_id
       and s.api10 = p.api10
     where p.source_id = 'nd_mpr_xlsx'
       and p.entity_type = 'well'
     order by p.source_manifest_id, p.api10, s.pool_reported, p.production_month,
              p.report_vintage, p.derivation_id desc
)
insert into canonical.well_completions
    (completion_key, api10, well_completion_pool, pool_reported, source_id, production_month,
     report_vintage, source_manifest_id, derivation_id)
select o.api10 || ':' || o.pool_reported, o.api10, o.pool_reported, o.pool_reported,
       'nd_mpr_xlsx', o.production_month, o.report_vintage, o.source_manifest_id,
       o.derivation_id
  from source_observations o
on conflict do nothing;
