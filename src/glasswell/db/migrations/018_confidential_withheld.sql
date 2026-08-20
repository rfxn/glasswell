-- `confidential_withheld` has been in the reason vocabulary since migration 011 with zero
-- rows, because cr_nd_days_range_1 judged the row first: between(days, 0, 31) cannot judge a
-- row that has no days, so a month NDIC withheld was filed as out_of_range_date — a code that
-- asserts a value exists and is wrong (fp-audit D2 / A5-F7, 1,055 well-months). The rule that
-- recognises a withholding is inserted here for an already-seeded database; a fresh one gets
-- it from glasswell.seed.conformance_nd, which carries the same content. It sorts before
-- cr_nd_days_range_1, and load_rules orders by rule_id, so it judges first.

insert into lineage.conformance_rules
    (rule_id, rule_family, source_id, stage, applies_to_fields, rule_kind, spec, rule,
     rationale, evidence_url, effective_from)
select 'cr_nd_confidential_1', 'cr_nd_confidential', 'nd_mpr_xlsx', 'validate', '{pool}',
       'validity_filter',
       jsonb_build_object(
           'predicate_ast', jsonb_build_object('or', jsonb_build_array(
               jsonb_build_object('is_null', jsonb_build_object('col', 'pool')),
               jsonb_build_object('not', jsonb_build_object('cmp', jsonb_build_array(
                   jsonb_build_object('col', 'pool'), '==',
                   jsonb_build_object('lit', 'CONFIDENTIAL')))))),
           'on_fail', 'quarantine',
           'reason_code', 'confidential_withheld'),
       'A month NDIC pools as CONFIDENTIAL is withheld, not missing and not invalid.',
       'ND publishes a confidential well''s month with the literal string NULL in Oil, Wtr, Gas'
       ' and Days and Pool = CONFIDENTIAL. cr_nd_days_range_1 compiles to between(days, 0, 31),'
       ' which cannot judge a row that has no days, so the row fell out under out_of_range_date'
       ' - a code asserting that a value exists and is wrong, for a value the regulator withheld'
       ' (fp-audit D2 / A5-F7, 1,055 well-months). This rule runs first, by rule_id order, and'
       ' gives the withholding its own name. Confidential is a status, and withheld is a'
       ' distinct state from missing (§3.0.3).',
       'https://www.dmr.nd.gov/oilgas/mpr/2026_03.xlsx',
       date '2026-08-20'
 where exists (select 1 from lineage.sources where source_id = 'nd_mpr_xlsx')
on conflict (rule_id) do nothing;

-- Bounded by the payload's own evidence: the pool NDIC filed and the day count it withheld.
-- A row with a day count out of range keeps the label it earned.
with corrected as (
    update lineage.quarantine_rows
       set reason_code = 'confidential_withheld',
           rule_id = 'cr_nd_confidential_1'
     where source_id = 'nd_mpr_xlsx'
       and reason_code = 'out_of_range_date'
       and row_payload ->> 'pool' = 'CONFIDENTIAL'
       and row_payload ->> 'days' is null
       and exists (select 1 from lineage.conformance_rules
                    where rule_id = 'cr_nd_confidential_1')
    returning quarantine_id)
insert into lineage.audit_events (event_id, occurred_at, actor, event_type, subject_type,
                                  subject_id, payload)
select 'evt_migration_018_cr_nd_confidential_1', now(), 'system:migration',
       'quarantine.relabelled', 'rule', 'cr_nd_confidential_1',
       jsonb_build_object('from', 'out_of_range_date', 'to', 'confidential_withheld',
                          'rows', count(*),
                          'bounded_by', 'row_payload->>pool = ''CONFIDENTIAL'' and'
                                        ' row_payload->>days is null',
                          'finding', 'fp-audit D2',
                          'migration', '018_confidential_withheld')
  from corrected
 having count(*) > 0;
