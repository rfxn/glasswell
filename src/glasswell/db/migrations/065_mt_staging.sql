-- Montana staging. Every column is text and source-faithful: staging holds no opinions
-- (§3.4.2), so the -999 sentinel, the end-of-month dates and the fifteen unpromoted PRU
-- disposition columns all land exactly as MBOGC filed them.

create table staging.mt_bogc_well (
    manifest_id        text not null references lineage.manifests (manifest_id),
    source_row_ordinal integer not null,
    ingested_at        timestamptz not null default now(),
    api_wellno         text,
    rpt_date           text,
    st_fmtn_cd         text,
    formation          text,
    lease_unit         text,
    opno               text,
    coname             text,
    bbls_oil_cond      text,
    mcf_gas            text,
    bbls_wtr           text,
    days_prod          text,
    amnd_rpt           text,
    dt_mod             text,
    primary key (manifest_id, source_row_ordinal)
);

comment on column staging.mt_bogc_well.lease_unit is
    'Carries the -999 sentinel verbatim. cr_mt_lease_unit_sentinel_1 is what turns it into a'
    ' null on the way to canonical; staging keeps what was filed.';
comment on column staging.mt_bogc_well.rpt_date is
    'End-of-month as filed. cr_mt_month_convention_1 normalises it to the first of the month.';

create table staging.mt_bogc_pru (
    manifest_id        text not null references lineage.manifests (manifest_id),
    source_row_ordinal integer not null,
    ingested_at        timestamptz not null default now(),
    lease_unit         text,
    rpt_date           text,
    dt_receive         text,
    amnd_rpt           text,
    dt_amend           text,
    opno               text,
    coname             text,
    startivn_oilcd     text,
    oil_prod           text,
    gas_prod           text,
    wtr_prod           text,
    oil_sold           text,
    gas_sold           text,
    oilspill           text,
    wtrspill           text,
    flarvnt_gas        text,
    useoil             text,
    usegas             text,
    oilinj             text,
    gasinj             text,
    wtrinj             text,
    wtrto_pit          text,
    other_oil          text,
    other_gas          text,
    other_wtr          text,
    dt_mod             text,
    primary key (manifest_id, source_row_ordinal)
);

comment on table staging.mt_bogc_pru is
    'The lease grain. Fifteen disposition columns stage here and promote nowhere: no canonical'
    ' stream vocabulary admits sold, flared, injected, spilled, used or inventory'
    ' (cr_mt_pru_stream_scope_1). Staging never serves, so holding them costs nothing and'
    ' losing them would cost a re-fetch.';
comment on column staging.mt_bogc_pru.startivn_oilcd is
    'A stock balance at the start of the month, not a flow. Never summed into production'
    ' (cr_mt_pru_inventory_1).';

create table staging.mt_gis_wells (
    manifest_id        text not null references lineage.manifests (manifest_id),
    source_row_ordinal integer not null,
    ingested_at        timestamptz not null default now(),
    api_wellno         text,
    coname             text,
    well_nm            text,
    status             text,
    type               text,
    mapsymbol          text,
    wh_twpn            text,
    wh_twpd            text,
    wh_rngn            text,
    wh_rngd            text,
    wh_sec             text,
    wh_qtr             text,
    completed          text,
    st_fldno           text,
    prod_field         text,
    field_no           text,
    reg_field          text,
    dtd                text,
    dor_id             text,
    geom               geometry(Point, 4326),
    primary key (manifest_id, source_row_ordinal)
);

create table staging.mt_gis_well_paths (
    manifest_id        text not null references lineage.manifests (manifest_id),
    source_row_ordinal integer not null,
    ingested_at        timestamptz not null default now(),
    api_wellno         text,
    well_nm            text,
    wellsub            text,
    formation          text,
    geom               geometry(LineString, 4326),
    primary key (manifest_id, source_row_ordinal)
);

comment on table staging.mt_gis_well_paths is
    'Cartographic centrelines, not directional surveys: no measured depth, no inclination, no'
    ' azimuth, no stations, and a mean of 2.82 vertices per path (cr_mt_paths_geometry_class_1).';
comment on column staging.mt_gis_well_paths.wellsub is
    'The wellbore suffix (LT01, ST01, WL01). 875 of 2,836 API-10s carry more than one path, so'
    ' geometry is keyed on the pair and never on the API-10 alone (cr_mt_paths_subkey_1).';

grant select, insert on
    staging.mt_bogc_well, staging.mt_bogc_pru,
    staging.mt_gis_wells, staging.mt_gis_well_paths
    to glasswell_pipeline;
