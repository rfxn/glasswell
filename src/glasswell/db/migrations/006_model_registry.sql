-- Model identity and lineage (SB-07 §7). Training, tuning and metrics belong to SB-02.

create table lineage.models (
    model_id                text primary key,
    artifact_sha256         text,
    artifact_uri            text,
    algo                    text not null,
    algo_version            text not null,
    target                  text not null check (target in ('oil', 'gas', 'water', 'allocation')),
    basin                   text,
    feature_version         text,
    feature_set_hash        text,
    training_window         jsonb not null default '{}'::jsonb,
    training_data_vintage   jsonb not null default '{}'::jsonb,
    holdout_def             jsonb not null default '{}'::jsonb,
    hyperparams             jsonb not null default '{}'::jsonb,
    seeds                   jsonb not null default '{}'::jsonb,
    env_id                  text references lineage.environments (env_id),
    determinism_class       text not null check (determinism_class in ('D1', 'D2', 'D3')),
    probe_set_ref           text,
    probe_tolerance         numeric(20, 12),
    calibration_report_ref  text references lineage.derivations (derivation_id),
    conformal_alpha         numeric(5, 4),
    coverage_observed       numeric(5, 4),
    training_derivation_id  text references lineage.derivations (derivation_id),
    promotion_status        text not null default 'candidate' check (promotion_status in (
                                'candidate', 'shadow', 'promoted', 'retired')),
    promoted_at             timestamptz,
    retired_at              timestamptz,
    supersedes_model_id     text references lineage.models (model_id),
    error_bounds            jsonb not null default '{}'::jsonb,
    created_at              timestamptz not null default now()
);

alter table lineage.derivations
    add constraint derivations_model_fk foreign key (model_id) references lineage.models (model_id);

-- A grade is an event, not a mutable score: re-grading appends (§3.5).
create table lineage.forecast_grades (
    grade_id                text primary key,
    forecast_derivation_id  text not null references lineage.derivations (derivation_id),
    model_id                text not null references lineage.models (model_id),
    trained_on_vintage      jsonb not null default '{}'::jsonb,
    graded_against_vintage  date not null,
    graded_at               timestamptz not null,
    grade_derivation_id     text not null references lineage.derivations (derivation_id),
    metrics                 jsonb not null default '{}'::jsonb,
    unique (forecast_derivation_id, graded_against_vintage)
);

create index models_status_idx on lineage.models (target, basin, promotion_status);
create index forecast_grades_model_idx on lineage.forecast_grades (model_id, graded_at);

grant select, insert, update on lineage.models to glasswell_pipeline;
grant select, insert on lineage.forecast_grades to glasswell_pipeline;
grant select on lineage.models, lineage.forecast_grades to glasswell_api;
