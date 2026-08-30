-- The New Mexico tile mart: a point layer and nothing else. There is no nm_laterals table
-- because there is no New Mexico lateral — cr_nm_wellhistory_geometry_scope_1 is the row that
-- says so, measured in both in-scope sources.

create table marts.nm_wells_tile (
    api10              text primary key,
    operator_name      text,
    status_canonical   text,
    status_reported    text,
    well_type_reported text,
    county_code        text,
    spud_year          integer,
    geom               geometry(Point, 4326) not null,
    derivation_id      text not null
);

create index nm_wells_tile_geom_idx on marts.nm_wells_tile using gist (geom);

comment on column marts.nm_wells_tile.status_reported is
    'The OCD status letter, carried because status_canonical is null for every New Mexico well:'
    ' cr_nm_wellhistory_status_vocab_1 records that no codebook maps these letters, so the map'
    ' shows the well unstyled rather than inventing a class for it.';

create view marts.tile_nm_wells as
select api10, operator_name, status_canonical, status_reported, well_type_reported, county_code,
       spud_year, derivation_id, geom
  from marts.nm_wells_tile;

grant select on marts.nm_wells_tile to glasswell_api;
grant select on marts.tile_nm_wells to martin, glasswell_api;
grant select, insert, delete, truncate on marts.nm_wells_tile to glasswell_pipeline;

-- The OCD public wells layer refreshes daily upstream while the FTP archive is frozen at
-- 2026-08-20. The cadence is a recommendation with an owner decision behind it, so it is
-- registered as owner-triggered like its nine FTP siblings until that decision is taken.
insert into lineage.source_poll_policies
    (source_id, cadence, expected_poll_interval, attempt_timeout)
values ('nm_ocd_wells_gis', 'Owner-triggered; no recurring timer', null, interval '6 hours')
on conflict (source_id) do nothing;
