-- The OCD public wells layer: a second, independent measurement of the same New Mexico well
-- population the FTP header archive carries. It refreshes daily upstream while that archive is
-- frozen at 2026-08-20, so the two disagree by construction and the disagreement is the point —
-- it is what makes a cross-source parity rule a measurement rather than a rhetorical device.
--
-- Staging is the terminus for this source, exactly as it is for nm_c115b_upstream. The parity
-- measurement decides whether and how it promotes; promoting first would make the parity rule a
-- rationalisation of a choice already made.

create table staging.nm_ocd_wells_gis (
    manifest_id             text not null references lineage.manifests (manifest_id),
    source_row_ordinal      integer not null,
    ingested_at             timestamptz not null default now(),
    id                      text,
    name                    text,
    type                    text,
    status                  text,
    sub_type_code           text,
    ogrid                   text,
    ogrid_name              text,
    district_code           text,
    district                text,
    county_code             text,
    county                  text,
    ulstr                   text,
    latitude                text,
    longitude               text,
    projection              text,
    directional_status      text,
    details                 text,
    files                   text,
    year_spudded            text,
    spud_date               text,
    lease_type              text,
    measured_vertical_depth text,
    true_vertical_depth     text,
    pool_id_list            text,
    last_production_date    text,
    plug_date               text,
    geom                    geometry(Point, 4326),
    primary key (manifest_id, source_row_ordinal)
);

comment on table staging.nm_ocd_wells_gis is
    'Every column text: staging is source-faithful and holds no opinions. `id` keeps the dashed
     API-10 the service ships; cr_nm_wells_gis_api10_1 is what undashes it, and a row whose id
     will not normalise is staged anyway and held beside itself.';
comment on column staging.nm_ocd_wells_gis.ulstr is
    'The layer''s PLSS unit-letter/section/township/range string. Not read by anything yet: it
     is the seam a New Mexico land grid would attach to, and it is staged so that decision is
     not blocked on a re-fetch.';

grant select, insert on staging.nm_ocd_wells_gis to glasswell_pipeline;
grant delete on staging.nm_ocd_wells_gis to glasswell_pipeline;

-- Migration 049 makes publication evidence a precondition for the conformance rows this
-- source's seeder inserts. v0.68 is the first tag to contain the ids; the commit is the `main`
-- head the branch was written against.
insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
select rule_id, date '2026-08-30', 'v0.68',
       'c8cffbc344e1ea36e454e43f3c0a4d7696aa1c0a'
  from unnest(array[
       'cr_nm_wells_gis_source_1', 'cr_nm_wells_gis_walk_order_1',
       'cr_nm_wells_gis_api10_1', 'cr_nm_wells_gis_datum_1', 'cr_nm_wells_gis_parity_1'
  ]::text[]) as rule_id
on conflict (rule_id) do nothing;
