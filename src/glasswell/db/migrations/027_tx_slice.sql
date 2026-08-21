-- The TX slice: spatial presence and wellbore identity. No production, by construction.
--
-- TX reports production at the lease (DIR-3), so a well-level series here would be an
-- allocation artifact posing as an observation. This migration therefore builds the well
-- universe, its geometry and its lease keys - the substrate the allocation chain will need -
-- and adds nothing that could serve a volume.
--
-- Staging geometry is NAD27 (EPSG:4267), not 4326. The RRC ships NAD27 and the shift is up to
-- ~46 m in the Permian (measured against the same files' own published NAD83 columns), so the
-- transform is a promotion step under cr_tx_nad27_1 with a pinned NADCON grid, not an
-- ST_Transform whose PROJ path silently degrades to a three-parameter fit when the grid is
-- absent. Storage stays 4326 everywhere it always was.

create table staging.tx_gis_wells_surface (
    manifest_id        text not null references lineage.manifests (manifest_id),
    source_row_ordinal integer not null,
    ingested_at        timestamptz not null default now(),
    source_county_code text not null,
    surface_id         text,
    symnum             text,
    api                text,
    reliab             text,
    long27             text,
    lat27              text,
    long83             text,
    lat83              text,
    wellid             text,
    geom               geometry(Point, 4267),
    primary key (manifest_id, source_row_ordinal)
);

comment on table staging.tx_gis_wells_surface is
    'Source-faithful: every column is the DBF field as shipped, and geom is in the CRS the
     archive''s own .prj declares (SB-01 2.8 step 2).';

comment on column staging.tx_gis_wells_surface.api is
    'Eight digits: RRC county code plus well number. It is not an API-10 - the state prefix is
     added by cr_tx_api10_build_1, never assumed here.';

create table staging.tx_gis_wells_bottomhole (
    manifest_id        text not null references lineage.manifests (manifest_id),
    source_row_ordinal integer not null,
    ingested_at        timestamptz not null default now(),
    source_county_code text not null,
    bottom_id          text,
    surface_id         text,
    symnum             text,
    apinum             text,
    reliab             text,
    api10              text,
    api                text,
    long27             text,
    lat27              text,
    long83             text,
    lat83              text,
    out_fips           text,
    cwellnum           text,
    radioact           text,
    wellid             text,
    stcode             text,
    geom               geometry(Point, 4267),
    primary key (manifest_id, source_row_ordinal)
);

comment on column staging.tx_gis_wells_bottomhole.api10 is
    'The RRC''s field name, not an API-10: it holds the same eight digits as api, with the
     wellbore code appended on the arc layer. cr_tx_api10_build_1 is what builds an API-10.';

create table staging.tx_gis_wells_lines (
    manifest_id        text not null references lineage.manifests (manifest_id),
    source_row_ordinal integer not null,
    ingested_at        timestamptz not null default now(),
    source_county_code text not null,
    bottom_id          text,
    surface_id         text,
    api10              text,
    api                text,
    stcode             text,
    shape_len          text,
    geom               geometry(Geometry, 4267),
    primary key (manifest_id, source_row_ordinal)
);

comment on column staging.tx_gis_wells_lines.shape_len is
    'The shipped arc length. Never served and never compared: cr_tx_compute_crs_1 measures
     geodesically on the ellipsoid, and a source length field is not a measurement this system
     can explain.';

create table staging.tx_wellbore_ewa (
    manifest_id        text not null references lineage.manifests (manifest_id),
    source_row_ordinal integer not null,
    ingested_at        timestamptz not null default now(),
    fields             text[] not null,
    primary key (manifest_id, source_row_ordinal)
);

comment on table staging.tx_wellbore_ewa is
    'The export ships no header row, so faithful means positional: every field of the record is
     kept in order and nothing is named here. The names live in cr_tx_ewa_layout_1, which
     carries the RRC layout manual''s field numbers and the assertions that prove them.';

create index tx_wellbore_ewa_api_idx on staging.tx_wellbore_ewa ((fields[3]));

-- A county file whose features carry another county's API is not a parse failure, an unknown
-- vocabulary or an orphan: it is a row outside the scope the fetch was made under, and the
-- existing codes would each assert something that did not happen.
alter table lineage.quarantine_rows drop constraint if exists quarantine_rows_reason_code_check;

alter table lineage.quarantine_rows add constraint quarantine_rows_reason_code_check
    check (reason_code in (
        'parse_error', 'encoding_error', 'schema_mismatch', 'unknown_vocab',
        'alias_unresolved', 'datum_undetermined', 'key_collision',
        'multi_wellbore_policy', 'impossible_volume', 'orphan_fk',
        'confidential_withheld', 'duplicate_row', 'out_of_range_date',
        'unreliable_numeric', 'stream_not_promoted', 'unknown_status',
        'segment_not_promoted', 'key_incomplete', 'out_of_scope'));

-- Identity, effective-dated like every other canonical well attribute.
alter table canonical.wells
    add column total_depth_ft  numeric(10, 1),
    add column completion_date date;

comment on column canonical.wells.total_depth_ft is
    'Total wellbore depth in feet as the source reported it (TX: EWA API_DEPTH). Feet is in the
     column name because this schema has no field_units registry yet.';
comment on column canonical.wells.completion_date is
    'Most recent completion date the regulator holds; not a spud date and not a first-production
     date.';

-- The well-to-lease link TX production will one day be allocated across. It is captured now
-- because the keys are only in the crosswalk, and it is kept separate from any canonical
-- production path: SB-01 2.9 makes this source Validator A, so link_role says which crosswalk
-- a row came from and no promotion may average two of them into one answer.
create table canonical.well_lease_links (
    api10              text not null,
    lease_key          text not null,
    oil_gas_code       text not null,
    district_no        text not null,
    lease_no           text not null,
    lease_name         text,
    well_no            text,
    field_no           text,
    field_name         text,
    link_role          text not null check (link_role in ('validator_a', 'canonical_crosswalk')),
    source_id          text not null references lineage.sources (source_id),
    effective_from     date not null,
    source_manifest_id text not null references lineage.manifests (manifest_id),
    derivation_id      text not null references lineage.derivations (derivation_id),
    created_at         timestamptz not null default now(),
    primary key (api10, lease_key, source_id, effective_from)
);

comment on column canonical.well_lease_links.lease_key is
    'Built by cr_tx_lease_key_1 from (oil_gas_code, district_no, lease_no). A bare lease_no is
     unique within a district only: 33,868 of 348,293 lease numbers in the 2026-08 export appear
     under more than one (code, district) pair, so keying on it alone is a measured collision.';

comment on table canonical.well_lease_links is
    'Append-only. A restatement is a new effective_from, never an update (DIR-2).';

create index well_lease_links_lease_idx on canonical.well_lease_links (lease_key, effective_from);

create trigger well_lease_links_append_only
    before update or delete on canonical.well_lease_links
    for each row execute function lineage.reject_mutation();

-- The status vocabulary, keyed by the frame column the rule maps (as lineage.nd_status_map is).
-- Values are the twenty-three WELL_TYPE_NAME values the RRC layout manual enumerates, plus the
-- PLUGGED sentinel cr_tx_plugged_precedence_1 writes when a W-3 plugging date is on file.
create table lineage.tx_status_map (
    status_input     text primary key,
    status_canonical text not null
);

insert into lineage.tx_status_map (status_input, status_canonical)
values ('PLUGGED',                    'plugged'),                -- 106,004 APIs in scope
       ('PRODUCING',                  'active'),                 -- 119,010 rows in scope
       ('SWR-10-WELL',                'active'),                 --   1,502
       ('PROD FACTOR WELL',           'active'),                 --     346
       ('SHUT IN',                    'inactive'),               --  42,094
       ('SHUT IN-MULTI-COMPL',        'inactive'),               --     135
       ('NO PRODUCTION',              'inactive'),               --   2,219
       ('NOT ELIGIBLE FOR ALLOWABLE', 'inactive'),               --     192
       ('TEMP ABANDONED',             'temporarily_abandoned'),  --   3,824
       ('PARTIAL PLUG',               'temporarily_abandoned'),  --     787
       ('ABANDONED',                  'plugged'),                --       5
       ('SEALED',                     'plugged'),                --       0
       ('INJECTION',                  'service'),                --  24,710
       ('WATER SUPPLY',               'service'),                --     839
       ('OBSERVATION',                'service'),                --      84
       ('BRINE MINING',               'service'),                --      82
       ('OTHER TYPE SERVICE',         'service'),                --      70
       ('LPG STORAGE',                'service'),                --      42
       ('GAS STRG-INJECTION',         'service'),                --      31
       ('GAS STRG-SALT FORMATION',    'service'),                --      12
       ('GAS STRG-WITHDRAWAL',        'service'),                --       2
       ('DOMESTIC USE WELL',          'service'),                --       8
       ('GEOTHERMAL WELL',            'service'),                --       0
       ('TRAINING',                   'service')                 --       0
on conflict do nothing;

comment on table lineage.tx_status_map is
    'RRC WELL_TYPE_NAME is a type, not a status: it names what a wellbore is used for. The
     mapping to the canonical status vocabulary is a decision, which is why it is a table a rule
     cites and a reviewer can supersede, not a case statement in a parser (R8).';

-- `service` is new to the canonical status vocabulary. ND has no injection or storage wells in
-- its GIS layer; TX has 26,000 in the Permian counties alone, and painting an injector as
-- active would be a claim about production that the source does not make.
insert into canonical.glossary_terms
    (term_id, term, aliases, short_definition, expanded_definition, domain_tags, source_refs,
     first_surfaced_in)
values ('gt_service_well', 'Service well', array['injection well', 'disposal well'],
        'A well used for injection, disposal, storage, observation or water supply rather than'
        ' production.',
        'The Railroad Commission records what a wellbore is used for in WELL_TYPE_NAME, and'
        ' eleven of its twenty-three values describe service rather than production - injection'
        ' and disposal being much the largest. glasswell maps those to the canonical status'
        ' service so a map reader can tell a producer from a disposal well, because the two'
        ' answer completely different questions about a lease. The mapping is'
        ' cr_tx_status_vocab_1 and the table behind it is lineage.tx_status_map.',
        array['identity', 'texas'], array['cr_tx_status_vocab_1'], 'TX slice')
on conflict do nothing;

-- Which compute-CRS rule governs a basin. The length method is registry-resolved rather than
-- pinned to ND's source id, so a TX length resolves a TX rule and its handle names one.
alter table lineage.crs_registry add column length_rule_source text;

update lineage.crs_registry
   set length_rule_source = 'nd_gis_horizontals_line'
 where basin = 'williston';

insert into lineage.crs_registry (basin, compute_epsg, storage_epsg, effective_from, note,
                                  length_rule_source)
values ('permian', 32613, 4326, date '2026-08-20',
        'UTM 13N for area and spacing work only. The Midland basin reaches about one degree east'
        ' of the zone, where scale error is about 1.1 mm/m - two orders below the NAD27 datum'
        ' hazard and systematic rather than random. Lateral length is measured geodesically'
        ' under cr_tx_compute_crs_1 and chooses no zone.',
        'tx_gis_wells_county')
on conflict do nothing;

-- Marts. Narrow projections of canonical, rebuilt in one transaction; float8 rather than
-- numeric on anything published, because ST_AsMVT has no numeric encoding (N-2).
create table marts.tx_wells_tile (
    api10              text primary key,
    operator_name      text,
    status_canonical   text,
    well_type_reported text,
    county_code        text,
    geom               geometry(Point, 4326) not null,
    derivation_id      text not null
);

create index tx_wells_tile_geom_idx on marts.tx_wells_tile using gist (geom);

create table marts.tx_laterals_tile (
    api10                   text not null,
    geom_key                text not null,
    operator_name           text,
    status_canonical        text,
    county_code             text,
    lateral_length_ft_exact numeric(12, 2),
    lateral_length_ft       double precision,
    geom                    geometry(Geometry, 4326) not null,
    derivation_id           text not null,
    primary key (api10, geom_key)
);

create index tx_laterals_tile_geom_idx on marts.tx_laterals_tile using gist (geom);

comment on column marts.tx_laterals_tile.lateral_length_ft_exact is
    'The unrounded length. It is deliberately outside the published view: numeric on the wire
     becomes a string and a MapLibre expression then compares it as one (migration 015, N-2).';

-- The publication boundary. martin holds select on these views and on no base relation, so a
-- column absent here cannot reach a tile whatever a config file declares (DR-05).
create view marts.tile_tx_wells as
select api10, operator_name, status_canonical, well_type_reported, county_code, derivation_id,
       geom
  from marts.tx_wells_tile;

create view marts.tile_tx_laterals as
select api10, geom_key, operator_name, status_canonical, county_code, lateral_length_ft,
       derivation_id, geom
  from marts.tx_laterals_tile;

grant select on marts.tx_wells_tile, marts.tx_laterals_tile to glasswell_api;
grant select on marts.tile_tx_wells, marts.tile_tx_laterals to martin, glasswell_api;
grant select, insert, delete, truncate on marts.tx_wells_tile, marts.tx_laterals_tile
    to glasswell_pipeline;
grant select, insert on staging.tx_gis_wells_surface, staging.tx_gis_wells_bottomhole,
    staging.tx_gis_wells_lines, staging.tx_wellbore_ewa, canonical.well_lease_links
    to glasswell_pipeline;
grant delete on staging.tx_gis_wells_surface, staging.tx_gis_wells_bottomhole,
    staging.tx_gis_wells_lines, staging.tx_wellbore_ewa to glasswell_pipeline;
grant select on staging.tx_gis_wells_surface, staging.tx_gis_wells_bottomhole,
    staging.tx_gis_wells_lines, staging.tx_wellbore_ewa, canonical.well_lease_links
    to glasswell_api;
grant select on lineage.tx_status_map to glasswell_pipeline, glasswell_api;
revoke update, delete on canonical.well_lease_links from glasswell_pipeline, glasswell_api;
