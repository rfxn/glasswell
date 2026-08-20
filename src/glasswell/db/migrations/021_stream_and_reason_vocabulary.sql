-- Two vocabularies the S-E key opens the door to, widened here so neither is discovered at
-- runtime by the state that needs it.
--
-- condensate: reconciliation.md:802 affirms C7 for ND (Oil already carries oil+condensate
-- under cr_nd_liquids_policy_1) and admits condensate as its own stream with NM and TX. ND
-- files no condensate column, so lineage.nd_stream_map gains no row and no ND row changes.
--
-- key_incomplete: the key_composite executor needs an exit for a record whose entity_key has a
-- null component. parse_error asserts a parse failure that did not happen, orphan_fk asserts an
-- FK that does not exist and key_collision asserts a duplicate that is not there.

alter table canonical.production_monthly drop constraint production_monthly_stream_check;

alter table canonical.production_monthly add constraint production_monthly_stream_check
    check (stream in ('oil', 'gas', 'water', 'condensate'));

alter table lineage.quarantine_rows drop constraint if exists quarantine_rows_reason_code_check;

alter table lineage.quarantine_rows add constraint quarantine_rows_reason_code_check
    check (reason_code in (
        'parse_error', 'encoding_error', 'schema_mismatch', 'unknown_vocab',
        'alias_unresolved', 'datum_undetermined', 'key_collision',
        'multi_wellbore_policy', 'impossible_volume', 'orphan_fk',
        'confidential_withheld', 'duplicate_row', 'out_of_range_date',
        'unreliable_numeric', 'stream_not_promoted', 'unknown_status',
        'segment_not_promoted', 'key_incomplete'));
