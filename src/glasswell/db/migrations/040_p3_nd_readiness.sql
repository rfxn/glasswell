-- Columns added to canonical.wells after migration 009 are not inherited by its explicit view
-- projection. Keep the view as an explicit contract, but refresh it whenever the table grows.

create or replace view canonical.wells_latest as
select api10, api14, state_code, county_code_at_permit, ndic_file_no, operator_name_reported,
       operator_id, well_name, status_canonical, status_reported, well_type_reported, spud_date,
       confidential_flag, basin, land_unit_label, effective_from, source_manifest_id,
       derivation_id, created_at, total_depth_ft, completion_date
  from (select w.*,
               row_number() over (partition by api10 order by effective_from desc,
                                  derivation_id desc) as effective_rank
          from canonical.wells w) ranked
 where effective_rank = 1;

comment on view canonical.wells_latest is
    'Current effective-dated well rows, including columns added after the original ND slice.';

create table staging.fracfocus_disclosures (
    manifest_id                 text not null references lineage.manifests (manifest_id),
    source_row_ordinal          integer not null,
    disclosure_id              text,
    job_start_date              text,
    job_end_date                text,
    api_number                  text,
    state_name                  text,
    county_name                 text,
    operator_name               text,
    well_name                   text,
    latitude                    text,
    longitude                   text,
    projection                  text,
    tvd                         text,
    total_base_water_volume     text,
    total_base_non_water_volume text,
    ff_version                  text,
    federal_well                text,
    indian_well                 text,
    ingested_at                 timestamptz not null default now(),
    primary key (manifest_id, source_row_ordinal)
);

create index fracfocus_disclosures_api_idx
    on staging.fracfocus_disclosures (api_number, manifest_id);

create table canonical.well_completion_anchors (
    disclosure_id      text not null,
    api10              text not null,
    job_start_date     date,
    completion_date    date not null,
    anchor_kind        text not null check (anchor_kind = 'hydraulic_frac_job_end'),
    source_id          text not null references lineage.sources (source_id),
    report_vintage     date not null,
    source_manifest_id text not null references lineage.manifests (manifest_id),
    derivation_id      text not null references lineage.derivations (derivation_id),
    created_at         timestamptz not null default now(),
    primary key (disclosure_id, source_id, report_vintage)
);

comment on table canonical.well_completion_anchors is
    'Source completion events used as pre-production anchors; FracFocus rows are hydraulic-frac'
    ' job-end dates, never spud or first-production proxies.';

create index well_completion_anchors_api_idx
    on canonical.well_completion_anchors (api10, completion_date, report_vintage);

create trigger well_completion_anchors_append_only
    before update or delete on canonical.well_completion_anchors
    for each row execute function lineage.reject_mutation();

create view canonical.well_completion_anchors_latest as
select disclosure_id, api10, job_start_date, completion_date, anchor_kind, source_id,
       report_vintage, source_manifest_id, derivation_id, created_at
  from (select a.*,
               row_number() over (
                   partition by disclosure_id, source_id
                   order by report_vintage desc, derivation_id desc) as vintage_rank
          from canonical.well_completion_anchors a) ranked
 where vintage_rank = 1;

alter table lineage.formation_aliases add column formation_group text;

comment on column lineage.formation_aliases.formation_group is
    'Benchmark peer group resolved from the reported pool; ambiguous and sub-threshold pools'
    ' use __other__ rather than being forced into a principal target.';

insert into canonical.well_completions
    (completion_key, api10, well_completion_pool, pool_reported, source_id, production_month,
     report_vintage, source_manifest_id, derivation_id)
select distinct on (p.api10, p.well_completion_pool, p.production_month, p.report_vintage)
       p.api10 || ':' || p.well_completion_pool, p.api10, p.well_completion_pool,
       p.well_completion_pool, p.source_id, p.production_month, p.report_vintage,
       p.source_manifest_id, p.derivation_id
  from canonical.production_monthly p
 where p.source_id = 'nd_mpr_xlsx'
   and p.api10 is not null
   and p.well_completion_pool is not null
 order by p.api10, p.well_completion_pool, p.production_month, p.report_vintage,
          p.derivation_id desc
on conflict do nothing;

grant select, insert, delete on staging.fracfocus_disclosures to glasswell_pipeline;
grant select, insert on canonical.well_completion_anchors to glasswell_pipeline;
grant select on canonical.well_completion_anchors,
    canonical.well_completion_anchors_latest to glasswell_api;
revoke update, delete on canonical.well_completion_anchors from glasswell_pipeline, glasswell_api;
