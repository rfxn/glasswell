-- R8 supersession of the compute-CRS rule (fp-audit A3-F1). EPSG:32614 was seeded as the ND
-- compute CRS, but 22,661 of 23,228 laterals (97.6%) lie west of 102W, outside zone 14N: the
-- fleet was overstated by 144,378.78 ft (+0.0709%) and 3,030 laterals by more than ten feet.
-- The Williston basin spans two UTM zones, so a registry keyed by basin cannot express the
-- right answer. cr_nd_compute_crs_1 is not edited — R8 forbids it, and the append-only trigger
-- enforces it. This inserts the successor row for a database that was already seeded; a fresh
-- one gets both rows from glasswell.seed.conformance_nd, which carries the same content.

insert into lineage.conformance_rules
    (rule_id, rule_family, supersedes_rule_id, source_id, stage, applies_to_fields, rule_kind,
     spec, rule, rationale, evidence_url, effective_from)
select 'cr_nd_compute_crs_2', 'cr_nd_compute_crs', 'cr_nd_compute_crs_1',
       'nd_gis_horizontals_line', 'conform', '{geom}', 'parse_directive',
       jsonb_build_object(
           'storage_epsg', 4326,
           'length_method', 'geodesic',
           'ellipsoid', 'WGS84',
           'purpose', 'length_computation',
           'length_expression', 'ST_Length(geom::geography)',
           'forbidden_field', 'SHAPE_Leng'),
       'Measure lateral length geodesically on the WGS84 ellipsoid; never project it into a'
       ' UTM zone and never read the shapefile''s own length field.',
       'Supersedes cr_nd_compute_crs_1 on the evidence in fp-audit A3-F1: 22,661 of 23,228 ND'
       ' laterals (97.6 percent) lie west of 102W, outside EPSG:32614''s band, which overstated'
       ' the fleet by 144,378.78 ft (+0.0709 percent) and 3,030 laterals by more than ten feet.'
       ' The Williston basin spans UTM 13N and 14N, so a basin-keyed compute CRS cannot be'
       ' correct for both halves of it and the schema cannot express the right answer. A'
       ' geodesic length chooses no zone. Measured against an independent pyproj'
       ' Geod(ellps=WGS84) traverse over a 100-lateral sample spanning 104.01W to 100.97W,'
       ' ST_Length(geom::geography) agrees to 2.4e-8 m (8e-8 ft, 1.1e-7 percent), while the'
       ' superseded EPSG:32614 differs by up to 6.632 ft (0.145 percent) and the best projected'
       ' alternative - per-feature UTM zone chosen by centroid longitude - by up to 1.460 ft'
       ' (0.033 percent). SHAPE_Leng stays forbidden for the reason cr_nd_compute_crs_1 gave:'
       ' it is published in degrees.',
       'https://gis.dmr.nd.gov/downloads/oilgas/shapefile/OGD_Horizontals_Line.zip',
       date '2026-08-20'
 where exists (select 1 from lineage.conformance_rules where rule_id = 'cr_nd_compute_crs_1')
on conflict (rule_id) do nothing;

insert into lineage.audit_events (event_id, occurred_at, actor, event_type, subject_type,
                                  subject_id, payload)
select 'evt_migration_014_cr_nd_compute_crs_2', now(), 'system:migration',
       'conformance.rule_superseded', 'rule', 'cr_nd_compute_crs_2',
       jsonb_build_object('supersedes', 'cr_nd_compute_crs_1',
                          'from_method', 'projected EPSG:32614',
                          'to_method', 'geodesic WGS84',
                          'finding', 'fp-audit A3-F1',
                          'migration', '014_geodesic_lateral_length')
 where exists (select 1 from lineage.conformance_rules where rule_id = 'cr_nd_compute_crs_2')
   and not exists (select 1 from lineage.audit_events
                    where event_id = 'evt_migration_014_cr_nd_compute_crs_2');

-- The registry keeps its projected CRS for area and spacing work; it is no longer the source
-- of lateral length, and the note says so rather than leaving the zone claim standing.
update lineage.crs_registry
   set note = 'UTM 14N for area and spacing work only. The Williston basin spans zones 13N and'
              ' 14N, so lateral length is measured geodesically under cr_nd_compute_crs_2'
              ' rather than projected into either (fp-audit A3-F1).'
 where basin = 'williston';

update canonical.glossary_terms
   set short_definition = 'Coordinate reference system. Storage is always EPSG:4326; lateral'
                          ' length is measured geodesically on the WGS84 ellipsoid, and a'
                          ' projected metre-based CRS is used for area and spacing work.',
       expanded_definition = 'The Williston basin spans UTM 13N and 14N and 97.6 percent of ND'
                             ' laterals lie west of 102W, so no single projected zone is right'
                             ' for the state: measuring them in UTM 14N overstated the fleet by'
                             ' 144,379 ft (fp-audit A3-F1). Lateral length is therefore geodesic'
                             ' on the ellipsoid under cr_nd_compute_crs_2, which chooses no'
                             ' zone. Distance maths in degrees remains a defect, not an'
                             ' approximation - which is why a shapefile''s own length field,'
                             ' shipped in degrees, is never served as a length.'
 where term_id = 'gt_crs_compute_crs';

-- SB-07 6.5 step 3: the affected surface is the tile mart, whose stored lengths were written
-- under the superseded rule. Recorded here, rebuilt by `python -m glasswell.marts.nd_wells`.
insert into lineage.audit_events (event_id, occurred_at, actor, event_type, subject_type,
                                  subject_id, payload)
select 'evt_migration_014_mart_invalidated', now(), 'system:migration', 'mart.invalidated',
       'rule', 'cr_nd_compute_crs_2',
       jsonb_build_object('datasets', jsonb_build_array('marts.nd_laterals_tile'),
                          'reason', 'lateral_length_ft was computed under cr_nd_compute_crs_1',
                          'rebuild_with', 'python -m glasswell.marts.nd_wells --dsn <dsn>',
                          'migration', '014_geodesic_lateral_length')
 where exists (select 1 from lineage.conformance_rules where rule_id = 'cr_nd_compute_crs_2')
   and not exists (select 1 from lineage.audit_events
                    where event_id = 'evt_migration_014_mart_invalidated');
