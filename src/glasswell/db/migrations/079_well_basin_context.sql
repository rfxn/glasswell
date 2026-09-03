-- The v0.80 well-card migration, train head + 1 in merge order; the integrator renumbers.
--
-- It carries the publication evidence for the two rule families the card registers, and the
-- basin-context mart the card's Basin and geology section reads. Publication evidence is what
-- brings a rule id into existence: lineage.conformance_rules refuses an insert for a rule id
-- with no row here (049's assign_conformance_rule_publication), so a seeded rule needs a line
-- in a migration whatever else it needs, which is why cr_nd_vintage_cohort_1 and the cadence
-- rules have theirs in 072 and 076.
--
-- REPOINT CHECKLIST (integrator, at the merge train):
--   1. evidence_tag UNRELEASED -> the tag that first carries these rules. It appears ONCE, at
--      the conformance_rule_publications insert below, so a half-repoint is not expressible.
--   2. evidence_commit forty zeros -> the FIRST COMMIT ON MAIN THAT CONTAINS THESE RULE IDS,
--      which is the MERGE COMMIT of this track's PR and not the head this branch was written
--      against. tests/unit/test_release_tooling.py runs `git grep -q <rule_id> <commit>` to
--      prove it.
--   3. published_vintage 2026-09-03 -> the date that tag is actually cut, and the table is
--      append-only so it cannot be corrected afterwards. It is read against the host's today,
--      so it must NEVER be a date the deploy host has not reached: a rule published in the
--      future resolves nowhere, /v1/conformance/<id> serves 404 for it, and every basin line
--      and status-history line on every card links to a 404.
--   4. This file's version integer lives in its filename and nowhere else, so a renumber is a
--      rename. It is certain here: feat/tx-lease-production already carries 079 and 080
--      on-branch, so this becomes 081 at the train. `grep -rn "079"` over src/ and tests/
--      returns only a latitude and a Texas county code, so nothing else moves with it.
--   5. The rule ids are immutable and must not change during the repoint: seven ids seeded by
--      seed/conformance_basin_context.py, seed/conformance_status_history.py and
--      seed/conformance_schedules.py read them back from the publication rows this file
--      writes, and 049's trigger refuses any rule whose id has no row here.

insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
select rule_id, date '2026-09-03', 'UNRELEASED',
       '0000000000000000000000000000000000000000'
  from unnest(array[
       'cr_nm_wellhistory_status_history_1',
       'cr_co_wells_status_history_1',
       'cr_job_cadence_marts_basin_context_1',
       'cr_nd_basin_context_1',
       'cr_tx_basin_context_1',
       'cr_mt_basin_context_1',
       'cr_nm_basin_context_1',
       'cr_co_basin_context_1'
  ]) as rule_id
on conflict do nothing;

-- The basin a well is in, as a served answer with a provenance class rather than as the bare
-- ingest scope label `canonical.wells.basin` has always been. Two different columns and two
-- different decisions: the label says which slice the ingest took, and this says which
-- published polygon the well's answering geometry falls in. Both are served, side by side,
-- with an agreement mark -- because for part of Texas they disagree, and a disagreement with
-- a handle is worth more than a silent overwrite.
--
-- Driven off canonical.wells_latest and left-joined to geometry, never the other way round:
-- canonical.well_spatial holds surface points for 1,486 api10s that have no row in
-- wells_latest, 1,400 of them Montana, and a mart driven off geometry would serve those as
-- rows with no well behind them.
create table if not exists marts.well_basin_context (
    api10             text primary key,
    state_code        text not null,
    -- The polygon answer. Null carries a class rather than a silence: outside every published
    -- boundary is an answer about the boundary set, and no geometry is an answer about the
    -- well, and neither is "we do not know".
    basin_name        text,
    basin_class       text not null check (basin_class in (
                          'in_published_boundary',
                          'outside_published_boundaries',
                          'no_geometry')),
    -- How many published basin polygons contain the answering geometry. Overlap is served
    -- rather than arbitrated (cr_eia_boundary_overlap_1); basin_name takes the smallest by
    -- published area so the answer is the most specific containing basin and is deterministic.
    basin_overlap     integer not null default 0 check (basin_overlap >= 0),
    -- Plural because plays stack: a location can sit in several at once and picking one would
    -- be a claim nobody published.
    play_name         text[] not null default '{}',
    play_class        text not null check (play_class in ('plays', 'no_play_at_this_location')),
    basin_label_filed text,
    label_class       text not null check (label_class in (
                          'agrees', 'disagrees', 'not_labelled', 'no_label_to_compare')),
    label_agrees      boolean,
    boundary_vintage  text,
    -- Which end of the well was asked. A Texas well has a surface point and a bottom hole and
    -- a long lateral can cross a boundary, so saying which geometry answered is the difference
    -- between a fact and an accident. v0.80 asks the surface point everywhere and says so.
    geometry_basis    text not null check (geometry_basis in (
                          'surface', 'lateral_midpoint', 'bottomhole', 'no_geometry')),
    boundary_id       text references canonical.basin_boundaries (boundary_id),
    rule_id           text references lineage.conformance_rules (rule_id),
    derivation_id     text not null references lineage.derivations (derivation_id),
    refreshed_at      timestamptz not null default now(),
    check ((basin_name is null) = (basin_class <> 'in_published_boundary')),
    check ((label_agrees is null) = (label_class in ('not_labelled', 'no_label_to_compare')))
);

comment on table marts.well_basin_context is
    'One row per well in canonical.wells_latest: the published basin polygon its answering'
    ' geometry falls in, the plays that stack there, the ingest scope label kept beside them,'
    ' whether the two agree, and which geometry answered. Rebuilt, never appended.';

create index if not exists well_basin_context_state_idx
    on marts.well_basin_context (state_code, basin_class);
create index if not exists well_basin_context_basin_idx
    on marts.well_basin_context (basin_name)
    where basin_name is not null;

grant select on marts.well_basin_context to glasswell_api, glasswell_pipeline;
grant insert, delete on marts.well_basin_context to glasswell_pipeline;

-- Without a registered profile every basin handle serves and /v1/explain answers 422, which is
-- a naked number wearing a ring (070's own comment, for the facet counts).
insert into lineage.selector_output_registry
    (operation, output_dataset, selector_profile, rationale)
values
    ('mart.refresh', 'marts.well_basin_context', 'basin_context',
     'The basin-context refresh persists the addressed well row: the polygon answer, its'
     ' plays, the filed label kept beside them, their agreement, the boundary vintage and the'
     ' geometry that answered.')
on conflict do nothing;
