-- SB-01 E5 / S-E: `well_completion_pool` appears in the §3.4.3 entity enum with no defining
-- entity and no table anywhere, which makes it unimplementable. NM — the first Permian basin
-- under DIR-9's inverted ordering — reports at exactly this granularity, so the gap blocks P7a.
--
-- The row is an observation about a completion at a knowledge vintage, so the table is
-- vintaged and append-only like every other canonical relation; the _latest view resolves it.

-- Grain is one observation per completion-month, not one row per completion: a completion's
-- first and last producing months are min() and max() over this table, and deriving them keeps
-- the table append-only with no upsert to widen a range.
create table canonical.well_completions (
    completion_key       text not null,
    api10                text not null,
    well_completion_pool text not null,
    pool_reported        text,
    source_id            text not null references lineage.sources (source_id),
    production_month     date not null,
    report_vintage       date not null,
    source_manifest_id   text not null references lineage.manifests (manifest_id),
    derivation_id        text not null references lineage.derivations (derivation_id),
    created_at           timestamptz not null default now(),
    primary key (completion_key, source_id, production_month, report_vintage)
);

comment on table canonical.well_completions is
    'The well_completion_pool entity (§3.0.2, SB-01 E5). completion_key is the S-E entity_key'
    ' of the production rows that report this completion.';
comment on column canonical.well_completions.pool_reported is
    'The pool label exactly as the source wrote it, before any vocabulary mapping.';

create index well_completions_api10_idx on canonical.well_completions (api10, production_month);

create trigger well_completions_append_only
    before update or delete on canonical.well_completions
    for each row execute function lineage.reject_mutation();

create view canonical.well_completions_latest as
select completion_key, api10, well_completion_pool, pool_reported, source_id, production_month,
       report_vintage, source_manifest_id, derivation_id, created_at
  from (select c.*,
               row_number() over (
                   partition by completion_key, source_id, production_month
                   order by report_vintage desc, derivation_id desc) as vintage_rank
          from canonical.well_completions c) ranked
 where vintage_rank = 1;

grant select, insert on canonical.well_completions to glasswell_pipeline;
grant select on canonical.well_completions, canonical.well_completions_latest to glasswell_api;
revoke update, delete on canonical.well_completions from glasswell_pipeline, glasswell_api;
