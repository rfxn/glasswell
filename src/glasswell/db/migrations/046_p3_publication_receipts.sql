-- Immutable acceptance receipts for the sealed P3 repaired-context publication gate.

create extension if not exists pgcrypto;

create table lineage.p3_publication_receipts (
    publication_id              text primary key check (
                                    publication_id ~ '^p3pub_[0-9a-f]{32}$'),
    receipt_schema              text not null check (
                                    receipt_schema = 'p3-publication-receipt/1'),
    document_sha256             text not null unique check (
                                    document_sha256 ~ '^[0-9a-f]{64}$'),
    document                    jsonb not null,
    document_canonical          text not null,
    basin                       text not null,
    eval_vintage                date not null,
    vintage_basis               text not null,
    feature_version             text not null check (
                                    feature_version ~ '^fv[0-9]+\.[0-9]+$'),
    model_dataset_version       text not null check (
                                    model_dataset_version ~ '^mdv[0-9]+\.[0-9]+$'),
    control_version             text not null check (
                                    control_version ~ '^tcv[0-9]+\.[0-9]+$'),
    split_set_id                text not null,
    code_version                text not null,
    environment_id              text not null references lineage.environments (env_id),
    lockfile_sha256             text not null check (lockfile_sha256 ~ '^[0-9a-f]{64}$'),
    feature_derivation_id       text not null references lineage.derivations (derivation_id),
    model_dataset_derivation_id text not null references lineage.derivations (derivation_id),
    control_derivation_id       text not null references lineage.derivations (derivation_id),
    created_at                  timestamptz not null default now(),
    unique (
        basin, eval_vintage, vintage_basis, feature_version, model_dataset_version,
        control_version, split_set_id
    ),
    check (document_canonical::jsonb = document),
    check (encode(digest(convert_to(document_canonical, 'UTF8'), 'sha256'), 'hex')
           = document_sha256),
    check (publication_id = 'p3pub_' || left(document_sha256, 32)),
    check (document ->> 'receipt_schema' = receipt_schema),
    check (document ->> 'status' = 'published'),
    check (document ->> 'basin' = basin),
    check (document ->> 'eval_vintage' = eval_vintage::text),
    check (document ->> 'vintage_basis' = vintage_basis),
    check (document ->> 'code_version' = code_version),
    check (document ->> 'environment_id' = environment_id),
    check (document #>> '{versions,feature}' = feature_version),
    check (document #>> '{versions,model_dataset}' = model_dataset_version),
    check (document #>> '{versions,type_curve}' = control_version),
    check (document #>> '{baseline,split_set_id}' = split_set_id),
    check (document #>> '{environment,lockfile_sha256}' = lockfile_sha256),
    check (document #>> '{derivations,feature}' = feature_derivation_id),
    check (document #>> '{derivations,model_dataset}' = model_dataset_derivation_id),
    check (document #>> '{derivations,type_curve}' = control_derivation_id)
);

comment on table lineage.p3_publication_receipts is
    'Content-addressed proof that both P3 build runs were byte-identical and all sealed coverage,'
    ' split, version and residual gates passed. The canonical JSON document is immutable.';

create trigger p3_publication_receipts_append_only
    before update or delete on lineage.p3_publication_receipts
    for each row execute function lineage.reject_mutation();

grant select, insert on lineage.p3_publication_receipts to glasswell_pipeline;
grant select on lineage.p3_publication_receipts to glasswell_api;
revoke update, delete, truncate on lineage.p3_publication_receipts
    from glasswell_pipeline, glasswell_api;
