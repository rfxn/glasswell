-- `nd_gis --restage` (migration 017's companion) re-parses a layer from the bytes already in
-- the raw zone, which means clearing the manifest's staged rows first. Migration 009 granted
-- the pipeline role select and insert on staging only, so the restage failed on the deployed
-- database with `permission denied for table nd_gis_laterals` while passing in the test tier,
-- whose connection owns every table. Staging is the parser's own scratch layer — canonical
-- stays append-only, and no grant here touches it.

grant delete on all tables in schema staging to glasswell_pipeline;

alter default privileges in schema staging grant delete on tables to glasswell_pipeline;
