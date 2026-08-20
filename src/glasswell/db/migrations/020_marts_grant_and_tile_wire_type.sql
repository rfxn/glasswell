-- Three pieces of database state that only ever existed by hand, or not at all.
--
-- The grant (DR-21). `marts.refresh_all` issues `create or replace function` and `create or
-- replace view` in schema `marts`, which needs `create` there; migration 009 grants `usage`
-- only. The deployed database reads `glasswell_pipeline=UC` because the privilege was applied
-- at the keyboard during P7, so the next rebuild on any database a migration built would have
-- failed on the first refresh. The view is granted to the API role for the same reason
-- migration 009's blanket `grant select on all tables` missed it: it did not exist yet.
--
-- The wire type (N-2). ST_AsMVT has no `numeric` encoding, so a numeric column leaves the
-- tile as a protobuf string and a MapLibre expression compares '9000' > '22727' — migration
-- 015's finding for lateral_length_ft, one layer over. `create or replace view` may not
-- change a column's type, so the type moves at the source column and the view is rebuilt
-- around it. All 10,571 rows on the deployed instance are integer-valued acreages
-- (max scale 0, 160..31000) and every one round-trips through double precision unchanged, so
-- this narrows no number anybody has.

grant create on schema marts to glasswell_pipeline;

drop view if exists marts.nd_spacing_units_tile;

alter table canonical.spacing_units
    alter column ds_size_acres type double precision;

create view marts.nd_spacing_units_tile as
select spacing_unit_id, label, formation_reported, ds_size_acres, derivation_id, geom
  from canonical.spacing_units;

grant select on marts.nd_spacing_units_tile to glasswell_api;

comment on column canonical.spacing_units.ds_size_acres is
    'Double precision, not numeric: this column is published as a tile attribute and
     ST_AsMVT has no numeric encoding (N-2, the class migration 015 opened).';

-- The tile server's own role (DR-05). `pg_hba` maps a socket connection to the role named for
-- the OS user (`local all all peer`), `martin.service` runs `User=martin`, and no role `martin`
-- existed — which is the whole of why infra/martin/config.yaml had never been adopted. The
-- name is not a choice: peer auth requires it to equal the OS user.
--
-- It gets the least a tile server can work with, and the column list is the point. martin is
-- given select on exactly the columns each layer publishes, so the privilege — not a
-- declaration in a config file — is what keeps everything else off the wire: `staging` (R:
-- staging never serves, blueprint 3.0.1), `canonical`, `lineage`, and
-- `lateral_length_ft_exact`, which is `numeric` and would ride an auto-published tile as a
-- 19-digit string. The spacing-unit view reads canonical with its owner's rights, so martin
-- needs no grant there at all.
do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'martin') then
        create role martin login;
    end if;
end
$$;

grant usage on schema marts to martin;

grant select (api10, linekey, operator_name, status_canonical, spud_year, lateral_length_ft,
              derivation_id, geom)
    on marts.nd_laterals_tile to martin;

grant select (api10, operator_name, status_canonical, spud_year, derivation_id, geom)
    on marts.nd_wells_tile to martin;

grant select (spacing_unit_id, label, formation_reported, ds_size_acres, derivation_id, geom)
    on marts.nd_spacing_units_tile to martin;
