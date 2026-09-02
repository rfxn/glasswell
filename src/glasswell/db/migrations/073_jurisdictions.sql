-- The jurisdiction registry: which regulators glasswell serves, on whose authority, under
-- which conformance rules, and how many wells each was measured to hold. R8 in its own
-- schema: a mapping decision that exists only in code fails review, so the four API-10
-- prefixes the serving path has been keyed on since 009 become rows with a rationale and a
-- date. Registrations are append-only and carry two clocks -- valid time (effective_from) and
-- knowledge time (published_at) -- so a supersession is a later effective_from and a
-- correction is a later published_at at the same one. Neither is ever an edit.
--
-- REPOINT CHECKLIST (integrator, at the merge train):
--   1. evidence_tag UNRELEASED -> the tag that first carries these registrations
--   2. evidence_commit forty zeros -> the main head this branch was written against
--   3. effective_from / published_at 2026-09-01 -> confirm it is the date the tag is cut, or
--      correct it
-- The jurisdiction codes and the rule ids are immutable and must not change during the
-- repoint. Both literals appear exactly once each, in the registration insert below and
-- nowhere else: a quoted placeholder anywhere above it re-arms the release guard through
-- prose, so this header names the columns rather than their values.

create table if not exists lineage.jurisdiction_codes (
    jurisdiction_code text primary key check (jurisdiction_code ~ '^[A-Z]{2}(-[A-Z]{2})?$'),
    level             text not null check (level in ('state', 'province'))
);

comment on table lineage.jurisdiction_codes is
    'Identity spine both jurisdiction ledgers reference. A code is a code before it is a'
    ' registration, so the registration ledger and the measurement ledger point at one row.';

create table if not exists lineage.jurisdictions (
    jurisdiction_code    text not null references lineage.jurisdiction_codes,
    effective_from       date not null,
    published_at         date not null,
    evidence_tag         text not null check (btrim(evidence_tag) <> ''),
    evidence_commit      text not null check (evidence_commit ~ '^[0-9a-f]{40}$'),
    name                 text not null,
    regulator_name       text not null,
    regulator_url        text not null check (regulator_url ~ '^https://'),
    identity_scheme      text not null check (identity_scheme in ('api10', 'uwi')),
    identity_is_unique   boolean not null default true,
    identity_prefix      text,
    identity_pattern     text,
    source_ids           text[] not null check (cardinality(source_ids) > 0),
    liquids_basis        text,
    wells_tile_layer_id  text,
    map_colour           text check (map_colour ~ '^#[0-9A-F]{6}$'),
    neighbors_available  boolean not null default false,
    -- Which jurisdiction the explorer opens on is a fact about the data, not a choice in the
    -- client: exactly one registration carries it, and the reason is in `rationale`.
    explorer_default     boolean not null default false,
    land_grid_state      boolean not null default false,
    land_grid_scope      boolean not null default false,
    status_dataset_detail text,
    rationale            text not null,
    primary key (jurisdiction_code, effective_from, published_at),
    check ((identity_prefix is null) = (identity_pattern is null)),
    -- coalesce, not the bare comparison: `false or null` is null and a CHECK rejects only on
    -- false, so without it an api10 registration with no prefix is admitted and every prefix
    -- lookup on the serving path then misses it (N-1).
    check (identity_scheme <> 'api10'
           or coalesce(identity_prefix ~ '^[0-9]{2}$', false)),
    check (not land_grid_state or land_grid_scope)
);

comment on table lineage.jurisdictions is
    'Append-only jurisdiction registrations under two clocks. A later effective_from supersedes;'
    ' a later published_at at the same effective_from restates what was published about it.'
    ' There is no effective_to: append-only means it could never be set.';

comment on column lineage.jurisdictions.identity_is_unique is
    'False where API-10 is not a well key (UT, AK, AL, MS). A property of the key, not of the'
    ' scheme, which is why it is its own boolean rather than a widened identity_scheme.';

-- At most one default per registration instant. The resolved set is the wider claim and no
-- index can make it: two registrations a day apart both resolve, so the standing gate in
-- test_jurisdiction_parity.py is what requires exactly one, and requires it to exist.
create unique index if not exists jurisdictions_explorer_default_key
    on lineage.jurisdictions (effective_from, published_at) where explorer_default;

create unique index if not exists jurisdictions_prefix_key
    on lineage.jurisdictions (identity_prefix, effective_from, published_at)
    where identity_prefix is not null;

create table if not exists lineage.jurisdiction_rules (
    jurisdiction_code text not null references lineage.jurisdiction_codes,
    effective_from    date not null,
    published_at      date not null,
    decision          text not null check (decision ~ '^[a-z][a-z0-9_]*(:[a-z][a-z0-9_]*)?$'),
    rule_id           text not null references lineage.conformance_rules (rule_id),
    serving           boolean not null default true,
    note              text,
    primary key (jurisdiction_code, effective_from, published_at, decision, rule_id),
    foreign key (jurisdiction_code, effective_from, published_at)
        references lineage.jurisdictions (jurisdiction_code, effective_from, published_at)
);

comment on table lineage.jurisdiction_rules is
    'One row per (registration, decision, rule). An array rather than a scalar column per'
    ' decision is what lets Montana carry both inventory rules with only one serving, and'
    ' makes a seventh decision a row instead of a migration.';

create unique index if not exists jurisdiction_rules_serving_key
    on lineage.jurisdiction_rules (jurisdiction_code, effective_from, published_at, decision)
    where serving;

create table if not exists lineage.jurisdiction_well_counts (
    jurisdiction_code text not null references lineage.jurisdiction_codes,
    measured_on       date not null,
    status_canonical  text,
    -- A null discriminator cannot sit in a primary key and an expression cannot either, so the
    -- sentinel is a stored column. '*total*' rather than '' because a class id matches [a-z_]+.
    status_key        text generated always as (coalesce(status_canonical, '*total*')) stored,
    well_count        integer not null check (well_count >= 0),
    derivation_id     text not null references lineage.derivations,
    primary key (jurisdiction_code, measured_on, status_key)
);

comment on table lineage.jurisdiction_well_counts is
    'The measurement ledger, append-only. A null status_canonical is the jurisdiction total.'
    ' derivation_id is not null, so there is no count without the refresh that produced it.';

drop trigger if exists jurisdictions_append_only on lineage.jurisdictions;
create trigger jurisdictions_append_only
    before update or delete on lineage.jurisdictions
    for each row execute function lineage.reject_mutation();

drop trigger if exists jurisdiction_rules_append_only on lineage.jurisdiction_rules;
create trigger jurisdiction_rules_append_only
    before update or delete on lineage.jurisdiction_rules
    for each row execute function lineage.reject_mutation();

drop trigger if exists jurisdiction_well_counts_append_only on lineage.jurisdiction_well_counts;
create trigger jurisdiction_well_counts_append_only
    before update or delete on lineage.jurisdiction_well_counts
    for each row execute function lineage.reject_mutation();

-- Two clocks, so two parameters. There is no jurisdictions_current view: as_of is defined as
-- "the greatest vintage at or before this date", which a static view cannot honour -- the
-- failure 049 exists to prevent.
create or replace function lineage.jurisdictions_as_of(knowledge_as_of date, valid_as_of date)
returns setof lineage.jurisdictions
language sql stable parallel safe as $$
    select (ranked.registration).*
      from (select j as registration,
                   row_number() over (partition by j.jurisdiction_code
                       order by j.effective_from desc, j.published_at desc) as rank
              from lineage.jurisdictions j
             where j.published_at <= knowledge_as_of
               and j.effective_from <= valid_as_of) ranked
     where ranked.rank = 1;
$$;

comment on function lineage.jurisdictions_as_of(date, date) is
    'The registration serving at a knowledge instant for a valid instant. published_at desc is'
    ' the tie-breaker between a founding row and a restatement at the same effective_from.';

insert into lineage.jurisdiction_codes (jurisdiction_code, level)
values ('ND', 'state'), ('TX', 'state'), ('NM', 'state'), ('MT', 'state')
on conflict do nothing;

-- source_ids is complete, not curated: every lineage.sources row carrying this jurisdiction.
-- The parity gate asserts set equality against that table, so a source registered here and
-- left out of the array reddens rather than passing a membership check.
insert into lineage.jurisdictions (
    jurisdiction_code, effective_from, published_at, evidence_tag, evidence_commit,
    name, regulator_name, regulator_url, identity_scheme, identity_is_unique,
    identity_prefix, identity_pattern, source_ids, liquids_basis, wells_tile_layer_id,
    map_colour, neighbors_available, explorer_default, land_grid_state, land_grid_scope,
    status_dataset_detail, rationale)
select r.jurisdiction_code, date '2026-09-01', date '2026-09-01',
       'UNRELEASED', '0000000000000000000000000000000000000000',
       r.name, r.regulator_name, r.regulator_url, 'api10', true,
       r.identity_prefix, '^' || r.identity_prefix || '[0-9]{8}$', r.source_ids,
       r.liquids_basis, r.wells_tile_layer_id, r.map_colour,
       r.neighbors_available, r.explorer_default, r.land_grid_state, r.land_grid_scope,
       r.status_dataset_detail, r.rationale
  from (values
    ('ND', 'North Dakota',
     'ND Dept. of Mineral Resources, Oil and Gas Division',
     'https://www.dmr.nd.gov/oilgas/mprindex.asp', '33',
     array['nd_mpr_xlsx', 'nd_gis_wells', 'nd_gis_horizontals_line', 'nd_gis_spacing_units',
           'nd_gis_directionals', 'blm_plss_townships', 'blm_plss_sections']::text[],
     'oil+condensate'::text, 'nd_wells'::text, '#3FA55E'::text, true, true, true, true,
     'Current effective-dated well entities, not accumulated source revisions.'::text,
     'The founding jurisdiction: NDIC DMR files the monthly production report and the GIS'
     ' layers the spine was built on. The two BLM PLSS layers are registered here because ND'
     ' is the extent they were loaded for, which is what lineage.sources.jurisdiction records.'
     ' It carries explorer_default because it is the only jurisdiction serving well-grain'
     ' production history end to end, which is what the explorer opens on rather than an'
     ' alphabetical accident.'),
    ('TX', 'Texas',
     'Railroad Commission of Texas',
     'https://www.rrc.texas.gov/resource-center/research/data-sets-available-for-download/',
     '42',
     array['tx_gis_wells_county', 'tx_wellbore_ewa_csv']::text[],
     null::text, 'tx_wells'::text, '#7C8B96'::text, false, false, false, false,
     'Current effective-dated well entities, not accumulated source revisions.'::text,
     'Served from the RRC county GIS layers and the Wellbore Query export. Texas files'
     ' production at the lease, so no liquids basis and no pool-rollup decision are registered'
     ' and the API serves cr_tx_allocation_scope_1''s disclosure instead of an empty series.'),
    ('NM', 'New Mexico',
     'New Mexico EMNRD Oil Conservation Division',
     'https://www.emnrd.nm.gov/ocd/ocd-data/', '30',
     array['nm_ocd_wcproduction', 'nm_ocd_wellhistory', 'nm_ocd_wchistory', 'nm_ocd_podwc',
           'nm_ocd_pod', 'nm_ocd_ogrid', 'nm_ocd_pool', 'nm_ocd_spacingunit',
           'nm_ocd_property', 'nm_ocd_wells_gis', 'nm_c115b_upstream']::text[],
     'oil'::text, 'nm_wells'::text, '#3FA55E'::text, false, false, false, false,
     'Current effective-dated well entities, not accumulated source revisions.'::text,
     'Served from the OCD FTP tables, the public wells layer and the C-115B waste service.'
     ' The status class is resolved at read time rather than written by the promotion, and'
     ' condensate is filed as its own stream, so the liquids basis is oil alone.'),
    ('MT', 'Montana',
     'Montana DNRC Board of Oil and Gas Conservation',
     'https://bogfiles.dnrc.mt.gov', '25',
     array['mt_gis_wells', 'mt_gis_well_paths', 'mt_bogc_well_production',
           'mt_bogc_pru_production']::text[],
     'oil+condensate'::text, 'mt_wells'::text, '#7C8B96'::text, true, false, false, false,
     'Headers only for the statuses cr_mt_gis_status_vocab_1 promotes; the six it does not'
     ' quarantine as unknown_status, so this is below the surface-point count and the'
     ' difference is in the quarantine ledger, not lost.'::text,
     'Served from the MBOGC GIS layers and the two historical production files. The PRU file'
     ' reports at lease grain, so its inventory rule is registered and not serving; the well'
     ' paths are cartographic centrelines, which is why length has its own scope decision.')
  ) as r(jurisdiction_code, name, regulator_name, regulator_url, identity_prefix, source_ids,
         liquids_basis, wells_tile_layer_id, map_colour, neighbors_available, explorer_default,
         land_grid_state, land_grid_scope, status_dataset_detail, rationale)
on conflict do nothing;

-- Guarded on residency for the reason 071's rule insert is: migrations run before the seed, so
-- on a fresh database lineage.conformance_rules is empty, the join finds nothing and
-- seed/jurisdictions.py supplies these rows. On a database that is already seeded -- the
-- deployed one -- this is the statement that lands them.
insert into lineage.jurisdiction_rules
    (jurisdiction_code, effective_from, published_at, decision, rule_id, serving, note)
select r.jurisdiction_code, date '2026-09-01', date '2026-09-01',
       r.decision, r.rule_id, r.serving, r.note
  from (values
    ('ND', 'status_vocabulary', 'cr_nd_status_vocab_1', true, null::text),
    ('ND', 'geometry_provenance', 'cr_nd_geometry_provenance_1', true, null::text),
    ('ND', 'liquids', 'cr_nd_liquids_policy_1', true, null::text),
    ('ND', 'production_grain', 'cr_nd_pool_rollup_1', true, null::text),
    ('ND', 'inventory_jurisdiction', 'cr_nd_inventory_jurisdiction_1', true, null::text),
    ('ND', 'identity', 'cr_nd_api_identity_1', true, null::text),
    ('TX', 'status_vocabulary', 'cr_tx_status_vocab_1', true, null::text),
    ('TX', 'identity', 'cr_tx_api10_build_1', true, null::text),
    ('TX', 'absence:operator', 'cr_tx_operator_absence_1', true, null::text),
    ('NM', 'status_vocabulary', 'cr_nm_wellhistory_status_vocab_2', true, null::text),
    ('NM', 'geometry_provenance', 'cr_nm_wellhistory_geometry_provenance_1', true, null::text),
    ('NM', 'liquids', 'cr_nm_wcproduction_liquids_1', true, null::text),
    ('NM', 'production_grain', 'cr_nm_wcproduction_pool_rollup_1', true, null::text),
    ('NM', 'inventory_jurisdiction', 'cr_nm_wcproduction_inventory_jurisdiction_1', true,
     null::text),
    ('NM', 'identity', 'cr_nm_wchistory_api10_1', true, null::text),
    ('MT', 'status_vocabulary', 'cr_mt_gis_status_vocab_1', true, null::text),
    ('MT', 'geometry_provenance', 'cr_mt_paths_geometry_class_1', true, null::text),
    ('MT', 'liquids', 'cr_mt_liquids_policy_1', true, null::text),
    ('MT', 'inventory_jurisdiction', 'cr_mt_inventory_jurisdiction_1', true, null::text),
    ('MT', 'inventory_jurisdiction', 'cr_mt_pru_inventory_jurisdiction_1', false,
     'PRU lease grain'),
    ('MT', 'length_scope', 'cr_mt_paths_length_scope_1', true, null::text),
    ('MT', 'absence:operator', 'cr_mt_operator_absence_1', true, null::text)
  ) as r(jurisdiction_code, decision, rule_id, serving, note)
 where exists (select 1 from lineage.conformance_rules c where c.rule_id = r.rule_id)
on conflict do nothing;

-- /v1/jurisdictions serves every well count as a figure, so the request derivation has to be
-- able to prove the selector it addressed. Without this row every one of those handles is
-- refused as ambiguous rather than resolved to the file the wells were promoted from.
insert into lineage.selector_output_registry
    (operation, output_dataset, selector_profile, rationale)
values
    ('api.respond', 'api.jurisdictions', 'response_output',
     'The request derivation records the jurisdiction total and the per-status counts it'
     ' returned for one page of the registry at one knowledge cut.')
on conflict do nothing;

-- 071 labelled every row of the read-time status resolver with a literal '30'. Which
-- jurisdiction New Mexico's map answers for is registry data, so the label comes from the
-- registration instead. The mapping table is still per-regulator and a fifth state with
-- read-time resolution still brings its own table and its own arm here — no row can conjure a
-- codebook — but its API prefix, and whether it resolves at read time at all, are rows.
--
-- The coupling this creates is deliberate and worth naming: with no resolved NM registration
-- the view yields nothing and New Mexico's statuses read as unmapped. That is the same
-- refusal `load_jurisdictions` makes, one layer down, and the registry ships with its rows.
create or replace view canonical.status_resolution as
select j.identity_prefix as for_state_code,
       m.status          as for_status_reported,
       m.status_canonical as resolved_status
  from lineage.nm_wellhistory_status_map m
  join lineage.jurisdictions_as_of(current_date, current_date) j
    on j.jurisdiction_code = 'NM';

grant select on lineage.jurisdiction_codes, lineage.jurisdictions, lineage.jurisdiction_rules,
    lineage.jurisdiction_well_counts to glasswell_api, glasswell_pipeline;
grant execute on function lineage.jurisdictions_as_of(date, date)
    to glasswell_api, glasswell_pipeline;
grant insert on lineage.jurisdiction_well_counts to glasswell_pipeline;
