-- M1-9: the NM OCD C-115B natural-gas-waste capture — staging and its waste vocabulary.
--
-- Why this source is urgent and why it stops at staging. The service's reporting_period is a
-- rolling ~13-month window (202507 .. 202607 measured 2026-08-22) and publishes nothing behind
-- it: a month that rolls out is unrecoverable from the endpoint. Preservation is discharged the
-- moment the bytes carry a manifest and the rows carry a reason, so the capture terminates at
-- staging and canonical promotion reads preserved bytes later, at leisure. A staging table is
-- the cheapest thing that makes the loss stop.
--
-- Why there is no canonical table here. Parsers write staging only (blueprint §3.4.2); a
-- canonical flaring grain, its liquids/gas policy and its rollup obligations under Protocol 4D
-- are a separate decision and take their own rules, not a column added in passing.
--
-- Why the source is OCDPUB/C115B_NaturalGasWaste layer 0 and not OCDView/Venting_Flaring. The
-- latter is the layer the obvious search finds and it is wrong: it stopped at C115Period 202207,
-- reports at property grain rather than well, and self-describes as "for demo purposes only". It
-- joins no identity spine. That rejection is cr_nm_c115b_source_1, not a comment.

create table staging.nm_c115b_upstream (
    manifest_id           text not null references lineage.manifests (manifest_id),
    source_row_ordinal    integer not null,
    ingested_at           timestamptz not null default now(),
    id                    text,
    name                  text,
    type                  text,
    status                text,
    lease_type            text,
    ogrid                 text,
    ogrid_name            text,
    latitude              text,
    longitude             text,
    pool_id_list          text,
    details               text,
    files                 text,
    structure_id          text,
    structure_type        text,
    reporting_period_year text,
    reporting_period      text,
    waste_type            text,
    volume                text,
    geom                  geometry(Point, 4326),
    primary key (manifest_id, source_row_ordinal)
);

comment on table staging.nm_c115b_upstream is
    'Every column text: staging is source-faithful and holds no opinions (blueprint §3.4.2).
     `id` keeps the dashed API-10 the service ships; cr_nm_c115b_api10_1 is what undashes it,
     and a row whose id will not normalise is staged anyway and held beside itself.';

comment on column staging.nm_c115b_upstream.reporting_period is
    'YYYYMM, and the reason this table exists: the service serves a rolling ~13-month window,
     so the union of this column across manifests is the only history there will ever be.';

comment on column staging.nm_c115b_upstream.volume is
    'The volume of gas the operator reported as flared or vented. Not a reserve, not a
     production figure, and never to be rolled up into one.';

create index nm_c115b_upstream_period_idx on staging.nm_c115b_upstream (reporting_period);

create table lineage.nm_waste_type_map (
    waste_type_raw       text primary key,
    waste_type_canonical text not null
);

comment on table lineage.nm_waste_type_map is
    'The C-115B waste vocabulary, as data. cr_nm_c115b_waste_vocab_1 reads it; a third code
     appearing upstream quarantines as unknown_vocab rather than being guessed at here.';

grant select, insert on staging.nm_c115b_upstream to glasswell_pipeline;
grant select on lineage.nm_waste_type_map to glasswell_pipeline, glasswell_api;

insert into lineage.nm_waste_type_map (waste_type_raw, waste_type_canonical)
values ('F', 'flared'), ('V', 'vented')
on conflict (waste_type_raw) do nothing;

-- The five decisions the capture executes, inserted here for an already-seeded database; a
-- fresh one gets identical content from glasswell.seed.conformance_c115b, which also registers
-- the source. The guards skip cleanly where the source is not registered yet — deploy runs
-- migrations before seed_all, so on the first deployed pass these land via the seeder.
insert into lineage.conformance_rules
    (rule_id, rule_family, source_id, stage, applies_to_fields, rule_kind, spec, rule,
     rationale, evidence_url, code_ref, effective_from)
select 'cr_nm_c115b_source_1', 'cr_nm_c115b_source', 'nm_c115b_upstream', 'parse',
       '{id,reporting_period,waste_type,volume}', 'parse_directive',
       jsonb_build_object(
           'service_url',
           'https://gis.emnrd.nm.gov/arcgis/rest/services/OCDPUB/C115B_NaturalGasWaste/FeatureServer',
           'layer_id', 0,
           'layer_name', 'C-115B Upstream by Well API',
           'where', '1=1',
           'grain', 'well API x reporting_period x waste_type',
           'rejected_sources', jsonb_build_array(
               'OCDPUB/C115B_NaturalGasWaste/MapServer/0 (same rows; declares no objectIdField'
               ' and capabilities Query,Map,Data rather than Query,Extract)',
               'OCDView/Venting_Flaring (stale at C115Period 202207, property grain, and'
               ' self-described as for demo purposes only)'),
           'window', jsonb_build_object(
               'kind', 'rolling', 'months', 13, 'measured_on', '2026-08-22',
               'min', 202507, 'max', 202607)),
       'Capture well-level flaring and venting from OCDPUB/C115B_NaturalGasWaste layer 0 on the'
       ' FeatureServer, whole layer, every month.',
       'Three NM services publish something called venting and flaring and only one of them is'
       ' this. OCDView/Venting_Flaring is the layer the obvious search finds: it stopped'
       ' updating at C115Period 202207, reports at property grain rather than well, joins no'
       ' identity spine, and its own description says it is for demo purposes only. The'
       ' MapServer sibling of the chosen service carries the same 71,447 rows but declares no'
       ' objectIdField and advertises Query,Map,Data where the FeatureServer advertises'
       ' Query,Extract, so the FeatureServer is the endpoint whose publisher intent to be'
       ' extracted is explicit. The whole layer is taken on every pass rather than the newest'
       ' month, because reporting_period is a rolling ~13-month window and a restatement inside'
       ' it is invisible to a newest-month filter.',
       'https://gis.emnrd.nm.gov/arcgis/rest/services/OCDPUB/C115B_NaturalGasWaste/FeatureServer/0',
       'src/glasswell/ingest/nm_c115b.py', date '2026-08-22'
 where exists (select 1 from lineage.sources where source_id = 'nm_c115b_upstream')
on conflict (rule_id) do nothing;

insert into lineage.conformance_rules
    (rule_id, rule_family, source_id, stage, applies_to_fields, rule_kind, spec, rule,
     rationale, evidence_url, code_ref, effective_from)
select 'cr_nm_c115b_walk_order_1', 'cr_nm_c115b_walk_order', 'nm_c115b_upstream', 'parse',
       '{id,reporting_period,waste_type}', 'parse_directive',
       jsonb_build_object(
           'order_by', 'id ASC, reporting_period ASC, waste_type ASC',
           'rejected_order', 'OBJECTID ASC',
           'reason', 'view_backed_layer_assigns_objectid_per_query',
           'tripwire', jsonb_build_object(
               'reason_code', 'duplicate_row',
               'note', 'a repeated identity key inside one harvest means the walk order'
                       ' stopped being total, not that the regulator filed twice'),
           'measured_2026_08_22', jsonb_build_object(
               'objectid_max', 71447, 'row_count', 71447,
               'adjacent_2000_row_pages_overlapping_under_objectid', 52,
               'adjacent_2000_row_pages_overlapping_under_this_order', 0,
               'duplicate_keys_in_the_2026_08_21_objectid_snapshot', 5309)),
       'Walk the layer ordered by (id, reporting_period, waste_type) — never by OBJECTID.',
       'The layer is view-backed: max(OBJECTID) equals the row count exactly and the same three'
       ' rows answered with OBJECTIDs 67199/59784/62372 and then 59844/61928/67791 seconds'
       ' apart, so OBJECTID is assigned per query and is not an identity. resultOffset re-runs'
       ' the query for every page, so an OBJECTID-ordered walk silently re-reads and skips rows'
       ' while count_before, count_after and features_written all reconcile: two adjacent'
       ' 2,000-row pages shared 52 rows under OBJECTID ASC and none under this order, and the'
       ' 2026-08-21 preservation snapshot taken that way carries 5,309 duplicated identity keys'
       ' that are pagination artifacts rather than upstream data. (id, reporting_period,'
       ' waste_type) is a total order, verified on a 521-row unpaginated slice where id is'
       ' unique. The duplicate_row quarantine is the standing tripwire if that ever stops'
       ' holding.',
       'https://gis.emnrd.nm.gov/arcgis/rest/services/OCDPUB/C115B_NaturalGasWaste/FeatureServer/0',
       'src/glasswell/ingest/nm_c115b.py', date '2026-08-22'
 where exists (select 1 from lineage.sources where source_id = 'nm_c115b_upstream')
on conflict (rule_id) do nothing;

insert into lineage.conformance_rules
    (rule_id, rule_family, source_id, stage, applies_to_fields, rule_kind, spec, rule,
     rationale, evidence_url, code_ref, effective_from)
select 'cr_nm_c115b_api10_1', 'cr_nm_c115b_api10', 'nm_c115b_upstream', 'parse',
       '{id}', 'key_composite',
       jsonb_build_object(
           'module_function', 'glasswell.ingest.nm_c115b:api10_from_dashed',
           'version', '1',
           'source_cols', jsonb_build_array('id'),
           'target_col', 'api10',
           'source_form', 'SS-CCC-NNNNN',
           'target_form', 'SSCCCNNNNN',
           'reason_code', 'key_incomplete'),
       'Normalise the dashed id (30-015-03890) to the undashed API-10 (3001503890) that is the'
       ' identity spine; an id that is not exactly 2-3-5 digits is held, never padded or'
       ' truncated into one.',
       'C-115B is the only NM source in the register that ships the API number dashed, and the'
       ' spine holds API-10 undashed, so every join from this source crosses this mapping —'
       ' which makes it a row rather than a strip() somewhere in a parser. All 71,440 ids in the'
       ' 2026-08-21 snapshot match 2-3-5 exactly, so the strictness costs nothing today and is'
       ' the point on the day it does: stripping non-digits from a 14-character API-14 would'
       ' silently key a wellbore onto its well, and zero-padding a short id would build a'
       ' syntactically perfect API-10 for a well that does not exist (the failure D1-P3 measured'
       ' on the RRC county plot points). Refusal to key is key_incomplete, the code migration'
       ' 021 added for exactly this exit.',
       'https://gis.emnrd.nm.gov/arcgis/rest/services/OCDPUB/C115B_NaturalGasWaste/FeatureServer/0',
       'src/glasswell/ingest/nm_c115b.py', date '2026-08-22'
 where exists (select 1 from lineage.sources where source_id = 'nm_c115b_upstream')
on conflict (rule_id) do nothing;

insert into lineage.conformance_rules
    (rule_id, rule_family, source_id, stage, applies_to_fields, rule_kind, spec, rule,
     rationale, evidence_url, code_ref, effective_from)
select 'cr_nm_c115b_waste_vocab_1', 'cr_nm_c115b_waste_vocab', 'nm_c115b_upstream', 'parse',
       '{waste_type}', 'vocab_map',
       jsonb_build_object(
           'mapping_table', 'nm_waste_type_map',
           'key_col', 'waste_type_raw',
           'value_col', 'waste_type_canonical',
           'source_field', 'waste_type',
           'unmapped_action', 'quarantine',
           'reason_code', 'unknown_vocab',
           'measured_2026_08_21', jsonb_build_object('F', 5195, 'V', 66245, 'other', 0)),
       'Map waste_type F to flared and V to vented; any other code is quarantined rather than'
       ' guessed.',
       'F and V are the only values the layer carries — 5,195 and 66,245 across all 71,440 rows'
       ' of the 2026-08-21 snapshot, with no third code and no nulls. The OCD publishes no'
       ' codebook for the field, so the reading is stated here where a reader can check it'
       ' rather than left implicit in a dictionary literal. The distinction is the whole value'
       ' of the source: flared gas was burned and vented gas was released unburned, and a'
       ' rollup that adds them without saying so answers a question nobody asked. Volumes under'
       ' this vocabulary are reported waste, never production and never a reserve.',
       'https://gis.emnrd.nm.gov/arcgis/rest/services/OCDPUB/C115B_NaturalGasWaste/FeatureServer/0',
       'src/glasswell/ingest/nm_c115b.py', date '2026-08-22'
 where exists (select 1 from lineage.sources where source_id = 'nm_c115b_upstream')
on conflict (rule_id) do nothing;

insert into lineage.conformance_rules
    (rule_id, rule_family, source_id, stage, applies_to_fields, rule_kind, spec, rule,
     rationale, evidence_url, effective_from)
select 'cr_nm_c115b_datum_1', 'cr_nm_c115b_datum', 'nm_c115b_upstream', 'parse',
       '{geom}', 'datum_transform',
       jsonb_build_object(
           'source_epsg', 4269,
           'target_epsg', 4326,
           'detect', jsonb_build_object('service_sr_wkid', 4269)),
       'Transform the NAD83 well points to EPSG:4326 before they reach storage.',
       'The layer''s own spatialReference is wkid 4269 (NAD83), read from the layer JSON on'
       ' every fetch and recorded on the manifest. Storage is always 4326 and the transform is'
       ' recorded as a derivation even though the shift is sub-metre: no coordinate reaches'
       ' storage untransformed and unrecorded (same rule as cr_nd_datum_1 and'
       ' cr_blm_plss_datum_1).',
       'https://gis.emnrd.nm.gov/arcgis/rest/services/OCDPUB/C115B_NaturalGasWaste/FeatureServer/0',
       date '2026-08-22'
 where exists (select 1 from lineage.sources where source_id = 'nm_c115b_upstream')
on conflict (rule_id) do nothing;
