-- Schemas, the two runtime roles, and PostGIS.
-- SB-07 §11: the API structurally cannot rewrite pipeline lineage.

create extension if not exists postgis;

create schema if not exists lineage;
create schema if not exists staging;
create schema if not exists canonical;
create schema if not exists marts;

do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'glasswell_pipeline') then
        create role glasswell_pipeline nologin;
    end if;
    if not exists (select 1 from pg_roles where rolname = 'glasswell_api') then
        create role glasswell_api nologin;
    end if;
end
$$;

grant usage on schema lineage, staging, canonical, marts
    to glasswell_pipeline, glasswell_api;
