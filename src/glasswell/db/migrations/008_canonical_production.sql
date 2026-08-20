-- Bitemporal production observations and the vintage ledger (SB-07 §3, DIR-2).

create table canonical.production_monthly (
    api10              text not null,
    production_month   date not null,
    stream             text not null check (stream in ('oil', 'gas', 'water')),
    source_id          text not null references lineage.sources (source_id),
    report_vintage     date not null,
    volume             numeric(18, 3) not null,
    unit               text not null,
    days_produced      smallint,
    granularity        text not null check (granularity in ('well_observed', 'lease_reported')),
    value_hash         text not null,
    source_manifest_id text not null references lineage.manifests (manifest_id),
    derivation_id      text not null references lineage.derivations (derivation_id),
    created_at         timestamptz not null default now(),
    primary key (api10, production_month, stream, source_id, report_vintage)
);

comment on column canonical.production_monthly.production_month is 'Valid time.';
comment on column canonical.production_monthly.report_vintage is
    'Knowledge time, equal to the manifest fetch_vintage that opened it.';
comment on column canonical.production_monthly.created_at is
    'Breaks report_vintage ties after a re-promotion under a corrected rule (§3.6).';

create index production_monthly_vintage_idx
    on canonical.production_monthly (report_vintage, production_month);

create trigger production_monthly_append_only
    before update or delete on canonical.production_monthly
    for each row execute function lineage.reject_mutation();

-- Default serving view. As-of reads apply the same window with report_vintage <= :as_of.
create view canonical.production_monthly_latest as
select api10, production_month, stream, source_id, report_vintage, volume, unit, days_produced,
       granularity, value_hash, source_manifest_id, derivation_id, created_at
  from (select p.*,
               row_number() over (
                   partition by api10, production_month, stream, source_id
                   order by report_vintage desc, created_at desc) as vintage_rank
          from canonical.production_monthly p) ranked
 where vintage_rank = 1;

create table lineage.vintages (
    vintage_id              text primary key,
    source_id               text not null references lineage.sources (source_id),
    vintage_date            date not null,
    manifest_ids            text[] not null default '{}',
    opened_at               timestamptz not null,
    promotion_derivation_id text references lineage.derivations (derivation_id),
    rows_examined           bigint not null default 0,
    rows_appended           bigint not null default 0,
    months_touched          text[] not null default '{}',
    restatement_summary     jsonb not null default '{}'::jsonb,
    unique (source_id, vintage_date)
);

grant select, insert on canonical.production_monthly to glasswell_pipeline;
grant select on canonical.production_monthly, canonical.production_monthly_latest
    to glasswell_api;
revoke update, delete on canonical.production_monthly from glasswell_pipeline, glasswell_api;

grant select, insert, update on lineage.vintages to glasswell_pipeline;
grant select on lineage.vintages to glasswell_api;
