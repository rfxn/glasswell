-- staging.nd_gis_laterals.geom was declared geometry(LineString), so a record the reader had
-- already parsed — attributes read, geometry read, type inspected — was staged with a NULL
-- geometry and filed as `parse_error` (fp-audit A5-F8). Nothing failed to parse: the shape did
-- not fit the column. 583 rows on the VM, six of them laterals, so six real centrelines never
-- reached canonical. The column widens to hold what the regulator ships; canonical.well_spatial
-- already accepts any geometry, and MVT encodes a multi-part line as LINESTRING either way.

alter table staging.nd_gis_laterals alter column geom type geometry(Geometry, 4326);
alter table marts.nd_laterals_tile alter column geom type geometry(Geometry, 4326);

comment on column staging.nd_gis_laterals.geom is
    'Any geometry the layer ships. A multi-part centreline is stored as it was published;
     staging holds no opinion about it.';

-- Bounded by the payload field that already stated the true cause, and marked superseded
-- rather than released: the entry is no longer the system''s position, and the re-ingest that
-- proves each row now stages is the deployer''s step, not this migration''s.
with corrected as (
    update lineage.quarantine_rows
       set reason_code = 'schema_mismatch',
           state = 'superseded',
           notes = 'Superseded by migration 017: staging.nd_gis_laterals.geom now holds any'
                   ' geometry, so this record stages with the shape it was published with.'
                   ' The label was parse_error; the row parsed (fp-audit A5-F8).'
     where source_id = 'nd_gis_horizontals_line'
       and reason_code = 'parse_error'
       and row_payload ->> 'detail' like '%does not fit the declared%'
    returning quarantine_id)
insert into lineage.audit_events (event_id, occurred_at, actor, event_type, subject_type,
                                  subject_id, payload)
select 'evt_migration_017_schema_mismatch', now(), 'system:migration', 'quarantine.relabelled',
       'quarantine', 'nd_gis_horizontals_line',
       jsonb_build_object('from', 'parse_error', 'to', 'schema_mismatch',
                          'state', 'superseded', 'rows', count(*),
                          'bounded_by', 'row_payload->>detail like ''%does not fit the'
                                        ' declared%''',
                          'finding', 'fp-audit A5-F8',
                          'migration', '017_multipart_geometry')
  from corrected
 having count(*) > 0;
