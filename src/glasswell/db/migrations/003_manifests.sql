-- Raw-zone manifests (SB-07 §2.2). Manifest identity is the content hash; a fetch is an event.

create table lineage.manifests (
    manifest_id            text primary key,
    sha256                 text not null unique,
    bytes                  bigint not null,
    source_id              text not null references lineage.sources (source_id),
    source_key             text not null,
    acquisition_url        text not null,
    acquisition_method     text not null check (acquisition_method in (
                               'https_get', 'ftp_anon', 'mft_guid_resolve', 'click_wall_accept')),
    acquisition_params     jsonb not null default '{}'::jsonb,
    fetched_at             timestamptz not null,
    fetch_vintage          date not null,
    upstream_mtime         timestamptz,
    upstream_etag          text,
    media_type             text,
    decompressed_inventory jsonb not null default '[]'::jsonb,
    supersedes_manifest_id text references lineage.manifests (manifest_id),
    storage_uri            text not null default '',
    license_note           text,
    redistributable        boolean not null default false,
    fetch_derivation_id    text references lineage.derivations (derivation_id),
    staging_load_ref       text references lineage.derivations (derivation_id),
    integrity_verified_at  timestamptz
);

comment on column lineage.manifests.fetch_vintage is
    'Self-stamped knowledge-time label; no regulator dates its artifacts reliably (DIR-9).';

create index manifests_source_idx on lineage.manifests (source_id, source_key, fetched_at);
create unique index manifests_supersedes_idx
    on lineage.manifests (supersedes_manifest_id)
    where supersedes_manifest_id is not null;
create index manifests_inventory_idx
    on lineage.manifests using gin (decompressed_inventory jsonb_path_ops);

-- Latest non-superseded manifest per (source_id, source_key): what an ingest job compares against.
create view lineage.manifest_head as
select m.*
  from lineage.manifests m
 where not exists (
           select 1
             from lineage.manifests s
            where s.supersedes_manifest_id = m.manifest_id);

grant select, insert, update on lineage.manifests to glasswell_pipeline;
grant select on lineage.manifests, lineage.manifest_head to glasswell_api;
