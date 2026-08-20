-- Quarantine (SB-07 §8). Rejects are quarantined with a reason, never dropped, never deleted.

create table lineage.quarantine_rows (
    quarantine_id          text primary key,
    row_fingerprint        text not null,
    source_id              text not null references lineage.sources (source_id),
    staging_table          text not null,
    stage                  text not null check (stage in ('parse', 'validate', 'conform', 'join')),
    reason_code            text not null check (reason_code in (
                               'parse_error', 'encoding_error', 'schema_mismatch', 'unknown_vocab',
                               'alias_unresolved', 'datum_undetermined', 'key_collision',
                               'multi_wellbore_policy', 'impossible_volume', 'orphan_fk',
                               'confidential_withheld', 'duplicate_row', 'out_of_range_date',
                               'unreliable_numeric')),
    rule_id                text references lineage.conformance_rules (rule_id),
    row_payload            jsonb not null default '{}'::jsonb,
    first_seen_at          timestamptz not null,
    first_seen_manifest_id text not null references lineage.manifests (manifest_id),
    last_seen_at           timestamptz not null,
    last_seen_manifest_id  text not null references lineage.manifests (manifest_id),
    occurrence_count       integer not null default 1,
    state                  text not null default 'open' check (state in (
                               'open', 'released', 'accepted_loss', 'superseded')),
    released_by_rule_id    text references lineage.conformance_rules (rule_id),
    released_at            timestamptz,
    release_derivation_id  text references lineage.derivations (derivation_id),
    notes                  text
);

-- One entry per rejected row per rule, with a counter — not one entry per re-pull (§8.1).
create unique index quarantine_rows_fingerprint_idx
    on lineage.quarantine_rows (row_fingerprint, reason_code, rule_id) nulls not distinct;
create index quarantine_rows_summary_idx
    on lineage.quarantine_rows (source_id, stage, reason_code, state);

grant select, insert, update on lineage.quarantine_rows to glasswell_pipeline;
grant select on lineage.quarantine_rows to glasswell_api;
