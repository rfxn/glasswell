-- The reason vocabulary admits the codes the seeded rules name, and the rows those rules
-- already proved are relabelled (M-3). Migration 007 omitted `stream_not_promoted` and
-- `unknown_status`, so glasswell.ingest.nd_mpr degraded every one to `unknown_vocab` — the
-- dominant label in the ledger read "the ingest does not understand its own source file",
-- which is the opposite of what cr_nd_stream_vocab_1 decided. The GIS wells path has no
-- degradation step at all, so an unmapped status would have raised on insert.

alter table lineage.quarantine_rows drop constraint quarantine_rows_reason_code_check;

alter table lineage.quarantine_rows add constraint quarantine_rows_reason_code_check
    check (reason_code in (
        'parse_error', 'encoding_error', 'schema_mismatch', 'unknown_vocab',
        'alias_unresolved', 'datum_undetermined', 'key_collision',
        'multi_wellbore_policy', 'impossible_volume', 'orphan_fk',
        'confidential_withheld', 'duplicate_row', 'out_of_range_date',
        'unreliable_numeric', 'stream_not_promoted', 'unknown_status'));

-- A label correction, not a rewrite of what happened: the rule that rejected the row is the
-- record of why, it names the code the CHECK refused, and the payload is untouched. Bounded
-- by rule_id for exactly that reason — a row whose rule proves nothing else stays unknown.
with corrected as (
    update lineage.quarantine_rows q
       set reason_code = truth.reason_code
      from (values ('cr_nd_stream_vocab_1', 'stream_not_promoted'),
                   ('cr_nd_status_vocab_1', 'unknown_status')) as truth (rule_id, reason_code)
     where q.rule_id = truth.rule_id
       and q.reason_code = 'unknown_vocab'
    returning q.rule_id, q.reason_code)
insert into lineage.audit_events (event_id, occurred_at, actor, event_type, subject_type,
                                  subject_id, payload)
select 'evt_migration_011_' || rule_id, now(), 'system:migration', 'quarantine.relabelled',
       'rule', rule_id,
       jsonb_build_object('from', 'unknown_vocab', 'to', reason_code, 'rows', count(*),
                          'migration', '011_quarantine_reason_vocabulary')
  from corrected
 group by rule_id, reason_code;
