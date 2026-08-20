-- Two pieces of database state that only ever existed by hand.
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
