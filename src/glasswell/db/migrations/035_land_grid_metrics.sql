-- M2-3: observed well and production rollups on the land grid, served as a tile mart.
--
-- Why a second mart rather than columns on land_units_tile. The land grid is reference
-- geometry on a monthly poll; the metrics are production-shaped and refresh with the MPR
-- cycle. Separately, the metrics mart holds only units with at least one member well, so a
-- unit with nothing observed is absent from the thematic tile and renders as bare grid —
-- "visibly empty rather than interpolated" (MAP-ROADMAP M2-3) is a row-count property here,
-- not a style promise.
--
-- Numeric columns are int4/float8: a numeric would reach MapLibre as an MVT string and
-- every ramp over it would silently fall back (the N-2 wire hazard).

create table marts.land_metrics_tile (
    land_unit_id    text primary key,
    unit_type       text not null,
    plssid          text not null,
    label           text not null,
    well_count      integer not null,
    prod_well_count integer not null,
    liquid_cum_bbl  double precision not null,
    gas_cum_mcf     double precision not null,
    water_cum_bbl   double precision not null,
    liquid_bin      integer not null,
    bin_edges       text not null,
    bin_population  integer not null,
    derivation_id   text not null,
    geom            geometry(MultiPolygon, 4326) not null
);

comment on table marts.land_metrics_tile is
    'Observed rollups per land unit: whole-well sums under cr_land_agg_membership_1, liquid
     per cr_nd_liquids_policy_1. Rebuilt, never appended (§3.0.1). liquid_bin is -1 where no
     liquid was observed; bin_edges/bin_population are the refresh-frozen percentile frame,
     identical across every row of one unit_type in one refresh.';

comment on column marts.land_metrics_tile.liquid_bin is
    'Index into the refresh''s percentile bins ([min,p2,p20,p40,p60,p80,p98,max], 7 bins),
     computed over the unit_type''s cells with observed liquid; -1 = nothing observed, which
     the style leaves unpainted rather than painting as "low".';

create index land_metrics_tile_geom_idx on marts.land_metrics_tile using gist (geom);

create index land_metrics_tile_type_idx on marts.land_metrics_tile (unit_type);

create view marts.tile_land_township_metrics as
select land_unit_id, unit_type, plssid, label, well_count, prod_well_count, liquid_cum_bbl,
       gas_cum_mcf, water_cum_bbl, liquid_bin, bin_edges, bin_population, derivation_id, geom
  from marts.land_metrics_tile
 where unit_type = 'township';

create view marts.tile_land_section_metrics as
select land_unit_id, unit_type, plssid, label, well_count, prod_well_count, liquid_cum_bbl,
       gas_cum_mcf, water_cum_bbl, liquid_bin, bin_edges, bin_population, derivation_id, geom
  from marts.land_metrics_tile
 where unit_type = 'section';

comment on view marts.tile_land_township_metrics is
    'What the tile server may see. The column list is the publication boundary: martin holds
     select on this view and on no base relation (DR-05).';

comment on view marts.tile_land_section_metrics is
    'What the tile server may see. The column list is the publication boundary: martin holds
     select on this view and on no base relation (DR-05).';

grant select on marts.land_metrics_tile to glasswell_api;
grant select, insert, delete, truncate on marts.land_metrics_tile to glasswell_pipeline;
grant select on marts.tile_land_township_metrics to martin, glasswell_api;
grant select on marts.tile_land_section_metrics to martin, glasswell_api;

-- THE mapping decision of M2-3, inserted here for an already-seeded database; a fresh one
-- gets the same content from glasswell.seed.conformance_land (the M1-7/M1-3/M1-4 pattern).
insert into lineage.conformance_rules
    (rule_id, rule_family, source_id, stage, applies_to_fields, rule_kind, spec, rule,
     rationale, evidence_url, code_ref, effective_from)
select 'cr_land_agg_membership_1', 'cr_land_agg_membership', 'blm_plss_sections', 'join',
       '{geom,land_unit_id,api10}', 'code_ref',
       jsonb_build_object(
           'module_function', 'glasswell.marts.land_metrics:refresh_land_metrics',
           'version', '1',
           'assign_by', 'lateral_midpoint_else_surface',
           'anchor', jsonb_build_object(
               'lateral', 'ST_LineInterpolatePoint(ST_LineMerge(lateral), 0.5) when the'
               ' merge yields a single LineString; ST_ClosestPoint(lateral,'
               ' ST_Centroid(lateral)) for the multi-part remainder (5 of 22,263 measured)',
               'no_lateral', 'the surface hole point, which for a vertical well is the'
               ' producing location itself'),
           'tie_break', 'min(land_unit_id) when the anchor intersects more than one section'
           ' (0 measured today; the dedupe is structural, not observed)',
           'township_membership', 'the parent township of the assigned section via the'
           ' plssid join, never an independent point test — a well is in the township of'
           ' its section',
           'unassigned', 'a well whose anchor falls in no land unit is excluded from'
           ' every cell; the refresh derivation params count the exclusions twice over —'
           ' in total (Texas is expected to be wholly unassigned until a TX land grid'
           ' exists) and for the grid''s own states, where a nonzero count is an anomaly'
           ' (0 ND wells measured today)',
           'observed_only', 'whole-well observed sums: each well lands in exactly one'
           ' section, no length-weighted apportionment, no interpolation, no estimate.'
           ' Fractional allocation is a superseding rule with Protocol 4D obligations,'
           ' not an edit',
           'contract_note', 'marts.land_metrics_tile and both metric tile layers carry'
           ' whole-well sums under this membership; the mart module is the executor, and a'
           ' different membership (apportionment, bottomhole) is a superseding row, not a'
           ' code change',
           'evidence_measured', jsonb_build_object(
               'measured_on', '2026-08-22, VM 111 canonical (73,512 land units, 398,403'
               ' production rows)',
               'nd_wells', 43817, 'with_surface_point', 43817, 'with_lateral', 22263,
               'with_bottomhole', 0,
               'laterals_crossing_2plus_sections', jsonb_build_object(
                   'count', 18903, 'of', 22261, 'share', '84.9%'),
               'midpoint_section_differs_from_surface', jsonb_build_object(
                   'count', 10464, 'of', 22100, 'share', '47.3%'),
               'liquid_volume_on_differing_wells_bbl', jsonb_build_object(
                   'bbl', 107785686, 'of_bbl', 188213452, 'share', '57.3%'),
               'township_grain_differs', jsonb_build_object(
                   'count', 1798, 'of', 22100, 'share', '8.1%'))),
       'A well belongs to the section holding its lateral midpoint when it has a filed'
       ' lateral, and the section holding its surface hole otherwise; townships inherit'
       ' through the section''s parent. Sums are whole-well and observed-only.',
       'Three candidate memberships were measured before choosing (M2-3). Bottomhole is'
       ' unavailable: canonical.well_spatial holds zero bottomhole geometries. Surface-point'
       ' membership is complete (43,817/43,817) but misplaces the producing footprint: 84.9%'
       ' of ND laterals cross two or more sections, the lateral midpoint sits in a different'
       ' section than the surface hole for 47.3% of laterals — and volume-weighted that is'
       ' 57.3% of every observed ND liquid barrel (107.8M of 188.2M bbl), because pads'
       ' cluster surface holes in one section while the rock that produced sits under the'
       ' next. At section grain a surface-point choropleth is a pad map wearing a production'
       ' map''s title. The lateral midpoint is the arc-length centre of the filed bore — a'
       ' producing-interval proxy that keeps each well whole in one cell, observed-only,'
       ' with the surface hole as the exact answer for verticals. Length-weighted'
       ' apportionment across crossed sections was rejected for v1: it manufactures'
       ' fractional well-months nothing observed, which is allocation modelling and takes a'
       ' superseding rule carrying its spacing assumption per Protocol 4D. At township grain'
       ' the same choice moves only 8.1% of laterals, so the township surface is robust to'
       ' it either way.',
       'https://gis.dmr.nd.gov/downloads/oilgas/shapefile/OGD_Horizontals_Line.zip',
       'src/glasswell/marts/land_metrics.py', date '2026-08-22'
 where exists (select 1 from lineage.sources where source_id = 'blm_plss_sections')
on conflict (rule_id) do nothing;
