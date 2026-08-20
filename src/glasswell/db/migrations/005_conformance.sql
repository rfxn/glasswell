-- Conformance registry and its lookup citizens (SB-07 §6.2, §6.4). Rows are append-only.

create table lineage.conformance_rules (
    rule_id             text primary key,
    rule_family         text not null,
    supersedes_rule_id  text references lineage.conformance_rules (rule_id),
    source_id           text not null references lineage.sources (source_id),
    stage               text not null check (stage in ('parse', 'validate', 'conform', 'join')),
    applies_to_fields   text[] not null default '{}',
    rule_kind           text not null check (rule_kind in (
                            'unit_conform', 'vocab_map', 'alias_join', 'datum_transform',
                            'key_composite', 'parse_directive', 'validity_filter', 'code_ref')),
    spec                jsonb not null default '{}'::jsonb,
    rule                text not null,
    rationale           text not null,
    evidence_url        text,
    evidence_sha256     text,
    effective_from      date not null,
    effective_to        date,
    code_ref            text,
    code_ref_sha256     text,
    created_by_event_id text
);

comment on column lineage.conformance_rules.stage is
    'Extends SB-07 §6.2: apply_rules() filters on a stage, so the row must carry one.';

create index conformance_rules_source_idx
    on lineage.conformance_rules (source_id, stage, effective_from);
create index conformance_rules_family_idx on lineage.conformance_rules (rule_family);
create index conformance_rules_fields_idx on lineage.conformance_rules using gin (applies_to_fields);

create trigger conformance_rules_append_only
    before update or delete on lineage.conformance_rules
    for each row execute function lineage.reject_mutation();

create table lineage.crs_registry (
    basin          text primary key,
    compute_epsg   integer not null,
    storage_epsg   integer not null default 4326,
    effective_from date not null,
    note           text
);

create table lineage.formation_aliases (
    formation_raw  text not null,
    formation      text not null,
    confidence     numeric(4, 3) not null,
    effective_from date not null,
    source_id      text references lineage.sources (source_id),
    primary key (formation_raw, effective_from)
);

-- Closes A-12: /operators/league and DIR-5's residual metric are not computable without it.
create table lineage.operator_aliases (
    operator_raw   text not null,
    operator       text not null,
    confidence     numeric(4, 3) not null,
    effective_from date not null,
    source_id      text references lineage.sources (source_id),
    primary key (operator_raw, effective_from)
);

grant select, insert on lineage.conformance_rules to glasswell_pipeline;
grant select, insert on lineage.crs_registry, lineage.formation_aliases,
    lineage.operator_aliases to glasswell_pipeline;
grant select on lineage.conformance_rules, lineage.crs_registry, lineage.formation_aliases,
    lineage.operator_aliases to glasswell_api;
revoke update, delete on lineage.conformance_rules from glasswell_pipeline, glasswell_api;
