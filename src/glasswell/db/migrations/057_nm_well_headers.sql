-- canonical.wells and canonical.well_spatial need no widening for API prefix 30: neither
-- carries a state constraint, and well_spatial.geom_type already admits 'surface'. What the New
-- Mexico header promotion does need is somewhere to file the two coordinate refusals, and an
-- index for the per-state newest-effective-row scan the tile marts run.

-- coordinate_absent and coordinate_sentinel are two different facts about a record and a single
-- code would lose the distinction: a nil ordinate is a regulator who filed no location, and a
-- zero ordinate is one who filed a placeholder. Rejects are quarantined with a reason, never
-- dropped, and neither refusal suppresses the well header itself.
alter table lineage.quarantine_rows drop constraint if exists quarantine_rows_reason_code_check;

alter table lineage.quarantine_rows add constraint quarantine_rows_reason_code_check
    check (reason_code in (
        'parse_error', 'encoding_error', 'schema_mismatch', 'unknown_vocab',
        'alias_unresolved', 'datum_undetermined', 'key_collision',
        'multi_wellbore_policy', 'impossible_volume', 'orphan_fk',
        'confidential_withheld', 'duplicate_row', 'out_of_range_date',
        'unreliable_numeric', 'stream_not_promoted', 'unknown_status',
        'segment_not_promoted', 'key_incomplete', 'out_of_scope', 'multi_completion',
        'insufficient_stations', 'coordinate_absent', 'coordinate_sentinel'));

comment on constraint quarantine_rows_reason_code_check on lineage.quarantine_rows is
    'coordinate_absent is emitted by cr_nm_wellhistory_coordinate_1 when either ordinate is nil,'
    ' checked first; coordinate_sentinel when neither is nil and either is exactly zero. A zero'
    ' longitude is not detectable by a range check, because 0.0 is a valid longitude everywhere.';

-- The tile marts read `distinct on (api10) ... where state_code = %(state_code)s order by api10,
-- effective_from desc`, and nothing supported it. At 447k resident rows plus New Mexico's
-- 321,510 it is worth one index.
create index if not exists wells_state_effective_idx
    on canonical.wells (state_code, effective_from desc);
