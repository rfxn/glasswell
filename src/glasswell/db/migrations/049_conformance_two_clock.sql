-- Conformance has always carried valid time (`effective_from` / `effective_to`), but not the
-- independent date on which glasswell published and could know a decision. A backdated rule
-- must not enter a retrospective run before its actual publication. The evidence below is the
-- first repository tag containing each immutable rule id, checked against git history on
-- 2026-08-28. `effective_from` is deliberately never used as a publication proxy.

create table if not exists lineage.conformance_rule_publications (
    rule_id             text primary key,
    published_vintage  date not null,
    evidence_tag        text not null check (btrim(evidence_tag) <> ''),
    evidence_commit     text not null check (evidence_commit ~ '^[0-9a-f]{40}$'),
    unique (rule_id, published_vintage)
);

comment on table lineage.conformance_rule_publications is
    'Immutable first-publication evidence for conformance rule ids. Dates come from the first'
    ' repository tag containing the rule, never from the rule effective interval.';

insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
select rule_id, date '2026-08-20', 'pre-inc3-train',
       'efa39772c2877a6c4ba333fade7fa446695c1f39'
  from unnest(array[
       'cr_nd_api_identity_1', 'cr_nd_compute_crs_1', 'cr_nd_compute_crs_2',
       'cr_nd_confidential_1', 'cr_nd_datum_1', 'cr_nd_days_range_1',
       'cr_nd_entity_key_1', 'cr_nd_land_unit_1', 'cr_nd_liquids_policy_1',
       'cr_nd_month_convention_1', 'cr_nd_mpr_format_1', 'cr_nd_multilateral_1',
       'cr_nd_null_semantics_1', 'cr_nd_pool_rollup_1', 'cr_nd_segment_vocab_1',
       'cr_nd_status_vocab_1', 'cr_nd_stream_vocab_1', 'cr_nd_units_1',
       'cr_nd_volume_range_1'
  ]::text[]) rule_id
on conflict (rule_id) do nothing;

insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
select rule_id, date '2026-08-21', 'v0.20',
       '7730b69c4db530871e5ad8cfcfd82514e29e6edf'
  from unnest(array[
       'cr_nm_ogrid_ftp_layout_1', 'cr_nm_ogrid_host_pin_1', 'cr_nm_ogrid_operator_1',
       'cr_nm_ogrid_pad_1', 'cr_nm_ogrid_parse_1', 'cr_nm_ogrid_registry_1',
       'cr_nm_ogrid_undated_vintage_1', 'cr_nm_pod_ftp_layout_1',
       'cr_nm_pod_host_pin_1', 'cr_nm_pod_pad_1', 'cr_nm_pod_parse_1',
       'cr_nm_pod_undated_vintage_1', 'cr_nm_podwc_ftp_layout_1',
       'cr_nm_podwc_host_pin_1', 'cr_nm_podwc_pad_1', 'cr_nm_podwc_parse_1',
       'cr_nm_podwc_pod_1', 'cr_nm_podwc_undated_vintage_1',
       'cr_nm_pool_ftp_layout_1', 'cr_nm_pool_host_pin_1', 'cr_nm_pool_pad_1',
       'cr_nm_pool_parse_1', 'cr_nm_pool_undated_vintage_1', 'cr_nm_pool_vocab_1',
       'cr_nm_property_ftp_layout_1', 'cr_nm_property_host_pin_1',
       'cr_nm_property_pad_1', 'cr_nm_property_parse_1',
       'cr_nm_property_undated_vintage_1', 'cr_nm_spacingunit_ftp_layout_1',
       'cr_nm_spacingunit_host_pin_1', 'cr_nm_spacingunit_pad_1',
       'cr_nm_spacingunit_parse_1', 'cr_nm_spacingunit_undated_vintage_1',
       'cr_nm_wchistory_api10_1', 'cr_nm_wchistory_completion_key_1',
       'cr_nm_wchistory_effective_1', 'cr_nm_wchistory_ftp_layout_1',
       'cr_nm_wchistory_host_pin_1', 'cr_nm_wchistory_lease_identifier_1',
       'cr_nm_wchistory_pad_1', 'cr_nm_wchistory_parse_1',
       'cr_nm_wchistory_status_domain_1', 'cr_nm_wchistory_status_vocab_1',
       'cr_nm_wchistory_undated_vintage_1', 'cr_nm_wchistory_wellbore_policy_1',
       'cr_nm_wcproduction_amend_ind_1', 'cr_nm_wcproduction_api10_1',
       'cr_nm_wcproduction_collision_1', 'cr_nm_wcproduction_county_parity_1',
       'cr_nm_wcproduction_days_1', 'cr_nm_wcproduction_entity_key_1',
       'cr_nm_wcproduction_flare_property_1', 'cr_nm_wcproduction_ftp_layout_1',
       'cr_nm_wcproduction_host_pin_1', 'cr_nm_wcproduction_lease_equivalent_1',
       'cr_nm_wcproduction_liquids_1', 'cr_nm_wcproduction_mod_dte_1',
       'cr_nm_wcproduction_month_1', 'cr_nm_wcproduction_null_semantics_1',
       'cr_nm_wcproduction_pad_1', 'cr_nm_wcproduction_parse_1',
       'cr_nm_wcproduction_restatement_1', 'cr_nm_wcproduction_status_vocab_1',
       'cr_nm_wcproduction_stream_vocab_1', 'cr_nm_wcproduction_undated_vintage_1',
       'cr_nm_wcproduction_units_1', 'cr_nm_wcproduction_volume_range_1',
       'cr_nm_wcproduction_window_1', 'cr_nm_wellhistory_ftp_layout_1',
       'cr_nm_wellhistory_host_pin_1', 'cr_nm_wellhistory_pad_1',
       'cr_nm_wellhistory_parse_1', 'cr_nm_wellhistory_undated_vintage_1',
       'cr_tx_allocation_scope_1', 'cr_tx_api10_build_1', 'cr_tx_compute_crs_1',
       'cr_tx_county_scope_1', 'cr_tx_ewa_layout_1', 'cr_tx_ewa_role_1',
       'cr_tx_ewa_scope_1', 'cr_tx_geometry_survivor_1', 'cr_tx_gis_layers_1',
       'cr_tx_identity_collapse_1', 'cr_tx_lateral_bounds_1', 'cr_tx_lease_key_1',
       'cr_tx_mft_resolve_1', 'cr_tx_multi_wellbore_1', 'cr_tx_nad27_1',
       'cr_tx_plugged_precedence_1', 'cr_tx_status_vocab_1', 'cr_tx_wellbore_key_1'
  ]::text[]) rule_id
on conflict (rule_id) do nothing;

insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
select rule_id, date '2026-08-21', 'v0.21',
       '92180b334c515c60f0b203f4c3bc0fbce987c599'
  from unnest(array[
       'cr_nd_survey_api_identity_1', 'cr_nd_survey_azimuth_reference_1',
       'cr_nd_survey_min_stations_1', 'cr_nd_survey_segment_vocab_1',
       'cr_nd_survey_station_order_1', 'cr_nd_survey_station_range_1'
  ]::text[]) rule_id
on conflict (rule_id) do nothing;

insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
values
    ('cr_nd_well_type_disposal_1', date '2026-08-22', 'v0.30',
     '88105aa99529996779111a0ab5c802307de0b7ff'),
    ('cr_nd_geometry_provenance_1', date '2026-08-22', 'v0.34',
     '2737c545761f43ece3de2d34728987e8235704b1'),
    ('cr_land_agg_membership_1', date '2026-08-22', 'v0.37',
     'dd49f630b66353440809368b3d3f200c7aa5b092')
on conflict (rule_id) do nothing;

insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
select rule_id, date '2026-08-22', 'v0.36',
       '4ddf231ca2e441fce390039c7e41a4642f44dde4'
  from unnest(array[
       'cr_blm_plss_datum_1', 'cr_blm_plss_publisher_1', 'cr_blm_plss_scope_1'
  ]::text[]) rule_id
on conflict (rule_id) do nothing;

insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
select rule_id, date '2026-08-23', 'v0.45',
       '7ef7f1d9765c6a962fb861edd0e773521aa7c723'
  from unnest(array[
       'cr_nm_c115b_api10_1', 'cr_nm_c115b_datum_1', 'cr_nm_c115b_source_1',
       'cr_nm_c115b_walk_order_1', 'cr_nm_c115b_waste_vocab_1'
  ]::text[]) rule_id
on conflict (rule_id) do nothing;

insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
select rule_id, date '2026-08-26', 'v0.50',
       '3e9d5202286b51be3fc53739cade3d178c98975b'
  from unnest(array[
       'cr_ff_api_identity_1', 'cr_ff_completion_anchor_1', 'cr_ff_disclosure_parse_1',
       'cr_nd_basin_1', 'cr_nd_formation_group_1'
  ]::text[]) rule_id
on conflict (rule_id) do nothing;

insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
select rule_id, date '2026-08-27', 'v0.57',
       '7d97a110d1d4e92499dba191bba212d61b9be9e1'
  from unnest(array[
       'cr_nd_neighbor_context_1', 'cr_nd_neighbor_distance_1'
  ]::text[]) rule_id
on conflict (rule_id) do nothing;

drop trigger if exists conformance_rule_publications_append_only
    on lineage.conformance_rule_publications;
create trigger conformance_rule_publications_append_only
    before update or delete on lineage.conformance_rule_publications
    for each row execute function lineage.reject_mutation();

alter table lineage.conformance_rules add column if not exists published_vintage date;

-- The table was append-only before it had this column. Temporarily disable only that user
-- trigger to populate repository evidence; a failed transaction restores the trigger state.
alter table lineage.conformance_rules disable trigger conformance_rules_append_only;
update lineage.conformance_rules r
   set published_vintage = p.published_vintage
  from lineage.conformance_rule_publications p
 where p.rule_id = r.rule_id
   and r.published_vintage is null;
alter table lineage.conformance_rules enable trigger conformance_rules_append_only;

do $$
begin
    if exists (
        select 1 from lineage.conformance_rules where published_vintage is null
    ) then
        raise exception 'a conformance rule has no repository publication evidence'
            using errcode = 'check_violation';
    end if;
end
$$;

alter table lineage.conformance_rules alter column published_vintage set not null;

do $$
begin
    if not exists (
        select 1 from pg_constraint
         where conrelid = 'lineage.conformance_rules'::regclass
           and conname = 'conformance_rules_publication_fk'
    ) then
        alter table lineage.conformance_rules
            add constraint conformance_rules_publication_fk
            foreign key (rule_id, published_vintage)
            references lineage.conformance_rule_publications (rule_id, published_vintage);
    end if;
end
$$;

create or replace function lineage.assign_conformance_rule_publication()
returns trigger language plpgsql as $$
declare
    expected date;
begin
    select published_vintage into expected
      from lineage.conformance_rule_publications
     where rule_id = new.rule_id;
    if expected is null then
        raise exception 'no publication evidence registered for conformance rule %', new.rule_id
            using errcode = 'check_violation';
    end if;
    if new.published_vintage is null then
        new.published_vintage := expected;
    elsif new.published_vintage <> expected then
        raise exception 'publication vintage for % must be %, not %',
            new.rule_id, expected, new.published_vintage
            using errcode = 'check_violation';
    end if;
    return new;
end
$$;

drop trigger if exists conformance_rules_assign_publication on lineage.conformance_rules;
create trigger conformance_rules_assign_publication
    before insert on lineage.conformance_rules
    for each row execute function lineage.assign_conformance_rule_publication();

comment on column lineage.conformance_rules.published_vintage is
    'Knowledge time: first repository-tag publication of this immutable rule version.';

create index if not exists conformance_rules_two_clock_idx
    on lineage.conformance_rules
       (source_id, stage, published_vintage, effective_from, rule_id);
create index if not exists conformance_rules_supersedes_idx
    on lineage.conformance_rules (supersedes_rule_id)
    where supersedes_rule_id is not null;

-- Static lookup rows are conformance decisions too. Their first tag is table-level evidence:
-- every currently shipped row entered with the table. Future inserts must supply their own
-- publication date because these columns intentionally have no default.
alter table lineage.nd_status_map add column if not exists published_vintage date;
alter table lineage.nd_stream_map add column if not exists published_vintage date;
alter table lineage.nd_segment_map add column if not exists published_vintage date;
alter table lineage.nd_survey_segment_map add column if not exists published_vintage date;
alter table lineage.tx_status_map add column if not exists published_vintage date;
alter table lineage.nm_stream_map add column if not exists published_vintage date;
alter table lineage.nm_waste_type_map add column if not exists published_vintage date;

-- nm_stream_map is populated by seed_all after migrations on a fresh database. Seed the same
-- four measured rows here so their historical publication is identical on fresh and upgraded
-- databases; the existing seeder remains an idempotent no-op.
insert into lineage.nm_stream_map
    (stream_raw, stream_canonical, promoted, published_vintage)
values ('C', 'condensate', true, date '2026-08-21'),
       ('G', 'gas',        true, date '2026-08-21'),
       ('O', 'oil',        true, date '2026-08-21'),
       ('W', 'water',      true, date '2026-08-21')
on conflict (stream_raw) do nothing;

update lineage.nd_status_map
   set published_vintage = date '2026-08-20' where published_vintage is null;
update lineage.nd_stream_map
   set published_vintage = date '2026-08-20' where published_vintage is null;
update lineage.nd_segment_map
   set published_vintage = date '2026-08-20' where published_vintage is null;
update lineage.nd_survey_segment_map
   set published_vintage = date '2026-08-21' where published_vintage is null;
update lineage.tx_status_map
   set published_vintage = date '2026-08-21' where published_vintage is null;
update lineage.nm_stream_map
   set published_vintage = date '2026-08-21' where published_vintage is null;
update lineage.nm_waste_type_map
   set published_vintage = date '2026-08-23' where published_vintage is null;

alter table lineage.nd_status_map alter column published_vintage set not null;
alter table lineage.nd_stream_map alter column published_vintage set not null;
alter table lineage.nd_segment_map alter column published_vintage set not null;
alter table lineage.nd_survey_segment_map alter column published_vintage set not null;
alter table lineage.tx_status_map alter column published_vintage set not null;
alter table lineage.nm_stream_map alter column published_vintage set not null;
alter table lineage.nm_waste_type_map alter column published_vintage set not null;

comment on column lineage.nd_status_map.published_vintage is
    'Knowledge time; first present in tag pre-inc3-train (2026-08-20).';
comment on column lineage.nd_stream_map.published_vintage is
    'Knowledge time; first present in tag pre-inc3-train (2026-08-20).';
comment on column lineage.nd_segment_map.published_vintage is
    'Knowledge time; first present in tag pre-inc3-train (2026-08-20).';
comment on column lineage.nd_survey_segment_map.published_vintage is
    'Knowledge time; first present in tag v0.21 (2026-08-21).';
comment on column lineage.tx_status_map.published_vintage is
    'Knowledge time; first present in tag v0.20 (2026-08-21).';
comment on column lineage.nm_stream_map.published_vintage is
    'Knowledge time; first present in tag v0.20 (2026-08-21).';
comment on column lineage.nm_waste_type_map.published_vintage is
    'Knowledge time; first present in tag v0.45 (2026-08-23).';

create index if not exists nd_status_map_publication_idx
    on lineage.nd_status_map (published_vintage, status);
create index if not exists nd_stream_map_publication_idx
    on lineage.nd_stream_map (published_vintage, stream_raw);
create index if not exists nd_segment_map_publication_idx
    on lineage.nd_segment_map (published_vintage, segment);
create index if not exists nd_survey_segment_map_publication_idx
    on lineage.nd_survey_segment_map (published_vintage, well_sub);
create index if not exists tx_status_map_publication_idx
    on lineage.tx_status_map (published_vintage, status_input);
create index if not exists nm_stream_map_publication_idx
    on lineage.nm_stream_map (published_vintage, stream_raw);
create index if not exists nm_waste_type_map_publication_idx
    on lineage.nm_waste_type_map (published_vintage, waste_type_raw);

-- seed_all deliberately repeats two static registries with ON CONFLICT DO NOTHING. PostgreSQL
-- checks NOT NULL before conflict resolution, so fill only the exact rows whose publication is
-- already proven above. Any new unclocked key remains null and is refused by the constraint.
create or replace function lineage.assign_static_lookup_publication()
returns trigger language plpgsql as $$
declare
    lookup_key text;
begin
    lookup_key := coalesce(
        to_jsonb(new) ->> 'stream_raw',
        to_jsonb(new) ->> 'waste_type_raw',
        to_jsonb(new) ->> 'segment'
    );
    if new.published_vintage is null
       and tg_table_name = 'nd_segment_map'
       and lookup_key = any(array['LAT', 'STK', 'VERT']) then
        new.published_vintage := date '2026-08-20';
    elsif new.published_vintage is null
       and tg_table_name = 'nm_stream_map'
       and lookup_key = any(array['C', 'G', 'O', 'W']) then
        new.published_vintage := date '2026-08-21';
    elsif new.published_vintage is null
       and tg_table_name = 'nm_waste_type_map'
       and lookup_key = any(array['F', 'V']) then
        new.published_vintage := date '2026-08-23';
    end if;
    return new;
end
$$;

drop trigger if exists nd_segment_map_assign_publication on lineage.nd_segment_map;
create trigger nd_segment_map_assign_publication
    before insert on lineage.nd_segment_map
    for each row execute function lineage.assign_static_lookup_publication();

drop trigger if exists nm_stream_map_assign_publication on lineage.nm_stream_map;
create trigger nm_stream_map_assign_publication
    before insert on lineage.nm_stream_map
    for each row execute function lineage.assign_static_lookup_publication();

drop trigger if exists nm_waste_type_map_assign_publication on lineage.nm_waste_type_map;
create trigger nm_waste_type_map_assign_publication
    before insert on lineage.nm_waste_type_map
    for each row execute function lineage.assign_static_lookup_publication();

-- Operator aliases are learned from source rows at runtime, so CURRENT_DATE is their actual
-- insertion knowledge rather than a substitute for the source's effective date. Existing rows
-- receive this migration's first defensible publication date; claiming an earlier date would
-- invent row-level history the old schema did not retain.
alter table lineage.operator_aliases add column if not exists published_vintage date;
update lineage.operator_aliases
   set published_vintage = date '2026-08-28' where published_vintage is null;
alter table lineage.operator_aliases alter column published_vintage set default current_date;
alter table lineage.operator_aliases alter column published_vintage set not null;
comment on column lineage.operator_aliases.published_vintage is
    'Knowledge time: first insertion into glasswell, distinct from source effective_from.';
create index if not exists operator_aliases_two_clock_idx
    on lineage.operator_aliases
       (source_id, published_vintage, effective_from, operator_raw);

-- CRS routing chooses the rule and storage frame behind served lengths, so it carries the same
-- independent clocks. Existing rows are pinned to their first repository tag; future rows use
-- their actual insertion date and cannot rewrite an older row in place.
alter table lineage.crs_registry add column if not exists published_vintage date;
update lineage.crs_registry
   set published_vintage = case basin
       when 'williston' then date '2026-08-20'
       when 'permian' then date '2026-08-21'
       else date '2026-08-28'
   end
 where published_vintage is null;
alter table lineage.crs_registry alter column published_vintage set default current_date;
alter table lineage.crs_registry alter column published_vintage set not null;
comment on column lineage.crs_registry.published_vintage is
    'Knowledge time: first publication of this immutable basin routing row.';

alter table lineage.crs_registry drop constraint if exists crs_registry_pkey;
alter table lineage.crs_registry
    add constraint crs_registry_pkey primary key (basin, effective_from, published_vintage);
create index if not exists crs_registry_two_clock_idx
    on lineage.crs_registry (basin, published_vintage, effective_from desc);

create or replace function lineage.guard_crs_registry_mutation()
returns trigger language plpgsql as $$
begin
    if tg_op = 'UPDATE' and new is not distinct from old then
        return new;
    end if;
    raise exception 'append_only_violation on lineage.crs_registry'
        using errcode = 'restrict_violation';
end
$$;

drop trigger if exists crs_registry_append_only on lineage.crs_registry;
create trigger crs_registry_append_only
    before update or delete on lineage.crs_registry
    for each row execute function lineage.guard_crs_registry_mutation();

-- Every table participating in a lookup is immutable after publication. A correction is a new
-- rule/table version (static vocabularies) or a later effective row (operator aliases).
do $$
declare
    relation text;
begin
    foreach relation in array array[
        'nd_status_map', 'nd_stream_map', 'nd_segment_map', 'nd_survey_segment_map',
        'tx_status_map', 'nm_stream_map', 'nm_waste_type_map', 'operator_aliases'
    ] loop
        execute format('drop trigger if exists %I on lineage.%I',
                       relation || '_append_only', relation);
        execute format(
            'create trigger %I before update or delete on lineage.%I '
            'for each row execute function lineage.reject_mutation()',
            relation || '_append_only', relation
        );
    end loop;
end
$$;

revoke update, delete on lineage.nd_status_map, lineage.nd_stream_map,
    lineage.nd_segment_map, lineage.nd_survey_segment_map, lineage.tx_status_map,
    lineage.nm_stream_map, lineage.nm_waste_type_map, lineage.operator_aliases
    from glasswell_pipeline, glasswell_api;
grant select on lineage.conformance_rule_publications to glasswell_pipeline, glasswell_api;
