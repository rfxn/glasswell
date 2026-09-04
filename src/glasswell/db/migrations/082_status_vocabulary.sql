-- The canonical status class domain becomes rows, and the read-time resolver stops needing a
-- migration per jurisdiction.
--
-- Three facts were true of the deployed instance when this was written and each is a defect.
-- The class domain existed nowhere: it was a union over five per-regulator maps computed at
-- query time, a prose enumeration in the glossary and a closed twelve-entry array in the
-- client, agreeing by coincidence with nothing checking them against each other. A class the
-- client did not hold was painted as the absence class by negation, so it had no legend row, no
-- count and no filter, and vanished when a reader unticked one box. And 078 left the per-map
-- refresh trigger written by hand: Colorado registered read-time resolution in the same train
-- and shipped with no trigger on its map, so an append to it does not rebuild the resolver.
--
-- REPOINT CHECKLIST (integrator, at the merge train):
--   1. evidence_tag UNRELEASED -> the tag that first carries these rows. It appears ONCE, at
--      the conformance_rule_publications insert; every other insert in this file reads it back
--      from that row, so a half-repoint is not expressible here.
--   2. evidence_commit forty zeros -> the first commit on main that contains them, which is the
--      merge commit and not the head this branch was written against.
--   3. published_vintage 2026-09-03 -> the date the tag is cut. It is read against the host's
--      today, so it must never be a date the deploy host has not reached: a rule published in
--      the future resolves nowhere and /v1/conformance/<id> serves 404 for it. The twelve
--      lineage.status_classes rows carry the same date as their effective_from and their
--      published_at.
--   4. The New Mexico rollup rule's effective_from -> strictly later than
--      cr_nm_wcproduction_pool_rollup_1's. A conformance rule is superseded by a later valid
--      time; this item is about lineage.conformance_rules and nothing else.
--   5. The restatement's published_at 2026-09-05 -> the same date as item 3, and it MUST be
--      strictly later than every published_at Montana and New Mexico already carry; if two
--      trains are cut on one day, the restatement carries the following day. It must also not
--      be a founding date plus one day: two standing gates plant a rival registration on that
--      instant and the partial unique indexes would refuse them. It need not be the table's
--      maximum: the card track's Texas supersession publishes at 2026-09-06 on another code,
--      which is later and bounds nothing here. This is the highest consequence line on this
--      list, because the knowledge cut lineage.refresh_status_resolution() reads is
--      max(published_at) over the whole table, so a restatement dated at or before what MT and
--      NM already carry resolves to the older row and neither grain decision serves.
--   6. seed/status_classes.py DOMAIN_EFFECTIVE_FROM / DOMAIN_EVIDENCE_TAG /
--      DOMAIN_EVIDENCE_COMMIT and seed/conformance_status_classes.py EFFECTIVE_FROM -> the same
--      values, in the same commit. The seed is the second writer and
--      tests/contract/test_status_class_parity.py compares all three.
--   7. seed/jurisdictions.py GRAIN_RESTATED_ON / GRAIN_EVIDENCE_TAG / GRAIN_EVIDENCE_COMMIT ->
--      item 5's date and item 1's pair.
--   8. This file's version integer lives in its filename and nowhere else, so a renumber is a
--      rename. No identifier, event id or payload below carries it.

-- (1) The evidence pair, written once. 049's trigger refuses a conformance rule whose
-- publication is not registered, so this lands before the rules themselves. The rollup mart's
-- cadence rule is here for the reason docs/runbook-add-a-state.md:158-185 gives and 080:55-57
-- follows: a track's cadence rows live in seed/conformance_schedules.py and their publication
-- evidence in the track's own migration.
insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
select rule_id, date '2026-09-03', 'UNRELEASED',
       '0000000000000000000000000000000000000000'
  from unnest(array[
       'cr_status_class_domain_1', 'cr_status_absence_basis_1', 'cr_status_absence_share_1',
       'cr_mt_bogc_pool_rollup_1', 'cr_nm_wcproduction_pool_rollup_2',
       'cr_job_cadence_marts_well_pool_rollup_1'
  ]::text[]) rule_id
on conflict (rule_id) do nothing;

-- (2) The domain's own three rules, in the two-writer shape 071 uses for the New Mexico
-- vocabulary rule: on a fresh database lineage.sources is empty at migrate time, so these are
-- no-ops and seed/conformance_status_classes.py supplies them; on a database that is already
-- seeded -- the deployed one -- this is what lands them. Everything below that depends on them
-- is guarded the same way, and lineage.attach_status_class_constraints() is what closes the
-- gap on the path where the seed is the writer.
insert into lineage.conformance_rules
    (rule_id, rule_family, supersedes_rule_id, source_id, stage, applies_to_fields, rule_kind,
     spec, rule, rationale, evidence_url, code_ref, effective_from)
select 'cr_status_class_domain_1', 'cr_status_class_domain', null, 'nd_mpr_xlsx', 'conform',
       array['status_canonical']::text[], 'code_ref',
       jsonb_build_object(
           'classes', jsonb_build_array('active', 'drilling', 'confidential', 'permitted',
                                        'inactive', 'temporarily_abandoned', 'service',
                                        'plugged', 'dry', 'documented_unmapped', 'expired'),
           'absence_class_rule', 'cr_status_absence_basis_1',
           'symbology_source', 'lineage.status_classes',
           'min_contrast_ratio', 3.0,
           'contrast_measured_against',
               jsonb_build_array('#121A21', '#0E151B', '#FFFFFF', '#F2F5F8'),
           'min_contrast_exceptions',
               jsonb_build_object('active', jsonb_build_array('light map'),
                                  'confidential',
                                      jsonb_build_array('light panel', 'light map'),
                                  'permitted',
                                      jsonb_build_array('light panel', 'light map')),
           'min_contrast_exceptions_routed_to', 'BRAND.md',
           'module_function', 'glasswell.lineage.status_classes:load_status_classes',
           'source_is_filing_anchor', true,
           'contract_note', 'a declaration the serving path reads, not a frame transformation:'
                            ' the domain is rows and the foreign keys are what enforce it',
           'superseded_by_action', 'a new rule and a single-transaction repoint of every map'
                                   ' that names a withdrawn class'),
       'The eleven mapped canonical well-status classes, their legend order and their symbology'
       ' are the rows of lineage.status_classes; every registered status map targets that set'
       ' through a foreign key.',
       'The domain existed in three places that agreed only by coincidence: a union over five'
       ' per-regulator maps computed at query time, a prose enumeration in the glossary, and a'
       ' closed array of object literals in the client. None was checked against another, so the'
       ' day a regulator''s map gained a class the client had never heard of, that class would'
       ' have been painted, counted and filtered as the absence class and would have vanished'
       ' the moment a reader unticked one box. Making the domain rows makes it a decision with a'
       ' rationale and an effective date, which is what R8 requires of the mapping that targets'
       ' it, and makes the foreign key the single writer rather than a second list. Presentation'
       ' travels with the class because presentation is what a client needs served: an enum'
       ' carries a name and nothing else, and a colour with no row behind it is a symbology'
       ' decision no gate can read. Two of the twelve are repainted rather than carried across,'
       ' and the bar is part of the decision so the next class has one to clear: a swatch is a'
       ' non-text mark, so 3:1 is its floor, and it is read against both theme panels and both'
       ' map substrates. The values carried across measured 2.19:1 for the absence class and'
       ' 2.94:1 for expired against the dark panel, which is the substrate the app opens on;'
       ' the absence class was the least legible mark on a canvas this same decision turns it'
       ' into a first-class row of. Three of the twelve do not clear it on the light theme and'
       ' are named in min_contrast_exceptions with the substrates they fail on rather than left'
       ' to a reader to discover: active on the light map, confidential and permitted on both'
       ' light substrates. Every one of those values is byte-identical to what shipped before'
       ' this decision, so they are carried forward rather than caused by it, and the palette'
       ' question they raise is routed to BRAND.md.',
       'https://glasswell.rpx.sh/conformance',
       'glasswell.lineage.status_classes:load_status_classes', date '2026-09-03'
 where exists (select 1 from lineage.sources where source_id = 'nd_mpr_xlsx')
on conflict (rule_id) do nothing;

insert into lineage.conformance_rules
    (rule_id, rule_family, supersedes_rule_id, source_id, stage, applies_to_fields, rule_kind,
     spec, rule, rationale, evidence_url, code_ref, effective_from)
select 'cr_status_absence_basis_1', 'cr_status_absence_basis', null, 'nd_mpr_xlsx', 'conform',
       array['status_canonical', 'status_reported']::text[], 'code_ref',
       jsonb_build_object(
           'served_class', 'unmapped',
           'distinguished_by', 'status_reported',
           'filed_code_present_means', 'the registered vocabulary has no row for this code',
           'filed_code_absent_means', 'the source filed no status',
           'module_function', 'glasswell.status_resolution:resolved_status',
           'source_is_filing_anchor', true,
           'contract_note', 'read at query-assembly time by the one helper every serving path'
                            ' calls, so the tile, the facet, the filter, the count and the card'
                            ' change together'),
       'No serving path emits a null status class. Where neither the promotion nor the registry'
       ' resolves one, the absence class is served and the filed code beside it is what says'
       ' which of the two cases holds.',
       'Null is indistinguishable from not-yet-loaded to every consumer, which is why the'
       ' blueprint forbids serving it, and it has been served anyway for every well whose source'
       ' filed no status code at all. The absence class is a class: it draws, it counts, it'
       ' filters and it carries a note. What it is not is a claim about why, and that is the'
       ' reason the two cases are distinguished by the reported code rather than by two classes.'
       ' A second class for a filed-but-unmapped code would mint a vocabulary entry for a fact'
       ' the registered mapping rule already answers.',
       'https://glasswell.rpx.sh/conformance',
       'glasswell.status_resolution:resolved_status', date '2026-09-03'
 where exists (select 1 from lineage.sources where source_id = 'nd_mpr_xlsx')
on conflict (rule_id) do nothing;

-- Cited by infra/verify.sh V-3 and by nothing on the wire, which is correct: it is an
-- operational threshold rather than a property of a served class. It is a rule and not a shell
-- literal because §3.4 removes the null that used to make a failed resolver visible, and the
-- signal that replaces it is a published decision or it is a number nobody agreed to.
insert into lineage.conformance_rules
    (rule_id, rule_family, supersedes_rule_id, source_id, stage, applies_to_fields, rule_kind,
     spec, rule, rationale, evidence_url, code_ref, effective_from)
select 'cr_status_absence_share_1', 'cr_status_absence_share', null, 'nd_mpr_xlsx', 'conform',
       array['status_canonical']::text[], 'code_ref',
       jsonb_build_object(
           'scope', 'per_jurisdiction',
           'max_share', 0.30,
           'measured_on', 'canonical.wells_latest',
           'module_function', 'glasswell.lineage.status_classes:absence_share_ceiling',
           'source_is_filing_anchor', true,
           'contract_note', 'an operational ceiling read by infra/verify.sh V-3 through that'
                            ' symbol, and by nothing on the wire: it is a property of a'
                            ' deployment, not of a class'),
       'No jurisdiction may serve the absence class for more than the registered share of its'
       ' resident wells.',
       'Serving a class for every well removes the null that used to make a failed resolver'
       ' visible, so the threshold is the replacement signal and it has to be a published'
       ' decision rather than a literal in a shell script. The highest legitimate share measured'
       ' on the deployed spine is 19.0 per cent, 68,186 of 359,421 Texas wells_latest rows on'
       ' 2026-09-03, every one of which filed no status code at all. The ceiling sits above that'
       ' with room for a load rather than at it, because a threshold set at the measurement'
       ' reddens on the next county rather than on the fault it exists to catch.',
       'https://glasswell.rpx.sh/conformance',
       'glasswell.lineage.status_classes:absence_share_ceiling', date '2026-09-03'
 where exists (select 1 from lineage.sources where source_id = 'nd_mpr_xlsx')
on conflict (rule_id) do nothing;

-- (3) The domain. Its own table rather than an enum or a column on lineage.jurisdictions: a
-- class carries presentation and presentation is what the client needs served, the domain is a
-- decision with a rationale and an effective date, and eleven of the twelve are shared across
-- five vocabularies so a per-registration column would make the shared set five copies again.
create table if not exists lineage.status_classes (
    status_canonical text primary key check (status_canonical ~ '^[a-z][a-z0-9_]*$'),
    label            text not null check (btrim(label) <> ''),
    colour           text not null check (colour ~ '^#[0-9A-F]{6}$'),
    glyph            text not null check (glyph in ('solid', 'hollow', 'bar', 'dashed',
                                                    'struck', 'struck-hollow')),
    min_zoom         integer not null check (min_zoom between 0 and 22),
    sort_order       integer not null,
    note             text not null check (btrim(note) <> ''),
    -- Produced by no mapping, and the only row a map may not target. A column rather than the
    -- comment served_status_vocabulary() carried, so the count writer, the resolver and the
    -- client cannot spell the absence class differently.
    is_absence       boolean not null default false,
    rule_id          text not null references lineage.conformance_rules (rule_id),
    effective_from   date not null,
    published_at     date not null,
    rationale        text not null
);

comment on table lineage.status_classes is
    'The canonical well-status class domain: one row per class, carrying the label, colour,'
    ' glyph, zoom floor, legend order and jurisdiction-neutral note the client is served, and'
    ' the rule that declared it. Every registered status map has a foreign key to it, so it is'
    ' a domain rather than a sixth copy of a list.';

comment on column lineage.status_classes.note is
    'Jurisdiction-neutral by construction: which regulator codes reach a class is the'
    ' per-jurisdiction mapping rule''s fact and resolves at /conformance/{rule_id}. A standing'
    ' gate refuses a note naming a registered jurisdiction, code or identity prefix.';

comment on column lineage.status_classes.is_absence is
    'The one class no mapping produces. A null status_canonical means quarantined in a map;'
    ' this row is what a serving path emits where nothing resolved.';

create unique index if not exists status_classes_sort_key
    on lineage.status_classes (sort_order);
create unique index if not exists status_classes_absence_key
    on lineage.status_classes (is_absence) where is_absence;
-- Two classes with the same swatch are indistinguishable on the canvas and in the legend. The
-- pair and not the colour alone: plugged and dry share #7C8B96 and differ in glyph, as do
-- inactive and temporarily_abandoned on #D9534F.
create unique index if not exists status_classes_colour_glyph_key
    on lineage.status_classes (colour, glyph);

drop trigger if exists reject_status_classes_mutation on lineage.status_classes;
create trigger reject_status_classes_mutation
    before update or delete on lineage.status_classes
    for each row execute function lineage.reject_mutation();

grant select on lineage.status_classes to glasswell_api, glasswell_pipeline;

-- The twelve rows. label, glyph and min_zoom are carried across verbatim from what the canvas
-- already draws. Two things are deliberate changes. Not one regulator code appears in a note,
-- which is what stops expired's note arguing from two regulators' letters while a third's codes
-- sit in the same class. And expired and unmapped are repainted: the values carried across
-- measured 2.94:1 and 2.19:1 against the dark panel, below the 3:1 non-text bar, and the
-- absence class is the one this file turns from a negation nobody could tick into a row drawn
-- on five jurisdictions. Every class clears 3:1 against both themes now.
--
-- Guarded on rule residency in the shape 075:233 uses. Here the guard reads this file's own
-- rule insert above rather than the seed's, because the foreign keys below are added in this
-- transaction and an empty domain would fail them against resident map rows.
insert into lineage.status_classes
    (status_canonical, label, colour, glyph, min_zoom, sort_order, note, is_absence, rule_id,
     effective_from, published_at, rationale)
select d.status_canonical, d.label, d.colour, d.glyph, d.min_zoom, d.sort_order, d.note,
       d.is_absence, d.rule_id, date '2026-09-03', date '2026-09-03',
       'The class domain is a decision with a rationale and an effective date, not the union of'
       ' five per-regulator maps computed at runtime. Every mapping targets this set through a'
       ' foreign key, so a class outside it is a mapping with no published decision behind it.'
  from (values
    ('active', 'Active', '#3FA55E', 'solid', 4, 10,
     'Producing, or filed as capable of production.', false, 'cr_status_class_domain_1'),
    ('drilling', 'Drilling', '#3D8BD4', 'bar', 4, 20,
     'Spudded and not yet filed as completed.', false, 'cr_status_class_domain_1'),
    ('confidential', 'Confidential', '#E4A33C', 'solid', 6, 30,
     'Withheld under an operator''s tight-hole election: a status, not missing data.',
     false, 'cr_status_class_domain_1'),
    ('permitted', 'Permitted', '#9FB0BC', 'hollow', 6, 40,
     'An approved location with no wellbore filed yet.', false, 'cr_status_class_domain_1'),
    ('inactive', 'Inactive', '#D9534F', 'bar', 8, 50,
     'Shut in, or carrying an inactive-well waiver.', false, 'cr_status_class_domain_1'),
    ('temporarily_abandoned', 'Temporarily abandoned', '#D9534F', 'dashed', 8, 60,
     'Suspended and not plugged.', false, 'cr_status_class_domain_1'),
    ('service', 'Service', '#7A6FD0', 'hollow', 8, 70,
     'Injection, disposal, storage, observation or water supply, not a producer.',
     false, 'cr_status_class_domain_1'),
    ('plugged', 'Plugged & abandoned', '#7C8B96', 'struck', 9, 80,
     'The wellbore is permanently plugged.', false, 'cr_status_class_domain_1'),
    ('dry', 'Dry hole', '#7C8B96', 'struck-hollow', 9, 90,
     'Drilled with no commercial completion filed.', false, 'cr_status_class_domain_1'),
    ('documented_unmapped', 'Documented, no class', '#8E6E9E', 'hollow', 9, 100,
     'The regulator publishes this code and glasswell has no equivalent class, so the filed'
     ' code is served instead of a guess.', false, 'cr_status_class_domain_1'),
    ('expired', 'Expired permit', '#4A7480', 'dashed', 9, 110,
     'A permit lapsed, was cancelled or was vacated before spud, so no wellbore exists.',
     false, 'cr_status_class_domain_1'),
    -- min_zoom 0: absence must not be the thing that hides. The note states both cases rather
    -- than minting a twelfth class for the second, because which codes a vocabulary declined is
    -- the mapping rule's fact and the filed code beside the class is what says which case holds.
    ('unmapped', 'Unmapped status', '#666A71', 'hollow', 0, 120,
     'No class resolved. Either the source filed no status, or it filed a code its registered'
     ' vocabulary has no row for; the well card and the hover say which, because they carry the'
     ' filed code.', true, 'cr_status_absence_basis_1')
  ) as d(status_canonical, label, colour, glyph, min_zoom, sort_order, note, is_absence,
         rule_id)
 where exists (select 1 from lineage.conformance_rules c where c.rule_id = d.rule_id)
on conflict (status_canonical) do nothing;

-- (4) The foreign keys, which are what make this a domain rather than a second list. A check
-- constraint would restate the twelve in five DDL bodies; the key makes lineage.status_classes
-- the single writer. Nullable on purpose: a null class is a quarantined code, which is what
-- Montana's six unpromoted rows are.
--
-- A function rather than six ALTER statements, for the reason the trigger attach below is one:
-- a constraint cannot point at a domain that is not resident yet, and on a fresh database the
-- domain arrives with the seed rather than with this file. Called from here, where the deployed
-- host lands it, and from seed_status_classes, where a fresh one does. Idempotent both ways.
--
-- lineage.nm_status_map deliberately gets none. It holds zero rows and no serving rule names
-- it, so a constraint on it would be a claim about a table nothing writes; the parity gate
-- lists it by name instead.
create or replace function lineage.attach_status_class_constraints() returns integer
language plpgsql as $$
declare
    target record;
    attached integer := 0;
begin
    if not exists (select 1 from lineage.status_classes) then
        return 0;
    end if;
    for target in
        select * from (values
            ('nd_status_map',              'status_canonical', 'nd_status_map_class_fk'),
            ('tx_status_map',              'status_canonical', 'tx_status_map_class_fk'),
            ('mt_status_map',              'status_canonical', 'mt_status_map_class_fk'),
            ('nm_wellhistory_status_map',  'status_canonical', 'nm_wh_status_map_class_fk'),
            ('co_facility_status_map',     'status_canonical', 'co_status_map_class_fk'),
            ('status_resolution_resolved', 'resolved_status',  'resolved_status_class_fk')
        ) as t(relation, key_col, constraint_name)
    loop
        if not exists (select 1 from pg_constraint where conname = target.constraint_name) then
            execute format(
                'alter table lineage.%I add constraint %I foreign key (%I)'
                ' references lineage.status_classes',
                target.relation, target.constraint_name, target.key_col);
            attached := attached + 1;
        end if;
    end loop;
    return attached;
end;
$$;

comment on function lineage.attach_status_class_constraints() is
    'Points every registered status map, and the resolved resolver table, at the class domain.'
    ' Idempotent, and a no-op while the domain is unloaded: on a fresh database the migration'
    ' runs before the seed that supplies the twelve rows, so seed_status_classes calls it too.';

grant execute on function lineage.attach_status_class_constraints() to glasswell_pipeline;

select lineage.attach_status_class_constraints();

-- (5) The per-map refresh trigger stops being written by hand. 078:297-301 named one map
-- literally and 078:265-274 told the next jurisdiction to write another; Colorado registered
-- read-time resolution in that same train and shipped with no trigger at all, so an append to
-- lineage.co_facility_status_map does not rebuild the resolver on the deployed host today.
--
-- A statement trigger is attached to a relation and the relations are per regulator, so this
-- cannot be one trigger for all maps. What it can be is created by the registry rather than by
-- hand, which is what removes the migration from a fifth read-time state.
--
-- Owner-defined and deliberately not security definer: create trigger requires ownership of the
-- relation, the migration and the seed both run as the owner, and neither glasswell_api nor
-- glasswell_pipeline may append a jurisdiction_rules row. That is the grant argument 078:174-180
-- already makes for the sibling format(%I) loop, reused rather than restated.
create or replace function lineage.attach_status_map_refresh() returns integer
language plpgsql as $$
declare
    registered record;
    attached integer := 0;
begin
    for registered in
        select distinct c.spec->>'mapping_table' as mapping_table
          from lineage.jurisdictions_as_of(
                   (select max(published_at) from lineage.jurisdictions), current_date) j
          join lineage.jurisdiction_rules r
            on r.jurisdiction_code = j.jurisdiction_code
           and r.effective_from = j.effective_from
           and r.published_at = j.published_at
           and r.decision = 'status_vocabulary'
           and r.serving
          join lineage.conformance_rules c on c.rule_id = r.rule_id
         where c.spec->>'resolved_at' = 'read_time'
           and c.spec->>'mapping_table' is not null
    loop
        -- Skipped with a notice for the reason 078:141-147 gives: a registration can land in a
        -- merge before the migration that creates its map, and a raise here would take the
        -- deploy's seed down with it.
        if to_regclass('lineage.' || quote_ident(registered.mapping_table)) is null then
            raise notice 'status resolver: lineage.% is registered for read-time resolution and does not exist; no refresh trigger is attached to it',
                registered.mapping_table;
            continue;
        end if;
        -- Idempotent across the deploy's repeated seed runs, which is the contract seed_all is
        -- bound to.
        execute format(
            'drop trigger if exists status_map_refresh_status_resolution on lineage.%I',
            registered.mapping_table);
        execute format(
            'create trigger status_map_refresh_status_resolution after insert on lineage.%I'
            ' for each statement execute function lineage.status_resolution_refresh()',
            registered.mapping_table);
        attached := attached + 1;
    end loop;
    return attached;
end;
$$;

comment on function lineage.attach_status_map_refresh() is
    'Attaches the resolver''s refresh trigger to every registered read-time status map, one per'
    ' relation because a statement trigger is attached to a relation. Called from this'
    ' migration, from the registry''s own append triggers and from seed_jurisdictions, so a'
    ' fifth read-time state is three rows and no trigger.';

grant execute on function lineage.attach_status_map_refresh() to glasswell_pipeline;

-- (6) One clock, and the row that records it. 078 resolved the registry at the host's calendar
-- while load_jurisdictions resolved it at max(published_at); the two already resolve different
-- rule-row sets for all four v0.76 jurisdictions and agree on status_vocabulary only by
-- accident. A superseding vocabulary rule published one day ahead of the host clock would be
-- served by /v1/wells as the rule that decided a well's class while the resolver still held the
-- classes its predecessor produced: the number on screen and the rule cited beside it would
-- come from different decisions, and no gate can see it because both halves are consistent.
--
-- max(published_at) is the later of the two, so no served jurisdiction loses a rule row at the
-- cut-over: every row the API resolves today the resolver resolves after this.
alter table lineage.status_resolution_resolved add column if not exists knowledge_for date;

comment on column lineage.status_resolution_resolved.built_for is
    'The valid date the registry was resolved at. Unchanged in meaning since 078: a registration'
    ' whose effective_from is later than this has not reached the resolver, because the refresh'
    ' is driven by appends and by every deploy rather than by the calendar.';

comment on column lineage.status_resolution_resolved.knowledge_for is
    'The knowledge cut the registry was resolved at: max(published_at) over lineage.jurisdictions,'
    ' which is what load_jurisdictions reads. Null on rows written before this migration, because'
    ' a backfilled value would be a claim about a run nobody observed.'
    ' infra/verify.sh V-4 compares it against that maximum.';

create or replace function lineage.refresh_status_resolution() returns integer
language plpgsql as $$
declare
    registered record;
    resolved integer := 0;
    added integer;
    repeated boolean;
    knowledge_cut date;
begin
    select max(published_at) into knowledge_cut from lineage.jurisdictions;
    delete from lineage.status_resolution_resolved;
    for registered in
        select j.identity_prefix, j.jurisdiction_code,
               c.spec->>'mapping_table' as mapping_table,
               c.spec->>'key_col'       as key_col,
               c.spec->>'value_col'     as value_col
          from lineage.jurisdictions_as_of(knowledge_cut, current_date) j
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
         order by j.identity_prefix
    loop
        -- Skipped, and said, for 078's reasons: aborting would take the migration or the
        -- deploy's seed down with it, and the transient case self-heals within one deploy.
        --
        -- Two failure modes skip with a notice and a third aborts, and the asymmetry is
        -- deliberate. A missing map and a map that went non-unique are transient or local: the
        -- jurisdiction resolves unmapped until it is fixed, which /v1/status and verify.sh
        -- report. A class the domain does not hold is neither: the resolved_status foreign key
        -- refuses the insert and the append fails loudly, because after the absence arm an
        -- unresolvable jurisdiction draws grey rather than null, and a skip would hide it.
        if to_regclass('lineage.' || quote_ident(registered.mapping_table)) is null then
            raise notice 'status resolver: % (%) registers lineage.% which does not exist; its wells resolve unmapped until it lands',
                registered.jurisdiction_code, registered.identity_prefix,
                registered.mapping_table;
            continue;
        end if;
        execute format(
            'select count(*) <> count(distinct m.%I) from lineage.%I m where m.%I is not null',
            registered.key_col, registered.mapping_table, registered.key_col)
          into repeated;
        if repeated then
            raise notice 'status resolver: lineage.% registered for % has a repeated %; its wells resolve unmapped until the map is keyed',
                registered.mapping_table, registered.jurisdiction_code, registered.key_col;
            continue;
        end if;
        -- WHAT MAKES THE %I INTERPOLATION SAFE IS A GRANT, NOT THE QUOTING: selecting the table
        -- takes a lineage.jurisdiction_rules row, and neither glasswell_api nor
        -- glasswell_pipeline may append one. 078:167-180 carries the whole argument.
        execute format(
            'insert into lineage.status_resolution_resolved (for_state_code,'
            ' for_status_reported, resolved_status, jurisdiction_code, built_for, knowledge_for)'
            ' select %L, m.%I::text, m.%I::text, %L, current_date, %L'
            '   from lineage.%I m'
            '  where m.%I is not null and m.%I is not null',
            registered.identity_prefix, registered.key_col, registered.value_col,
            registered.jurisdiction_code, knowledge_cut, registered.mapping_table,
            registered.key_col, registered.value_col);
        get diagnostics added = row_count;
        resolved := resolved + added;
    end loop;
    return resolved;
end;
$$;

comment on function lineage.refresh_status_resolution() is
    'Rebuilds lineage.status_resolution_resolved from every registration resolving at the'
    ' registry''s own knowledge cut, max(published_at), whose status-vocabulary rule says'
    ' resolved_at = read_time, reading the mapping table and its key and value columns out of'
    ' that rule spec. Idempotent, and cheap: the product is tens of rows. A registered mapping'
    ' table that has not been created yet is skipped with a notice; /v1/status''s status_resolver'
    ' check and infra/verify.sh are what catch a skip that lasts.';

-- Gated on the calling relation, and the gate is a cost decision rather than a correctness one.
-- 078:259-263 measured the current design at about 26 refreshes per seed_all, because the
-- triggers are per statement and psycopg's executemany sends one statement per row. Attaching
-- from every one of those firings would add a drop-and-create pair per read-time map to each,
-- every drop taking ACCESS EXCLUSIVE on a map relation. A map's own trigger is also the one
-- firing that cannot change the registered set, so it is the one that never needs to re-attach.
create or replace function lineage.status_resolution_refresh() returns trigger
language plpgsql as $$
begin
    if TG_TABLE_NAME in ('jurisdictions', 'jurisdiction_rules') then
        perform lineage.attach_status_map_refresh();
    end if;
    perform lineage.refresh_status_resolution();
    return null;
end;
$$;

-- Colorado's missing trigger, attached as this migration's first act on the deployed host.
select lineage.attach_status_map_refresh();

-- (7) The mart New Mexico's per-well series is read from. Not the client, which would be a
-- served-looking per-well number with no derivation; not canonical, which is append-only and
-- holds no filing glasswell invented; not a view, because a sum over rows carrying different
-- derivation ids has no single handle. A mart reads canonical and writes marts, which is the
-- only layer this can sit in.
--
-- Registry-driven: the refresh builds for every jurisdiction whose production_grain rule spec
-- carries served_rollup, so a sixth pool-grain state is a spec key rather than a module.
create table if not exists marts.well_pool_rollup (
    api10            text not null,
    state_code       text not null,
    production_month date not null,
    stream           text not null check (stream in ('liquid', 'gas', 'water')),
    volume           numeric(20, 3) not null,
    unit             text not null,
    days_produced    smallint,
    pools_summed     integer not null check (pools_summed > 0),
    aggregation      text not null check (aggregation = 'sum_over_pools'),
    derivation_id    text not null references lineage.derivations (derivation_id),
    primary key (api10, production_month, stream)
);

comment on table marts.well_pool_rollup is
    'The per-well monthly series for a jurisdiction that files at completion-pool grain and'
    ' registers a served rollup: the exact sum of the pool filings, days_produced as the maximum'
    ' over them and never the sum, and the count of pools summed. Disclosed as an aggregation,'
    ' never as a filing: the regulator filed no per-well number and canonical still holds none.';

comment on column marts.well_pool_rollup.derivation_id is
    'One refresh, one handle, which is coarser than a per-month one and is stated as such where'
    ' the series is served. The refresh references every input derivation rather than an opaque'
    ' scope, so a reader can still reach the filings behind a series.';

create index if not exists well_pool_rollup_state_idx
    on marts.well_pool_rollup (state_code, production_month);

grant select on marts.well_pool_rollup to glasswell_api;
grant select, insert, delete, truncate on marts.well_pool_rollup to glasswell_pipeline;

-- (8) Montana's and New Mexico's grain decisions, appended as a restatement pair in the
-- 075:143-190 shape so the registration and its rule rows move together. A rule row joins its
-- registration on the whole clock pair, so a decision appended at an instant that was already
-- published would be an edit spelled as an append; New Mexico's production_grain row also has
-- to repoint from _1 to its successor, which is not something an existing instant can express.
--
-- Every value but the clock is carried over from the row being restated rather than restated by
-- hand, and the evidence pair is read back from the publication insert above: one literal in
-- this file, and a repoint that moves the registration without the rules is not expressible.
-- On a fresh database lineage.jurisdictions is empty at migrate time and this lands nothing;
-- seed/jurisdictions.py is the writer there, which is the two-writer contract 073 set.
insert into lineage.jurisdictions (
    jurisdiction_code, effective_from, published_at, evidence_tag, evidence_commit,
    name, regulator_name, regulator_url, identity_scheme, identity_is_unique,
    identity_prefix, identity_pattern, source_ids, liquids_basis, wells_tile_layer_id,
    map_colour, neighbors_available, explorer_default, land_grid_state, land_grid_scope,
    status_dataset_detail, rationale, wells_layer_id, wells_style_layer_ids, wells_draw_order,
    wells_default_on, wells_snapshot_key, wells_subtitle_template, legend_note)
select prior.jurisdiction_code, prior.effective_from, date '2026-09-05',
       evidence.evidence_tag, evidence.evidence_commit,
       prior.name, prior.regulator_name, prior.regulator_url,
       prior.identity_scheme, prior.identity_is_unique, prior.identity_prefix,
       prior.identity_pattern, prior.source_ids, prior.liquids_basis,
       prior.wells_tile_layer_id, prior.map_colour, prior.neighbors_available,
       prior.explorer_default, prior.land_grid_state, prior.land_grid_scope,
       prior.status_dataset_detail, prior.rationale, prior.wells_layer_id,
       prior.wells_style_layer_ids, prior.wells_draw_order, prior.wells_default_on,
       prior.wells_snapshot_key, prior.wells_subtitle_template, prior.legend_note
  from lineage.jurisdictions_as_of(
           (select max(published_at) from lineage.jurisdictions), current_date) prior
 cross join (select evidence_tag, evidence_commit
               from lineage.conformance_rule_publications
              where rule_id = 'cr_status_class_domain_1') evidence
 where prior.jurisdiction_code in ('MT', 'NM');

-- The rules the restatement carries: every row the restated instant declared, read back rather
-- than respelled. The two production_grain decisions are appended below rather than copied,
-- because Montana has none to copy and New Mexico's has to repoint to the successor.
insert into lineage.jurisdiction_rules
    (jurisdiction_code, effective_from, published_at, decision, rule_id, serving, note)
select prior.jurisdiction_code, prior.effective_from, date '2026-09-05', prior.decision,
       prior.rule_id, prior.serving, prior.note
  from lineage.jurisdiction_rules prior
  join lineage.jurisdictions restated
    on restated.jurisdiction_code = prior.jurisdiction_code
   and restated.effective_from = prior.effective_from
   and restated.published_at = date '2026-09-05'
 where prior.jurisdiction_code in ('MT', 'NM')
   and prior.decision <> 'production_grain'
   and prior.published_at = (select max(p.published_at) from lineage.jurisdiction_rules p
                              where p.jurisdiction_code = prior.jurisdiction_code
                                and p.published_at < date '2026-09-05')
on conflict do nothing;

-- Montana's, which closes a live R8 violation with no code change: 389 API-10s carry a summed
-- figure on their well rows today with no rule named beside it, no breakdown link and no
-- aggregation warning, because production.py gates all three on a registered grain rule and
-- Montana registers none. Guarded on rule residency in the 075:233 shape, because the rule
-- itself is seeded in Python.
insert into lineage.jurisdiction_rules
    (jurisdiction_code, effective_from, published_at, decision, rule_id, serving, note)
select restated.jurisdiction_code, restated.effective_from, restated.published_at,
       'production_grain', 'cr_mt_bogc_pool_rollup_1', true, null
  from lineage.jurisdictions restated
 where restated.jurisdiction_code = 'MT'
   and restated.published_at = date '2026-09-05'
   and exists (select 1 from lineage.conformance_rules c
                where c.rule_id = 'cr_mt_bogc_pool_rollup_1')
on conflict do nothing;

-- New Mexico's, repointed to the successor where the successor is resident and left on the
-- founding rule where it is not: the two are seeded in different trains, and a registration
-- that lost its production_grain row between them would be a registration claiming fewer
-- decisions than it has. _2 supersedes nothing it contradicts: rolls_up_to_the_well stays
-- false, because that is a fact about the OCD's filings and about canonical, and neither moved.
insert into lineage.jurisdiction_rules
    (jurisdiction_code, effective_from, published_at, decision, rule_id, serving, note)
select restated.jurisdiction_code, restated.effective_from, restated.published_at,
       'production_grain', successor.rule_id, true, null
  from lineage.jurisdictions restated
 cross join lateral (
      select case when exists (select 1 from lineage.conformance_rules c
                                where c.rule_id = 'cr_nm_wcproduction_pool_rollup_2')
                  then 'cr_nm_wcproduction_pool_rollup_2'
                  else 'cr_nm_wcproduction_pool_rollup_1' end as rule_id) successor
 where restated.jurisdiction_code = 'NM'
   and restated.published_at = date '2026-09-05'
   and exists (select 1 from lineage.conformance_rules c
                where c.rule_id = successor.rule_id)
on conflict do nothing;

-- The supersession, recorded on the audit trail the way 071 and 075 record one: the rule is
-- appended, never edited, and what changed between the two is readable without the rationale.
insert into lineage.audit_events (event_id, occurred_at, actor, event_type, subject_type,
                                  subject_id, payload)
select 'evt_migration_cr_nm_wcproduction_pool_rollup_2', now(), 'system:migration',
       'conformance.rule_superseded', 'rule', 'cr_nm_wcproduction_pool_rollup_2',
       jsonb_build_object('supersedes', 'cr_nm_wcproduction_pool_rollup_1',
                          'from_spec', 'no served rollup; the regulator files at completion-pool'
                                       ' grain and glasswell performs none',
                          'to_spec', 'served_rollup: sum_over_pools, served_from:'
                                     ' marts.well_pool_rollup, promotes_to_canonical: false',
                          'migration', 'status_vocabulary')
 where exists (select 1 from lineage.conformance_rules
                where rule_id = 'cr_nm_wcproduction_pool_rollup_2')
   and not exists (select 1 from lineage.audit_events
                    where event_id = 'evt_migration_cr_nm_wcproduction_pool_rollup_2');

-- (9) Last, as 078:319 does: the resolver is rebuilt at the knowledge cut this file introduced,
-- with the trigger set this file attached.
select lineage.refresh_status_resolution();
