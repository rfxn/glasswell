from __future__ import annotations

from datetime import date

import psycopg
import pytest

from tests.support.seed import seed_derivation, seed_manifest, seed_well, seed_well_spatial

ND_TABLES = [
    ("staging", "nd_mpr_oil"),
    ("staging", "nd_gis_wells"),
    ("staging", "nd_gis_laterals"),
    ("staging", "nd_gis_spacing_units"),
    ("staging", "nd_gis_directionals"),
    ("canonical", "wells"),
    ("canonical", "well_spatial"),
    ("canonical", "spacing_units"),
    ("canonical", "well_survey_stations"),
    ("canonical", "glossary_terms"),
    ("lineage", "nd_status_map"),
    ("lineage", "nd_stream_map"),
    ("lineage", "nd_survey_segment_map"),
    ("marts", "nd_well_card"),
    ("marts", "nd_laterals_tile"),
    ("marts", "nd_wells_tile"),
    ("marts", "nd_survey_traces_tile"),
]

GEOMETRY_COLUMNS = [
    ("staging", "nd_gis_wells", "POINT"),
    # The layer ships multi-part centrelines; refusing them dropped six laterals (A5-F8).
    ("staging", "nd_gis_laterals", "GEOMETRY"),
    ("staging", "nd_gis_spacing_units", "MULTIPOLYGON"),
    ("staging", "nd_gis_directionals", "POINT"),
    ("canonical", "well_spatial", "GEOMETRY"),
    ("canonical", "spacing_units", "MULTIPOLYGON"),
    ("canonical", "well_survey_stations", "POINT"),
    ("marts", "nd_laterals_tile", "GEOMETRY"),
    ("marts", "nd_wells_tile", "POINT"),
    ("marts", "nd_survey_traces_tile", "LINESTRING"),
]

STAGING_LINEAGE_COLUMNS = ("manifest_id", "source_row_ordinal", "ingested_at")


def columns(connection: psycopg.Connection, schema: str, table: str) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            "select column_name from information_schema.columns"
            " where table_schema = %s and table_name = %s",
            (schema, table),
        )
        return {row[0] for row in cursor.fetchall()}


@pytest.mark.parametrize(("schema", "table"), ND_TABLES)
def test_the_nd_slice_table_exists_in_its_own_schema(db, schema, table):
    with db.cursor() as cursor:
        cursor.execute("select to_regclass(%s)", (f"{schema}.{table}",))
        assert cursor.fetchone()[0] is not None


@pytest.mark.parametrize(("schema", "table"), [(s, t) for s, t in ND_TABLES if s == "staging"])
def test_every_staging_row_can_be_traced_to_the_bytes_it_came_from(db, schema, table):
    assert set(STAGING_LINEAGE_COLUMNS) <= columns(db, schema, table)


def test_wells_is_keyed_by_api10_and_the_date_the_record_took_effect(db):
    with db.cursor() as cursor:
        cursor.execute(
            "select k.column_name from information_schema.table_constraints c"
            " join information_schema.key_column_usage k"
            "   on k.constraint_name = c.constraint_name"
            "  and k.constraint_schema = c.constraint_schema"
            " where c.table_schema = 'canonical' and c.table_name = 'wells'"
            "   and c.constraint_type = 'PRIMARY KEY'"
            " order by k.ordinal_position"
        )
        assert [row[0] for row in cursor.fetchall()] == ["api10", "effective_from"]


def test_a_later_gis_refresh_appends_a_row_instead_of_being_refused(db):
    seed_well(db, api10="3305303901", effective_from=date(2026, 6, 1), status_canonical="drilling")
    seed_well(db, api10="3305303901", effective_from=date(2026, 8, 1), status_canonical="active")
    with db.cursor() as cursor:
        cursor.execute("select count(*) from canonical.wells where api10 = '3305303901'")
        assert cursor.fetchone()[0] == 2


def test_wells_latest_resolves_to_the_greatest_effective_from(db):
    seed_well(db, api10="3305303901", effective_from=date(2026, 6, 1), status_canonical="drilling")
    seed_well(db, api10="3305303901", effective_from=date(2026, 8, 1), status_canonical="active")
    with db.cursor() as cursor:
        cursor.execute("select api10, status_canonical from canonical.wells_latest")
        assert cursor.fetchall() == [("3305303901", "active")]


def test_wells_latest_exposes_later_well_schema_columns(db):
    assert {"total_depth_ft", "completion_date"} <= columns(db, "canonical", "wells_latest")


def test_a_wells_row_cannot_be_edited_in_place(db):
    seed_well(db, api10="3305303901")
    with pytest.raises(psycopg.errors.RestrictViolation, match="append_only_violation"), db.cursor() as cursor:  # noqa: E501
        cursor.execute("update canonical.wells set status_canonical = 'plugged'")
    db.rollback()


def test_a_well_spatial_row_cannot_be_edited_in_place(db):
    seed_well(db, api10="3305303901")
    seed_well_spatial(db, api10="3305303901")
    with pytest.raises(psycopg.errors.RestrictViolation, match="append_only_violation"), db.cursor() as cursor:  # noqa: E501
        cursor.execute("update canonical.well_spatial set source_datum = 'EPSG:4326'")
    db.rollback()


@pytest.mark.parametrize(("schema", "table", "geometry_type"), GEOMETRY_COLUMNS)
def test_every_stored_geometry_declares_its_type_and_stores_in_4326(
    db, schema, table, geometry_type
):
    with db.cursor() as cursor:
        cursor.execute(
            "select type, srid from geometry_columns"
            " where f_table_schema = %s and f_table_name = %s and f_geometry_column = 'geom'",
            (schema, table),
        )
        assert cursor.fetchone() == (geometry_type, 4326)


@pytest.mark.parametrize(
    ("schema", "table"),
    [
        ("canonical", "well_spatial"),
        ("canonical", "spacing_units"),
        ("marts", "nd_laterals_tile"),
        ("marts", "nd_wells_tile"),
    ],
)
def test_every_served_geometry_column_has_a_gist_index(db, schema, table):
    with db.cursor() as cursor:
        cursor.execute(
            "select indexdef from pg_indexes where schemaname = %s and tablename = %s",
            (schema, table),
        )
        definitions = [row[0] for row in cursor.fetchall()]
    assert [d for d in definitions if "USING gist" in d and "(geom)" in d]


def test_well_spatial_is_keyed_so_a_well_can_carry_several_laterals(db):
    seed_well(db, api10="3305303901")
    seed_well_spatial(db, api10="3305303901", geom_key="33053039010000_LAT1")
    seed_well_spatial(db, api10="3305303901", geom_key="33053039010000_LAT2")
    with db.cursor() as cursor:
        cursor.execute("select count(*) from canonical.well_spatial")
        assert cursor.fetchone()[0] == 2


def test_a_glossary_term_cannot_be_seeded_twice_under_two_ids(db):
    insert = (
        "insert into canonical.glossary_terms"
        " (term_id, term, short_definition, expanded_definition) values (%s, 'Manifest', 's', 'e')"
    )
    with db.cursor() as cursor:
        cursor.execute(insert, ("gt_a",))
    with pytest.raises(psycopg.errors.UniqueViolation), db.cursor() as cursor:
        cursor.execute(insert, ("gt_b",))
    db.rollback()


def test_production_carries_the_three_null_meanings_it_must_never_collapse(db):
    with db.cursor() as cursor:
        cursor.execute(
            "select column_default, is_nullable from information_schema.columns"
            " where table_schema = 'canonical' and table_name = 'production_monthly'"
            "   and column_name = 'null_semantics'"
        )
        assert cursor.fetchone() == ("'reported'::text", "NO")
        cursor.execute(
            "select pg_get_constraintdef(oid) from pg_constraint"
            " where conrelid = 'canonical.production_monthly'::regclass"
            "   and pg_get_constraintdef(oid) like '%null_semantics%'"
        )
        definition = cursor.fetchone()[0]
    for state in ("reported", "reported_zero", "no_report", "withheld"):
        assert state in definition


def test_the_default_serving_view_exposes_null_semantics(db):
    assert "null_semantics" in columns(db, "canonical", "production_monthly_latest")


def test_a_mart_is_rebuildable_because_marts_are_not_append_only(db):
    derivation = seed_derivation(db)
    with db.cursor() as cursor:
        cursor.execute(
            "insert into marts.nd_wells_tile (api10, geom, derivation_id)"
            " values ('3305303901', st_setsrid(st_point(-103.58, 47.91), 4326), %s)",
            (derivation,),
        )
        cursor.execute("delete from marts.nd_wells_tile")
        cursor.execute("select count(*) from marts.nd_wells_tile")
        assert cursor.fetchone()[0] == 0
    db.rollback()


@pytest.mark.parametrize(
    ("role", "table", "privilege", "expected"),
    [
        ("glasswell_api", "canonical.wells", "select", True),
        ("glasswell_api", "marts.nd_wells_tile", "select", True),
        ("glasswell_api", "canonical.wells", "insert", False),
        ("glasswell_pipeline", "staging.nd_mpr_oil", "insert", True),
        # --restage clears a manifest's staged rows and re-parses them from the raw bytes;
        # staging is the parser's own scratch layer, so the delete belongs to the pipeline.
        ("glasswell_pipeline", "staging.nd_gis_laterals", "delete", True),
        ("glasswell_pipeline", "staging.nd_mpr_oil", "delete", True),
        ("glasswell_pipeline", "canonical.wells", "insert", True),
        # Canonical stays append-only whatever staging may do.
        ("glasswell_pipeline", "canonical.wells", "delete", False),
        ("glasswell_pipeline", "marts.nd_wells_tile", "delete", True),
        ("glasswell_pipeline", "marts.nd_wells_tile", "truncate", True),
    ],
)
def test_the_two_runtime_roles_hold_exactly_the_rights_their_job_needs(
    db, role, table, privilege, expected
):
    with db.cursor() as cursor:
        cursor.execute("select has_table_privilege(%s, %s, %s)", (role, table, privilege))
        assert cursor.fetchone()[0] is expected


def test_a_lateral_geometry_row_records_the_manifest_and_derivation_that_placed_it(db):
    manifest = seed_manifest(db, sha256="c" * 64)
    derivation = seed_derivation(db)
    seed_well(db, api10="3305303901")
    seed_well_spatial(
        db,
        api10="3305303901",
        geom_key="33053039010000_LAT1",
        manifest_id=manifest,
        derivation_id=derivation,
    )
    with db.cursor() as cursor:
        cursor.execute(
            "select source_manifest_id, derivation_id, st_srid(geom) from canonical.well_spatial"
        )
        assert cursor.fetchone() == (manifest, derivation, 4326)
