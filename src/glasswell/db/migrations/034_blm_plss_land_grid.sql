-- M1-4: the ND PLSS land grid — staging, canonical.land_units, and the tile mart.
--
-- Why BLM and not the DMR zips already in the register. SB-01 §1.1 carries
-- nd_gis_sections/_townships as DMR shapefiles "static since 2020"; the BLM national CadNSDI
-- NAD83 service is the live refresh path (data-sources-land.md A1), publishes both first
-- division and township, and is the publisher whose counts the divergence measurement below
-- is anchored to. The publisher choice is a conformance row, not a code path.
--
-- Why one canonical table for two unit types. M2-3 groups thematics onto "the land grid",
-- and a rollup that joins townships and sections from two tables re-implements the grid's
-- own hierarchy. unit_type is the discriminator; a section's parent township is its plssid.
--
-- Why two published tile layers over one mart. A z8 tile over the basin holds hundreds of
-- townships but thousands of sections; splitting the publication lets the section source
-- start at a deeper zoom so its tiles are never fetched where nothing draws them (the same
-- source-floor reasoning as web/src/map/style.ts lowestDrawnZoom). EVA publishes its land
-- grid split the same way (peer-map-novi-eva.md §B3).

-- SB-01 §1.2.1 / SB-07 H11: the fifth acquisition method. The enum lives in this check and
-- in glasswell.lineage.models.AcquisitionMethod, updated together.
alter table lineage.manifests drop constraint manifests_acquisition_method_check;

alter table lineage.manifests add constraint manifests_acquisition_method_check
    check (acquisition_method in (
        'https_get', 'ftp_anon', 'mft_guid_resolve', 'click_wall_accept',
        'arcgis_rest_paginate'));

create table staging.blm_plss_townships (
    manifest_id        text not null references lineage.manifests (manifest_id),
    source_row_ordinal integer not null,
    ingested_at        timestamptz not null default now(),
    plssid             text,
    twnshpno           text,
    twnshpdir          text,
    rangeno            text,
    rangedir           text,
    twnshplab          text,
    prinmer            text,
    survtyp            text,
    geom               geometry(MultiPolygon, 4326),
    primary key (manifest_id, source_row_ordinal)
);

comment on table staging.blm_plss_townships is
    'Every column text: staging is source-faithful and holds no opinions (blueprint §3.4.2).';

create table staging.blm_plss_sections (
    manifest_id        text not null references lineage.manifests (manifest_id),
    source_row_ordinal integer not null,
    ingested_at        timestamptz not null default now(),
    plssid             text,
    frstdivid          text,
    frstdivno          text,
    frstdivlab         text,
    frstdivtyp         text,
    survtyp            text,
    geom               geometry(MultiPolygon, 4326),
    primary key (manifest_id, source_row_ordinal)
);

comment on table staging.blm_plss_sections is
    'CadNSDI first division, ND slice. plssid is the parent township''s id, verbatim.';

create table canonical.land_units (
    land_unit_id       text primary key,
    unit_type          text not null check (unit_type in ('township', 'section')),
    state              text not null,
    plssid             text not null,
    frstdivid          text,
    label              text not null,
    township_no        text,
    township_dir       text,
    range_no           text,
    range_dir          text,
    section_no         text,
    principal_meridian text,
    survey_type        text,
    geom               geometry(MultiPolygon, 4326) not null,
    source_datum       text not null,
    transform_rule_id  text,
    source_manifest_id text not null references lineage.manifests (manifest_id),
    derivation_id      text not null references lineage.derivations (derivation_id),
    created_at         timestamptz not null default now(),
    check (unit_type != 'section' or frstdivid is not null)
);

comment on table canonical.land_units is
    'One PLSS unit at one grain. The identity is the publisher''s own id — plssid for a
     township, frstdivid for a section — under cr_blm_plss_publisher_1, which is the row that
     says whose grid this is and by how much the other publishers of it disagree.';

comment on column canonical.land_units.plssid is
    'The township id. On a section row it is the parent township, so the hierarchy is a join
     on this column and never a substring parse.';

create trigger land_units_append_only
    before update or delete on canonical.land_units
    for each row execute function lineage.reject_mutation();

create index land_units_geom_idx on canonical.land_units using gist (geom);

create index land_units_type_plssid_idx on canonical.land_units (unit_type, plssid);

create table marts.land_units_tile (
    land_unit_id  text primary key,
    unit_type     text not null,
    plssid        text not null,
    label         text not null,
    derivation_id text not null,
    geom          geometry(MultiPolygon, 4326) not null
);

comment on table marts.land_units_tile is
    'The land grid, one row per unit. Rebuilt, never appended (§3.0.1).';

create index land_units_tile_geom_idx on marts.land_units_tile using gist (geom);

create index land_units_tile_type_idx on marts.land_units_tile (unit_type);

create view marts.tile_land_townships as
select land_unit_id, unit_type, plssid, label, derivation_id, geom
  from marts.land_units_tile
 where unit_type = 'township';

create view marts.tile_land_sections as
select land_unit_id, unit_type, plssid, label, derivation_id, geom
  from marts.land_units_tile
 where unit_type = 'section';

comment on view marts.tile_land_townships is
    'What the tile server may see. The column list is the publication boundary: martin holds
     select on this view and on no base relation (DR-05).';

comment on view marts.tile_land_sections is
    'What the tile server may see. The column list is the publication boundary: martin holds
     select on this view and on no base relation (DR-05).';

grant select, insert on staging.blm_plss_townships to glasswell_pipeline;
grant delete on staging.blm_plss_townships to glasswell_pipeline;
grant select, insert on staging.blm_plss_sections to glasswell_pipeline;
grant delete on staging.blm_plss_sections to glasswell_pipeline;
grant select, insert on canonical.land_units to glasswell_pipeline;
grant select on canonical.land_units to glasswell_api;
revoke update, delete on canonical.land_units from glasswell_pipeline, glasswell_api;
grant select on marts.land_units_tile to glasswell_api;
grant select, insert, delete, truncate on marts.land_units_tile to glasswell_pipeline;
grant select on marts.tile_land_townships to martin, glasswell_api;
grant select on marts.tile_land_sections to martin, glasswell_api;

-- The three classing decisions, inserted here for an already-seeded database; a fresh one
-- gets the same content from glasswell.seed.conformance_land. The guards skip cleanly where
-- the sources are not registered yet — deploy runs migrations before seed_all, so on the
-- first deployed pass these land via the seeder.
insert into lineage.conformance_rules
    (rule_id, rule_family, source_id, stage, applies_to_fields, rule_kind, spec, rule,
     rationale, evidence_url, code_ref, effective_from)
select 'cr_blm_plss_publisher_1', 'cr_blm_plss_publisher', 'blm_plss_sections', 'conform',
       '{geom,plssid,frstdivid}', 'code_ref',
       jsonb_build_object(
           'module_function', 'glasswell.ingest.blm_plss:LAYERS',
           'version', '1',
           'publisher', 'BLM_Natl_PLSS_CadNSDI_NAD83',
           'rejected_publishers',
           jsonb_build_array('BLM_MT_ND_SD_CadNSDI (regional)', 'NM OCD OCD_PLSS (mirror)'),
           'divergence_measured', jsonb_build_object(
               'nd_townships', jsonb_build_object('national', 2067, 'regional', 2067),
               'nd_first_division', jsonb_build_object('national', 71486, 'regional', 71486),
               'nd_second_division', jsonb_build_object('national', 1131664,
                                                        'regional', 1131639),
               'nm_townships', jsonb_build_object('national', 3299, 'mirror', 3283),
               'nm_first_division', jsonb_build_object('national', 110237, 'mirror', 109995)),
           'contract_note', 'canonical.land_units and both land tile layers carry this'
           ' publisher''s own unit ids verbatim (plssid, frstdivid); the ingest module is the'
           ' executor, and a different publisher is a superseding row, not a code change'),
       'Serve the PLSS grid from the BLM national CadNSDI NAD83 service; the regional and'
       ' mirror publishers of the nominally identical grid are cross-checks, not sources.',
       'Three publishers of the same BLM CadNSDI grid disagree, measured 2026-08-21'
       ' (data-sources-land.md §2): ND second division differs by 25 features between the'
       ' national and regional services, and NM diverges by 16 townships and 242 first-division'
       ' features against the OCD mirror. ND townships and first division agree to the feature,'
       ' so the grain this repository ingests is publisher-stable today — but which service is'
       ' authoritative is still a choice three regulators would answer differently, so it is'
       ' this row. The NAD83 sibling is taken over the web-mercator default because storage'
       ' takes a datum, not a projection.',
       'https://gis.blm.gov/arcgis/rest/services/Cadastral/BLM_Natl_PLSS_CadNSDI_NAD83/MapServer',
       'src/glasswell/ingest/blm_plss.py', date '2026-08-22'
 where exists (select 1 from lineage.sources where source_id = 'blm_plss_sections')
on conflict (rule_id) do nothing;

insert into lineage.conformance_rules
    (rule_id, rule_family, source_id, stage, applies_to_fields, rule_kind, spec, rule,
     rationale, evidence_url, effective_from)
select 'cr_blm_plss_datum_1', 'cr_blm_plss_datum', 'blm_plss_sections', 'conform',
       '{geom}', 'datum_transform',
       jsonb_build_object(
           'source_epsg', 4269,
           'target_epsg', 4326,
           'detect', jsonb_build_object('service_sr_wkid', 4269)),
       'Transform NAD83 land-grid polygons to EPSG:4326 before they reach storage.',
       'The service''s own spatialReference is wkid 4269 (NAD83), read from the layer JSON on'
       ' every fetch and recorded on the manifest. Storage is always 4326 and the transform is'
       ' recorded as a derivation even though the shift is sub-metre: no coordinate reaches'
       ' storage untransformed and unrecorded (same rule as cr_nd_datum_1).',
       'https://gis.blm.gov/arcgis/rest/services/Cadastral/BLM_Natl_PLSS_CadNSDI_NAD83/MapServer',
       date '2026-08-22'
 where exists (select 1 from lineage.sources where source_id = 'blm_plss_sections')
on conflict (rule_id) do nothing;

insert into lineage.conformance_rules
    (rule_id, rule_family, source_id, stage, applies_to_fields, rule_kind, spec, rule,
     rationale, evidence_url, effective_from)
select 'cr_blm_plss_scope_1', 'cr_blm_plss_scope', 'blm_plss_sections', 'parse',
       '{plssid}', 'parse_directive',
       jsonb_build_object(
           'where', 'PLSSID LIKE ''ND%''',
           'layers', jsonb_build_array('townships', 'sections'),
           'state', 'ND'),
       'Harvest the national grid''s North Dakota slice only: PLSSID LIKE ''ND%'' on both the'
       ' township and section layers.',
       'PLSSID is state-prefixed (sample ND051640N1030W0), verified by count queries that'
       ' reconcile with the published ND totals (2,067 townships, 71,486 sections). The slice'
       ' is a scope decision the fetch applies server-side, so it is a row rather than a'
       ' where-clause only the code can see; widening to NM is a new rule, not an edit.',
       'https://gis.blm.gov/arcgis/rest/services/Cadastral/BLM_Natl_PLSS_CadNSDI_NAD83/MapServer/2',
       date '2026-08-22'
 where exists (select 1 from lineage.sources where source_id = 'blm_plss_sections')
on conflict (rule_id) do nothing;
