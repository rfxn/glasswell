-- The ND slice: staging, canonical, marts and the rule lookups. All slice DDL lands here
-- because discover_migrations refuses gaps, so a cut phase must not be able to leave one.

create table staging.nd_mpr_oil (
    manifest_id        text not null references lineage.manifests (manifest_id),
    source_row_ordinal integer not null,
    ingested_at        timestamptz not null default now(),
    report_date        text,
    api_wellno         text,
    file_no            text,
    company            text,
    well_name          text,
    quarter            text,
    section            text,
    township           text,
    range              text,
    county             text,
    field_name         text,
    pool               text,
    oil                text,
    wtr                text,
    days               text,
    runs               text,
    gas                text,
    gas_sold           text,
    flared             text,
    lat                text,
    long               text,
    primary key (manifest_id, source_row_ordinal)
);

comment on table staging.nd_mpr_oil is
    'Every column text: staging is source-faithful and holds no opinions (blueprint §3.4.2).';

create table staging.nd_gis_wells (
    manifest_id        text not null references lineage.manifests (manifest_id),
    source_row_ordinal integer not null,
    ingested_at        timestamptz not null default now(),
    fileno             text,
    api_no             text,
    operator           text,
    well_name          text,
    td                 text,
    spud_date          text,
    field_name         text,
    qq                 text,
    sec                text,
    twp                text,
    rng                text,
    feet_ns            text,
    fnsl               text,
    feet_ew            text,
    fewl               text,
    latitude           text,
    longitude          text,
    well_type          text,
    status             text,
    api                text,
    county             text,
    symbol             text,
    geom               geometry(Point, 4326),
    primary key (manifest_id, source_row_ordinal)
);

create table staging.nd_gis_laterals (
    manifest_id        text not null references lineage.manifests (manifest_id),
    source_row_ordinal integer not null,
    ingested_at        timestamptz not null default now(),
    linekey            text,
    fileno             text,
    shape_leng         text,
    geom               geometry(LineString, 4326),
    primary key (manifest_id, source_row_ordinal)
);

comment on column staging.nd_gis_laterals.shape_leng is
    'Degrees, not a length. Never served or compared; see rule cr_nd_compute_crs_1.';

create table staging.nd_gis_spacing_units (
    manifest_id        text not null references lineage.manifests (manifest_id),
    source_row_ordinal integer not null,
    ingested_at        timestamptz not null default now(),
    formation          text,
    refcode            text,
    caseno             text,
    orderno            text,
    welltype           text,
    mapsymbol          text,
    dssize             text,
    dstype             text,
    geom               geometry(MultiPolygon, 4326),
    primary key (manifest_id, source_row_ordinal)
);

create table canonical.wells (
    api10                  text not null,
    api14                  text,
    state_code             text,
    county_code_at_permit  text,
    ndic_file_no           text,
    operator_name_reported text,
    operator_id            text,
    well_name              text,
    status_canonical       text,
    status_reported        text,
    well_type_reported     text,
    spud_date              date,
    confidential_flag      boolean not null default false,
    basin                  text,
    land_unit_label        text,
    effective_from         date not null,
    source_manifest_id     text not null references lineage.manifests (manifest_id),
    derivation_id          text not null references lineage.derivations (derivation_id),
    created_at             timestamptz not null default now(),
    primary key (api10, effective_from)
);

comment on table canonical.wells is
    'Append-only and effective-dated: a status change is a new row, never an update (M13).';

create index wells_status_idx on canonical.wells (status_canonical);

create view canonical.wells_latest as
select api10, api14, state_code, county_code_at_permit, ndic_file_no, operator_name_reported,
       operator_id, well_name, status_canonical, status_reported, well_type_reported, spud_date,
       confidential_flag, basin, land_unit_label, effective_from, source_manifest_id,
       derivation_id, created_at
  from (select w.*,
               row_number() over (partition by api10 order by effective_from desc,
                                  created_at desc) as effective_rank
          from canonical.wells w) ranked
 where effective_rank = 1;

create table canonical.well_spatial (
    api10              text not null,
    geom_type          text not null check (geom_type in ('surface', 'bottomhole', 'lateral')),
    geom_key           text not null,
    geom               geometry(Geometry, 4326) not null,
    source_datum       text not null,
    transform_rule_id  text,
    source_manifest_id text not null references lineage.manifests (manifest_id),
    derivation_id      text not null references lineage.derivations (derivation_id),
    created_at         timestamptz not null default now(),
    primary key (api10, geom_type, geom_key)
);

-- No FK to canonical.wells: M13's composite PK leaves no single-column key to reference,
-- so the promotion path quarantines an unmatched api10 as orphan_fk instead (C10).
comment on column canonical.well_spatial.api10 is
    'Identity is enforced by the promotion path, not a foreign key; orphans quarantine.';

create index well_spatial_geom_idx on canonical.well_spatial using gist (geom);

create table canonical.spacing_units (
    spacing_unit_id     text primary key,
    state               text,
    label               text,
    formation_reported  text,
    case_no             text,
    order_no            text,
    ds_size_acres       numeric,
    geom                geometry(MultiPolygon, 4326) not null,
    source_manifest_id  text not null references lineage.manifests (manifest_id),
    derivation_id       text not null references lineage.derivations (derivation_id),
    created_at          timestamptz not null default now()
);

create index spacing_units_geom_idx on canonical.spacing_units using gist (geom);

create table canonical.glossary_terms (
    term_id             text primary key,
    term                text not null unique,
    aliases             text[] not null default '{}',
    short_definition    text not null,
    expanded_definition text not null,
    domain_tags         text[] not null default '{}',
    related_terms       text[] not null default '{}',
    source_refs         text[] not null default '{}',
    first_surfaced_in   text,
    effective_from      date not null default current_date,
    highlightable       boolean not null default true
);

comment on column canonical.glossary_terms.highlightable is
    'M7: ordinary words stay clickable but are not auto-scanned, or the card is a sea of rules.';

create table lineage.nd_status_map (
    status           text primary key,
    status_canonical text not null,
    confidential     boolean not null default false
);

comment on table lineage.nd_status_map is
    'Key column is named for the frame column the rule maps: _vocab_map reads spec.key_col '
    'from both the frame and this table.';

create table lineage.nd_stream_map (
    stream_raw       text primary key,
    stream_canonical text,
    promoted         boolean not null default true
);

-- _vocab_map stringifies every lookup value, so a NULL would promote as the text 'None'.
-- The rule reads this view; the unpromoted rows stay in the table as C7's measured evidence.
create view lineage.nd_stream_promoted_map as
select stream_raw, stream_canonical
  from lineage.nd_stream_map
 where promoted and stream_canonical is not null;

alter table canonical.production_monthly
    add column null_semantics text not null default 'reported'
        check (null_semantics in ('reported', 'reported_zero', 'no_report', 'withheld'));

comment on column canonical.production_monthly.null_semantics is
    'No report filed, reported zero, and withheld are three different facts (§3.0.3).';

create or replace view canonical.production_monthly_latest as
select api10, production_month, stream, source_id, report_vintage, volume, unit, days_produced,
       granularity, value_hash, source_manifest_id, derivation_id, created_at, null_semantics
  from (select p.*,
               row_number() over (
                   partition by api10, production_month, stream, source_id
                   order by report_vintage desc, created_at desc) as vintage_rank
          from canonical.production_monthly p) ranked
 where vintage_rank = 1;

create table marts.nd_well_card (
    api10                   text primary key,
    well_name               text,
    operator_name           text,
    status_canonical        text,
    county                  text,
    land_unit_label         text,
    spud_date               date,
    first_production_month  date,
    latest_production_month date,
    cum_oil_bbl             numeric(18, 3),
    cum_gas_mcf             numeric(18, 3),
    cum_water_bbl           numeric(18, 3),
    lateral_length_ft       numeric(12, 2),
    lateral_count           int,
    derivation_id           text not null references lineage.derivations (derivation_id),
    refreshed_at            timestamptz not null default now()
);

create table marts.nd_laterals_tile (
    api10             text not null,
    linekey           text not null,
    operator_name     text,
    status_canonical  text,
    spud_year         int,
    lateral_length_ft numeric(12, 2),
    geom              geometry(LineString, 4326) not null,
    derivation_id     text not null,
    primary key (api10, linekey)
);

create index nd_laterals_tile_geom_idx on marts.nd_laterals_tile using gist (geom);

create table marts.nd_wells_tile (
    api10            text primary key,
    operator_name    text,
    status_canonical text,
    spud_year        int,
    geom             geometry(Point, 4326) not null,
    derivation_id    text not null
);

create index nd_wells_tile_geom_idx on marts.nd_wells_tile using gist (geom);

create trigger wells_append_only
    before update or delete on canonical.wells
    for each row execute function lineage.reject_mutation();

create trigger well_spatial_append_only
    before update or delete on canonical.well_spatial
    for each row execute function lineage.reject_mutation();

grant usage on schema staging, canonical, marts to glasswell_pipeline, glasswell_api;
grant select on all tables in schema canonical, marts to glasswell_api;
grant select, insert on all tables in schema staging, canonical to glasswell_pipeline;
grant select on lineage.nd_status_map, lineage.nd_stream_map, lineage.nd_stream_promoted_map
    to glasswell_pipeline, glasswell_api;
-- Marts are rebuilt, not appended: P5 refreshes with delete + insert. Canonical must not
-- gain delete alongside it (R2), which is why these are three statements and not one.
grant select, insert, delete, truncate on all tables in schema marts to glasswell_pipeline;
revoke update, delete on canonical.wells, canonical.well_spatial
    from glasswell_pipeline, glasswell_api;
