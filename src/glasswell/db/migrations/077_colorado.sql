-- Colorado as a registration. The fifth jurisdiction arrives as rows: one lineage.jurisdictions
-- registration, its jurisdiction_rules children, the ECMC status codebook a read-time
-- resolver reads, four staging tables, a tile mart and the schedule rows that make
-- the first load the scheduler's rather than an operator's. Nothing in api/, marts/ or web/ is
-- edited to add it, which is the claim this file exists to make good.
--
-- The API prefix is written down exactly once, in the registration insert below, and every
-- other statement in this file reaches it through lineage.jurisdictions_as_of. That is the
-- difference between declaring an identity and hardcoding one.
--
-- REPOINT CHECKLIST (integrator, at the merge train):
--   1. evidence_tag UNRELEASED -> the tag that first carries the Colorado registration and its
--      rules. It appears ONCE, at the conformance_rule_publications insert; the registration
--      reads it back from that row, so a half-repoint is not expressible in this file.
--   2. evidence_commit forty zeros -> the FIRST COMMIT ON MAIN THAT CONTAINS THESE RULE IDS,
--      which is the MERGE COMMIT of this track's PR and not the head this branch was written
--      against. scripts/release.py says so and tests/unit/test_release_tooling.py runs
--      `git grep -q <rule_id> <commit> -- src/` to prove it.
--   3. published_vintage 2026-09-01 -> the vintage of the ECMC archives these decisions
--      describe. It is read against the host's today, so it must never be a date the deploy
--      host has not reached: a rule published in the future resolves nowhere and
--      /v1/conformance/<id> serves 404 for it.
--   4. The registration's effective_from and published_at 2026-09-02 -> the date the tag is
--      cut. Both appear in the registration insert and again in the jurisdiction_rules insert,
--      and they must move together: jurisdiction_rules carries a composite foreign key on
--      (jurisdiction_code, effective_from, published_at), so a half-repoint aborts the migrate.
--      NEVER a date the deploy host has not reached: the status resolver reads the
--      registration through jurisdictions_as_of(current_date, current_date), so a future
--      registration resolves nowhere and Colorado draws unmapped with no error to say so.
--   5. seed/jurisdictions.py CO_REGISTERED_ON / CO_EVIDENCE_TAG / CO_EVIDENCE_COMMIT -> the
--      same three values, in the same commit. The seed is the second writer and
--      tests/contract/test_jurisdiction_parity.py holds the two copies to each other.
-- The jurisdiction code and the rule ids are immutable and must not change during the repoint.

-- The evidence pair, written once for all twenty-two Colorado rules: sixteen data rules and the
-- six cadence rules the schedule rows point at. 049's trigger refuses a conformance rule whose
-- publication is not registered, so this lands before any seeder that carries them.
insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
select rule_id, date '2026-09-01', 'v0.78',
       '5b37bf0363095b3e0cda2d6c3fb5d57e235de28f'
  from unnest(array[
       'cr_co_wells_api10_1',
       'cr_co_wells_status_vocab_1',
       'cr_co_wells_dedup_1',
       'cr_co_wells_source_selection_1',
       'cr_co_wells_datum_1',
       'cr_co_wells_geometry_provenance_1',
       'cr_co_wells_location_qualifier_1',
       'cr_co_wells_geometry_scope_1',
       'cr_co_wells_effective_1',
       'cr_co_wells_well_type_1',
       'cr_co_inventory_not_served_1',
       'cr_co_production_liquids_1',
       'cr_co_production_entity_key_1',
       'cr_co_production_grain_1',
       'cr_co_production_schema_drift_1',
       'cr_co_production_vintage_1',
       'cr_job_cadence_co_ecmc_gis_1',
       'cr_job_cadence_co_ecmc_production_1',
       'cr_job_cadence_co_wells_1',
       'cr_job_cadence_co_production_1',
       'cr_job_cadence_co_tiles_1',
       'cr_job_cadence_co_counts_1'
  ]::text[]) rule_id
on conflict (rule_id) do nothing;

-- Staging: source-faithful text and nothing else. No opinions, no serving grants, and every
-- column named as ECMC names it so a reader can hold the file and the table side by side.
create table if not exists staging.co_ecmc_wells (
    manifest_id        text not null references lineage.manifests (manifest_id),
    source_row_ordinal integer not null,
    ingested_at        timestamptz not null default now(),
    api                text,
    api_county         text,
    api_seq            text,
    api_label          text,
    operat_num         text,
    operator           text,
    well_name          text,
    well_num           text,
    spud_date          text,
    max_md             text,
    max_tvd            text,
    facil_id           text,
    facil_type         text,
    facil_stat         text,
    well_class         text,
    stat_date          text,
    loc_qual           text,
    loc_id             text,
    section            text,
    township           text,
    "range"            text,
    meridian           text,
    latitude           text,
    longitude          text,
    geom               geometry(Point, 4326),
    primary key (manifest_id, source_row_ordinal)
);

comment on table staging.co_ecmc_wells is
    'ECMC well headers, verbatim. The API column is eight characters and carries no state code;'
    ' cr_co_wells_api10_1 is what builds the API-10 from api_county and api_seq, and the'
    ' quoted "range" is the PLSS range as ECMC spells it, not a type name.';

create table if not exists staging.co_ecmc_directional_bh (
    manifest_id        text not null references lineage.manifests (manifest_id),
    source_row_ordinal integer not null,
    ingested_at        timestamptz not null default now(),
    api                text,
    api_label          text,
    operator           text,
    well_name          text,
    bh_status          text,
    md                 text,
    tvd                text,
    deviation          text,
    field_code         text,
    field_name         text,
    lat                text,
    "long"             text,
    utm_x              text,
    utm_y              text,
    geom               geometry(Point, 4326),
    primary key (manifest_id, source_row_ordinal)
);

create table if not exists staging.co_ecmc_directional_lines (
    manifest_id        text not null references lineage.manifests (manifest_id),
    source_row_ordinal integer not null,
    ingested_at        timestamptz not null default now(),
    api                text,
    api_label          text,
    operator           text,
    well_name          text,
    dir_status         text,
    md                 text,
    tvd                text,
    deviation          text,
    field_code         text,
    field_name         text,
    geom               geometry(Geometry, 4326),
    primary key (manifest_id, source_row_ordinal)
);

comment on table staging.co_ecmc_directional_lines is
    'Filed traces, not survey paths: ECMC publishes no stations, so cr_co_wells_geometry_scope_1'
    ' stages these and promotes none of them until a rule says what a Colorado lateral is.';

create table if not exists staging.co_ecmc_production (
    manifest_id           text not null references lineage.manifests (manifest_id),
    source_row_ordinal    integer not null,
    ingested_at           timestamptz not null default now(),
    docnum                text,
    reportmonth           text,
    reportyear            text,
    daysproduced          text,
    accepteddate          text,
    revised               text,
    opname                text,
    opnumber              text,
    facilityid            text,
    apicountycode         text,
    apisequencenumber     text,
    apisidetrack          text,
    well                  text,
    wellstatus            text,
    formationcode         text,
    oilproduced           text,
    oilsales              text,
    oiladjustment         text,
    oilgravity            text,
    gasproduced           text,
    gassales              text,
    gasbtusales           text,
    gasusedonlease        text,
    gasshrinkage          text,
    gaspressuretubing     text,
    gaspressurecasing     text,
    waterproduced         text,
    waterpressuretubing   text,
    waterpressurecasing   text,
    flaredvented          text,
    bominvent             text,
    eominvent             text,
    primary key (manifest_id, source_row_ordinal)
);

comment on table staging.co_ecmc_production is
    'Column names are the rolling file''s spellings. One archive year spells three of them'
    ' differently and moves a fourth; cr_co_production_schema_drift_1 registers the aliases, so'
    ' the parse resolves each file against its own header rather than by ordinal.';

grant select, insert, delete on staging.co_ecmc_wells to glasswell_pipeline;
grant select, insert, delete on staging.co_ecmc_directional_bh to glasswell_pipeline;
grant select, insert, delete on staging.co_ecmc_directional_lines to glasswell_pipeline;
grant select, insert, delete on staging.co_ecmc_production to glasswell_pipeline;

-- How good a coordinate is, on the row that holds the coordinate. Nullable, so no resident
-- jurisdiction's geometry moves: only a promotion that has a location-qualifier rule writes it,
-- and Colorado's is cr_co_wells_location_qualifier_1. It is not geometry_provenance, which
-- answers which feature this is; the two are orthogonal axes with disjoint vocabularies, and
-- registering the second under the first's key would serve two answers on one screen.
alter table canonical.well_spatial
    add column if not exists location_qualifier text;

comment on column canonical.well_spatial.location_qualifier is
    'The class the source''s own coordinate-quality field maps to, where the jurisdiction'
    ' registers a location_qualifier decision. Null where none is registered, which is a'
    ' different fact from a coordinate whose quality the regulator did not state.';

-- The codebook, as rows. decode is ECMC's own wording, kept beside the mapping so the decision
-- can be read against its source; status_canonical is never null, because two codes are
-- documented and have no equivalent and carry a registered class rather than a gap.
create table if not exists lineage.co_facility_status_map (
    status            text primary key,
    decode            text not null,
    status_canonical  text not null,
    published_vintage date not null
);

comment on table lineage.co_facility_status_map is
    'ECMC Facil_Stat -> canonical well status, from the live Well Status reference list'
    ' (cr_co_wells_status_vocab_1). Three ECMC legends disagree; that rule says which governs.';

insert into lineage.co_facility_status_map (status, decode, status_canonical, published_vintage)
values
    ('PA', 'PLUGGED AND ABANDONED WELL.', 'plugged', date '2026-09-01'),
    ('PR', 'PRODUCING WELL.', 'active', date '2026-09-01'),
    ('AL', 'ABANDONED LOCATION: PERMIT VACATED; PER OPERATOR: WELL HAS NOT BEEN SPUD.',
     'expired', date '2026-09-01'),
    ('SI', 'SHUT-IN WELL: COMPLETED WELL IS NOT PRODUCING BUT IS MECHANICALLY CAPABLE OF'
     ' PRODUCTION.', 'inactive', date '2026-09-01'),
    ('TA', 'TEMPORARILY ABANDONED WELL: COMPLETED WELL NOT MECHANICALLY CAPABLE OF PRODUCTION'
     ' WITHOUT INTERVENTION.', 'temporarily_abandoned', date '2026-09-01'),
    ('AP', 'ACTIVE PERMIT: APPROVED PERMIT TO DRILL WELL; NOT YET REPORTED AS SPUD.',
     'permitted', date '2026-09-01'),
    ('IJ', 'INJECTION WELL FOR WASTE DISPOSAL OR SECONDARY RECOVERY.', 'service',
     date '2026-09-01'),
    ('EP', 'EXPIRED PERMIT: EXPIRED PERMIT TO DRILL WELL.', 'expired', date '2026-09-01'),
    ('WO', 'WAITING ON COMPLETION: WELL HAS BEEN DRILLED BUT IS NOT YET REPORTED AS COMPLETED.',
     'drilling', date '2026-09-01'),
    ('AC', 'ACTIVE WELL: GAS STORAGE, OBSERVATION, OR DOMESTIC WELL.', 'service',
     date '2026-09-01'),
    ('DG', 'DRILLING: WELL HAS SPUD BUT IS NOT REPORTED AS COMPLETED.', 'drilling',
     date '2026-09-01'),
    ('SO', 'SUSPENDED OPERATIONS: DRILLING OPERATIONS SUSPENDED BEFORE REACHING PLANNED TOTAL'
     ' DEPTH.', 'documented_unmapped', date '2026-09-01'),
    ('UN', 'UNKNOWN: OLD WELL WITH MINIMAL INFORMATION.', 'documented_unmapped',
     date '2026-09-01')
on conflict (status) do nothing;

drop trigger if exists co_facility_status_map_append_only on lineage.co_facility_status_map;
create trigger co_facility_status_map_append_only
    before update or delete on lineage.co_facility_status_map
    for each row execute function lineage.reject_mutation();

create index if not exists co_facility_status_map_publication_idx
    on lineage.co_facility_status_map (published_vintage, status);

-- This file does NOT define canonical.status_resolution, and the omission is the decision.
--
-- 073's own comment invites a fifth state to bring its own arm here, and this migration did
-- until the facets track's resolver landed: that track replaces the view with a keyed table,
-- lineage.status_resolution_resolved, rebuilt by lineage.refresh_status_resolution() from the
-- registration resolving today and the per-regulator map. Two writers of one view, merged in
-- either order, means one of them is silently discarded -- and since that track merges last,
-- the arm written here would be the one discarded, leaving every Colorado well resolving
-- unmapped with no error anywhere to say so.
--
-- So the codebook above is registered and this file stops there. What a registry-driven
-- resolver owes Colorado is exact and checkable: one row per (identity_prefix, status) for the
-- thirteen rows of lineage.co_facility_status_map, at the prefix the CO registration resolves
-- to. tests/integration/test_migration_colorado.py states it as a query and asserts it against
-- the resolved table wherever that table exists.

grant select on lineage.co_facility_status_map to glasswell_pipeline, glasswell_api;
revoke update, delete on lineage.co_facility_status_map
    from glasswell_pipeline, glasswell_api;

-- The tile mart: a point layer and nothing else, for the reason New Mexico has one.
-- cr_co_wells_geometry_scope_1 is the row that says the directional archives are staged and
-- not promoted this release.
create table if not exists marts.co_wells_tile (
    api10               text primary key,
    operator_name       text,
    status_canonical    text,
    status_reported     text,
    well_type_reported  text,
    county_code         text,
    spud_year           integer,
    loc_qual_class      text,
    geometry_provenance text,
    geom                geometry(Point, 4326) not null,
    derivation_id       text not null
);

create index if not exists co_wells_tile_geom_idx on marts.co_wells_tile using gist (geom);

comment on column marts.co_wells_tile.status_canonical is
    'Resolved by the mart refresh from canonical.status_resolution, never written by the'
    ' promotion: canonical.wells is append-only and ECMC refreshes daily, so a class written at'
    ' promotion would invent a valid time the regulator never filed (cr_co_wells_status_vocab_1).';
comment on column marts.co_wells_tile.loc_qual_class is
    'Loc_Qual''s first token, case-folded: how good the coordinate is, which is a different'
    ' axis from which feature it is. 44.67% of these points are planned locations'
    ' (cr_co_wells_location_qualifier_1), and the well card has to say so.';
comment on column marts.co_wells_tile.geometry_provenance is
    'The geom_type served verbatim, constant surface this release'
    ' (cr_co_wells_geometry_provenance_1). Published rather than omitted because the legend'
    ' reads a registered class the box does not hold as zero rather than as absent.';

create or replace view marts.tile_co_wells as
select api10, operator_name, status_canonical, status_reported, well_type_reported, county_code,
       spud_year, loc_qual_class, geometry_provenance, derivation_id, geom
  from marts.co_wells_tile;

grant select on marts.co_wells_tile to glasswell_api;
grant select on marts.tile_co_wells to martin, glasswell_api;
grant select, insert, delete, truncate on marts.co_wells_tile to glasswell_pipeline;

-- One row per line: declared_poll_policy_ids() scrapes the leading tuple of each line, so a row
-- that does not begin its own line is invisible to the guard that pairs sources with cadences.
-- The archives get a null interval and an owner-triggered cadence, the nm_ocd_wells_gis shape:
-- the 2.49 GB backfill is its own dispatch, and a poll interval on a source nothing will ever
-- poll is the same false claim in miniature.
insert into lineage.source_poll_policies
    (source_id, cadence, expected_poll_interval, attempt_timeout)
values
    ('co_ecmc_wells_shp', 'Daily', interval '1 day', interval '6 hours'),
    ('co_ecmc_directional_bh', 'Daily', interval '1 day', interval '6 hours'),
    ('co_ecmc_directional_lines', 'Daily', interval '1 day', interval '6 hours'),
    ('co_ecmc_monthly_prod', 'Monthly, mid-month', interval '35 days', interval '6 hours'),
    ('co_ecmc_prod_reports', 'Owner-triggered; the archive backfill is its own dispatch', null,
     interval '6 hours')
on conflict (source_id) do nothing;

insert into lineage.jurisdiction_codes (jurisdiction_code, level)
values ('CO', 'state')
on conflict do nothing;

-- source_ids is complete, not curated: every lineage.sources row carrying this jurisdiction.
-- identity_pattern is derived from the prefix rather than restated, and the evidence pair is
-- read back from the publication rows above, so a registration cannot claim a tag its own
-- rules do not carry.
insert into lineage.jurisdictions (
    jurisdiction_code, effective_from, published_at, evidence_tag, evidence_commit,
    name, regulator_name, regulator_url, identity_scheme, identity_is_unique,
    identity_prefix, identity_pattern, source_ids, liquids_basis, wells_tile_layer_id,
    map_colour, neighbors_available, explorer_default, land_grid_state, land_grid_scope,
    status_dataset_detail, rationale, wells_layer_id, wells_style_layer_ids, wells_draw_order,
    wells_default_on, wells_snapshot_key, wells_subtitle_template, legend_note)
select r.jurisdiction_code, date '2026-09-02', date '2026-09-02',
       evidence.evidence_tag, evidence.evidence_commit,
       r.name, r.regulator_name, r.regulator_url, 'api10', true,
       r.identity_prefix, '^' || r.identity_prefix || '[0-9]{8}$', r.source_ids,
       r.liquids_basis, r.wells_tile_layer_id, r.map_colour,
       false, false, false, false,
       r.status_dataset_detail, r.rationale, r.wells_layer_id, r.wells_style_layer_ids,
       r.wells_draw_order, true, null::text, r.wells_subtitle_template, r.legend_note
  from (values
    ('CO', 'Colorado',
     'Colorado Energy and Carbon Management Commission',
     'https://ecmc.state.co.us', '05',
     array['co_ecmc_wells_shp', 'co_ecmc_directional_bh', 'co_ecmc_directional_lines',
           'co_ecmc_monthly_prod', 'co_ecmc_prod_reports']::text[],
     'oil+condensate'::text, 'co_wells'::text, '#7C8B96'::text,
     'Current effective-dated well entities, not accumulated source revisions.'::text,
     'Served from the ECMC GIS shapefiles and the rolling production CSV. The status class is'
     ' resolved at read time rather than written by the promotion, because the header refreshes'
     ' daily against an append-only spine; ECMC files one liquid stream with no condensate'
     ' column, so the liquids basis is oil plus condensate by the shape of the filing rather'
     ' than by a rollup; and inventory is a registered refusal rather than an omission, because'
     ' no PLSS grid, no spacing-unit source and no support score exist for Colorado and'
     ' Protocol 4D admits no slot without them.'::text,
     'co-wells'::text, array['co-wells', 'co-wells-struck']::text[], 45,
     'ECMC well headers · {count} points, eleven of thirteen published status codes classed and'
     ' two documented without an equivalent (cr_co_wells_status_vocab_1) · 44.67% of points are'
     ' permit locations, not surveyed (cr_co_wells_location_qualifier_1) · surface points'
     ' only'::text,
     'Colorado''s AL code is a vacated permit, not an abandoned well: those points have no'
     ' wellbore and are drawn as expired permits (cr_co_wells_status_vocab_1).'::text)
  ) as r(jurisdiction_code, name, regulator_name, regulator_url, identity_prefix, source_ids,
         liquids_basis, wells_tile_layer_id, map_colour, status_dataset_detail, rationale,
         wells_layer_id, wells_style_layer_ids, wells_draw_order, wells_subtitle_template,
         legend_note)
 cross join (select evidence_tag, evidence_commit
               from lineage.conformance_rule_publications
              where rule_id = 'cr_co_wells_status_vocab_1') evidence
on conflict do nothing;

-- Guarded on residency exactly as 073's and 075's inserts are: migrations run before the seed,
-- so on a fresh database lineage.conformance_rules is empty and seed/jurisdictions.py supplies
-- these. On a database that is already seeded -- the deployed one -- this is what lands them.
insert into lineage.jurisdiction_rules
    (jurisdiction_code, effective_from, published_at, decision, rule_id, serving, note)
select r.jurisdiction_code, date '2026-09-02', date '2026-09-02',
       r.decision, r.rule_id, true, null::text
  from (values
    ('CO', 'status_vocabulary', 'cr_co_wells_status_vocab_1'),
    ('CO', 'identity', 'cr_co_wells_api10_1'),
    ('CO', 'deduplication', 'cr_co_wells_dedup_1'),
    ('CO', 'source_selection', 'cr_co_wells_source_selection_1'),
    ('CO', 'crs', 'cr_co_wells_datum_1'),
    ('CO', 'geometry_provenance', 'cr_co_wells_geometry_provenance_1'),
    ('CO', 'location_qualifier', 'cr_co_wells_location_qualifier_1'),
    ('CO', 'geometry_scope', 'cr_co_wells_geometry_scope_1'),
    ('CO', 'inventory_jurisdiction', 'cr_co_inventory_not_served_1'),
    ('CO', 'liquids', 'cr_co_production_liquids_1'),
    ('CO', 'entity_key', 'cr_co_production_entity_key_1'),
    ('CO', 'production_grain', 'cr_co_production_grain_1'),
    ('CO', 'cumulatives_scope', 'cr_co_production_grain_1')
  ) as r(jurisdiction_code, decision, rule_id)
 where exists (select 1 from lineage.conformance_rules c where c.rule_id = r.rule_id)
on conflict do nothing;

-- The schedule rows, written by both writers. seed/schedules.py carries them too and the parity
-- gate holds the two copies equal; this insert is what makes a deploy that seeds nothing still
-- schedule Colorado. Every one is guarded on residency for the reason the rule rows above are:
-- on a fresh database the sources and the cadence rules are not there yet and the seed supplies
-- all four tables together.
insert into lineage.scheduled_jobs
    (job_id, label, kind, entry_point, argv, anchor_source_id, jurisdiction, run_as, rationale)
select j.job_id, j.label, j.kind, j.entry_point, j.argv, j.anchor_source_id, j.jurisdiction,
       'glasswell', j.rationale
  from (values
    ('co_ecmc_gis', 'Colorado ECMC GIS ingest', 'ingest', 'glasswell.ingest.co_ecmc_gis',
     array['--layer', 'all']::text[], 'co_ecmc_directional_bh', 'CO'::text,
     'The three ECMC archives are republished together every night and are pulled in one pass,'
     ' so one job carries three job_sources rows and takes the shortest of their'
     ' intervals.'::text),
    ('co_ecmc_production', 'Colorado ECMC rolling production ingest', 'ingest',
     'glasswell.ingest.co_ecmc_production', array['--file', 'rolling']::text[],
     'co_ecmc_monthly_prod', 'CO'::text,
     'The rolling file only. The 2.49 GB annual archives are their own dispatch and no schedule'
     ' claims them, which is why their source carries no interval.'::text),
    ('co_wells', 'Colorado header promotion', 'ingest', 'glasswell.ingest.co_wells',
     array[]::text[], 'co_ecmc_wells_shp', 'CO'::text,
     'The promotion reads the staged header table, so it reacts to the ingest that wrote it'
     ' rather than to a clock of its own.'::text),
    ('co_production', 'Colorado production promotion', 'ingest',
     'glasswell.ingest.co_production', array[]::text[], 'co_ecmc_monthly_prod', 'CO'::text,
     'The promotion projects the staged rolling file and has nothing to do when the pull was'
     ' unchanged.'::text),
    ('co_tiles', 'Colorado tile mart', 'mart', 'glasswell.marts.wells',
     array['--jurisdiction', 'CO']::text[], 'co_ecmc_monthly_prod', 'CO'::text,
     'One engine, one entry point: the jurisdiction is an argument and the profile it names is a'
     ' row, so a fifth mart is this row and no module.'::text),
    ('co_counts', 'Registry well counts after Colorado', 'mart', 'glasswell.marts.counts',
     array[]::text[], 'co_ecmc_monthly_prod', null::text,
     'marts.counts has no natural source of its own: it measures whatever the registry holds,'
     ' so it anchors on the source its dependency anchors on, and this row exists because'
     ' /v1/jurisdictions serves a new registration with no well_count and no measured_on until'
     ' something has measured it.'::text)
  ) as j(job_id, label, kind, entry_point, argv, anchor_source_id, jurisdiction, rationale)
 where exists (select 1 from lineage.sources s where s.source_id = j.anchor_source_id)
on conflict do nothing;

insert into lineage.job_sources (job_id, source_id)
select e.job_id, e.source_id
  from (values
    ('co_ecmc_gis', 'co_ecmc_directional_bh'),
    ('co_ecmc_gis', 'co_ecmc_directional_lines'),
    ('co_ecmc_gis', 'co_ecmc_wells_shp'),
    ('co_ecmc_production', 'co_ecmc_monthly_prod'),
    ('co_wells', 'co_ecmc_wells_shp'),
    ('co_production', 'co_ecmc_monthly_prod')
  ) as e(job_id, source_id)
 where exists (select 1 from lineage.scheduled_jobs j where j.job_id = e.job_id)
   and exists (select 1 from lineage.sources s where s.source_id = e.source_id)
on conflict do nothing;

-- launch, not observe, and the exception is conditioned rather than assumed: Colorado adds no
-- unit file, so no installed timer drives any of these six entry points and there is nothing a
-- launched run could collide with. Each job's own cr_job_cadence_<job>_1 rationale states it.
insert into lineage.job_schedules
    (job_id, effective_from, published_at, rule_id, trigger, launch_mode, cadence_interval,
     cadence_note, memory_max, timeout_seconds)
select s.job_id, date '2026-09-02', date '2026-09-02',
       'cr_job_cadence_' || s.job_id || '_1', s.trigger, 'launch', s.cadence_interval,
       s.cadence_note, s.memory_max, s.timeout_seconds
  from (values
    ('co_ecmc_gis', 'cadence', interval '1 day',
     'Daily, the cadence the three archives'' own stamps show'::text, '6G'::text, 3600),
    ('co_ecmc_production', 'cadence', interval '35 days',
     'Every 35 days; the rolling file carries one mid-month stamp'::text, '6G'::text, 3600),
    ('co_wells', 'after_dependency', null::interval,
     'After the GIS ingest that stages the header table'::text, '6G'::text, 3600),
    ('co_production', 'after_dependency', null::interval,
     'After the ingest that stages the rolling production file'::text, '6G'::text, 3600),
    ('co_tiles', 'after_dependency', null::interval,
     'After the two promotions it projects'::text, '6G'::text, 3600),
    ('co_counts', 'after_dependency', null::interval,
     'After the Colorado mart, so the served counts are measured'::text, '2G'::text, 1800)
  ) as s(job_id, trigger, cadence_interval, cadence_note, memory_max, timeout_seconds)
 where exists (select 1 from lineage.scheduled_jobs j where j.job_id = s.job_id)
   and exists (select 1 from lineage.conformance_rules c
                where c.rule_id = 'cr_job_cadence_' || s.job_id || '_1')
on conflict do nothing;

insert into lineage.job_dependencies (job_id, depends_on_job_id, trigger_on, rationale)
select d.job_id, d.depends_on_job_id, 'changed', d.rationale
  from (values
    ('co_wells', 'co_ecmc_gis',
     'The header promotion reads what the GIS ingest staged, so a pull that changed nothing'
     ' leaves it with nothing to promote.'::text),
    ('co_production', 'co_ecmc_production',
     'The production promotion reads the staged rolling file and reacts to a pull that actually'
     ' moved rows.'::text),
    ('co_tiles', 'co_wells', 'The tile mart projects the promoted header spine.'::text),
    ('co_tiles', 'co_production',
     'The mart''s status and production facets are read from the promoted rows, so it waits on'
     ' both promotions rather than drawing a header spine with no volumes behind it.'::text),
    ('co_counts', 'co_tiles',
     'The registry''s served counts are measured after the mart that changed what there is to'
     ' count, never asserted.'::text)
  ) as d(job_id, depends_on_job_id, rationale)
 where exists (select 1 from lineage.scheduled_jobs j where j.job_id = d.job_id)
   and exists (select 1 from lineage.scheduled_jobs p where p.job_id = d.depends_on_job_id)
on conflict do nothing;

-- Which jurisdictions the per-well cumulative mart covers, as a registry dimension rather than
-- a tuple in the mart. North Dakota's row is appended at its own restatement instant, where
-- 075 left its rules; the rule each names is the one deciding whether the jurisdiction writes a
-- well-grain row, because the mart reads only those and a jurisdiction in scope without one
-- would publish never_reported over production that is sitting in canonical.
--
-- That instant is read from the registry rather than written down. It is 075's RESTATED_ON,
-- which is one of the five values the integrator repoints at the train, and a literal here
-- would match nothing the moment it moved -- leaving North Dakota with no cumulatives_scope
-- row and the migration reporting success.
insert into lineage.jurisdiction_rules
    (jurisdiction_code, effective_from, published_at, decision, rule_id, serving, note)
select j.jurisdiction_code, j.effective_from, j.published_at, 'cumulatives_scope',
       'cr_nd_pool_rollup_1', true, null::text
  from lineage.jurisdictions j
 where j.jurisdiction_code = 'ND'
   and (j.effective_from, j.published_at) = (
           select effective_from, published_at from lineage.jurisdictions
            where jurisdiction_code = 'ND'
            order by published_at desc, effective_from desc
            limit 1)
   and exists (select 1 from lineage.conformance_rules where rule_id = 'cr_nd_pool_rollup_1')
on conflict do nothing;
