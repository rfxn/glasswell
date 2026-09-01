-- New Mexico's status class, resolved at read time from the registry rather than backfilled.
--
-- canonical.wells.status_canonical stays null for every New Mexico header: the table is
-- append-only, its promotion anti-joins on (api10, effective_from), and a re-promotion would
-- have to invent a valid time OCD never filed. The class is therefore a join, not a column
-- write, and canonical.status_resolution is the one place the tile mart and the API both read
-- it from — an API-only resolver would leave the tiles serving null while the well card read
-- "Active", which is one screen with two answers.
--
-- REPOINT CHECKLIST (integrator, at the merge train):
--   1. evidence_tag UNRELEASED -> the tag that first carries cr_nm_wellhistory_status_vocab_2
--   2. evidence_commit forty zeros -> the main head this branch was written against
--   3. published_vintage 2026-09-01 -> confirm it is the date that tag is cut, or correct it
-- The rule id itself is immutable and must not change during the repoint.

insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
values ('cr_nm_wellhistory_status_vocab_2', date '2026-09-01', 'v0.74',
        'a4f9be5416e152b84a487ecf39ae4897cec901c7')
on conflict (rule_id) do nothing;

-- Not lineage.nm_status_map: that table is the declared target_map of the well-*completion*
-- rules (cr_nm_wchistory_status_vocab_1, cr_nm_wcproduction_status_vocab_1), whose letters are
-- a different vocabulary under the same regulator — wchistory P is "Zone Permanently Plugged"
-- where wellhistory P is "Plugged (site released)". One table for both would hand the
-- completion rules a codebook that is wrong for them on the day they promote.
create table if not exists lineage.nm_wellhistory_status_map (
    status            text primary key,
    decode            text not null,
    status_canonical  text not null,
    published_vintage date not null
);

comment on table lineage.nm_wellhistory_status_map is
    'OCD wellhistory.status -> canonical well status, from the OCD data dictionary sheet'
    ' "consolidated code list" (cr_nm_wellhistory_status_vocab_2). decode is the regulator''s'
    ' own wording, kept beside the mapping so the decision can be read against its source.';

comment on column lineage.nm_wellhistory_status_map.status_canonical is
    'Never null. Four codes are documented and have no canonical equivalent; they carry the'
    ' registered class documented_unmapped rather than a null, because collapsing them into'
    ' the absence class would erase the fact that the regulator did say something.';

-- Counts are wells, not records: canonical.wells is effective-dated and the map serves
-- wells_latest, where the 321,510 header records resolve to 142,000 wells. Measured on the
-- deployed database 2026-09-01 and reproduced code for code against OCD's own live
-- Wells_Public layer, which pairs the letters with these labels.
insert into lineage.nm_wellhistory_status_map (status, decode, status_canonical, published_vintage)
values
    ('A', 'Active',                          'active',                date '2026-09-01'), -- 54326
    ('P', 'Plugged (site released)',         'plugged',               date '2026-09-01'), -- 48268
    ('N', 'New',                             'permitted',             date '2026-09-01'), -- 18176
    ('C', 'Cancelled',                       'expired',               date '2026-09-01'), -- 17067
    ('H', 'Plugged (not released)',          'plugged',               date '2026-09-01'), --  2758
    ('T', 'Temporary Abandonment',           'temporarily_abandoned', date '2026-09-01'), --   513
    ('J', 'Reclamation Fund Approved',       'documented_unmapped',   date '2026-09-01'), --   470
    ('E', 'Temporary Abandonment (expired)', 'temporarily_abandoned', date '2026-09-01'), --   266
    ('X', 'Never Drilled',                   'expired',               date '2026-09-01'), --   103
    ('Q', 'Zone Plugged (permanent)',        'documented_unmapped',   date '2026-09-01'), --    25
    ('D', 'Dry Hole',                        'dry',                   date '2026-09-01'), --    15
    ('Z', 'Zone Plugged (temporary)',        'documented_unmapped',   date '2026-09-01'), --     9
    ('S', 'Shut In',                         'inactive',              date '2026-09-01'), --     0
    ('I', 'Reclamation Fund Pending',        'documented_unmapped',   date '2026-09-01')  --     4
on conflict (status) do nothing;

drop trigger if exists nm_wellhistory_status_map_append_only on lineage.nm_wellhistory_status_map;
create trigger nm_wellhistory_status_map_append_only
    before update or delete on lineage.nm_wellhistory_status_map
    for each row execute function lineage.reject_mutation();

create index if not exists nm_wellhistory_status_map_publication_idx
    on lineage.nm_wellhistory_status_map (published_vintage, status);

-- Column names are deliberately unlike the spine's. Every consumer joins this view onto a
-- query that already selects state_code, status_reported and status_canonical unqualified, so
-- a matching name here would turn a working WHERE clause ambiguous at runtime.
create or replace view canonical.status_resolution as
select '30'::text as for_state_code,
       m.status   as for_status_reported,
       m.status_canonical as resolved_status
  from lineage.nm_wellhistory_status_map m;

comment on view canonical.status_resolution is
    'Read-time status resolution: the class a served status carries where the promotion wrote'
    ' none. One row per (state, reported code); a state absent from it resolves to null, which'
    ' is the unmapped class and not a defect.';

grant select on lineage.nm_wellhistory_status_map, canonical.status_resolution
    to glasswell_pipeline, glasswell_api;
revoke update, delete on lineage.nm_wellhistory_status_map
    from glasswell_pipeline, glasswell_api;

-- On a fresh database the seed supplies this row and this insert is a no-op; on a deployed one
-- the ancestor is already resident and this is the statement that lands the successor. The two
-- copies are held identical by tests/integration/test_migration_071_nm_status_resolution.py.
insert into lineage.conformance_rules
    (rule_id, rule_family, supersedes_rule_id, source_id, stage, applies_to_fields, rule_kind,
     spec, rule, rationale, evidence_url, code_ref, effective_from)
select 'cr_nm_wellhistory_status_vocab_2', 'cr_nm_wellhistory_status_vocab',
       'cr_nm_wellhistory_status_vocab_1', 'nm_ocd_wellhistory', 'conform',
       array['status']::text[], 'vocab_map',
       '{
         "active_producing_share": {
           "share": "90.4%",
           "wells": 54326,
           "window_months": 24,
           "with_reported_volume": 49117
         },
         "canonical_mapping": {
           "A": "active",
           "C": "expired",
           "D": "dry",
           "E": "temporarily_abandoned",
           "H": "plugged",
           "I": "documented_unmapped",
           "J": "documented_unmapped",
           "N": "permitted",
           "P": "plugged",
           "Q": "documented_unmapped",
           "S": "inactive",
           "T": "temporarily_abandoned",
           "X": "expired",
           "Z": "documented_unmapped"
         },
         "corroborating_url": "https://gis.emnrd.nm.gov/arcgis/rest/services/OCDView/Wells_Public/FeatureServer/0",
         "documented_without_equivalent": [
           "I",
           "J",
           "Q",
           "Z"
         ],
         "documented_without_equivalent_class": "documented_unmapped",
         "evidence_sha256": "b95c45d3e4e17f1f0c901f6a83777acacece08dc1c29166a4e8543224ff3c413",
         "evidence_sheet": "consolidated code list",
         "key_col": "status",
         "mapping_table": "nm_wellhistory_status_map",
         "measured_domain": {
           "&#x20;": 6,
           "A": 206195,
           "C": 17400,
           "D": 34,
           "E": 733,
           "H": 4762,
           "I": 5,
           "J": 486,
           "N": 36615,
           "P": 50211,
           "Q": 1652,
           "S": 506,
           "T": 2512,
           "X": 331,
           "Z": 62
         },
         "measured_domain_wells_latest": {
           "A": 54326,
           "C": 17067,
           "D": 15,
           "E": 266,
           "H": 2758,
           "I": 4,
           "J": 470,
           "N": 18176,
           "P": 48268,
           "Q": 25,
           "T": 513,
           "X": 103,
           "Z": 9
         },
         "measured_rows": 321510,
         "measured_wells": 142000,
         "promoted_to": "status_reported",
         "published_decodes": {
           "A": "Active",
           "C": "Cancelled",
           "D": "Dry Hole",
           "E": "Temporary Abandonment (expired)",
           "H": "Plugged (not released)",
           "I": "Reclamation Fund Pending",
           "J": "Reclamation Fund Approved",
           "N": "New",
           "P": "Plugged (site released)",
           "Q": "Zone Plugged (permanent)",
           "S": "Shut In",
           "T": "Temporary Abandonment",
           "X": "Never Drilled",
           "Z": "Zone Plugged (temporary)"
         },
         "resolved_at": "read_time",
         "resolver_view": "canonical.status_resolution",
         "transposed_in_dictionary": [
           "I",
           "J"
         ],
         "unmapped_action": "passthrough",
         "value_col": "status_canonical",
         "writes_canonical_column": false
       }'::jsonb,
       'Map wellhistory.status onto the canonical status vocabulary through'
        ' lineage.nm_wellhistory_status_map, resolved at read time. status_reported keeps the'
        ' filed letter, canonical.wells.status_canonical stays null, and the served class is the'
        ' join.',
       'cr_nm_wellhistory_status_vocab_1 refused to map these letters because no codebook was'
        ' in evidence, and stated the condition on which it could be superseded. That condition'
        ' is met: the OCD publishes a data dictionary on the EMNRD domain, sheet consolidated'
        ' code list rows 57 to 70, linked from the OCD data page and byte-stable across'
        ' independent fetches. The published domain is fourteen codes and the measured domain is'
        ' those same fourteen plus the CHAR padding blank, so the vocabulary is closed against'
        ' the regulator list rather than sampled. Ten codes reach a canonical class. Four do not:'
        ' Q and Z are zone-plugged states and I and J are reclamation-fund states, and glasswell'
        ' has no class for a wellbore whose zones are plugged or for a financial-assurance state.'
        ' Forcing them into plugged would strike 508 wells through on a claim the regulator never'
        ' made, and collapsing them into the unmapped class would erase the fact that the'
        ' regulator did say something, so they carry the registered class documented_unmapped'
        ' instead. The dictionary prints I and J the other way round from both live OCD services,'
        ' and the services win on a per-well check rather than on frequency: the four wells'
        ' carrying I in canonical.wells_latest are exactly the four the public layer labels'
        ' Reclamation Fund Pending, and the nine carrying Z are exactly the nine it labels Zone'
        ' Plugged (temporary). Resolution is at read time because canonical.wells is append-only,'
        ' its promotion anti-joins on api10 and effective_from, and a re-promotion appends zero'
        ' rows: the only backfills available were to invent a valid time the OCD never filed or'
        ' to weaken the refusal. unmapped_action is passthrough rather than the quarantine North'
        ' Dakota and Montana use, because this rule reads a header table that is the identity'
        ' spine production joins to, and quarantining would drop 2,211 records from it - a larger'
        ' error than an unmapped status. Measured at the wells_latest grain every served surface'
        ' reads, 142,000 wells: A 54,326, P 48,268, N 18,176, C 17,067, H 2,758, T 513, J 470, E'
        ' 266, X 103, Q 25, D 15, Z 9 and I 4. N is the mapping worth arguing with. OCD decodes'
        ' it as New and its own wchistory sheet decodes the same letter as New, Not Drilled, so'
        ' it maps to permitted - yet 7,614 of those 18,176 wells reported volume in the trailing'
        ' 24 months, which is the OCD calculated status lagging rather than a second meaning, and'
        ' is recorded here so that nobody reads permitted as a claim that no wellbore exists. A'
        ' is the opposite case and the one the ratification asked to be checked: 49,117 of 54,326'
        ' A wells reported volume over the same window, 90.4 percent, so Active is a producing'
        ' state here and not a records one.',
       'https://www.emnrd.nm.gov/ocd/wp-content/uploads/sites/6/OCD-Interface-v1.1-Data-Dictionary-Protected.xlsx',
       'src/glasswell/marts/nm_wells.py', date '2026-09-01'
 where exists (select 1 from lineage.conformance_rules
                where rule_id = 'cr_nm_wellhistory_status_vocab_1')
on conflict (rule_id) do nothing;

insert into lineage.audit_events (event_id, occurred_at, actor, event_type, subject_type,
                                  subject_id, payload)
select 'evt_migration_071_cr_nm_wellhistory_status_vocab_2', now(), 'system:migration',
       'conformance.rule_superseded', 'rule', 'cr_nm_wellhistory_status_vocab_2',
       jsonb_build_object('supersedes', 'cr_nm_wellhistory_status_vocab_1',
                          'from_mapping', 'none; status_canonical null on every NM well',
                          'to_mapping', 'lineage.nm_wellhistory_status_map, resolved at read time',
                          'register', 'DR-N1',
                          'migration', '071_nm_status_resolution')
 where exists (select 1 from lineage.conformance_rules
                where rule_id = 'cr_nm_wellhistory_status_vocab_2')
   and not exists (select 1 from lineage.audit_events
                    where event_id = 'evt_migration_071_cr_nm_wellhistory_status_vocab_2');

-- SB-07 6.5 step 3: the surface the rule changes is the New Mexico tile mart, whose stored
-- status_canonical was written under the superseded rule and is null on all 141,778 rows.
insert into lineage.audit_events (event_id, occurred_at, actor, event_type, subject_type,
                                  subject_id, payload)
select 'evt_migration_071_mart_invalidated', now(), 'system:migration', 'mart.invalidated',
       'rule', 'cr_nm_wellhistory_status_vocab_2',
       jsonb_build_object('datasets', jsonb_build_array('marts.nm_wells_tile'),
                          'reason', 'status_canonical was written under'
                                    ' cr_nm_wellhistory_status_vocab_1, which mapped nothing',
                          'rebuild_with', 'python -m glasswell.marts.nm_wells --dsn <dsn>',
                          'migration', '071_nm_status_resolution')
 where exists (select 1 from lineage.conformance_rules
                where rule_id = 'cr_nm_wellhistory_status_vocab_2')
   and not exists (select 1 from lineage.audit_events
                    where event_id = 'evt_migration_071_mart_invalidated');

comment on column marts.nm_wells_tile.status_reported is
    'The OCD status letter, carried beside the class it resolves to under'
    ' cr_nm_wellhistory_status_vocab_2 so the mapping is readable rather than implicit.';
