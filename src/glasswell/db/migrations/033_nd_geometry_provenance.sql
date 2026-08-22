-- M1-3: coordinate-source provenance as a served wire field on the ND wells and laterals
-- tiles, and the row that classes it.
--
-- canonical.well_spatial.geom_type has said where every geometry came from since migration
-- 009; the survey-traces mart already serves it as geometry_provenance (030). What never
-- existed is the column on the wells and laterals tile marts, so the two layers whose
-- provenance differs most — a reported wellhead point, a filed centreline that is not a
-- survey — carried no machine-readable statement of it. Text end to end, so the N-2
-- wire-type hazard (015/026) does not arise.
--
-- Views are dropped and recreated rather than replaced: `create or replace view` may only
-- append columns at the end, and the published order follows glasswell.marts.tiles. Grants
-- are restated because the drop takes them with it (DR-05: martin reads these views and no
-- base relation).

alter table marts.nd_wells_tile add column geometry_provenance text;
alter table marts.nd_laterals_tile add column geometry_provenance text;

drop view marts.tile_nd_wells;

create view marts.tile_nd_wells as
select api10, operator_name, status_canonical, spud_year, well_type_reported,
       geometry_provenance, derivation_id, geom
  from marts.nd_wells_tile;

drop view marts.tile_nd_laterals;

create view marts.tile_nd_laterals as
select api10, linekey, operator_name, status_canonical, spud_year, lateral_length_ft,
       geometry_provenance, derivation_id, geom
  from marts.nd_laterals_tile;

grant select on marts.tile_nd_wells to martin, glasswell_api;
grant select on marts.tile_nd_laterals to martin, glasswell_api;

-- The classing rule, inserted here for an already-seeded database; a fresh one gets the
-- same content from glasswell.seed.conformance_nd. Which ND filing each geometry family's
-- coordinates come from is a cross-source mapping decision, so it is a row served at
-- /v1/conformance (R8), not a constant that exists only in web code.
insert into lineage.conformance_rules
    (rule_id, rule_family, source_id, stage, applies_to_fields, rule_kind, spec, rule,
     rationale, evidence_url, code_ref, effective_from)
select 'cr_nd_geometry_provenance_1', 'cr_nd_geometry_provenance', 'nd_gis_wells', 'conform',
       '{geom}', 'code_ref',
       jsonb_build_object(
           'module_function', 'glasswell.marts.nd_wells:_PROJECTIONS',
           'version', '1',
           'classification', 'geometry_provenance',
           'classes', jsonb_build_object(
               'surface', 'reported wellhead point from OGD_Wells.zip',
               'lateral', 'filed horizontal centreline from OGD_Horizontals_Line.zip —'
               ' not a directional survey trace',
               'survey_trace', 'plan-view path assembled from OGD_Directionals.zip'
               ' MD/INC/AZI/TVD stations'),
           'code_semantics', 'verbatim canonical geom_type values; served unchanged as'
           ' geometry_provenance on every ND tile layer, no per-class decode beyond this map',
           'tx_exclusion', 'TX RRC publishes GIS_LOCATION_SOURCE (data-sources-wellops.md'
           ' §6.2) but the field is RRC content and sits under the RF-1 licence question'
           ' (data-sources-infra.md §10); the TX half of M1-3 is not served until RF-1 is'
           ' answered',
           'contract_note', 'the nd_wells, nd_laterals and nd_survey_traces tiles each carry'
           ' geometry_provenance verbatim from canonical.well_spatial.geom_type; each layer'
           ' is homogeneous in it, so the layer toggles are the provenance filter and the'
           ' per-layer paints are the style channel (web/src/map/provenance.ts is the'
           ' consumer)'),
       'Serve canonical.well_spatial.geom_type verbatim as geometry_provenance on every ND'
       ' tile layer: surface, lateral or survey_trace.',
       'Each ND geometry family''s coordinates come from a distinct DMR filing: OGD_Wells'
       ' publishes the reported wellhead point, OGD_Horizontals_Line the filed centreline'
       ' (explicitly not a survey — its linekeys are LAT/STK/VERT segments), and'
       ' OGD_Directionals the survey stations a trace is assembled from. Mapping each'
       ' filing to one geom_type class at ingest is the provenance decision, and serving the'
       ' class verbatim gives the laterals row''s hand-written caveat ("not a directional'
       ' survey trace") a machine-readable backing. The classes are homogeneous within each'
       ' layer, so no within-layer filter is asserted: the layer toggle is the filter.'
       ' TX is excluded on licence, not on reach — see spec.tx_exclusion.',
       'https://gis.dmr.nd.gov/downloads/oilgas/shapefile/OGD_Wells.zip',
       'web/src/map/provenance.ts', date '2026-08-22'
 where exists (select 1 from lineage.sources where source_id = 'nd_gis_wells')
on conflict (rule_id) do nothing;
