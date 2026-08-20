-- S-E: canonical.production_monthly is keyed by the entity that reported, not by API-10.
-- Migration 008's key is correct for ND and only for ND. It cannot represent a TX lease row,
-- it cannot hold the two pool filings one API-10 makes in one month (fp-audit D1: 78 wells,
-- 454 well-months, 139,644 bbl served as zero), and it omits source_id, which change-only
-- append needs once two sources report the same entity-month on independent vintages.
--
-- reporting_level is S-B's second axis. granularity stays the composed serving token that
-- migration 012 legislated and the serializer validates; the composition CHECK below is what
-- makes S-B's "canonical never estimates" mechanically checkable rather than a convention.
--
-- The backfill is a generated column that is then de-generated, not an UPDATE: the append-only
-- trigger is never disarmed, and no column an earlier vintage wrote is touched (DIR-2).

alter table canonical.production_monthly
    add column entity_type          text not null default 'well',
    add column reporting_level      text not null default 'well',
    add column well_completion_pool text,
    add column aggregation          text;

alter table canonical.production_monthly
    add column entity_key text generated always as (api10) stored;

alter table canonical.production_monthly alter column entity_key drop expression;
alter table canonical.production_monthly alter column entity_key set not null;

alter table canonical.production_monthly drop constraint production_monthly_pkey;

alter table canonical.production_monthly
    add primary key (entity_type, entity_key, production_month, stream, source_id,
                     report_vintage);

-- api10 is retained denormalised (S-E); a lease row has no well to name. Only possible once
-- the old key that held it has been dropped.
alter table canonical.production_monthly alter column api10 drop not null;

alter table canonical.production_monthly
    add constraint production_monthly_entity_type_check
        check (entity_type in ('well', 'lease', 'well_completion_pool')),
    add constraint production_monthly_reporting_level_check
        check (reporting_level in ('well', 'lease', 'well_completion_pool')),
    add constraint production_monthly_entity_pool_check
        check (entity_type <> 'well_completion_pool' or well_completion_pool is not null),
    add constraint production_monthly_granularity_composition_check
        check ((reporting_level in ('well', 'well_completion_pool')
                and granularity = 'well_observed')
            or (reporting_level = 'lease' and granularity = 'lease_reported')),
    add constraint production_monthly_aggregation_check
        check (aggregation is null
            or (aggregation = 'sum_over_pools'
                and entity_type = 'well'
                and reporting_level = 'well_completion_pool'
                and well_completion_pool is null));

comment on column canonical.production_monthly.entity_type is
    'What the row is about: well, lease, or well_completion_pool (§3.0.2, S-E).';
comment on column canonical.production_monthly.entity_key is
    'The entity''s key. For entity_type = well it is the API-10; composite keys are built by a'
    ' key_composite conformance rule, never by a literal in the parser (R8).';
comment on column canonical.production_monthly.reporting_level is
    'The level the source reported at (S-B). A well row whose reporting_level is'
    ' well_completion_pool was summed from pool rows and says so in aggregation.';
comment on column canonical.production_monthly.aggregation is
    'sum_over_pools where a well figure is the exact sum of its pool rows under'
    ' cr_nd_pool_rollup_1. Null means the row is a single filing, not an aggregate.';
comment on constraint production_monthly_granularity_composition_check
    on canonical.production_monthly is
    'S-B/DIR-3: canonical carries observations only, so the composed token is a function of'
    ' reporting_level. lease_allocated is an allocation artifact and never a canonical row.';

create index production_monthly_api10_idx
    on canonical.production_monthly (api10, production_month, stream);

create index production_monthly_pool_idx
    on canonical.production_monthly (api10, well_completion_pool, production_month)
 where entity_type = 'well_completion_pool';

-- A well's entity key is its API-10 by the definition of entity_type = 'well'. This keeps a
-- direct well-level insert honest without letting any other entity key itself by accident.
create function canonical.production_entity_key_default() returns trigger
language plpgsql as $$
begin
    if new.entity_key is null then
        if new.entity_type <> 'well' then
            raise exception
                'entity_key is required for entity_type %; build it with a key_composite rule',
                new.entity_type;
        end if;
        new.entity_key := new.api10;
    end if;
    return new;
end;
$$;

create trigger production_monthly_entity_key_default
    before insert on canonical.production_monthly
    for each row execute function canonical.production_entity_key_default();

-- SB-01 H2: the tiebreak after report_vintage is derivation_id, not created_at. Wall-clock is
-- not replay-stable, so it silently breaks R7 for any re-promotion at the same vintage.
create or replace view canonical.production_monthly_latest as
select api10, production_month, stream, source_id, report_vintage, volume, unit, days_produced,
       granularity, value_hash, source_manifest_id, derivation_id, created_at, null_semantics,
       entity_type, entity_key, reporting_level, well_completion_pool, aggregation
  from (select p.*,
               row_number() over (
                   partition by entity_type, entity_key, production_month, stream, source_id
                   order by report_vintage desc, derivation_id desc) as vintage_rank
          from canonical.production_monthly p) ranked
 where vintage_rank = 1;

insert into lineage.audit_events (event_id, occurred_at, actor, event_type, subject_type,
                                  subject_id, payload)
select 'evt_migration_020_production_entity_key', now(), 'system:migration',
       'conformance.rule_applied_summary', 'dataset', 'canonical.production_monthly',
       jsonb_build_object('migration', '020_production_entity_key',
                          'backfilled_rows', count(*),
                          'entity_type', 'well',
                          'entity_key', 'api10',
                          'reporting_level', 'well',
                          'ruling', 'reconciliation.md S-E')
  from canonical.production_monthly
having count(*) > 0;
