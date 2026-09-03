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
--      host has not reached: a rule published in the future resolves nowhere and
--      /v1/conformance/<id> serves 404 for it.
--   4. The supersession's published_at 2026-09-06 -> the same date, and it MUST be strictly
--      later than every published_at Texas already carries (2026-09-02 founding, 2026-09-04
--      restatement), or the supersession does not resolve and Texas keeps serving the row
--      that says it has no production. It must also be neither the founding date plus one day
--      nor the restatement date plus one day: standing gates plant a rival registration on
--      each of those instants and the partial unique indexes would refuse them.
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
grant select, insert on marts.tx_allocation_census to glasswell_pipeline;

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
