-- M1-7: the disposal layer's wire attribute, and the row that classes it.
--
-- well_type has been canonical since migration 009 (canonical.wells.well_type_reported) and
-- ingested since nd_gis first ran; what never existed is the column on the wells tile mart
-- and on the published view, so no tile ever carried it. Text end to end — no numeric, so
-- the N-2 wire-type hazard (migrations 015/026) does not arise.
--
-- The view is dropped and recreated rather than replaced: `create or replace view` may only
-- append columns at the end, and the published order follows glasswell.marts.tiles. Grants
-- are restated because the drop takes them with it (DR-05: martin reads this view and no
-- base relation).

alter table marts.nd_wells_tile add column well_type_reported text;

drop view marts.tile_nd_wells;

create view marts.tile_nd_wells as
select api10, operator_name, status_canonical, spud_year, well_type_reported, derivation_id,
       geom
  from marts.nd_wells_tile;

grant select on marts.tile_nd_wells to martin, glasswell_api;

-- The classing rule, inserted here for an already-seeded database; a fresh one gets the same
-- content from glasswell.seed.conformance_nd. Which well_type codes the disposal layer draws
-- is a vocabulary decision, so it is a row served at /v1/conformance (R8), not a constant
-- that exists only in web code.
insert into lineage.conformance_rules
    (rule_id, rule_family, source_id, stage, applies_to_fields, rule_kind, spec, rule,
     rationale, evidence_url, code_ref, effective_from)
select 'cr_nd_well_type_disposal_1', 'cr_nd_well_type_disposal', 'nd_gis_wells', 'conform',
       '{well_type}', 'code_ref',
       jsonb_build_object(
           'module_function', 'glasswell.marts.tiles:ND_LAYERS',
           'version', '1',
           'classification', 'disposal_injection',
           'well_type_codes',
           jsonb_build_array('SWD', 'WI', 'CO2I', 'AI', 'GI', 'SFI', 'MWUI', 'INJP'),
           'code_semantics', 'verbatim NDIC well_type codes; no per-code decode is asserted',
           'contract_note', 'the map''s disposal-wells layer draws exactly these eight codes'
           ' as a ring; the attribute reaches the tile verbatim from'
           ' canonical.wells.well_type_reported (web/src/map/disposal.ts is the filter)'),
       'Class a well as disposal/injection where NDIC''s well_type code is SWD, WI, CO2I,'
       ' AI, GI, SFI, MWUI or INJP.',
       'Measured by groupBy on the NDIC Wells FeatureServer (43,824 wells): OG 40,180,'
       ' SWD 1,059, Confidential 964, WI 848, GASD 279, ST 183, GASC 106, WS 95, CO2I 43,'
       ' AI 22, GI 10, SFI 4, MWUI 2, INJP 1. The eight listed codes are the injection'
       ' class the survey verified, 1,989 wells; the excluded codes are not asserted to be'
       ' injection wells by any NDIC statement held here. The SWD / EXP-SWD / PANF-SWD'
       ' labels on NDIC''s own vector tiles are status-type composites, not distinct types'
       ' — status independently carries EXP (18) and PANF (27) — so the class is keyed to'
       ' well_type alone. The codes are drawn verbatim; which words each abbreviates is the'
       ' regulator''s decoder to own, and this rule asserts no decode.',
       'https://gis.dmr.nd.gov/dmrpublicservices/rest/services/'
       'OilGasPublicMapDataVectorTiles/Wells/FeatureServer/0',
       'web/src/map/disposal.ts', date '2026-08-22'
 where exists (select 1 from lineage.sources where source_id = 'nd_gis_wells')
on conflict (rule_id) do nothing;
