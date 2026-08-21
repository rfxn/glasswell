-- The NM OCD slice: staging for nine sources, the NM lookup registries, and the batch index a
-- 122x canonical needs. All of it lands in one migration because discover_migrations refuses a
-- gap, so a phase that is cut must not be able to leave one.
--
-- Two shapes, chosen by size. The eight sibling tables are verbatim text rows in Postgres; the
-- production spine is 48,310,560,330 bytes across 48,104,334 records and lives in Parquet under
-- SB-01 §3.2, with only its partition registered here. `source_row_ordinal` is 0-based per
-- SB-01 §3.1.3; ND's staging is 1-based (nd_mpr.py:167), which is shipped and is not being
-- changed to match.
--
-- No reason-code CHECK change: migration 021 already admits `key_incomplete`, which is the exit
-- the key_composite executor needs and the only code PLAN-NM §1.8 asked this migration to add.
-- The live vocabulary is 18 codes and D1 adds none. `crosswalk_disagreement` and
-- `withheld_trade_secret` belong to SB-01 handback H5, which CADENCE assigns to Track B-gate.

create table staging.stg_nm_ocd_wellhistory__records (
    manifest_id                 text not null references lineage.manifests (manifest_id),
    source_row_ordinal          integer not null,
    ingested_at                 timestamptz not null default now(),
    api_st_cde                  text,
    api_cnty_cde                text,
    api_well_idn                text,
    eff_dte                     text,
    rec_termn_dte               text,
    ogrid_cde                   text,
    well_name                   text,
    prod_prop_idn               text,
    prop_fm_desc                text,
    well_nbr_idn                text,
    well_typ_cde                text,
    lease_typ_cde               text,
    ocd_district                text,
    last_apd_status             text,
    last_apd_apr_date           text,
    last_apd_cancel_date        text,
    latitude                    text,
    longitude                   text,
    datum                       text,
    sdiv_twp_idn                text,
    sdiv_rng_idn                text,
    sdiv_sect_num               text,
    sdiv_unlt_idn               text,
    ocd_unlt_idn                text,
    lot_idn                     text,
    ftg_ns_num                  text,
    ftg_ew_num                  text,
    ns_cde                      text,
    ew_cde                      text,
    status                      text,
    spud_dte                    text,
    plug_dte                    text,
    directional_status          text,
    completed_in_adjacent_state text,
    elev_gl_num                 text,
    dpth_tgt_num                text,
    dpth_tvd_num                text,
    dpth_mvd_num                text,
    primary key (manifest_id, source_row_ordinal)
);

comment on table staging.stg_nm_ocd_wellhistory__records is
    'Well header history. Carries latitude, longitude and datum, which wcproduction does not:
    NM geometry is out of scope for D1 (PLAN-NM §6) but the columns are staged verbatim rather
    than dropped, because staging holds no opinions and the finding is now on the record.';

create table staging.stg_nm_ocd_wchistory__records (
    manifest_id        text not null references lineage.manifests (manifest_id),
    source_row_ordinal integer not null,
    ingested_at        timestamptz not null default now(),
    api_st_cde         text,
    api_cnty_cde       text,
    api_well_idn       text,
    pool_idn           text,
    eff_dte            text,
    rec_termn_dte      text,
    wc_stat_cde        text,
    ogrid_cde          text,
    spc_unit_idn       text,
    prod_prop_idn      text,
    well_nbr_idn       text,
    sdiv_twp_idn       text,
    sdiv_rng_idn       text,
    sdiv_sect_num      text,
    sdiv_unlt_idn      text,
    ocd_unlt_idn       text,
    ftg_ns_num         text,
    ftg_ew_num         text,
    ns_cde             text,
    ew_cde             text,
    dpth_perf_top_num  text,
    dpth_perf_btm_num  text,
    compl_dte          text,
    fst_oil_prodn_dte  text,
    fst_gas_deliv_dte  text,
    tst_dte            text,
    c104_apr_dte       text,
    bh_psd_act_ind     text,
    dhc_cmngl_ind      text,
    dhc_dte            text,
    well_typ_cde       text,
    prodn_meth_cde     text,
    primary key (manifest_id, source_row_ordinal)
);

comment on table staging.stg_nm_ocd_wchistory__records is
    'Well-completion history: the api x pool grain the production spine is keyed on.';

create table staging.stg_nm_ocd_podwc__records (
    manifest_id        text not null references lineage.manifests (manifest_id),
    source_row_ordinal integer not null,
    ingested_at        timestamptz not null default now(),
    pod_idn            text,
    api_st_cde         text,
    api_cnty_cde       text,
    api_well_idn       text,
    pool_idn           text,
    eff_dte            text,
    primary key (manifest_id, source_row_ordinal)
);

comment on table staging.stg_nm_ocd_podwc__records is
    'POD to well-completion crosswalk.';

create table staging.stg_nm_ocd_pod__records (
    manifest_id        text not null references lineage.manifests (manifest_id),
    source_row_ordinal integer not null,
    ingested_at        timestamptz not null default now(),
    pod_idn            text,
    pod_typ_cde        text,
    pod_dsc            text,
    ogrid_cde          text,
    api_cnty_cde       text,
    sdiv_twp_idn       text,
    sdiv_rng_idn       text,
    sdiv_sect_num      text,
    sdiv_unlt_idn      text,
    fac_typ_cde        text,
    eff_dte            text,
    primary key (manifest_id, source_row_ordinal)
);

comment on table staging.stg_nm_ocd_pod__records is
    'Pooled development units.';

create table staging.stg_nm_ocd_ogrid__records (
    manifest_id        text not null references lineage.manifests (manifest_id),
    source_row_ordinal integer not null,
    ingested_at        timestamptz not null default now(),
    ogrid_cde          text,
    ogrid_nam          text,
    ogrid_adr_nam      text,
    mail_stop          text,
    line1_adr          text,
    line2_adr          text,
    line3_adr          text,
    city_nam           text,
    st_nam             text,
    zip_cde            text,
    ctry_nam           text,
    phone_num          text,
    fax_num            text,
    stat_eff_dte       text,
    issng_ag_cde       text,
    lst_modified_dte   text,
    created_dte        text,
    ogrid_stat_cde     text,
    primary key (manifest_id, source_row_ordinal)
);

comment on table staging.stg_nm_ocd_ogrid__records is
    'Operator registry. ogrid_cde is an exact key, unlike ND''s name-only operator join.';

create table staging.stg_nm_ocd_pool__records (
    manifest_id        text not null references lineage.manifests (manifest_id),
    source_row_ordinal integer not null,
    ingested_at        timestamptz not null default now(),
    pool_idn           text,
    eff_dte            text,
    pool_nam           text,
    std_spc_oil_num    text,
    std_spc_gas_num    text,
    gor_lim_num        text,
    top_allow_oil_num  text,
    csghd_gas_lim_num  text,
    ft_end_ln_num      text,
    ft_side_ln_num     text,
    ft_near_well_num   text,
    ft_qq_ln_num       text,
    acre_basis_num     text,
    del_basis_num      text,
    pool_reg_cde       text,
    pool_typ_cde       text,
    dpth_allow_min_num text,
    simult_dedt_yon    text,
    primary key (manifest_id, source_row_ordinal)
);

comment on table staging.stg_nm_ocd_pool__records is
    'Pool registry. pool_nam is space-padded to a fixed width in the source, so it needs a
    declared trim exactly as prd_knd_cde does.';

create table staging.stg_nm_ocd_spacingunit__records (
    manifest_id        text not null references lineage.manifests (manifest_id),
    source_row_ordinal integer not null,
    ingested_at        timestamptz not null default now(),
    spc_unit_idn       text,
    eff_dte            text,
    dedt_acre_dec      text,
    pool_idn           text,
    acre_typ           text,
    primary key (manifest_id, source_row_ordinal)
);

comment on table staging.stg_nm_ocd_spacingunit__records is
    'Spacing units: the legal areal unit D3''s Validator B groups on.';

create table staging.stg_nm_ocd_property__records (
    manifest_id        text not null references lineage.manifests (manifest_id),
    source_row_ordinal integer not null,
    ingested_at        timestamptz not null default now(),
    prod_prop_idn      text,
    eff_dte            text,
    prod_prop_nam      text,
    ogrid_cde          text,
    prod_prop_stat_cde text,
    primary key (manifest_id, source_row_ordinal)
);

comment on table staging.stg_nm_ocd_property__records is
    'Properties, keyed by prod_prop_idn.';

create table staging.stg_nm_ocd_wcproduction__partitions (
    manifest_id text primary key references lineage.manifests (manifest_id),
    parquet_uri text        not null,
    rows        bigint      not null,
    sha256      text        not null,
    sort_order  text        not null,
    written_at  timestamptz not null default now()
);

comment on table staging.stg_nm_ocd_wcproduction__partitions is
    'The production spine stages to Parquet (SB-01 §3.2), so this registry - not a __records '
    'table - is what makes the partition discoverable from SQL and gives quarantine rows and '
    'derivations a stable staging_table identifier. One row per manifest (SB-07 §1.2).';
comment on column staging.stg_nm_ocd_wcproduction__partitions.sha256 is
    'Content address of the Parquet file under the SB-01 §3.6 write profile: the same rows '
    'written twice produce the same bytes, which is what makes the partition D1.';

create table lineage.nm_pool_map (
    pool_idn  text primary key,
    pool_name text,
    promoted  boolean not null default true
);

create table lineage.nm_status_map (
    status           text primary key,
    status_canonical text not null
);

create table lineage.nm_stream_map (
    stream_raw       text primary key,
    stream_canonical text,
    promoted         boolean not null default true
);

comment on column lineage.nm_stream_map.stream_raw is
    'The TRIMMED code. prd_knd_cde is CHAR(2) and arrives as ''O ''; the trim is a declared '
    'mapping decision (cr_nm_wcproduction_pad_1), so the map must not encode the padding twice.';

-- _vocab_map stringifies every lookup value, so a NULL would promote as the text 'None'. The
-- rule reads this view; an unpromoted code stays in the table as the evidence it was seen.
create view lineage.nm_stream_promoted_map as
select stream_raw, stream_canonical
  from lineage.nm_stream_map
 where promoted and stream_canonical is not null;

grant select, insert on
    staging.stg_nm_ocd_wellhistory__records,
    staging.stg_nm_ocd_wchistory__records,
    staging.stg_nm_ocd_podwc__records,
    staging.stg_nm_ocd_pod__records,
    staging.stg_nm_ocd_ogrid__records,
    staging.stg_nm_ocd_pool__records,
    staging.stg_nm_ocd_spacingunit__records,
    staging.stg_nm_ocd_property__records,
    staging.stg_nm_ocd_wcproduction__partitions
    to glasswell_pipeline;
-- delete arrives from migration 019's default privilege on schema staging; re-granting it here
-- would hide a regression in that default rather than fail on it. glasswell_api gets nothing in
-- schema staging (SB-01 §3.1.4) and nothing here changes that.
grant select on lineage.nm_pool_map, lineage.nm_status_map, lineage.nm_stream_map,
    lineage.nm_stream_promoted_map to glasswell_pipeline, glasswell_api;

-- Canonical goes from 394,278 rows to ~48.6M. Promotion reads and writes one
-- (source_id, production_month) batch at a time (PLAN-NM P4.4), and under the S-E primary key
-- that predicate has no index to sit on. The api10 lookup /v1/wells/{api10}/production runs
-- keeps the index migration 020 gave it, so ND's well card does not regress because NM loaded.
create index production_monthly_source_month_idx
    on canonical.production_monthly (source_id, production_month);
