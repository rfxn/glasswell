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
--   1. Nothing dated. This file registers no conformance rule, appends no jurisdiction row
--      and cites no publication evidence, so it carries no tag, commit or vintage to move.
--      An earlier revision of it registered a Texas absence decision; that row was withdrawn
--      before it was ever applied, because the deployed spine carries 228,169 Texas
--      completion dates and the rationale on it was false. See the gate report, H-1.
--   2. This file's version integer lives in its filename and nowhere else, so a renumber is a
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
-- and record the version by hand afterwards. Either way, do not run it inside the 02:00 backup
-- window: pg_dump holds ACCESS SHARE on the spine for its whole run and the lock_timeout below
-- will refuse the migrate rather than wait behind it.
--
-- The gain depends on the visibility map, because an index-only scan that cannot consult it
-- falls back to a heap fetch per row: measured on that same fixture, the rebuilt index reads
-- 809,191 heap fetches before a vacuum and 0 after. The deployed table is autovacuumed, so this
-- is a note about a restore, not about the deploy.

-- Bounded, because nothing else bounds it. The host runs `lock_timeout = 0`, so without this
-- the DROP below waits for the longest in-flight reader to finish -- and a waiting ACCESS
-- EXCLUSIVE request sits at the head of the lock queue, so every new read on canonical.wells
-- queues behind it for the same duration. The readers on that host include the status facet at
-- 1.7 s, the mart refreshes, and a nightly in-VM pg_dump that holds ACCESS SHARE on every table
-- for its whole run. The exposure was never the 1.25 s rebuild; it was whatever was already
-- open in front of it.
--
-- `set local`, because migrate.py runs the whole file in one transaction. On timeout the
-- transaction aborts and deploy.sh refuses, which is this project's own posture: a refused
-- migrate is a retry, an unbounded exclusive lock on the serving spine is an outage. Retry
-- outside the backup window, or run the two statements out of band per the note above.
set local lock_timeout = '5s';

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

-- Registry-driven, and it has to be. Which jurisdictions resolve at read time, and which table
-- and columns each one's classes live in, are already rows: `jurisdiction_rules.decision =
-- status_vocabulary` names the rule, and the rule's own spec carries `resolved_at`,
-- `mapping_table`, `key_col` and `value_col`. This is the same pair of queries
-- `glasswell/status_resolution.py` reads (`_RESOLVER_RULES`, `_VOCABULARY_SOURCES`), so the
-- resolver and the serving path answer from one definition.
--
-- A jurisdiction named by the registry but whose mapping table has not arrived yet is skipped
-- rather than raised on: migrations arrive in merge order and a registration can precede the
-- table its rule names, and a refresh that aborted would take the migration -- or the deploy's
-- seed that calls it -- down with it.
create or replace function lineage.refresh_status_resolution() returns integer
language plpgsql as $$
declare
    registered record;
    resolved integer := 0;
    added integer;
begin
    delete from lineage.status_resolution_resolved;
    for registered in
        select j.identity_prefix, j.jurisdiction_code,
               c.spec->>'mapping_table' as mapping_table,
               c.spec->>'key_col'       as key_col,
               c.spec->>'value_col'     as value_col
          from lineage.jurisdictions_as_of(current_date, current_date) j
          join lineage.jurisdiction_rules r
            on r.jurisdiction_code = j.jurisdiction_code
           and r.effective_from = j.effective_from
           and r.published_at = j.published_at
           and r.decision = 'status_vocabulary'
           and r.serving
          join lineage.conformance_rules c on c.rule_id = r.rule_id
         where j.identity_prefix is not null
           and c.spec->>'resolved_at' = 'read_time'
           and c.spec->>'mapping_table' is not null
           and c.spec->>'key_col' is not null
           and c.spec->>'value_col' is not null
           and to_regclass('lineage.' || quote_ident(c.spec->>'mapping_table')) is not null
         order by j.identity_prefix
    loop
        -- format %I quotes every identifier the registry named; nothing here is concatenated
        -- raw, and the three it interpolates are all read from a rule spec.
        execute format(
            'insert into lineage.status_resolution_resolved (for_state_code,'
            ' for_status_reported, resolved_status, jurisdiction_code, built_for)'
            ' select %L, m.%I::text, m.%I::text, %L, current_date'
            '   from lineage.%I m'
            '  where m.%I is not null and m.%I is not null',
            registered.identity_prefix, registered.key_col, registered.value_col,
            registered.jurisdiction_code, registered.mapping_table,
            registered.key_col, registered.value_col);
        get diagnostics added = row_count;
        resolved := resolved + added;
    end loop;
    return resolved;
end;
$$;

comment on function lineage.refresh_status_resolution() is
    'Rebuilds lineage.status_resolution_resolved from every registration resolving today whose'
    ' status-vocabulary rule says resolved_at = read_time, reading the mapping table and its'
    ' key and value columns out of that rule spec. Idempotent, and cheap: the product is tens'
    ' of rows. A registered mapping table that has not been created yet is skipped.';

-- Both sources are append-only, so an append is the only way their content can change and a
-- statement trigger on it is exact. The refresh is also called by seed_jurisdictions(), which
-- every deploy runs between migrate and the API restart, so a database restored from a dump
-- lands a correct resolver without an append.
--
-- FOR A LATER JURISDICTION THAT RESOLVES AT READ TIME. Do not redefine
-- canonical.status_resolution and do not add an arm to anything here: the function above reads
-- the registry, so a new jurisdiction needs three rows and one trigger. (1) its mapping table
-- in `lineage`, (2) a status-vocabulary conformance rule whose spec carries
-- `"resolved_at": "read_time"` with `mapping_table`, `key_col` and `value_col`, (3) the
-- `jurisdiction_rules` row pointing at it -- and then a statement trigger on its own map, in
-- the same shape as the one below, plus `select lineage.refresh_status_resolution();` at the
-- end of the migration. A second `create or replace view` on canonical.status_resolution would
-- silently drop every other jurisdiction's arm, whichever order the two migrations merge in.
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

-- The rule rows are the fact the refresh actually reads: a registration alone says nothing
-- about read-time resolution, and a jurisdiction's rules are appended after it because of the
-- composite foreign key. Without this trigger the registration's own refresh runs one statement
-- too early and the jurisdiction is resolved only at the next deploy.
drop trigger if exists jurisdiction_rules_refresh_status_resolution on lineage.jurisdiction_rules;
create trigger jurisdiction_rules_refresh_status_resolution
    after insert on lineage.jurisdiction_rules
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

