-- The Montana tile marts: a point layer and a path layer, plus the one conformance rule that
-- serving Montana forced. Migration 049 makes publication evidence a precondition for a rule
-- insert, so it is registered here before glasswell.seed.conformance_mt seeds the body.
--
-- REPOINT CHECKLIST (integrator, at the merge train):
--   1. evidence_tag -> the tag that first carries cr_mt_paths_length_scope_1
--   2. evidence_commit -> the main head this branch was written against
--   3. published_vintage -> confirm it is the date that tag is cut, or correct it
-- The rule id itself is immutable and must not change during the repoint. The header names the
-- columns rather than their values: a quoted placeholder above the insert re-arms the release
-- guard through prose, so repointing could never clear the refusal.
insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
values ('cr_mt_paths_length_scope_1', date '2026-08-31', 'v0.70',
        '258d88dce644fbc842a88be66a3050f717fb70d8')
on conflict (rule_id) do nothing;

--
-- The path layer carries geometry_class and vertex_count as columns rather than as a caveat in
-- a doc, because cr_mt_paths_geometry_class_1 requires the map-stick distinction to be stated
-- wherever the geometry is served. It carries no length: lengths.resolve_length_method is keyed
-- by basin, cr_mt_basin_scope_1 leaves every Montana well untagged, and a length measured under
-- another basin's compute CRS would be a naked number wearing a borrowed rule.

create table marts.mt_wells_tile (
    api10              text primary key,
    operator_name      text,
    status_canonical   text,
    status_reported    text,
    well_type_reported text,
    completion_year    integer,
    geom               geometry(Point, 4326) not null,
    derivation_id      text not null
);

create index mt_wells_tile_geom_idx on marts.mt_wells_tile using gist (geom);

comment on column marts.mt_wells_tile.completion_year is
    'Montana publishes a completion date and no spud date, so this is the year of Completed as'
    ' MBOGC filed it. It is not a spud year and the two are never mixed in one column.';
comment on column marts.mt_wells_tile.status_reported is
    'The MBOGC Status string beside the class it mapped to. Unlike New Mexico, Montana has a'
    ' codebook: cr_mt_gis_status_vocab_1 maps thirteen of nineteen values and quarantines the'
    ' other six as unknown_status rather than defaulting them to active.';

create table marts.mt_paths_tile (
    api10            text not null,
    geom_key         text not null,
    operator_name    text,
    status_canonical text,
    geometry_class   text not null,
    vertex_count     integer not null,
    geom             geometry(LineString, 4326) not null,
    derivation_id    text not null,
    primary key (api10, geom_key)
);

create index mt_paths_tile_geom_idx on marts.mt_paths_tile using gist (geom);

comment on table marts.mt_paths_tile is
    'Cartographic centrelines, not directional surveys (cr_mt_paths_geometry_class_1). Keyed on'
    ' the API-10 and WellSub pair because 875 wells carry more than one path'
    ' (cr_mt_paths_subkey_1), and covering 2,836 of 20,021 producing wells'
    ' (cr_mt_paths_coverage_1) — absence here is the normal case, not a gap.';
comment on column marts.mt_paths_tile.geometry_class is
    'Served on every feature so a client reads the class off the tile rather than off a doc it'
    ' may not have. map_stick, never survey_trace.';
comment on column marts.mt_paths_tile.vertex_count is
    'ST_NPoints of the served line. A two-vertex path is a straight line between two filed'
    ' points, and the count is what lets a reader see that without measuring it.';

create view marts.tile_mt_wells as
select api10, operator_name, status_canonical, status_reported, well_type_reported,
       completion_year, derivation_id, geom
  from marts.mt_wells_tile;

create view marts.tile_mt_paths as
select api10, geom_key, operator_name, status_canonical, geometry_class, vertex_count,
       derivation_id, geom
  from marts.mt_paths_tile;

grant select on marts.mt_wells_tile, marts.mt_paths_tile to glasswell_api;
grant select on marts.tile_mt_wells, marts.tile_mt_paths to martin, glasswell_api;
grant select, insert, delete, truncate on marts.mt_wells_tile, marts.mt_paths_tile
    to glasswell_pipeline;
