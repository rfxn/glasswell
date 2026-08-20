-- Derivation graph (SB-07 §1.4) plus the pinned-environment and recipe tables it stamps.

create table lineage.sources (
    source_id      text primary key,
    name           text not null,
    jurisdiction   text,
    license_note   text,
    redistributable boolean not null default false,
    created_at     timestamptz not null default now()
);

create table lineage.environments (
    env_id          text primary key,
    image_digest    text,
    lockfile_sha256 text,
    python_version  text,
    threads         integer,
    cpu_model       text,
    tz              text not null default 'UTC',
    locale          text not null default 'C',
    created_at      timestamptz not null default now()
);

create table lineage.recipes (
    recipe_id  text primary key,
    operation  text not null,
    document   jsonb not null,
    created_at timestamptz not null default now()
);

create table lineage.derivations (
    derivation_id         text primary key,
    operation             text not null check (operation in (
                              'raw.fetch', 'stage.parse', 'canonical.promote', 'features.build',
                              'model.train', 'model.calibrate', 'forecast.batch',
                              'forecast.scenario', 'econ.value', 'econ.sensitivity', 'alloc.apply',
                              'typecurve.build', 'analog.index', 'analog.query', 'mart.refresh',
                              'tiles.build', 'ledger.grade', 'inventory.run')),
    output_store          text not null check (output_store in (
                              'parquet', 'postgres', 'postgis', 'duckdb_view', 'file', 'response')),
    output_dataset        text not null,
    output_partition      jsonb not null default '{}'::jsonb,
    output_locator        text not null default '',
    output_sha256         text,
    output_rows           bigint,
    output_schema_version text not null default '',
    params                jsonb not null default '{}'::jsonb,
    params_hash           text not null,
    code_version          text not null,
    code_dirty            boolean not null default false,
    env_id                text not null references lineage.environments (env_id),
    model_id              text,
    recipe_id             text references lineage.recipes (recipe_id),
    created_vintage       date,
    created_at            timestamptz not null,
    duration_ms           integer not null default 0,
    correlation_id        text not null,
    status                text not null check (status in ('ok', 'failed')),
    determinism_class     text not null check (determinism_class in ('D1', 'D2', 'D3')),
    ttl_class             text not null check (ttl_class in ('permanent', 'ephemeral'))
);

comment on column lineage.derivations.created_vintage is
    'Knowledge time: max source vintage over all inputs, not wall clock.';

create index derivations_dataset_idx on lineage.derivations (output_dataset);
create index derivations_partition_idx
    on lineage.derivations using gin (output_partition jsonb_path_ops);
create index derivations_correlation_idx on lineage.derivations (correlation_id);
create index derivations_created_idx on lineage.derivations (created_at, derivation_id);

create table lineage.derivation_inputs (
    derivation_id  text not null references lineage.derivations (derivation_id) on delete restrict,
    ord            integer not null,
    kind           text not null check (kind in (
                       'derivation', 'manifest', 'rule', 'model', 'external')),
    ref_id         text not null,
    selector       text,
    as_of_vintage  date,
    role           text not null default 'primary' check (role in (
                       'primary', 'crosswalk', 'validator', 'calibration', 'grid')),
    primary key (derivation_id, ord)
);

create index derivation_inputs_ref_idx on lineage.derivation_inputs (ref_id);

-- Separate from derivation_inputs so "which derivations cite rule X" is one index scan (§1.4).
create table lineage.derivation_rules (
    derivation_id text not null references lineage.derivations (derivation_id) on delete restrict,
    rule_id       text not null,
    applied_rows  bigint,
    primary key (derivation_id, rule_id)
);

create index derivation_rules_rule_idx on lineage.derivation_rules (rule_id);

grant select, insert, update on lineage.derivations to glasswell_pipeline;
grant select, insert, delete on lineage.derivation_inputs to glasswell_pipeline;
grant select, insert, delete on lineage.derivation_rules to glasswell_pipeline;
grant select, insert, update, delete on lineage.sources to glasswell_pipeline;
grant select, insert on lineage.environments, lineage.recipes to glasswell_pipeline;

grant select on lineage.derivations, lineage.derivation_inputs, lineage.derivation_rules,
    lineage.sources, lineage.environments, lineage.recipes to glasswell_api;
grant insert on lineage.derivations, lineage.derivation_inputs to glasswell_api;
