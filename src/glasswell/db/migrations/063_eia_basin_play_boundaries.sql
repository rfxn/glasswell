-- Basin and play boundaries: staging, canonical.basin_boundaries, and the tile mart.
--
-- Why EIA and not USGS. The map serves wells, laterals and a PLSS grid and can draw no
-- geological frame, while every ND well already carries basin=williston from a constant in the
-- ND ingest. EIA publishes basin and play as two separate archives with a stated distinction
-- between them, which is the distinction this repository has to keep; USGS assessment units
-- slice the same rock for assessment arithmetic. Both archives are plain anonymous HTTPS zips,
-- so neither passes through the ArcGIS host allowlist and neither needs an amendment to it.
--
-- Why one canonical table for two kinds. A play sits inside a basin and the hierarchy is a
-- join; two tables would re-implement it. boundary_kind is the discriminator, and the two are
-- published as two tile layers so a play surface never draws as a basin.
--
-- Why the areas are the publisher's. EIA states no equal-area projection for Area_sq_mi, so a
-- recomputed area would sit next to a name and a boundary that are EIA's and read as one
-- source's row. area_basis says publisher_reported on every row.
--
-- Two of the forty-eight published features are invalid — both Williston plays. The repair and
-- its evidence are cr_eia_geometry_repair_1; invalid_geometry joins the reject vocabulary here.

alter table lineage.quarantine_rows drop constraint if exists quarantine_rows_reason_code_check;

alter table lineage.quarantine_rows add constraint quarantine_rows_reason_code_check
    check (reason_code in (
        'parse_error', 'encoding_error', 'schema_mismatch', 'unknown_vocab',
        'alias_unresolved', 'datum_undetermined', 'key_collision',
        'multi_wellbore_policy', 'impossible_volume', 'orphan_fk',
        'confidential_withheld', 'duplicate_row', 'out_of_range_date',
        'unreliable_numeric', 'stream_not_promoted', 'unknown_status',
        'segment_not_promoted', 'key_incomplete', 'out_of_scope', 'multi_completion',
        'insufficient_stations', 'invalid_geometry'));

create table staging.eia_basins (
    manifest_id        text not null references lineage.manifests (manifest_id),
    source_row_ordinal integer not null,
    ingested_at        timestamptz not null default now(),
    source_layer       text,
    name               text,
    area_sq_mi         text,
    area_sq_km         text,
    geom               geometry(MultiPolygon, 4326),
    primary key (manifest_id, source_row_ordinal)
);

comment on table staging.eia_basins is
    'Every column text: staging is source-faithful and holds no opinions (blueprint §3.4.2).
     geom holds the published ring as shipped, invalid rings included — validity is judged at
     promotion, not here.';

create table staging.eia_plays (
    manifest_id        text not null references lineage.manifests (manifest_id),
    source_row_ordinal integer not null,
    ingested_at        timestamptz not null default now(),
    source_layer       text,
    shale_play         text,
    basin              text,
    sub_basin          text,
    lithology          text,
    age_shale          text,
    source_label       text,
    area_sq_mi         text,
    area_sq_km         text,
    geom               geometry(MultiPolygon, 4326),
    primary key (manifest_id, source_row_ordinal)
);

comment on table staging.eia_plays is
    'One archive, twelve shapefiles, sixteen features. source_layer is the shapefile stem the
     row was read from, which is also where its vintage is stated.';

create table canonical.basin_boundaries (
    boundary_id           text primary key,
    boundary_kind         text not null check (boundary_kind in ('basin', 'play')),
    name                  text not null,
    basin_name            text,
    basin_boundary_id     text references canonical.basin_boundaries (boundary_id),
    sub_basin             text,
    lithology             text,
    age_shale             text,
    area_sq_mi            double precision,
    area_basis            text not null,
    vintage_label         text not null,
    geometry_repair       text,
    geometry_repair_reason text,
    geom                  geometry(MultiPolygon, 4326) not null,
    source_datum          text not null,
    transform_rule_id     text,
    source_manifest_id    text not null references lineage.manifests (manifest_id),
    derivation_id         text not null references lineage.derivations (derivation_id),
    created_at            timestamptz not null default now(),
    check (boundary_kind = 'play' or basin_name is null),
    check (boundary_kind = 'play' or basin_boundary_id is null),
    check (boundary_kind = 'play' or sub_basin is null),
    check (geometry_repair is null or geometry_repair_reason is not null)
);

comment on table canonical.basin_boundaries is
    'One published boundary at one kind. The identity is minted here because EIA publishes no
     feature id — basin_<slug(NAME)>, play_<slug(Shale_play)>_<slug(Basin)> — under
     cr_eia_boundary_publisher_1, which is the row that says whose interpretation this is.';

comment on column canonical.basin_boundaries.basin_name is
    'The play layer''s own Basin string, verbatim. Kept even when it resolves to no basin row,
     so a later crosswalk supersedes cr_eia_basin_link_1 rather than re-deriving from nothing.';

comment on column canonical.basin_boundaries.basin_boundary_id is
    'Null means the publisher''s Basin string matched no basin NAME. The play promotion refuses
     to run before the basin layer is loaded, so it never means the basin layer was absent.';

comment on column canonical.basin_boundaries.vintage_label is
    'The publisher''s own shapefile member name, verbatim — which is where EIA states the
     vintage. The play archive carries three different ones, so this is per feature and never
     per archive.';

comment on column canonical.basin_boundaries.area_sq_mi is
    'The publisher''s own Area_sq_mi. area_basis names it publisher_reported; glasswell does not
     measure these polygons (cr_eia_area_provenance_1).';

comment on column canonical.basin_boundaries.geometry_repair is
    'The repair applied under cr_eia_geometry_repair_1, or null where the published ring was
     already valid. Every repaired row also has a released quarantine row.';

create trigger basin_boundaries_append_only
    before update or delete on canonical.basin_boundaries
    for each row execute function lineage.reject_mutation();

create index basin_boundaries_geom_idx on canonical.basin_boundaries using gist (geom);

create index basin_boundaries_kind_idx on canonical.basin_boundaries (boundary_kind, name);

create table marts.basin_boundaries_tile (
    boundary_id       text primary key,
    boundary_kind     text not null,
    name              text not null,
    basin_name        text,
    basin_boundary_id text,
    sub_basin         text,
    lithology         text,
    age_shale         text,
    area_sq_mi        double precision,
    area_basis        text not null,
    vintage_label     text not null,
    geometry_repair   text,
    derivation_id     text not null,
    geom              geometry(MultiPolygon, 4326) not null
);

comment on table marts.basin_boundaries_tile is
    'The boundary set, one row per published feature. Rebuilt, never appended (§3.0.1).';

create index basin_boundaries_tile_geom_idx on marts.basin_boundaries_tile using gist (geom);

create index basin_boundaries_tile_kind_idx on marts.basin_boundaries_tile (boundary_kind);

create view marts.tile_basins as
select boundary_id, boundary_kind, name, area_sq_mi, area_basis, vintage_label,
       geometry_repair, derivation_id, geom
  from marts.basin_boundaries_tile
 where boundary_kind = 'basin';

create view marts.tile_plays as
select boundary_id, boundary_kind, name, basin_name, basin_boundary_id, sub_basin, lithology,
       age_shale, area_sq_mi, area_basis, vintage_label, geometry_repair, derivation_id, geom
  from marts.basin_boundaries_tile
 where boundary_kind = 'play';

comment on view marts.tile_basins is
    'What the tile server may see. The column list is the publication boundary: martin holds
     select on this view and on no base relation (DR-05).';

comment on view marts.tile_plays is
    'What the tile server may see. The column list is the publication boundary: martin holds
     select on this view and on no base relation (DR-05).';

grant select, insert on staging.eia_basins to glasswell_pipeline;
grant delete on staging.eia_basins to glasswell_pipeline;
grant select, insert on staging.eia_plays to glasswell_pipeline;
grant delete on staging.eia_plays to glasswell_pipeline;
grant select, insert on canonical.basin_boundaries to glasswell_pipeline;
grant select on canonical.basin_boundaries to glasswell_api;
revoke update, delete on canonical.basin_boundaries from glasswell_pipeline, glasswell_api;
grant select on marts.basin_boundaries_tile to glasswell_api;
grant select, insert, delete, truncate on marts.basin_boundaries_tile to glasswell_pipeline;
grant select on marts.tile_basins to martin, glasswell_api;
grant select on marts.tile_plays to martin, glasswell_api;

-- Migration 049 made publication evidence a precondition for every conformance rule, so the
-- eight cr_eia_* decisions register theirs before either home inserts them.
--
-- The evidence below is a PLACEHOLDER and the integrator repoints it at the merge train. A
-- branch cannot know which tag it will ship in — merge order decides that — so guessing a
-- number writes a false claim about when glasswell could know these rules.
-- `lineage.conformance_rule_publications` is append-only and this migration is sha256-pinned
-- once applied, so the repoint must happen BEFORE the production migrate; afterwards the only
-- remedy is a restore.
--
-- Repoint all THREE fields on the insert below, not two:
--   evidence_tag       the UNRELEASED literal -> the tag this actually ships in
--   evidence_commit    the 40-zero literal    -> the `main` head it was written against
--   published_vintage  the date               -> the DATE THAT TAG IS CUT
-- The third is easy to miss and is not independent of the other two: 049's own column comment
-- defines published_vintage as "first repository-tag publication of this immutable rule
-- version", so it is the release date, not the authoring date.
--
-- `scripts/release.py::placeholder_evidence_blockers` refuses to cut a release while either
-- quoted literal is still here, so the tag and the commit cannot ship by omission. The date has
-- no such guard: it is a real date either way, and only a reader can tell whether it is right.

insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
select rule_id, date '2026-08-30', 'UNRELEASED',
       '0000000000000000000000000000000000000000'
  from unnest(array[
       'cr_eia_area_provenance_1', 'cr_eia_basin_link_1', 'cr_eia_boundary_datum_1',
       'cr_eia_boundary_overlap_1', 'cr_eia_boundary_publisher_1',
       'cr_eia_boundary_taxonomy_1', 'cr_eia_geometry_repair_1', 'cr_eia_well_membership_1'
  ]::text[]) rule_id
on conflict (rule_id) do nothing;

-- The eight classing decisions, inserted here for an already-seeded database; a fresh one gets
-- the same content from glasswell.seed.conformance_basins. The guards skip cleanly where the
-- sources are not registered yet — deploy runs migrations before seed_all, so on the first
-- deployed pass these land via the seeder.

insert into lineage.conformance_rules
    (rule_id, rule_family, source_id, stage, applies_to_fields, rule_kind, spec, rule,
     rationale, evidence_url, code_ref, effective_from)
select 'cr_eia_boundary_publisher_1', 'cr_eia_boundary_publisher', 'eia_shale_plays', 'conform',
       '{geom,boundary_id,name}', 'code_ref',
       jsonb_build_object(
           'module_function', 'glasswell.ingest.eia_boundaries:LAYERS',
           'version', '1',
           'publisher', 'US Energy Information Administration',
           'archives', jsonb_build_object(
               'basins', jsonb_build_object(
                   'url', 'https://www.eia.gov/maps/map_data/SedimentaryBasins_US_EIA.zip',
                   'shapefile', 'SedimentaryBasins_US_May2011_v2',
                   'bytes', 440871,
                   'sha256',
                   '02a017ccb84bdcc15726838098e3cfa73450b9655cf06e28d2eca6f3c04edcff',
                   'upstream_last_modified', '2016-03-10T16:39:22Z',
                   'features', 32),
               'plays', jsonb_build_object(
                   'url', 'https://www.eia.gov/maps/map_data/'
                          'TightOil_ShaleGas_IndividualPlays_Lower48_EIA.zip',
                   'bytes', 2931129,
                   'sha256',
                   '20be8ea37727b05fc83e234a3257c069df5e5771b74501f40fc0828a7195c84b',
                   'upstream_last_modified', '2019-01-22T18:17:21Z',
                   'features', 16,
                   'shapefiles', 12)),
           'rejected_publishers', jsonb_build_array(
               'USGS National Oil and Gas Assessment assessment units',
               'state survey basin outlines (ND DMR, TX RRC, NM BGMR)'),
           'identity', 'EIA publishes no feature id on either layer, so the key is minted'
           ' here: basin_<slug(NAME)> and play_<slug(Shale_play)>_<slug(Basin)>. The play pair'
           ' is the key rather than the play name alone because Niobrara is published as five'
           ' features under five different Basin labels. Minting a key is a decision: a'
           ' publisher that later ships its own id supersedes this row.',
           'contract_note', 'canonical.basin_boundaries and both boundary tile layers carry'
           ' this publisher''s own names and areas verbatim under a minted key; the ingest'
           ' module is the executor, and a different publisher is a superseding row, not a'
           ' code change'),
       'Draw basin and play boundaries from the EIA lower-48 map archives; USGS assessment'
       ' units and state-survey outlines are cross-checks, not sources.',
       'The boundary layers a map needs are a published interpretation, and the choice of whose'
       ' interpretation is the decision. EIA was taken over the USGS National Oil and Gas'
       ' Assessment because it publishes basin and play as two separate archives with a stated'
       ' distinction between them, which is the distinction this repository has to keep; USGS'
       ' assessment units are chosen for assessment arithmetic and slice the same rock'
       ' differently, so adopting them would import a boundary set whose purpose is not'
       ' cartographic reference. Both EIA archives are plain anonymous HTTPS zips, so neither'
       ' goes through the ArcGIS host allowlist (blueprint v0.6 §4E.7) and neither needs an'
       ' amendment to it. The vintages are old and stated rather than hidden: the basin layer'
       ' is EIA''s May 2011 compilation republished 2016-03-10, and the play archive is a'
       ' 2019-01-22 bundle whose members carry per-feature vintages between Aug 2015 and Sep'
       ' 2018. A boundary is never authoritative here — it is one agency''s published'
       ' interpretation at a vintage, and vintage_label says which one on every served feature.',
       'https://www.eia.gov/maps/maps.htm',
       'src/glasswell/ingest/eia_boundaries.py', date '2026-08-30'
 where exists (select 1 from lineage.sources where source_id = 'eia_shale_plays')
on conflict (rule_id) do nothing;

insert into lineage.conformance_rules
    (rule_id, rule_family, source_id, stage, applies_to_fields, rule_kind, spec, rule,
     rationale, evidence_url, code_ref, effective_from)
select 'cr_eia_boundary_taxonomy_1', 'cr_eia_boundary_taxonomy', 'eia_shale_plays', 'conform',
       '{boundary_kind,name,basin_name,sub_basin}', 'code_ref',
       jsonb_build_object(
           'module_function', 'glasswell.ingest.eia_boundaries:LAYERS',
           'version', '1',
           'boundary_kind', jsonb_build_object(
               'basin', 'a structural sedimentary basin outline: the depositional container,'
               ' independent of what is producible in it. 32 features, one layer.',
               'play', 'a producible interval''s mapped extent inside one or more basins.'
               ' 16 features over 12 shapefiles, each with its own vintage.'),
           'never_merged', 'the two kinds share canonical.basin_boundaries and are'
           ' discriminated by boundary_kind; they are published as two tile layers and are'
           ' never unioned, because a play extent inside a basin is not a smaller basin',
           'sub_basin', 'carried only where the publisher states one. Wolfcamp is the only'
           ' feature that does (SubBasin = Delaware); Delaware and Midland are also published'
           ' as plays in their own right, which is the publisher''s inconsistency and is'
           ' reproduced rather than reconciled',
           'contract_note', 'marts.basin_boundaries_tile and both boundary tile layers carry'
           ' boundary_kind on every feature; the ingest module is the executor, and merging or'
           ' re-classing the two kinds is a superseding row, not a code change'),
       'A basin and a play are different objects and are stored under one table with an'
       ' explicit boundary_kind discriminator, never conflated and never unioned.',
       'The two words are used interchangeably in trade press and they are not'
       ' interchangeable: the Permian basin is one structural container and Wolfcamp, Bone'
       ' Spring, Spraberry, Delaware, Abo-Yeso and Glorieta-Yeso are six mapped producible'
       ' extents inside it, five of which overlap. A single ''basin'' layer that flattened'
       ' both would make ''wells in the Permian'' answerable two ways with no way to tell'
       ' which was meant. One table with a discriminator keeps the hierarchy joinable without'
       ' asserting that a play is a kind of basin.',
       'https://www.eia.gov/maps/map_data/TightOil_ShaleGas_IndividualPlays_Lower48_EIA.zip',
       'src/glasswell/ingest/eia_boundaries.py', date '2026-08-30'
 where exists (select 1 from lineage.sources where source_id = 'eia_shale_plays')
on conflict (rule_id) do nothing;

insert into lineage.conformance_rules
    (rule_id, rule_family, source_id, stage, applies_to_fields, rule_kind, spec, rule,
     rationale, evidence_url, code_ref, effective_from)
select 'cr_eia_basin_link_1', 'cr_eia_basin_link', 'eia_shale_plays', 'join',
       '{basin_name,basin_boundary_id}', 'code_ref',
       jsonb_build_object(
           'module_function', 'glasswell.ingest.eia_boundaries:_promote_plays',
           'version', '1',
           'match', 'case-folded exact equality between the play layer''s own Basin string and'
           ' the basin layer''s NAME; no suffix stripping, no token overlap, no fuzzy distance',
           'unresolved', 'basin_boundary_id stays null and basin_name keeps the publisher''s'
           ' string verbatim; a play is never dropped for failing to link',
           'measured_2026_08_30', jsonb_build_object(
               'play_features', 16, 'resolved', 12, 'unresolved', 4,
               'refused_near_matches', jsonb_build_object(
                   'Piceance Basin', 'the basin layer publishes UINTA-PICEANCE, a combined'
                   ' outline that is materially larger than the Piceance alone; linking would'
                   ' silently widen the play''s parent',
                   'Denver Basin', 'the basin layer publishes DENVER; the strings differ only'
                   ' by the word Basin, and stripping it is a transform that would also have'
                   ' to be defended for Piceance and Park, where it is wrong',
                   'Park Basin', 'the basin layer publishes NORTH PARK; whether the play''s'
                   ' Park is North Park, Middle Park or both is not stated by the publisher',
                   'North-Central MT', 'a geographic descriptor, not a basin name; the basin'
                   ' layer publishes no feature it can mean')),
           'contract_note', 'canonical.basin_boundaries.basin_boundary_id is populated only by'
           ' this rule and only for plays; the promotion refuses to run before the basin layer'
           ' is loaded, so a null link means the name did not resolve and never means the'
           ' basin layer was absent'),
       'A play links to a basin by case-folded exact name match against the basin layer, and'
       ' links to nothing when the name does not resolve.',
       'The two EIA archives are separate publications with no shared key, so the only join'
       ' available is on a name string, and four of sixteen plays do not resolve: Piceance'
       ' Basin, Denver Basin, Park Basin and North-Central MT. Each is a near miss with a'
       ' plausible repair and each repair is a different guess — strip the word Basin and'
       ' Denver resolves correctly while Piceance resolves into UINTA-PICEANCE, a larger'
       ' container the publisher did not name. A join that is right twelve times and quietly'
       ' wrong twice is worse than one that reports four unresolved links, because only the'
       ' second is visible at /conformance. The publisher''s own string is kept on the row'
       ' either way, so a later rule can supersede this one with a stated crosswalk rather'
       ' than re-deriving it.',
       'https://www.eia.gov/maps/map_data/TightOil_ShaleGas_IndividualPlays_Lower48_EIA.zip',
       'src/glasswell/ingest/eia_boundaries.py', date '2026-08-30'
 where exists (select 1 from lineage.sources where source_id = 'eia_shale_plays')
on conflict (rule_id) do nothing;

insert into lineage.conformance_rules
    (rule_id, rule_family, source_id, stage, applies_to_fields, rule_kind, spec, rule,
     rationale, evidence_url, code_ref, effective_from)
select 'cr_eia_boundary_overlap_1', 'cr_eia_boundary_overlap', 'eia_shale_plays', 'conform',
       '{geom}', 'code_ref',
       jsonb_build_object(
           'module_function', 'glasswell.marts.basin_boundaries:refresh_basin_boundaries',
           'version', '1',
           'policy', 'boundaries are stored and served exactly as published: never dissolved,'
           ' never clipped to one another, never assigned a precedence order',
           'membership_is_a_set', 'a point may be inside zero, one or several plays and inside'
           ' zero or one basins; any consumer needing a single value must name its own'
           ' arbitration rule, which is a new conformance row and not a default here',
           'measured_2026_08_30', jsonb_build_object(
               'permian_plays_overlapping', jsonb_build_array(
                   'Wolfcamp', 'Bone Spring', 'Spraberry', 'Delaware', 'Abo-Yeso',
                   'Glorieta-Yeso'),
               'williston_plays_overlapping', jsonb_build_array('Bakken', 'Three Forks'),
               'note', 'Bakken and Three Forks are stacked intervals over almost the same'
               ' footprint; a dissolve would erase the fact that they are two targets'),
           'outside_everything', 'a point inside no published boundary is unassigned. It is'
           ' never defaulted to the nearest boundary and never to a basin implied by its'
           ' state.',
           'contract_note', 'marts.basin_boundaries_tile carries one row per published feature'
           ' with its geometry unaltered except for the repair cr_eia_geometry_repair_1'
           ' governs; a de-overlapped or dissolved surface is a superseding row'),
       'Published boundaries overlap and are served overlapping; membership is a set, there is'
       ' no precedence, and a location inside none of them is unassigned.',
       'Play polygons nest and intersect by construction — six Permian plays share the same'
       ' ground because they are stacked intervals, not neighbouring territories. Dissolving'
       ' them into a partition would produce a tidy map that answers the wrong question, and'
       ' picking a precedence order would bury a ranking decision in a mart. Serving the'
       ' overlap is the honest surface: it shows the reader that the Permian is six targets,'
       ' and it forces any single-valued basin or play attribute downstream to declare the'
       ' arbitration it used.',
       'https://www.eia.gov/maps/map_data/TightOil_ShaleGas_IndividualPlays_Lower48_EIA.zip',
       'src/glasswell/marts/basin_boundaries.py', date '2026-08-30'
 where exists (select 1 from lineage.sources where source_id = 'eia_shale_plays')
on conflict (rule_id) do nothing;

insert into lineage.conformance_rules
    (rule_id, rule_family, source_id, stage, applies_to_fields, rule_kind, spec, rule,
     rationale, evidence_url, code_ref, effective_from)
select 'cr_eia_geometry_repair_1', 'cr_eia_geometry_repair', 'eia_shale_plays', 'conform',
       '{geom,geometry_repair,geometry_repair_reason}', 'code_ref',
       jsonb_build_object(
           'module_function', 'glasswell.ingest.eia_boundaries:_promote_plays',
           'version', '1',
           'test', 'ST_IsValid on the staged geometry, which holds the source bytes verbatim',
           'repair', 'ST_Multi(ST_CollectionExtract(ST_MakeValid(geom), 3)) — polygonal'
           ' components only, so a repair that sheds a degenerate spike sheds it rather than'
           ' smuggling a line into a polygon column',
           'refusal', 'a repair whose result is empty or not polygonal is refused: the row is'
           ' quarantined invalid_geometry and never promoted',
           'never_silent', 'every repaired feature is written to lineage.quarantine_rows with'
           ' reason_code invalid_geometry and ST_IsValidReason as evidence, then released'
           ' under this rule id with the promotion derivation recorded. The row carries'
           ' geometry_repair and geometry_repair_reason so the repair is visible without'
           ' reading the ledger.',
           'measured_2026_08_30', jsonb_build_object(
               'features_examined', 48, 'invalid', 2,
               'invalid_features', jsonb_build_object(
                   'Bakken', 'Ring Self-intersection at -101.784379615, 48.9030813580001',
                   'Three Forks', 'Ring Self-intersection at -103.224838549,'
                   ' 46.7023706000001'),
               'relative_area_change', 'below 1e-15 for both, i.e. the repair closes a'
               ' self-touching ring and moves no boundary a reader could see',
               'three_forks_note', 'ST_MakeValid returns a GeometryCollection for Three Forks,'
               ' which is why the extract step is part of the repair and not an afterthought'),
           'contract_note', 'canonical.basin_boundaries.geometry_repair names the repair'
           ' applied to each row and is null where none was; repairing by any other operator,'
           ' or promoting an unrepairable geometry, is a superseding row'),
       'An invalid published boundary is repaired by ST_MakeValid with polygonal extraction,'
       ' recorded as a released quarantine row, and refused outright when the repair does not'
       ' yield a polygon.',
       'Two of the forty-eight published features are invalid, and both are Williston plays —'
       ' the two this repository most needs to draw. Quarantining them would remove the Bakken'
       ' from a Bakken product to uphold a rule about ring topology; silently repairing them'
       ' would put a geometry on the map that no publisher published. The third option is the'
       ' one taken: repair, but make the repair a fact. The reject is written with its reason'
       ' code and ST_IsValidReason before it is released under this rule, so /v1/quarantine'
       ' shows a released row rather than nothing at all, and the measured area change is'
       ' recorded so a future reader can see the repair was topological and not cartographic.'
       ' A repair that cannot return a polygon is not a repair and is refused.',
       'https://www.eia.gov/maps/map_data/TightOil_ShaleGas_IndividualPlays_Lower48_EIA.zip',
       'src/glasswell/ingest/eia_boundaries.py', date '2026-08-30'
 where exists (select 1 from lineage.sources where source_id = 'eia_shale_plays')
on conflict (rule_id) do nothing;

insert into lineage.conformance_rules
    (rule_id, rule_family, source_id, stage, applies_to_fields, rule_kind, spec, rule,
     rationale, evidence_url, code_ref, effective_from)
select 'cr_eia_area_provenance_1', 'cr_eia_area_provenance', 'eia_shale_plays', 'conform',
       '{area_sq_mi,area_basis}', 'code_ref',
       jsonb_build_object(
           'module_function', 'glasswell.marts.basin_boundaries:refresh_basin_boundaries',
           'version', '1',
           'area_basis', 'publisher_reported',
           'published_field', 'Area_sq_mi on both archives, carried through unrecomputed and'
           ' rounded to two decimals at the mart boundary',
           'not_recomputed', 'glasswell does not measure these polygons. EIA states no'
           ' equal-area projection for the figure, so a recomputed area would differ from the'
           ' published one by an unstated amount and there would be two areas on the map.',
           'handle', 'every served area rides marts.basin_boundaries_tile alongside the'
           ' refresh derivation_id, which /v1/explain resolves to the manifest the figure came'
           ' from — the figure is the publisher''s, and the handle says so',
           'contract_note', 'area_sq_mi is the publisher''s own number and area_basis names it'
           ' as such on every row; computing an area here is a superseding row that must state'
           ' its projection'),
       'The served area is the publisher''s own Area_sq_mi, labelled publisher_reported, never'
       ' recomputed by glasswell.',
       'An area is a figure and R6 gives it a handle, but the handle has to resolve to the'
       ' truth. Recomputing the area in an equal-area projection would produce a number'
       ' glasswell could defend and EIA never published, sitting next to a name and a boundary'
       ' that are EIA''s — a mixed-provenance row that reads as one source''s. Carrying the'
       ' published figure with area_basis stating its origin keeps the whole row attributable'
       ' to one publication, and leaves recomputation to a superseding rule that would have to'
       ' name the projection it used.',
       'https://www.eia.gov/maps/map_data/SedimentaryBasins_US_EIA.zip',
       'src/glasswell/marts/basin_boundaries.py', date '2026-08-30'
 where exists (select 1 from lineage.sources where source_id = 'eia_shale_plays')
on conflict (rule_id) do nothing;

insert into lineage.conformance_rules
    (rule_id, rule_family, source_id, stage, applies_to_fields, rule_kind, spec, rule,
     rationale, evidence_url, code_ref, effective_from)
select 'cr_eia_well_membership_1', 'cr_eia_well_membership', 'eia_shale_plays', 'join',
       '{geom,boundary_id,api10}', 'code_ref',
       jsonb_build_object(
           'module_function', 'glasswell.marts.basin_boundaries:refresh_basin_boundaries',
           'version', '1',
           'test', 'ST_Intersects between the well''s surface-hole point and the boundary'
           ' polygon, in EPSG:4326, evaluated against the served boundary geometry',
           'anchor', 'the surface hole. The lateral midpoint anchor cr_land_agg_membership_1'
           ' uses is a section-grain choice; at basin grain a lateral is far shorter than the'
           ' smallest boundary and the two anchors agree except at a boundary edge, so the'
           ' simpler anchor is stated rather than the more elaborate one being borrowed.',
           'multiple', 'a well may be inside several plays; membership is the set of'
           ' boundaries it intersects, per cr_eia_boundary_overlap_1, and is not collapsed',
           'unassigned', 'a well inside no boundary is unassigned. It is never defaulted to a'
           ' basin implied by its state or its operator.',
           'not_the_wells_basin_column', 'canonical.wells.basin is a per-source declared'
           ' constant written by the ND and TX ingests, not a geometric test against these'
           ' boundaries, and the two must not be read as the same claim. All 43,817 ND wells'
           ' carry basin=williston because the ND ingest declares it, not because anything'
           ' tested a point against the Williston outline.',
           'no_stored_membership_yet', 'as of this rule''s effective date glasswell serves the'
           ' boundaries and stores no well-to-boundary assignment. This row is the definition'
           ' any basin-scoped rollup must implement, registered before the first consumer'
           ' rather than after it.',
           'contract_note', 'any served figure scoped to a basin or play must cite this rule'
           ' or a superseding one; a rollup that assigns wells by a different anchor, or that'
           ' collapses multi-play membership to a single value, is a superseding row'),
       'A well is inside a basin or play when its surface hole intersects that boundary;'
       ' membership is a set, and a well inside none of them is unassigned.',
       'The map already labels every North Dakota well basin=williston, and that label comes'
       ' from a constant in the ND ingest rather than from any boundary — exactly the'
       ' mapping-in-code R8 exists to refuse. Registering the geometric definition now, before'
       ' the first basin-scoped rollup is built, means the rollup inherits a written'
       ' membership test instead of inventing one, and means the existing declared-constant'
       ' column is on the record as a different claim from the geometric one. No stored'
       ' assignment is derived here: the boundaries are the spine, and a membership mart is'
       ' the consumer this definition is waiting for.',
       'https://www.eia.gov/maps/map_data/TightOil_ShaleGas_IndividualPlays_Lower48_EIA.zip',
       'src/glasswell/marts/basin_boundaries.py', date '2026-08-30'
 where exists (select 1 from lineage.sources where source_id = 'eia_shale_plays')
on conflict (rule_id) do nothing;

insert into lineage.conformance_rules
    (rule_id, rule_family, source_id, stage, applies_to_fields, rule_kind, spec, rule,
     rationale, evidence_url, effective_from)
select 'cr_eia_boundary_datum_1', 'cr_eia_boundary_datum', 'eia_shale_plays', 'conform',
       '{geom}', 'datum_transform',
       jsonb_build_object(
           'source_epsg', 4326,
           'target_epsg', 4326,
           'detect', jsonb_build_object('prj_geogcs', 'GCS_WGS_1984')),
       'Both EIA boundary archives ship WGS 84 geographic coordinates; the transform to'
       ' EPSG:4326 storage is the identity and is still asserted on every fetch.',
       'Every .prj in both archives resolves to EPSG:4326, so the transform does nothing —'
       ' which is precisely why it is a row. The datum is read from the shipped .prj through'
       ' the strict resolver and compared against this rule before a coordinate is staged, so'
       ' a republished archive in a different frame fails loudly instead of landing silently'
       ' shifted. No datum is ever defaulted (same rule as cr_nd_datum_1 and'
       ' cr_blm_plss_datum_1).',
       'https://www.eia.gov/maps/map_data/SedimentaryBasins_US_EIA.zip', date '2026-08-30'
 where exists (select 1 from lineage.sources where source_id = 'eia_shale_plays')
on conflict (rule_id) do nothing;
