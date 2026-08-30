-- Montana registry: poll cadence, the two lookup vocabularies the MT rules read, and the
-- first-publication evidence migration 049 requires before any conformance rule may be seeded.
--
-- REPOINT CHECKLIST (integrator, at the merge train):
--   1. evidence_tag  'UNRELEASED'                                -> the tag that first carries
--                                                                   the cr_mt_* rule ids
--   2. evidence_commit '0000...0000' (forty zeros)               -> the `main` head this branch
--                                                                   was written against
--   3. published_vintage date '2026-08-30'                       -> confirm it is the date that
--                                                                   tag is cut, or correct it
-- The rule ids themselves are immutable and must not change during the repoint.

insert into lineage.source_poll_policies
    (source_id, cadence, expected_poll_interval, attempt_timeout)
values
    ('mt_bogc_well_production', 'Every 35 days', interval '35 days', interval '6 hours'),
    ('mt_bogc_pru_production', 'Every 35 days', interval '35 days', interval '6 hours'),
    ('mt_gis_wells', 'Every 35 days', interval '35 days', interval '6 hours'),
    ('mt_gis_well_paths', 'Every 35 days', interval '35 days', interval '6 hours')
on conflict (source_id) do nothing;

-- The reported measure column names live here rather than in the parser, so a new disposition
-- column upstream is a row and not a code change (cr_mt_stream_vocab_1).
create table if not exists lineage.mt_stream_map (
    stream_raw        text primary key,
    stream_canonical  text,
    promoted          boolean not null default true,
    published_vintage date
);

comment on table lineage.mt_stream_map is
    'Montana reported measure column -> canonical stream. An unpromoted column keeps its row as'
    ' the evidence it was seen; cr_mt_pru_stream_scope_1 is why fifteen of them are unpromoted.';

-- _vocab_map stringifies every lookup value, so a NULL would promote as the text 'None'.
create or replace view lineage.mt_stream_promoted_map as
select stream_raw, stream_canonical
  from lineage.mt_stream_map
 where promoted and stream_canonical is not null;

insert into lineage.mt_stream_map
    (stream_raw, stream_canonical, promoted, published_vintage)
values
    ('BBLS_OIL_COND', 'oil', true, date '2026-08-30'),
    ('MCF_GAS', 'gas', true, date '2026-08-30'),
    ('BBLS_WTR', 'water', true, date '2026-08-30'),
    ('Oil_Prod', 'oil', true, date '2026-08-30'),
    ('Gas_Prod', 'gas', true, date '2026-08-30'),
    ('Wtr_Prod', 'water', true, date '2026-08-30'),
    ('StartIvn_OilCd', null, false, date '2026-08-30'),
    ('Oil_Sold', null, false, date '2026-08-30'),
    ('Gas_Sold', null, false, date '2026-08-30'),
    ('OilSpill', null, false, date '2026-08-30'),
    ('WtrSpill', null, false, date '2026-08-30'),
    ('FlarVnt_Gas', null, false, date '2026-08-30'),
    ('UseOil', null, false, date '2026-08-30'),
    ('UseGas', null, false, date '2026-08-30'),
    ('OilInj', null, false, date '2026-08-30'),
    ('GasInj', null, false, date '2026-08-30'),
    ('WtrInj', null, false, date '2026-08-30'),
    ('WtrTo_Pit', null, false, date '2026-08-30'),
    ('Other_Oil', null, false, date '2026-08-30'),
    ('Other_Gas', null, false, date '2026-08-30'),
    ('Other_Wtr', null, false, date '2026-08-30')
on conflict (stream_raw) do nothing;

create table if not exists lineage.mt_status_map (
    status            text primary key,
    status_canonical  text,
    promoted          boolean not null default true,
    published_vintage date
);

comment on table lineage.mt_status_map is
    'MBOGC Status -> canonical well status. Type and MapSymbol are parallel classifications and'
    ' are retained as reported context rather than mapped (cr_mt_gis_status_vocab_1).';

create or replace view lineage.mt_status_promoted_map as
select status, status_canonical
  from lineage.mt_status_map
 where promoted and status_canonical is not null;

grant select on lineage.mt_stream_map, lineage.mt_stream_promoted_map,
    lineage.mt_status_map, lineage.mt_status_promoted_map
    to glasswell_pipeline, glasswell_api;

insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
select rule_id, date '2026-08-30', 'UNRELEASED',
       '0000000000000000000000000000000000000000'
  from unnest(array[
        'cr_mt_api_identity_1', 'cr_mt_basin_scope_1', 'cr_mt_days_range_1',
        'cr_mt_entity_key_1', 'cr_mt_formation_rollup_1',
        'cr_mt_gis_api_identity_1', 'cr_mt_gis_border_outliers_1',
        'cr_mt_gis_datum_1', 'cr_mt_gis_encoding_1', 'cr_mt_gis_layer_selection_1',
        'cr_mt_gis_status_vocab_1', 'cr_mt_gis_wells_format_1',
        'cr_mt_grain_uniqueness_1', 'cr_mt_host_pin_1', 'cr_mt_knowledge_time_1',
        'cr_mt_lease_unit_sentinel_1', 'cr_mt_liquids_policy_1',
        'cr_mt_month_convention_1', 'cr_mt_null_semantics_1',
        'cr_mt_operator_absence_1', 'cr_mt_paths_coverage_1', 'cr_mt_paths_datum_1',
        'cr_mt_paths_format_1', 'cr_mt_paths_geometry_class_1',
        'cr_mt_paths_subkey_1', 'cr_mt_producing_well_scope_1',
        'cr_mt_pru_entity_key_1', 'cr_mt_pru_format_1',
        'cr_mt_pru_grain_uniqueness_1', 'cr_mt_pru_inventory_1',
        'cr_mt_pru_liquids_policy_1', 'cr_mt_pru_month_convention_1',
        'cr_mt_pru_null_semantics_1', 'cr_mt_pru_reconciliation_1',
        'cr_mt_pru_reporting_level_1', 'cr_mt_pru_restatement_1',
        'cr_mt_pru_stream_scope_1', 'cr_mt_pru_units_1', 'cr_mt_pru_volume_range_1',
        'cr_mt_stream_vocab_1', 'cr_mt_trailing_record_1', 'cr_mt_units_1',
        'cr_mt_volume_range_1', 'cr_mt_well_format_1', 'cr_mt_well_list_scope_1'
  ]::text[]) rule_id
on conflict (rule_id) do nothing;
