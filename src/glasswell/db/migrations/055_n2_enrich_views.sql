-- N2: the completion-design canonical table, the two cumulative marts, their selector-output
-- registry rows, and the glossary terms the three new figures bind to.

create table canonical.well_completion_design (
    disclosure_id             text not null,
    api10                     text not null,
    base_water_volume         numeric(18, 2),
    base_water_unit           text not null,
    base_water_null_semantics text not null check (base_water_null_semantics in (
                                  'reported', 'reported_zero', 'no_report', 'withheld')),
    source_id                 text not null references lineage.sources (source_id),
    report_vintage            date not null,
    source_manifest_id        text not null references lineage.manifests (manifest_id),
    derivation_id             text not null references lineage.derivations (derivation_id),
    created_at                timestamptz not null default now(),
    primary key (disclosure_id, source_id, report_vintage)
);

comment on table canonical.well_completion_design is
    'Completion design quantities as the source reported them; the base fluid volume is the '
    'disclosure''s own figure and is never inferred from a missing one.';

create index well_completion_design_api_idx
    on canonical.well_completion_design (api10, report_vintage);

create trigger well_completion_design_append_only
    before update or delete on canonical.well_completion_design
    for each row execute function lineage.reject_mutation();

create view canonical.well_completion_design_latest as
select disclosure_id, api10, base_water_volume, base_water_unit, base_water_null_semantics,
       source_id, report_vintage, source_manifest_id, derivation_id, created_at
  from (select d.*,
               row_number() over (
                   partition by disclosure_id, source_id
                   order by report_vintage desc, derivation_id desc) as vintage_rank
          from canonical.well_completion_design d) ranked
 where vintage_rank = 1;

-- No state regex and no nd_ prefix: the scope lives in marts.cumulatives.STATE_API_PREFIXES,
-- so Montana widens a Python constant rather than altering shipped DDL (045_nd_neighbors.sql:5).
-- numeric rather than double precision: the API reads these directly, so exact decimals are
-- what a served figure needs and the MVT wire hazard of 035_land_grid_metrics.sql:11 does not
-- apply.
create table marts.well_cumulatives (
    api10                   text not null,
    state_code              text not null,
    stream                  text not null check (stream in ('liquid', 'gas', 'water')),
    cum_volume              numeric(20, 3),
    unit                    text not null,
    basis                   text,
    months_reported         integer not null,
    months_reported_zero    integer not null,
    months_no_report_stored integer not null,
    months_withheld_stored  integer not null,
    months_absent           integer not null,
    span_months             integer not null,
    first_month             date,
    last_month              date,
    coverage_outcome        text not null
                                 check (coverage_outcome in ('observed', 'never_reported')),
    snapshot_vintage        date not null,
    derivation_id           text not null references lineage.derivations (derivation_id),
    primary key (api10, stream)
);

comment on table marts.well_cumulatives is
    'One per-well cumulative per stream with its month-class coverage; cum_volume is null for '
    'a well that never reported, because a zero there would be a filed zero.';

create index well_cumulatives_state_idx on marts.well_cumulatives (state_code, stream);

-- A second grain, not a denormalisation: ND withholding is month-grained, never stream-grained
-- (api/routers/production.py reads only production_month from the ledger payload).
create table marts.well_withholding (
    api10                text primary key,
    state_code           text not null,
    months_withheld      integer not null,
    withheld_first_month date,
    withheld_last_month  date,
    rule_ids             text[] not null default '{}',
    snapshot_vintage     date not null,
    derivation_id        text not null references lineage.derivations (derivation_id)
);

grant select on marts.well_cumulatives, marts.well_withholding to glasswell_api;
grant select, insert, delete, truncate on marts.well_cumulatives, marts.well_withholding
    to glasswell_pipeline;
grant select, insert on canonical.well_completion_design to glasswell_pipeline;
grant select on canonical.well_completion_design, canonical.well_completion_design_latest
    to glasswell_api;
revoke update, delete on canonical.well_completion_design
    from glasswell_pipeline, glasswell_api;

insert into lineage.selector_output_registry
    (operation, output_dataset, selector_profile, rationale)
values
    ('canonical.promote', 'canonical.well_completion_design', 'completion_design',
     'The FracFocus design promotion persists the addressed base-fluid measurement.'),
    ('mart.refresh', 'marts.well_cumulatives', 'well_cumulative',
     'The cumulative mart persists the addressed per-well, per-stream total and its coverage.'),
    ('api.respond', 'api.well_cumulatives', 'response_output',
     'The request derivation records the cumulative and coverage figures it returned.'),
    ('api.respond', 'api.well_vintage_cohorts', 'response_output',
     'The request derivation records every cohort aggregate it returned.'),
    ('api.respond', 'api.well_completions', 'response_output',
     'The request derivation records the serve-time fluid intensity it returned.');

-- First-publication evidence for the rule ids this track registers. The tag and commit are
-- this branch's; the integrator repoints them at the release that actually carries them,
-- alongside the migration renumber.
insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
select rule_id, date '2026-08-30', 'v0.67',
       'be26c93c6857aed80537c6efcb28bdd1ca959a85'
  from unnest(array[
       'cr_nd_vintage_cohort_1'
  ]) as rule_id
    on conflict (rule_id) do nothing;

-- The industry meaning of an industry term stays in the short definition; glasswell's own
-- cohort key belongs beside the rule that made it (014_geodesic_lateral_length.sql:61).
insert into canonical.glossary_terms
    (term_id, term, aliases, short_definition, expanded_definition, domain_tags,
     related_terms, source_refs, highlightable)
values (
    'gt_vintage_well_vintage',
    'Vintage (well vintage)',
    array['Well vintage', 'Vintage'],
    'The year or period a well was completed.',
    'Distinct from report vintage; both appear in this system and the glossary keeps them apart'
    ' deliberately, because a chart that mixes them looks like a trend and is an artefact.'
    ' glasswell keys its North Dakota vintage cohorts on the spud year rather than the'
    ' completion year, because spud dates cover 84 percent of the ND population against the'
    ' completion anchor''s 40 percent and reach back to 1922 rather than to 2009, which is when'
    ' the disclosure registry began rather than when the basin was drilled. That choice is'
    ' cr_nd_vintage_cohort_1, with its measured rationale; the completion anchor is still served'
    ' per well at /v1/wells/{api10}/completions, it is simply not the cohort key.',
    array['production', 'time'],
    array['Report vintage', 'First production', 'Spud date'],
    array['blueprint-v0.6 §9', 'cr_nd_vintage_cohort_1'],
    false)
on conflict (term_id) do update
    set expanded_definition = excluded.expanded_definition,
        related_terms = excluded.related_terms,
        source_refs = excluded.source_refs;

insert into canonical.glossary_terms
    (term_id, term, aliases, short_definition, expanded_definition, domain_tags,
     related_terms, source_refs, highlightable)
values (
    'gt_fluid_intensity',
    'Fluid intensity',
    array['Base fluid intensity', 'Fluid per lateral foot'],
    'Base fluid pumped per foot of lateral, in US gallons per foot.',
    'The disclosed total base water volume divided by the well''s summed lateral length. It is a'
    ' completion-design figure, not a production one: a bigger number means a larger job, never'
    ' a better well. Both operands come from different sources measured at different times - the'
    ' volume from a voluntary FracFocus disclosure under cr_ff_base_water_units_1, the length'
    ' computed geodesically from canonical geometry - so a well missing either gets a stated'
    ' reason rather than a zero. cr_ff_fluid_intensity_1 declares the minimum lateral the'
    ' division is defensible over and the ceiling above which the result is withdrawn.',
    array['completion', 'design'],
    array['Wellbore', 'Completion event', 'Conformance rule'],
    array['canonical.well_completion_design', 'cr_ff_fluid_intensity_1'],
    false)
on conflict (term_id) do nothing;

insert into canonical.glossary_terms
    (term_id, term, aliases, short_definition, expanded_definition, domain_tags,
     related_terms, source_refs, highlightable)
values (
    'gt_cumulative_production',
    'Cumulative production',
    array['Cumulative', 'Cum'],
    'The sum of a well''s filed monthly volumes for one stream, over a stated span.',
    'A total is only as complete as the record under it, so the figure is served beside the'
    ' months that make it up: months reported, months reported as zero, months with no report,'
    ' and months the regulator withheld. Those four are different facts and are never collapsed'
    ' into one gap. The cumulative is a mart snapshot at a stated vintage, so the live monthly'
    ' series can already hold months it has not absorbed; when it does, the response says so'
    ' rather than leaving a reader to find the difference by arithmetic.',
    array['production', 'time'],
    array['Report vintage', 'Withheld', 'Liquids policy'],
    array['marts.well_cumulatives', 'blueprint-v0.6 §9'],
    false)
on conflict (term_id) do nothing;
