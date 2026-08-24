-- P3 foundation: auditable feature semantics are data, never mutable code-only declarations.

create schema if not exists features;

grant usage on schema features to glasswell_pipeline, glasswell_api;

create table features.feature_specs (
    feature_id                  text not null,
    family                      text not null check (family in (
                                    'design', 'location', 'geology', 'spacing',
                                    'operator', 'vintage')),
    dtype                       text not null check (btrim(dtype) != ''),
    unit                        text not null check (btrim(unit) != ''),
    knowable_at_rule            text not null check (knowable_at_rule in (
                                    'permit_date', 'spud_date', 'completion_date',
                                    'first_production_month', 'anchor')),
    publication_lag_days_p50    integer not null check (publication_lag_days_p50 >= 0),
    transform_id                text not null check (btrim(transform_id) != ''),
    params                      jsonb not null default '{}'::jsonb,
    source_refs                 text[] not null check (cardinality(source_refs) > 0),
    missing_policy              text not null check (missing_policy in (
                                    'native_nan', 'indicator', 'quarantine')),
    member_of                   text[] not null check (cardinality(member_of) > 0),
    introduced_in_fv            text not null check (
                                    introduced_in_fv ~ '^fv(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'),
    retired_in_fv               text check (
                                    retired_in_fv is null or
                                    retired_in_fv ~ '^fv(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'),
    created_at                  timestamptz not null default now(),
    primary key (feature_id, introduced_in_fv),
    check (feature_id ~ '^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$')
);

comment on table features.feature_specs is
    'Append-only feature semantics from SB-02 §1.5. A semantic change appends a new lifecycle
     row and changes feature_version; readers select the latest introduced row at their feature
     version. A row introduced and retired in the same version is a terminal retirement row,
     preserving the prior specification without leaving it active.';

create trigger feature_specs_append_only
    before update or delete on features.feature_specs
    for each row execute function lineage.reject_mutation();

grant select, insert on features.feature_specs to glasswell_pipeline;
grant select on features.feature_specs to glasswell_api;
revoke update, delete on features.feature_specs from glasswell_pipeline, glasswell_api;
