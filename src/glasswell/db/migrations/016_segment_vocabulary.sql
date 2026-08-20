-- The horizontals layer ships `<API14>_LAT<n>`, `<API14>_STK<n>` and `<API14>_VERT`, and the
-- loader selected laterals with a literal `segment == "LAT"` — a mapping decision living only
-- in code, against R8. Its 24,872 rejects were labelled `unknown_vocab`, which asserts the
-- ingest did not understand its source for rows whose segment the ingest had itself parsed and
-- written into the payload (fp-audit A5-F6). The segment vocabulary becomes a rule, the label
-- becomes the one that rule names, and the existing rows are relabelled from the evidence they
-- already carry — bounded by that evidence, exactly as migration 011 was bounded by rule_id.

create table if not exists lineage.nd_segment_map (
    segment   text primary key,
    geom_type text,
    promoted  boolean not null default true
);

comment on table lineage.nd_segment_map is
    'Key column is named for the frame column cr_nd_segment_vocab_1 maps: _vocab_map reads '
    'spec.key_col from both the frame and this table.';

-- _vocab_map stringifies every lookup value, so a NULL would promote as the text 'None'.
-- The unpromoted rows stay in the table as the evidence for what the layer actually ships.
create or replace view lineage.nd_segment_promoted_map as
select segment, geom_type
  from lineage.nd_segment_map
 where promoted and geom_type is not null;

grant select on lineage.nd_segment_map, lineage.nd_segment_promoted_map
    to glasswell_pipeline, glasswell_api;

insert into lineage.nd_segment_map (segment, geom_type, promoted)
values ('LAT',  'lateral', true),
       ('STK',  null,      false),
       ('VERT', null,      false)
on conflict do nothing;

alter table lineage.quarantine_rows drop constraint if exists quarantine_rows_reason_code_check;

alter table lineage.quarantine_rows add constraint quarantine_rows_reason_code_check
    check (reason_code in (
        'parse_error', 'encoding_error', 'schema_mismatch', 'unknown_vocab',
        'alias_unresolved', 'datum_undetermined', 'key_collision',
        'multi_wellbore_policy', 'impossible_volume', 'orphan_fk',
        'confidential_withheld', 'duplicate_row', 'out_of_range_date',
        'unreliable_numeric', 'stream_not_promoted', 'unknown_status',
        'segment_not_promoted'));

-- The card asks "was anything held back for this well?" per request; without this the answer
-- costs a filter over every GIS row in the ledger.
create index if not exists quarantine_rows_api10_idx
    on lineage.quarantine_rows (source_id, (row_payload ->> 'api10'));

insert into lineage.conformance_rules
    (rule_id, rule_family, source_id, stage, applies_to_fields, rule_kind, spec, rule,
     rationale, evidence_url, effective_from)
select 'cr_nd_segment_vocab_1', 'cr_nd_segment_vocab', 'nd_gis_horizontals_line', 'conform',
       '{segment}', 'vocab_map',
       jsonb_build_object(
           'mapping_table', 'nd_segment_promoted_map',
           'key_col', 'segment',
           'value_col', 'geom_type',
           'unmapped_action', 'quarantine',
           'reason_code', 'segment_not_promoted'),
       'Promote the LAT centreline; hold the vertical hole and the sidetrack as a disposition.',
       'OGD_Horizontals_Line ships three segment kinds in linekey: LAT (23,234 rows), VERT'
       ' (21,302) and STK (4,147). Only the lateral is a producing centreline, so promoting a'
       ' vertical segment as one would be wrong - but the other two are not unknown vocabulary,'
       ' which is what the loader''s literal made the ledger say for 24,872 rows whose own'
       ' payload carried the segment the loader had parsed (fp-audit A5-F6). The choice is a'
       ' vocabulary, so it is a table, and the rows it holds back say what they are. 68 wells'
       ' have a sidetrack and no lateral; their card discloses the held-back trace rather than'
       ' reading as a well with no horizontal at all (fp-audit A3-F3).',
       'https://gis.dmr.nd.gov/downloads/oilgas/shapefile/OGD_Horizontals_Line.zip',
       date '2026-08-20'
 where exists (select 1 from lineage.sources where source_id = 'nd_gis_horizontals_line')
on conflict (rule_id) do nothing;

-- Evidence-bounded: only rows whose own payload carries a segment the map does not promote.
with corrected as (
    update lineage.quarantine_rows q
       set reason_code = 'segment_not_promoted',
           rule_id = 'cr_nd_segment_vocab_1'
      from lineage.nd_segment_map m
     where q.source_id = 'nd_gis_horizontals_line'
       and q.reason_code = 'unknown_vocab'
       and q.row_payload ->> 'segment' = m.segment
       and not m.promoted
    returning q.quarantine_id)
insert into lineage.audit_events (event_id, occurred_at, actor, event_type, subject_type,
                                  subject_id, payload)
select 'evt_migration_016_cr_nd_segment_vocab_1', now(), 'system:migration',
       'quarantine.relabelled', 'rule', 'cr_nd_segment_vocab_1',
       jsonb_build_object('from', 'unknown_vocab', 'to', 'segment_not_promoted',
                          'rows', count(*),
                          'bounded_by', 'row_payload->>segment in (select segment from'
                                        ' lineage.nd_segment_map where not promoted)',
                          'finding', 'fp-audit A5-F6',
                          'migration', '016_segment_vocabulary')
  from corrected
 having count(*) > 0;
