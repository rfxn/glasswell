-- Texas files production at the lease, so the largest jurisdiction in the spine has served no
-- well-level volume at all. This migration is the schema half of allocation v0: the RRC PDQ
-- dump lands at its native lease grain in canonical, and the per-well share -- an estimate --
-- lands in a mart that says so on every row. 4F.1 keeps the fact at its native grain and 4F.2
-- keeps the estimate out of canonical; 020_production_entity_key.sql:43-46 enforces it
-- independently, so a lease_allocated row cannot be written to canonical.production_monthly.
--
-- The Texas registration is superseded rather than edited. Its founding row says Texas files
-- at the lease so no liquids basis and no grain decision are registered, which stops being
-- true the day the allocation ships. lineage.jurisdictions is append-only and keyed on the
-- whole clock pair, so the correction is a new registration carrying every rule row and every
-- presentation column of the one it supersedes, plus the four decisions this track registers.
--
-- The facets trigger on lineage.jurisdictions (078_facet_status_resolution.sql:277-280) fires
-- lineage.refresh_status_resolution() on that append. It skips Texas, whose status vocabulary
-- rule carries no resolved_at and therefore resolves at promote time; the skip notice in the
-- migrate log is expected.
--
-- Between this migration and the phase that adds the Python profiles,
-- lineage.selector_output_registry names selector profiles _KNOWN_PROFILES does not contain,
-- so validate_selector would raise "selector registry contains unknown profiles" for a handle
-- on those datasets. Nothing serves such a handle in between: the datasets do not exist yet.
--
-- REPOINT CHECKLIST (integrator, at the merge train):
--   1. evidence_tag UNRELEASED -> the tag that first carries these rows. It appears ONCE, at
--      the conformance_rule_publications insert; the registration insert reads it back from
--      that row, so a half-repoint is not expressible in this file.
--   2. evidence_commit forty zeros -> the first commit on main that contains them, which is
--      the merge commit and not the head this branch was written against.
--   3. published_vintage 2026-09-02 -> the date the tag is cut. It is the conformance rules'
--      own clock and is read against the host's today, so it must never be a date the deploy
--      host has not reached: lineage/conformance.py:891 takes max(today, min(vintage)) as its
--      knowledge cut, so a rule published in the future leaves allocated_series_rule None and
--      the card falls back to the pending-allocation disclosure, while
--      api/routers/conformance.py:404 serves 404 for the rule id the cumulative row is still
--      citing -- a split brain in which the total says "allocated, see this rule" and the rule
--      does not exist.
--   4. The supersession's published_at 2026-09-06 or later. It is INDEPENDENT of item 3: it
--      need not equal that vintage, and unlike it, it MAY sit ahead of the host's today --
--      load_jurisdictions reads max(published_at) as its knowledge cut, not the host clock
--      (lineage/jurisdictions.py:207-209), which is why the v0.78 restatement shipped a day
--      ahead of the host and resolved. What it MUST be is strictly later than every
--      published_at Texas already carries (2026-09-02 founding, 2026-09-04 restatement), or
--      the supersession does not resolve and Texas keeps serving the row that says it has no
--      production; and neither the founding date plus one day nor the restatement date plus
--      one day, because standing gates plant a rival registration on each of those instants
--      and the partial unique indexes would refuse them.
--   5. seed/jurisdictions.py TX_SUPERSEDED_ON / TX_SUPERSEDED_EVIDENCE_TAG /
--      TX_SUPERSEDED_EVIDENCE_COMMIT -> the same three values, in the same commit. The seed is
--      the second writer.

-- The evidence pair, written once. 049's trigger refuses a conformance rule whose publication
-- is not registered, so this lands before the seeders that carry the rules themselves. The
-- three cadence rules belong to the jobs a later phase registers: the runbook's procedure
-- (docs/runbook-add-a-state.md:158-185) puts their publication evidence in the track's own
-- migration, which is this file, and their rows in seed/conformance_schedules.py.
insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
select rule_id, date '2026-09-02', 'UNRELEASED',
       '0000000000000000000000000000000000000000'
  from unnest(array[
       'cr_tx_pdq_format_1', 'cr_tx_pdq_scope_1', 'cr_tx_production_grain_1',
       'cr_tx_pdq_crosswalk_1', 'cr_tx_allocation_v0_1', 'cr_alloc_v0_error_bounds_1',
       'cr_tx_liquids_basis_1', 'cr_tx_gas_basis_1', 'cr_tx_geometry_provenance_1',
       'cr_tx_well_status_archive_1',
       'cr_job_cadence_ingest_tx_pdq_1', 'cr_job_cadence_marts_tx_allocation_1',
       'cr_job_cadence_marts_allocation_backtest_1'
  ]::text[]) rule_id
on conflict (rule_id) do nothing;

-- Staging: source-faithful text and nothing else. The dump is `}`-delimited with a header row
-- and no enclosure, so every column arrives as text and every opinion about it is a rule.
create table staging.tx_pdq_lease_cycle (
    manifest_id            text not null references lineage.manifests (manifest_id),
    source_row_ordinal     integer not null,
    oil_gas_code           text,
    district_no            text,
    lease_no               text,
    cycle_year_month       text,
    operator_no            text,
    field_no               text,
    field_type             text,
    gas_well_no            text,
    prod_report_filed_flag text,
    lease_oil_prod_vol     text,
    lease_gas_prod_vol     text,
    lease_cond_prod_vol    text,
    lease_csgd_prod_vol    text,
    lease_name             text,
    operator_name          text,
    field_name             text,
    ingested_at            timestamptz not null default now(),
    primary key (manifest_id, source_row_ordinal)
);

comment on table staging.tx_pdq_lease_cycle is
    'OG_LEASE_CYCLE as filed: one row per lease per cycle month, oil and gas leases in one'
    ' table discriminated by oil_gas_code. No county column exists here, which is why'
    ' cr_tx_pdq_scope_1 applies the county scope at promotion rather than at parse. The grain'
    ' is the manual''s: FIELD_NO is nullable on this table and nullable columns do not key it,'
    ' and OG_FIELD_CYCLE exists precisely to aggregate by field.';

create table staging.tx_pdq_well_completion (
    manifest_id            text not null references lineage.manifests (manifest_id),
    source_row_ordinal     integer not null,
    oil_gas_code           text,
    district_no            text,
    lease_no               text,
    well_no                text,
    api_county_code        text,
    api_unique_no          text,
    onshore_assc_cnty      text,
    well_root_no           text,
    wellbore_shutin_dt     text,
    well_shutin_dt         text,
    well_14b2_status_code  text,
    well_subject_14b2_flag text,
    wellbore_location_code text,
    ingested_at            timestamptz not null default now(),
    primary key (manifest_id, source_row_ordinal)
);

comment on table staging.tx_pdq_well_completion is
    'OG_WELL_COMPLETION as filed: the in-dump crosswalk carrying the lease key and the API-10'
    ' parts in one row, so lease-to-well is exact and needs no external join.';

create table staging.tx_pdq_regulatory_lease (
    manifest_id          text not null references lineage.manifests (manifest_id),
    source_row_ordinal   integer not null,
    oil_gas_code         text,
    district_no          text,
    lease_no             text,
    district_name        text,
    lease_name           text,
    operator_no          text,
    operator_name        text,
    field_no             text,
    field_name           text,
    well_no              text,
    lease_off_sched_flag text,
    lease_severance_flag text,
    ingested_at          timestamptz not null default now(),
    primary key (manifest_id, source_row_ordinal)
);

grant select, insert, delete on staging.tx_pdq_lease_cycle to glasswell_pipeline;
grant select, insert, delete on staging.tx_pdq_well_completion to glasswell_pipeline;
grant select, insert, delete on staging.tx_pdq_regulatory_lease to glasswell_pipeline;

-- The plug date is already parsed (ingest/tx_wellbore.py:406 ranks on it) and has never been
-- persisted. Allocation needs it as a right bound: a well the RRC plugged in 2015 would
-- otherwise take an equal share every month to the present while the same card serves
-- status_canonical = plugged.
alter table canonical.wells add column if not exists plug_date date;

comment on column canonical.wells.plug_date is
    'The filed plugging date where the regulator published one. A dated fact, so it bounds'
    ' eligibility; a plugged status with no date does not bound and is labelled instead.';

-- Columns added to canonical.wells after migration 009 are not inherited by its explicit view
-- projection (040_p3_nd_readiness.sql:1-2). This is the third definition, and the new column
-- goes last: create or replace view permits appending a column, never reordering.
create or replace view canonical.wells_latest as
select api10, api14, state_code, county_code_at_permit, ndic_file_no, operator_name_reported,
       operator_id, well_name, status_canonical, status_reported, well_type_reported, spud_date,
       confidential_flag, basin, land_unit_label, effective_from, source_manifest_id,
       derivation_id, created_at, total_depth_ft, completion_date, plug_date
  from (select w.*,
               row_number() over (partition by api10 order by effective_from desc,
                                  derivation_id desc) as effective_rank
          from canonical.wells w) ranked
 where effective_rank = 1;

comment on view canonical.wells_latest is
    'Current effective-dated well rows, including columns added after the original ND slice.';

-- Membership is jurisdiction-keyed and general: Texas writes the regulator's own published
-- crosswalk, Montana writes what it reads off the production file's lease_unit column, and
-- link_role says which kind of evidence a row is rather than letting one word describe both.
create table canonical.lease_membership (
    jurisdiction_code  text not null references lineage.jurisdiction_codes (jurisdiction_code),
    lease_key          text not null,
    api10              text not null,
    link_role          text not null
                            check (link_role in ('canonical_crosswalk', 'filing_derived')),
    source_id          text not null references lineage.sources (source_id),
    effective_from     date not null,
    source_manifest_id text not null references lineage.manifests (manifest_id),
    derivation_id      text not null references lineage.derivations (derivation_id),
    created_at         timestamptz not null default now(),
    primary key (jurisdiction_code, lease_key, api10, source_id, effective_from)
);

comment on table canonical.lease_membership is
    'Which wells a lease held at an export vintage, appended per vintage and never edited. A'
    ' production month resolves to the greatest effective_from at or before the resolution'
    ' clock, so a later vintage that drops a well removes it from no month already resolved.';

create index lease_membership_lease_idx
    on canonical.lease_membership (jurisdiction_code, lease_key, effective_from desc);
create index lease_membership_api_idx
    on canonical.lease_membership (jurisdiction_code, api10, effective_from desc);

create trigger lease_membership_append_only
    before update or delete on canonical.lease_membership
    for each row execute function lineage.reject_mutation();

grant select, insert on canonical.lease_membership to glasswell_pipeline;
grant select on canonical.lease_membership to glasswell_api;

-- The estimate, and every column that keeps it from reading as an observation. Keyed by lease
-- as well as by well because 21.9 percent of Texas API-10s carry more than one lease record
-- (cr_tx_identity_collapse_1, 78,579 of 359,421): folding a well's shares into one row would
-- make lease_key, eligible_wells, allocation_class and membership_vintage ambiguous.
create table marts.tx_allocated_production (
    api10                text not null,
    lease_key            text not null,
    production_month     date not null,
    stream               text not null check (stream in ('liquid', 'gas')),
    volume               numeric(18, 3) not null,
    unit                 text not null,
    basis                text,
    allocation_class     text not null check (allocation_class in
                             ('observed_gas_well', 'observed_single_well_lease',
                              'allocated_equal_share', 'allocated_after_status_change',
                              'excluded_after_plug')),
    granularity          text not null
                             check (granularity in ('well_observed', 'lease_allocated')),
    allocation_model_id  text not null,
    allocation_rule_id   text not null references lineage.conformance_rules (rule_id),
    eligible_wells       integer not null,
    membership_vintage   date not null,
    incomplete_window    boolean not null default false,
    error_bounds_outcome text not null
                             check (error_bounds_outcome in ('not_measured', 'measured')),
    error_rule_id        text not null references lineage.conformance_rules (rule_id),
    error_bed            text,
    error_lo             numeric(5, 4),
    error_hi             numeric(5, 4),
    lease_derivation_id  text not null references lineage.derivations (derivation_id),
    snapshot_vintage     date not null,
    derivation_id        text not null references lineage.derivations (derivation_id),
    check ((granularity = 'lease_allocated')
           = (allocation_class not in ('observed_gas_well', 'observed_single_well_lease'))),
    check (case error_bounds_outcome
               when 'measured'
                   then error_lo is not null and error_hi is not null and error_bed is not null
               else error_lo is null and error_hi is null and error_bed is null end),
    check (allocation_class <> 'excluded_after_plug' or volume = 0),
    primary key (api10, lease_key, production_month, stream)
);

comment on table marts.tx_allocated_production is
    'One share per (well, lease, month, stream). The served well series is the sum over a'
    ' well''s shares for the month, computed at request time; allocation_rule_id is the R8'
    ' decision and allocation_model_id is the versioned artifact that produced the number.';

create index tx_allocated_well_idx
    on marts.tx_allocated_production (api10, production_month, stream);

-- V-1, decomposed. Conservation is exact by construction under the sign-aware split, so a
-- residual is never a rounding term: it is volume with no eligible well to carry it, and the
-- cause vocabulary is closed because each cause is a different question about the data.
create table marts.tx_allocation_ledger (
    lease_key        text not null,
    production_month date not null,
    stream           text not null check (stream in ('liquid', 'gas')),
    lease_volume     numeric(18, 3) not null,
    cause            text not null check (cause in
                         ('no_crosswalk_row', 'no_eligible_well', 'all_wells_after_month',
                          'negative_correction')),
    snapshot_vintage date not null,
    derivation_id    text not null references lineage.derivations (derivation_id),
    primary key (lease_key, production_month, stream)
);

-- V-2a. Two regulator-published crosswalks that agree prove nothing once averaged; their
-- disagreement is the only measurement of allocation error this system will have.
create table marts.tx_crosswalk_residual (
    district_no       text not null,
    disagreement_kind text not null,
    well_count        integer not null,
    share             numeric(5, 4) not null,
    snapshot_vintage  date not null,
    derivation_id     text not null references lineage.derivations (derivation_id),
    primary key (district_no, disagreement_kind)
);

-- The Montana method study, keyed by bed. It is a control on the method, not a decoration on
-- a Texas figure: no band reaches the Texas wire until the transferability measurement shows
-- the distributions overlap.
create table marts.allocation_method_error (
    bed_jurisdiction         text not null
                                 references lineage.jurisdiction_codes (jurisdiction_code),
    model_id                 text not null,
    error_lo                 numeric(5, 4),
    error_hi                 numeric(5, 4),
    p50                      numeric(5, 4),
    wells_scored             integer not null,
    lease_months_scored      integer not null,
    months_measured          text[] not null,
    mean_wells_per_lease     numeric(6, 3),
    excluded_zero_zero_share numeric(5, 4),
    snapshot_vintage         date not null,
    derivation_id            text not null references lineage.derivations (derivation_id),
    primary key (bed_jurisdiction, model_id)
);

-- A series, not a latest: lineage.jurisdiction_well_counts keys (jurisdiction_code,
-- measured_on, status_key) for the same reason (073_jurisdictions.sql:119-130). R-5 needs to
-- see the in-scope population move, which is what tells the owner whether the scope narrows.
create table marts.tx_allocation_census (
    measure       text not null,
    measured_on   date not null,
    value         numeric not null,
    derivation_id text not null references lineage.derivations (derivation_id),
    primary key (measure, measured_on)
);

grant select on marts.tx_allocated_production, marts.tx_allocation_ledger,
                marts.tx_crosswalk_residual, marts.allocation_method_error,
                marts.tx_allocation_census to glasswell_api;
grant select, insert, delete, truncate on marts.tx_allocated_production,
                marts.tx_allocation_ledger, marts.tx_crosswalk_residual,
                marts.allocation_method_error to glasswell_pipeline;
grant select, insert, delete on marts.tx_allocation_census to glasswell_pipeline;

-- A total that sums allocated months without saying so is the naked number the no-naked-numbers
-- rule exists to prevent, so the coverage class gains a third value and the share is a column
-- rather than a footnote.
alter table marts.well_cumulatives
    add column allocated_months integer not null default 0,
    add column allocated_share  numeric(5, 4);

alter table marts.well_cumulatives drop constraint well_cumulatives_coverage_outcome_check;
alter table marts.well_cumulatives add constraint well_cumulatives_coverage_outcome_check
    check (coverage_outcome in ('observed', 'never_reported', 'observed_with_allocated'));

comment on column marts.well_cumulatives.allocated_share is
    'The share of cum_volume contributed by allocated months. Served beside the total, never'
    ' after it: an allocation estimate that reads as an observation is the defect.';

-- Handles are fail-closed, so every admitted claim shape is registered. The operation is
-- alloc.apply, already in the vocabulary at 048_selector_output_registry.sql:8 and the honest
-- name for this node: mart.refresh would make the allocation indistinguishable from any other
-- refresh in the chain.
insert into lineage.selector_output_registry
    (operation, output_dataset, selector_profile, rationale)
values
    ('alloc.apply', 'marts.tx_allocated_production', 'tx_allocated_series',
     'One stored share per well, lease, month and stream, addressed with the lease key as a'
     ' required term because a wellbore on two leases has two rows at the well grain.'),
    ('alloc.apply', 'marts.tx_allocation_ledger', 'tx_allocation_ledger',
     'The conservation residual per lease-month and stream, with the cause that produced it.'),
    ('alloc.apply', 'marts.tx_crosswalk_residual', 'tx_crosswalk_residual',
     'The crosswalk disagreement per district, which bounds identity-mapping error.'),
    ('alloc.apply', 'marts.allocation_method_error', 'allocation_method_error',
     'The method study''s bounds, keyed by the bed they were measured on.'),
    ('api.respond', 'api.tx_production', 'response_output',
     'The summed per-well series is computed at request time over a well''s lease shares and'
     ' is stored nowhere, so the request derivation records the figures it returned.'),
    ('api.respond', 'api.allocation_validators', 'response_output',
     'The validators response records every residual figure it served for the jurisdiction.');

-- What becomes of 048_selector_output_registry.sql:55-56, the alloc.apply ->
-- canonical.production_monthly row: DIR-3 and 020_production_entity_key.sql:43-46's
-- composition check later made that shape unreachable -- an allocated row cannot be written to
-- canonical at all -- so it is superseded by this comment rather than left asserting something
-- the schema forbids. The row stays: a migration is applied history, not an editable file.

-- A null expected_poll_interval makes a missed window undetectable and R-03 requires
-- /v1/health to go degraded on one. The measured cadence is the listing's own sentence. The
-- 12-hour attempt timeout stands: the archive is 3.65 GB and the server ignores Range, so
-- there is no resume and a slow fetch is not a stuck one.
update lineage.source_poll_policies
   set cadence = 'Last Saturday each month', expected_poll_interval = interval '35 days'
 where source_id = 'tx_pdq_dsv';

-- The two well-status archives, registered with the same cadence they are pulled on. They hold
-- a rolling 26-month window against 402 months of PDQ history, so a missed window is a window
-- no regulator can give back -- which is exactly what R-03 wants /v1/health to say.
insert into lineage.source_poll_policies
    (source_id, cadence, expected_poll_interval, attempt_timeout)
values
    ('tx_w10_wlf607', 'Every 35 days', interval '35 days', interval '1 hour'),
    ('tx_g10_gse10', 'Every 35 days', interval '35 days', interval '1 hour')
on conflict (source_id) do nothing;
-- The supersession. Every value but the ones this track changes is carried over from the row
-- being superseded rather than restated by hand, so the supersession cannot drift from what it
-- supersedes -- including the seven presentation columns, whose loss would blank the Texas
-- Wells row in the web legend. The evidence pair is read back from the publication row above.
insert into lineage.jurisdictions (
    jurisdiction_code, effective_from, published_at, evidence_tag, evidence_commit,
    name, regulator_name, regulator_url, identity_scheme, identity_is_unique,
    identity_prefix, identity_pattern, source_ids, liquids_basis, wells_tile_layer_id,
    map_colour, neighbors_available, explorer_default, land_grid_state, land_grid_scope,
    status_dataset_detail, rationale, wells_layer_id, wells_style_layer_ids, wells_draw_order,
    wells_default_on, wells_snapshot_key, wells_subtitle_template, legend_note)
select serving.jurisdiction_code, serving.effective_from, date '2026-09-06',
       evidence.evidence_tag, evidence.evidence_commit,
       serving.name, serving.regulator_name, serving.regulator_url,
       serving.identity_scheme, serving.identity_is_unique, serving.identity_prefix,
       serving.identity_pattern,
       (select array_agg(distinct s order by s)
          from unnest(serving.source_ids
                      || array['tx_pdq_dsv', 'tx_w10_wlf607', 'tx_g10_gse10']) s),
       'oil+condensate',
       serving.wells_tile_layer_id, serving.map_colour, serving.neighbors_available,
       serving.explorer_default, serving.land_grid_state, serving.land_grid_scope,
       serving.status_dataset_detail,
       'Served from the RRC county GIS layers, the Wellbore Query export and the PDQ dump.'
       ' Texas files production at the lease, so the well-level series is an allocation: the'
       ' lease volume is promoted at its native grain and the per-well share is a mart figure'
       ' carrying its class, its model id and its error-bounds outcome. The liquids basis is'
       ' oil plus condensate because the two columns are disjoint populations keyed by'
       ' OIL_GAS_CODE, which is why a reader comparing to the RRC''s published crude figure'
       ' will find glasswell higher.',
       serving.wells_layer_id, serving.wells_style_layer_ids, serving.wells_draw_order,
       serving.wells_default_on, serving.wells_snapshot_key, serving.wells_subtitle_template,
       serving.legend_note
  from lineage.jurisdictions_as_of(date '2026-09-04', date '2026-09-02') serving
 cross join (select evidence_tag, evidence_commit
               from lineage.conformance_rule_publications
              where rule_id = 'cr_tx_allocation_v0_1') evidence
 where serving.jurisdiction_code = 'TX';

-- Guarded on residency exactly as 073's, 075's and 077's inserts are: migrations run before
-- the seed, so on a fresh database lineage.conformance_rules is empty and seed/jurisdictions.py
-- supplies these. On a database that is already seeded -- the deployed one -- this is what
-- lands them. Five rows are carried forward from the registration being superseded; dropping
-- length_source or basin_scope would silently remove Texas's lateral-length measurement and
-- basin CRS from the tile mart.
insert into lineage.jurisdiction_rules
    (jurisdiction_code, effective_from, published_at, decision, rule_id, serving, note)
select r.jurisdiction_code, date '2026-09-02', date '2026-09-06',
       r.decision, r.rule_id, true, null::text
  from (values
    ('TX', 'status_vocabulary', 'cr_tx_status_vocab_1'),
    ('TX', 'identity', 'cr_tx_api10_build_1'),
    ('TX', 'absence:operator', 'cr_tx_operator_absence_1'),
    ('TX', 'basin_scope', 'cr_tx_basin_scope_1'),
    ('TX', 'length_source', 'cr_tx_length_source_1'),
    ('TX', 'production_grain', 'cr_tx_production_grain_1'),
    ('TX', 'liquids', 'cr_tx_liquids_basis_1'),
    ('TX', 'geometry_provenance', 'cr_tx_geometry_provenance_1'),
    ('TX', 'cumulatives_scope', 'cr_tx_allocation_v0_1')
  ) as r(jurisdiction_code, decision, rule_id)
 where exists (select 1 from lineage.conformance_rules c where c.rule_id = r.rule_id)
   and exists (select 1 from lineage.jurisdictions j
                where j.jurisdiction_code = 'TX' and j.effective_from = date '2026-09-02'
                  and j.published_at = date '2026-09-06')
on conflict do nothing;

-- The job rows, written by both writers. seed/schedules.py carries them too and the parity
-- gate holds the two copies equal; this insert is what makes a deploy that seeds nothing still
-- schedule, because seed_all is not on the migrate path.
--
-- No ExecStart line and no unit file. An entry point named in a unit joins the set an
-- installed timer already drives, and the double-run guard then forbids that job a launching
-- row -- which is a narrower rule than the posture below, where every row observes whatever
-- drives it.
insert into lineage.scheduled_jobs
    (job_id, label, kind, entry_point, argv, anchor_source_id, jurisdiction, run_as, rationale)
select j.job_id, j.label, j.kind, j.entry_point, j.argv, j.anchor_source_id, j.jurisdiction,
       'glasswell', j.rationale
  from (values
    ('ingest_tx_pdq', 'Texas PDQ dump ingest', 'ingest', 'glasswell.ingest.tx_pdq',
     array[]::text[], 'tx_g10_gse10', 'TX'::text,
     'One fetch a month to the raw zone, then a two-pass parse from the stored artifact. The'
     ' archive is republished on the last Saturday of each month and the server ignores Range,'
     ' so a missed window is a whole month re-downloaded rather than resumed. The two 26-month'
     ' well-status files are archived by the same job, because they are pulled in one pass and'
     ' parsed by nothing.'::text),
    ('marts_tx_allocation', 'Texas allocated production mart', 'mart',
     'glasswell.marts.tx_allocation', array[]::text[], 'tx_g10_gse10', 'TX'::text,
     'The split reads the lease rows the ingest promoted and the membership it staged, so it'
     ' reacts to that ingest rather than to a clock of its own. It refuses rather than'
     ' publishing when conservation fails, so a defect stops the mart instead of shipping a'
     ' share that does not sum back to what the operator filed.'::text),
    ('marts_allocation_backtest', 'Allocation method study', 'mart',
     'glasswell.marts.allocation_backtest', array[]::text[], 'mt_bogc_pru_production',
     'MT'::text,
     'The study is measured on Montana''s two grains, so it is a Montana job by jurisdiction'
     ' whatever it is a control for: the standing gate asks a mart to wait on an ingest of its'
     ' own jurisdiction, and Montana''s is the one whose filings it reads.'::text)
  ) as j(job_id, label, kind, entry_point, argv, anchor_source_id, jurisdiction, rationale)
 where exists (select 1 from lineage.sources s where s.source_id = j.anchor_source_id)
on conflict do nothing;

-- One job, three sources. The dump and the two well-status files are pulled from the same
-- portal in one pass, and `tx_pdq_dsv` leaves UNJOBBED_SOURCES in this same commit: the
-- parity gate is a two-sided equality and an exempted source with a job row reddens it from
-- both directions.
insert into lineage.job_sources (job_id, source_id)
select e.job_id, e.source_id
  from (values
    ('ingest_tx_pdq', 'tx_pdq_dsv'),
    ('ingest_tx_pdq', 'tx_w10_wlf607'),
    ('ingest_tx_pdq', 'tx_g10_gse10')
  ) as e(job_id, source_id)
 where exists (select 1 from lineage.scheduled_jobs j where j.job_id = e.job_id)
   and exists (select 1 from lineage.sources s where s.source_id = e.source_id)
on conflict do nothing;

-- observe, on the owner's ruling of 2026-09-03: the plan is computed and recorded on every
-- tick and nothing is started. No installed timer drives these three entry points, which is
-- what a launching row would have argued from, and it is not the whole decision -- plan.py:363
-- rewrites a due would_run entry to run and runner.py:306 starts it, so a launching row here
-- is a 3.65 GB unresumable fetch on the first tick after a deploy. The ingest takes the
-- registry's six-hour ceiling; its source's own attempt timeout is twelve hours and answers a
-- different question -- how long one fetch may take, against how long the whole job may. Six
-- hours at 3.65 GB is about 170 KB/s, below which the fetch is broken rather than slow.
insert into lineage.job_schedules
    (job_id, effective_from, published_at, rule_id, trigger, launch_mode, cadence_interval,
     cadence_note, memory_max, timeout_seconds)
select s.job_id, date '2026-09-02', date '2026-09-02',
       'cr_job_cadence_' || s.job_id || '_1', s.trigger, 'observe', s.cadence_interval,
       s.cadence_note, s.memory_max, s.timeout_seconds
  from (values
    ('ingest_tx_pdq', 'cadence', interval '35 days',
     'Every 35 days; the RRC republishes on the last Saturday of the month'::text,
     '6G'::text, 21600),
    ('marts_tx_allocation', 'after_dependency', null::interval,
     'After the ingest that promotes the lease rows it splits'::text, '6G'::text, 7200),
    ('marts_allocation_backtest', 'after_dependency', null::interval,
     'After the Montana ingest whose two grains it scores against'::text, '6G'::text, 3600)
  ) as s(job_id, trigger, cadence_interval, cadence_note, memory_max, timeout_seconds)
 where exists (select 1 from lineage.scheduled_jobs j where j.job_id = s.job_id)
   and exists (select 1 from lineage.conformance_rules c
                where c.rule_id = 'cr_job_cadence_' || s.job_id || '_1')
on conflict do nothing;

insert into lineage.job_dependencies (job_id, depends_on_job_id, trigger_on, rationale)
select d.job_id, d.depends_on_job_id, 'changed', d.rationale
  from (values
    ('marts_tx_allocation', 'ingest_tx_pdq',
     'The split reads the lease rows and the membership that ingest promoted, so a pull that'
     ' changed nothing leaves it with nothing to re-split.'::text),
    ('marts_allocation_backtest', 'ingest_mt_bogc',
     'The study is measured on Montana''s well and lease grains, so it waits on the ingest'
     ' that promotes them rather than on the jurisdiction it is a control for.'::text),
    ('marts_cumulatives', 'marts_tx_allocation',
     'Texas writes its well-grain cumulative row from the allocated mart, so the cumulative'
     ' refresh reads a mart that has to have been rebuilt first.'::text)
  ) as d(job_id, depends_on_job_id, rationale)
 where exists (select 1 from lineage.scheduled_jobs j where j.job_id = d.job_id)
   and exists (select 1 from lineage.scheduled_jobs p where p.job_id = d.depends_on_job_id)
on conflict do nothing;
