-- The two rules that make the S-E key usable for ND, inserted here for an already-seeded
-- database; a fresh one gets the same content from glasswell.seed.conformance_nd.
--
-- cr_nd_entity_key_1 builds the pool entity key. cr_nd_pool_rollup_1 is the legislated sum
-- that replaces D1's interim withdrawal: it is a policy statement, so it is recorded as
-- code_ref exactly like cr_nd_liquids_policy_1 and cr_nd_null_semantics_1, and it is served at
-- /v1/conformance so the aggregation a well figure carries names a rule a reader can open.

insert into lineage.conformance_rules
    (rule_id, rule_family, source_id, stage, applies_to_fields, rule_kind, spec, rule,
     rationale, evidence_url, code_ref, effective_from)
select 'cr_nd_entity_key_1', 'cr_nd_entity_key', 'nd_mpr_xlsx', 'conform',
       '{api10,pool}', 'key_composite',
       jsonb_build_object(
           'source_cols', jsonb_build_array('api10', 'pool'),
           'separator', ':',
           'target_col', 'entity_key',
           'on_missing', 'passthrough',
           'uniqueness_scope', 'api10'),
       'The pool entity key is the API-10 joined to the pool the operator filed under.',
       'The MPR''s grain is (API-14, pool, month) while migration 008 keyed canonical on'
       ' (api10, month, stream), so a well completed in two pools collided on real data and'
       ' all but the first row by spreadsheet ordinal were quarantined (fp-audit D1: 78 wells,'
       ' 454 well-months, 139,644 bbl). The key is built from registry columns rather than a'
       ' literal in the parser because the same executor builds NM''s well-completion key and'
       ' TX''s (OIL_GAS_CODE, DISTRICT_NO, LEASE_NO) lease key (SB-01 §2.10, §4.1). A month'
       ' NDIC filed with no pool label passes through unkeyed: it is an observation of the'
       ' well, and inventing a pool for it would be a fact the source does not carry.',
       'https://www.dmr.nd.gov/oilgas/mpr/2026_03.xlsx', null, date '2026-08-20'
 where exists (select 1 from lineage.sources where source_id = 'nd_mpr_xlsx')
on conflict (rule_id) do nothing;

insert into lineage.conformance_rules
    (rule_id, rule_family, source_id, stage, applies_to_fields, rule_kind, spec, rule,
     rationale, evidence_url, code_ref, effective_from)
select 'cr_nd_pool_rollup_1', 'cr_nd_pool_rollup', 'nd_mpr_xlsx', 'conform',
       '{volume,days_produced,null_semantics}', 'code_ref',
       jsonb_build_object(
           'module_function', 'glasswell.ingest.nd_mpr:pool_promotion_records',
           'version', '1',
           'aggregation', 'sum_over_pools',
           'volume', 'exact sum over the pool filings of the well-month-stream',
           'days_produced', 'maximum over the pool filings, never the sum',
           'null_semantics', 'reported unless every pool filing is absent, then no_report',
           'contract_note',
           'one filing promotes as the well; two or more promote as one row per pool plus a'
           ' well row carrying their exact sum, disclosed as aggregation = sum_over_pools'),
       'A well that filed in more than one pool is one row per pool plus a well total that'
       ' says it is a sum.',
       'Summing across pools is legislated here rather than performed at serve time: a'
       ' serve-time sum is a figure with no derivation to cite, which R6 and R7 forbid, and it'
       ' was why D1''s interim fix withdrew the point instead. Volume sums exactly because the'
       ' pool filings are disjoint observations of the same wellbore-month. Days do not sum -'
       ' a well cannot produce more days than the month holds and the pool filings are'
       ' concurrent, so the well''s days are the maximum over its pools. The well row carries'
       ' reporting_level = well_completion_pool and aggregation = sum_over_pools so the'
       ' consumer can tell a two-pool well from a one-pool well, which S-B requires because'
       ' they are different objects. A well-month with exactly one filing is promoted as the'
       ' well directly: the sum over one pool is that pool, and relabelling 394,278 unaffected'
       ' rows as aggregates would signal a restatement that did not happen (DIR-2).',
       'https://www.dmr.nd.gov/oilgas/mpr/2026_03.xlsx',
       'glasswell.ingest.nd_mpr:pool_promotion_records', date '2026-08-20'
 where exists (select 1 from lineage.sources where source_id = 'nd_mpr_xlsx')
on conflict (rule_id) do nothing;

insert into lineage.audit_events (event_id, occurred_at, actor, event_type, subject_type,
                                  subject_id, payload)
select 'evt_migration_023_' || rule_id, now(), 'system:migration', 'conformance.rule_added',
       'rule', rule_id,
       jsonb_build_object('migration', '023_nd_pool_rules',
                          'rule_kind', rule_kind,
                          'closes', 'DR-38 structural half / fp-audit D1')
  from lineage.conformance_rules
 where rule_id in ('cr_nd_entity_key_1', 'cr_nd_pool_rollup_1');
