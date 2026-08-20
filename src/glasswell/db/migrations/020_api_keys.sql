-- App API keys (SB-06 §8.3), scoped per S-G. sha256 is the only representation at rest.
-- Number is provisional: CADENCE §2.2 reserves 025-026 for track A2, but the runner enforces
-- contiguity, so the branch carries 020 and the integrator renames it after A1b's block.
-- Never applied to a durable database, which is what makes that rename a file rename.

create table lineage.api_keys (
    key_id       text primary key,
    sha256       text not null unique,
    label        text not null,
    scope        text not null check (scope in ('owner', 'agent', 'guest')),
    created_at   timestamptz not null,
    created_by   text not null,
    expires_at   timestamptz,
    revoked_at   timestamptz,
    revoked_by   text,
    last_used_at timestamptz,
    check (revoked_at is null or revoked_by is not null)
);

comment on table lineage.api_keys is
    'Cleartext is shown once at issuance and never stored. A lost key is rotated, not recovered.';
comment on column lineage.api_keys.scope is
    'S-G: for a service principal the effective scope comes from the key, not the Access class.';

-- Rotation reissues under the same label, so uniqueness holds only over live keys.
create unique index api_keys_live_label_idx
    on lineage.api_keys (label)
    where revoked_at is null;
create index api_keys_scope_idx on lineage.api_keys (scope, created_at desc);

grant select, insert, update on lineage.api_keys to glasswell_api;
grant select on lineage.api_keys to glasswell_pipeline;
