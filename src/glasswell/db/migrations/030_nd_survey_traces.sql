-- ND directional-survey traces: the station grain, the trace geometry, and the tile mart.
-- All of the slice lands here because discover_migrations refuses gaps (M1-5).
--
-- Why a new source at all. `OGD_Directionals.zip` is 3.4 MB for 52,579 station records with
-- measured depth, inclination, azimuth and TVD. Its geodatabase sibling `NDOGD_Surveys.gdb.zip`
-- is 313.6 MB and was proved by HTTP-Range inspection of its GDB system catalog to hold exactly
-- the same two feature classes plus editor-tracking columns, so the register keeps the
-- shapefile and the geodatabase is not fetched (data-sources-wellops.md §4.2).
--
-- Why the trace is not a lateral. `canonical.well_spatial.geom_type` already carries 'lateral'
-- for the GIS bore line ND draws heel to toe. A survey trace is a different fact about the same
-- hole: it is the surveyed path through every station the operator filed, and a reader has to
-- be able to tell which one is on the screen. It is a third geom_type, not a second 'lateral'.
--
-- Why the stations are their own table rather than vertices. A vertex is a coordinate; a
-- station also carries the measurement that produced it. `landing_tvd_ft` and the structural
-- work behind it need MD/INC/AZI/TVD queryable per station, which a LineString cannot answer.
--
-- Why the trace is derived from the stations rather than read from the line ND ships beside
-- them. `OGD_Directionals.zip` also carries `OGD_Directionals_Line`, one feature per segment,
-- and it is a generalised rendering: 11,358 vertices against the station layer's 52,579, with
-- 585 of its 586 features carrying fewer vertices than the segment they draw, and a Hausdorff
-- distance from the filed stations of up to 1.06e-4 degrees (about 9 m). Assembling the trace
-- here keeps every station the operator filed, which is the whole point of the item.

create table staging.nd_gis_directionals (
    manifest_id        text not null references lineage.manifests (manifest_id),
    source_row_ordinal integer not null,
    ingested_at        timestamptz not null default now(),
    wl_permit          text,
    api_wellno         text,
    api_format         text,
    long               text,
    lat                text,
    well_sub           text,
    measdpth           text,
    inclinatio         text,
    azimuth            text,
    tvd                text,
    coordns            text,
    coordnsdir         text,
    coordew            text,
    coordewdir         text,
    surveytype         text,
    geom               geometry(Point, 4326),
    primary key (manifest_id, source_row_ordinal)
);

comment on table staging.nd_gis_directionals is
    'Every column text: staging is source-faithful and holds no opinions (blueprint §3.4.2).';

comment on column staging.nd_gis_directionals.inclinatio is
    'The DBF truncates the name at the shapefile 10-character limit; the geodatabase spells it
     inclination. Both spellings are the same field and neither is corrected here.';

create table canonical.well_survey_stations (
    api10                  text not null,
    api14                  text,
    wellbore_segment       text not null,
    segment_kind           text not null,
    station_ordinal        integer not null,
    measured_depth_ft      double precision,
    true_vertical_depth_ft double precision,
    inclination_deg        double precision,
    azimuth_deg            double precision,
    ns_offset_ft           double precision,
    ns_offset_dir          text,
    ew_offset_ft           double precision,
    ew_offset_dir          text,
    station_type           text,
    geom                   geometry(Point, 4326) not null,
    source_datum           text not null,
    transform_rule_id      text,
    source_manifest_id     text not null references lineage.manifests (manifest_id),
    derivation_id          text not null references lineage.derivations (derivation_id),
    created_at             timestamptz not null default now(),
    primary key (api10, wellbore_segment, station_ordinal)
);

-- Double precision, not numeric, from the first row: ST_AsMVT has no numeric encoding, so a
-- numeric column that later reaches a tile leaves it as a protobuf string and a MapLibre
-- expression compares '9000' > '22727'. Migration 015 found that class and 026 paid to move a
-- column that had already shipped (N-2).
comment on table canonical.well_survey_stations is
    'One filed survey station. Append-only; a station is a measurement and is never edited.';

comment on column canonical.well_survey_stations.station_ordinal is
    'Dense from 0 in ascending measured depth under cr_nd_survey_station_order_1, tie-broken by
     source row order. It is the vertex index of the trace in canonical.well_spatial, assigned
     in the same pass, so station n and vertex n are the same station by construction.';

comment on column canonical.well_survey_stations.azimuth_deg is
    'Reported, never converted. ND publishes no north reference for this field; the gap is
     stated by cr_nd_survey_azimuth_reference_1 rather than closed by an assumption.';

comment on column canonical.well_survey_stations.ns_offset_dir is
    'N or S as ND ships it. The magnitude and the letter stay separate because a signed offset
     would be a sign convention this repository chose, and ND states none.';

alter table canonical.well_spatial drop constraint well_spatial_geom_type_check;

alter table canonical.well_spatial add constraint well_spatial_geom_type_check
    check (geom_type in ('surface', 'bottomhole', 'lateral', 'survey_trace'));

comment on column canonical.well_spatial.geom_type is
    'How the geometry was arrived at, not only what shape it is: a survey_trace is built from
     filed stations and a lateral is the GIS centreline ND draws. The mart publishes it so the
     map can say which one a reader is looking at.';

create trigger well_survey_stations_append_only
    before update or delete on canonical.well_survey_stations
    for each row execute function lineage.reject_mutation();

create index well_survey_stations_geom_idx on canonical.well_survey_stations using gist (geom);

-- Keyed for the mart's aggregate, which groups every station of one segment.
create index well_survey_stations_segment_idx
    on canonical.well_survey_stations (api14, wellbore_segment);

-- The well_sub vocabulary. ND's own attribute definition for the field reads "categorized well
-- bore portions are assigned a description as Lateral (LAT), Vertical (VERT), or Sidetrack
-- (STK)", and the layer then ships DIR for 40,138 of its 52,579 stations — a value the
-- publisher's own metadata does not list, because this layer's abstract is "deviated well bore
-- but not at the severity of a horizontal". Which labels are known survey segments, and what
-- each one is called once conformed, is a mapping, so it is a table (R8, fp-audit A5-F6).
create table lineage.nd_survey_segment_map (
    well_sub     text primary key,
    segment_kind text,
    promoted     boolean not null default true
);

comment on table lineage.nd_survey_segment_map is
    'Key column is named for the frame column cr_nd_survey_segment_vocab_1 maps: _vocab_map '
    'reads spec.key_col from both the frame and this table.';

create view lineage.nd_survey_segment_promoted_map as
select well_sub, segment_kind
  from lineage.nd_survey_segment_map
 where promoted and segment_kind is not null;

grant select on lineage.nd_survey_segment_map, lineage.nd_survey_segment_promoted_map
    to glasswell_pipeline, glasswell_api;

-- LAT carries no station in the measured vintage. It is seeded anyway because ND's published
-- attribute definition names it, and a vocabulary seeded only from one file's contents
-- quarantines every row on the day the publisher uses the value it documented.
insert into lineage.nd_survey_segment_map (well_sub, segment_kind, promoted)
values ('DIR',  'directional', true),
       ('VERT', 'vertical',    true),
       ('STK1', 'sidetrack',   true),
       ('STK2', 'sidetrack',   true),
       ('STK3', 'sidetrack',   true),
       ('STK4', 'sidetrack',   true),
       ('LAT',  'lateral',     true)
on conflict do nothing;

-- insufficient_stations: a segment with one station is not a parse failure, not an unknown
-- vocabulary and not an orphan — it is a real station whose segment cannot be two points. The
-- station promotes; the trace that cannot be drawn is what this code records.
alter table lineage.quarantine_rows drop constraint if exists quarantine_rows_reason_code_check;

alter table lineage.quarantine_rows add constraint quarantine_rows_reason_code_check
    check (reason_code in (
        'parse_error', 'encoding_error', 'schema_mismatch', 'unknown_vocab',
        'alias_unresolved', 'datum_undetermined', 'key_collision',
        'multi_wellbore_policy', 'impossible_volume', 'orphan_fk',
        'confidential_withheld', 'duplicate_row', 'out_of_range_date',
        'unreliable_numeric', 'stream_not_promoted', 'unknown_status',
        'segment_not_promoted', 'key_incomplete', 'out_of_scope', 'multi_completion',
        'insufficient_stations'));

create table marts.nd_survey_traces_tile (
    api10                     text not null,
    trace_key                 text not null,
    operator_name             text,
    status_canonical          text,
    spud_year                 int,
    wellbore_segment          text,
    segment_kind              text,
    station_count             int,
    deepest_station_md_ft     double precision,
    deepest_station_tvd_ft    double precision,
    geometry_provenance       text,
    geom                      geometry(LineString, 4326) not null,
    derivation_id             text not null,
    primary key (api10, trace_key)
);

-- No length column. The trace is stored in 4326 as the plan view of a three-dimensional path,
-- so ST_Length over it measures horizontal travel and not hole length — a number that would
-- read as the one thing it is not. Measured depth is what the source actually filed, so the
-- deepest station's MD is published instead.
comment on table marts.nd_survey_traces_tile is
    'The surveyed bore path, one row per wellbore segment. Rebuilt, never appended (§3.0.1).';

create index nd_survey_traces_tile_geom_idx on marts.nd_survey_traces_tile using gist (geom);

create view marts.tile_nd_survey_traces as
select api10, trace_key, operator_name, status_canonical, spud_year, wellbore_segment,
       segment_kind, station_count, deepest_station_md_ft, deepest_station_tvd_ft,
       geometry_provenance, derivation_id, geom
  from marts.nd_survey_traces_tile;

comment on view marts.tile_nd_survey_traces is
    'What the tile server may see. The column list is the publication boundary: martin holds
     select on this view and on no base relation (DR-05).';

grant select, insert on staging.nd_gis_directionals to glasswell_pipeline;
grant delete on staging.nd_gis_directionals to glasswell_pipeline;
grant select, insert on canonical.well_survey_stations to glasswell_pipeline;
grant select on canonical.well_survey_stations to glasswell_api;
revoke update, delete on canonical.well_survey_stations
    from glasswell_pipeline, glasswell_api;
grant select on marts.nd_survey_traces_tile to glasswell_api;
grant select, insert, delete, truncate on marts.nd_survey_traces_tile to glasswell_pipeline;
grant select on marts.tile_nd_survey_traces to martin, glasswell_api;
