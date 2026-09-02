-- What a facet over every jurisdiction costs, closed at the two places it was paid.
--
-- `/v1/wells/facets` scopes to a set of states as of this train, and `all` asks the spine one
-- question over every promoted well. Measured read-only on the deployed database at 809,191
-- spine rows, four of the five dimensions answer index-only off wells_facet_dimensions_idx in
-- 490-613 ms with 0 heap fetches. `status` costs 1,561-1,647 ms and reads 296,767 buffers
-- against their 12,778, all of it heap, and the plan says why in two places. This migration
-- addresses both. web/PERF.md section 7 carries the measurements and the plans.
--
-- REPOINT CHECKLIST (integrator, at the merge train):
--   1. The jurisdiction_rules row below carries NO date literal. Its (effective_from,
--      published_at) are read from the Texas registration resolving at apply time, so the pair
--      073's checklist repoints is inherited rather than restated here. Nothing to move.
--   2. seed/jurisdictions.py's JURISDICTION_RULES gains the same row and writes it at
--      REGISTERED_ON, which 073's checklist already governs. Do not add a second date.
--   3. The publication evidence below is 053's, NOT this train's. cr_tx_ewa_measures_1 was
--      first published in v0.62 on 2026-08-29 and that fact is immutable; the insert is a
--      no-op on any database at schema 53 or later and lands only on one restored below it.
--      Repointing those three literals would claim a first publication that did not happen.
--      Leave them. They are 053's own values, copied byte for byte.
--   4. This file's version integer lives in its filename and nowhere else, so a renumber is a
--      rename. No identifier, event id or payload below carries it.
--
-- DEPLOY NOTE. glasswell-migrate applies each file inside one transaction
-- (db/migrate.py: `with connection.transaction()`), so `create index concurrently` is not
-- available here -- it is refused inside a transaction block. The rebuild below therefore
-- takes ACCESS EXCLUSIVE on canonical.wells from the drop until the transaction commits, and
-- scripts/deploy.sh applies migrations at step 6 while the API is still serving: reads on the
-- spine block from the drop until the transaction commits. Measured on an ephemeral PostGIS at
-- 809,191 rows over a 160 MB heap, the rebuild takes 1.25 s and the index grows from 95 MB to
-- 98 MB. The deployed heap is larger, so budget a few seconds rather than one. A deploy that
-- cannot afford even that should run this file alone, out of band, with the two statements
-- split into `drop index concurrently` and `create index concurrently` outside a transaction,
-- and record the version by hand afterwards.
--
-- The gain depends on the visibility map, because an index-only scan that cannot consult it
-- falls back to a heap fetch per row: measured on that same fixture, the rebuilt index reads
-- 809,191 heap fetches before a vacuum and 0 after. The deployed table is autovacuumed, so this
-- is a note about a restore, not about the deploy.

-- (a) status_reported joins the covering list. It is the one dimension column the INCLUDE did
-- not carry, because until this train the read-time resolver was joined only on surfaces that
-- were already visiting the heap for other columns. The facet is not one of those: it selects
-- five dimension columns and a derivation id and nothing else, so a single uncovered column
-- costs it the index-only scan and, at four states, 296,762 buffers of heap.
drop index if exists canonical.wells_facet_dimensions_idx;

create index wells_facet_dimensions_idx
    on canonical.wells (state_code, api10, effective_from desc, created_at desc)
    include (operator_name_reported, county_code_at_permit, status_canonical, status_reported,
             well_type_reported, completion_date, derivation_id);

comment on index canonical.wells_facet_dimensions_idx is
    'Index-only support for /v1/wells/facets: dedup per state in api10 order, group by'
    ' dimension. status_reported is in the INCLUDE because the status dimension resolves'
    ' through canonical.status_resolution and joins on it.';

-- (b) The resolver becomes a relation the planner can look up, rather than a view it can only
-- scan. 073 made canonical.status_resolution registry-driven, which is right and stays; what
-- it cost is that the view is a window function over lineage.jurisdictions joined to a
-- fourteen-row map, so the planner has no index and no order for it. Over a set of states it
-- chose a merge join on state_code alone and applied the status equality as a join filter:
-- 4,179,636 rows removed by that filter on the deployed load, every New Mexico spine row
-- compared against all fourteen map rows.
--
-- Forcing a hash join instead was measured and is worse -- 2,248 ms against 1,647 -- because
-- the hash destroys the index order `distinct on` needs and the sort of 809,191 rows costs
-- more than the heap did. The plan that is both cheap and ordered is a nested loop with an
-- index lookup on the inner, and that needs a keyed relation.
create table if not exists lineage.status_resolution_resolved (
    for_state_code      text not null,
    for_status_reported text not null,
    resolved_status     text not null,
    jurisdiction_code   text not null references lineage.jurisdiction_codes,
    built_for           date not null,
    primary key (for_state_code, for_status_reported)
);

comment on table lineage.status_resolution_resolved is
    'The read-time status resolver, resolved: one row per (API state code, reported code), keyed'
    ' so a join on both can be answered by index lookup rather than by scanning a view. Derived'
    ' data with no authority of its own -- lineage.jurisdictions and the per-regulator map are'
    ' the sources, and lineage.refresh_status_resolution() is the only writer.';

comment on column lineage.status_resolution_resolved.built_for is
    'The valid date the registry was resolved at. A registration whose effective_from is later'
    ' than this has not reached the resolver: the refresh is driven by appends and by every'
    ' deploy, not by the calendar.';

create or replace function lineage.refresh_status_resolution() returns integer
language plpgsql as $$
declare
    resolved integer;
begin
    delete from lineage.status_resolution_resolved;
    insert into lineage.status_resolution_resolved
        (for_state_code, for_status_reported, resolved_status, jurisdiction_code, built_for)
    select j.identity_prefix, m.status, m.status_canonical, j.jurisdiction_code, current_date
      from lineage.nm_wellhistory_status_map m
      join lineage.jurisdictions_as_of(current_date, current_date) j
        on j.jurisdiction_code = 'NM'
     where j.identity_prefix is not null;
    get diagnostics resolved = row_count;
    return resolved;
end;
$$;

comment on function lineage.refresh_status_resolution() is
    'Rebuilds lineage.status_resolution_resolved from the registration resolving today and the'
    ' per-regulator status map. Idempotent, and cheap: the product is tens of rows.';

-- Both sources are append-only, so an append is the only way their content can change and a
-- statement trigger on it is exact. The refresh is also called by seed_jurisdictions(), which
-- every deploy runs between migrate and the API restart, so a database restored from a dump
-- lands a correct resolver without an append.
create or replace function lineage.status_resolution_refresh() returns trigger
language plpgsql as $$
begin
    perform lineage.refresh_status_resolution();
    return null;
end;
$$;

drop trigger if exists jurisdictions_refresh_status_resolution on lineage.jurisdictions;
create trigger jurisdictions_refresh_status_resolution
    after insert on lineage.jurisdictions
    for each statement execute function lineage.status_resolution_refresh();

drop trigger if exists status_map_refresh_status_resolution
    on lineage.nm_wellhistory_status_map;
create trigger status_map_refresh_status_resolution
    after insert on lineage.nm_wellhistory_status_map
    for each statement execute function lineage.status_resolution_refresh();

-- Same name, same columns, same types: every consumer reads through
-- glasswell.status_resolution.resolver_join and none of them moves.
create or replace view canonical.status_resolution as
select for_state_code, for_status_reported, resolved_status
  from lineage.status_resolution_resolved;

comment on view canonical.status_resolution is
    'Read-time status resolution: the class a served status carries where the promotion wrote'
    ' none. One row per (state, reported code); a state absent from it resolves to null, which'
    ' is the unmapped class and not a defect. Backed by lineage.status_resolution_resolved so'
    ' a join on both keys is an index lookup.';

grant select on lineage.status_resolution_resolved to glasswell_api, glasswell_pipeline;
grant insert, delete on lineage.status_resolution_resolved to glasswell_pipeline;
grant execute on function lineage.refresh_status_resolution() to glasswell_pipeline;

select lineage.refresh_status_resolution();

-- (c) R8: what a missing Texas completion year means is a registered decision, not an
-- inference the facet makes. The RRC's Wellbore Query export withholds COMPLETION_DATE for
-- every well, which cr_tx_ewa_measures_1 already states as a field-level withholding; this
-- registers it at the (jurisdiction, dimension) grain the facet surface resolves absence at,
-- so `state=all&by=completion_year` names Texas as absent by rule instead of folding 359,421
-- withheld wells into the same "not reported" bucket as North Dakota's genuinely missing dates.
--
-- No date literal: the pair is the Texas registration resolving at apply time. On a fresh
-- database lineage.jurisdictions is empty when migrations run and seed/jurisdictions.py
-- supplies the row; on the deployed one this is the statement that lands it.
insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
values ('cr_tx_ewa_measures_1', date '2026-08-29', 'v0.62',
        '307d65d25dc85785c0d87ac9097ef59085ec819a')
    on conflict (rule_id) do nothing;

insert into lineage.jurisdiction_rules
    (jurisdiction_code, effective_from, published_at, decision, rule_id, serving, note)
select j.jurisdiction_code, j.effective_from, j.published_at,
       'absence:completion_year', 'cr_tx_ewa_measures_1', true,
       'The RRC withholds COMPLETION_DATE on every well in the Wellbore Query export, so a'
       ' Texas well carrying no completion year is a withheld value under'
       ' cr_tx_ewa_measures_1 and not a value the regulator failed to record.'
  from lineage.jurisdictions_as_of(current_date, current_date) j
 where j.jurisdiction_code = 'TX'
   and exists (select 1 from lineage.conformance_rules c
                where c.rule_id = 'cr_tx_ewa_measures_1')
on conflict do nothing;

insert into lineage.audit_events (event_id, occurred_at, actor, event_type, subject_type,
                                  subject_id, payload)
select 'evt_tx_absence_completion_year_registered', now(), 'system:migration',
       'conformance.rule_added', 'rule', 'cr_tx_ewa_measures_1',
       jsonb_build_object('jurisdiction', 'TX',
                          'decision', 'absence:completion_year',
                          'surface', '/v1/wells/facets',
                          'effect', 'withheld completion years leave the shared'
                                    ' not-reported bucket and are counted per jurisdiction',
                          'migration', 'facet_status_resolution')
 where exists (select 1 from lineage.jurisdiction_rules
                where rule_id = 'cr_tx_ewa_measures_1'
                  and decision = 'absence:completion_year')
   and not exists (select 1 from lineage.audit_events
                    where event_id = 'evt_tx_absence_completion_year_registered');
