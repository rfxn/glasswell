"""The N2 schema: the completion-design canonical table and the two cumulative marts.

The head-version assertion reads `discover_migrations()` rather than a literal, so the
integrator can renumber the file at the merge train without editing a test.
"""

from __future__ import annotations

from datetime import date

import psycopg
import pytest

from glasswell.db.migrate import discover_migrations
from tests.support.seed import seed_derivation, seed_manifest

DESIGN_COLUMNS = {
    "disclosure_id",
    "api10",
    "base_water_volume",
    "base_water_unit",
    "base_water_null_semantics",
    "source_id",
    "report_vintage",
    "source_manifest_id",
    "derivation_id",
    "created_at",
}

REGISTRY_ROWS = {
    ("canonical.promote", "canonical.well_completion_design", "completion_design"),
    ("mart.refresh", "marts.well_cumulatives", "well_cumulative"),
    ("api.respond", "api.well_cumulatives", "response_output"),
    ("api.respond", "api.well_vintage_cohorts", "response_output"),
    ("api.respond", "api.well_completions", "response_output"),
}


@pytest.fixture
def a_design_row(db: psycopg.Connection) -> tuple[str, str]:
    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.sources (source_id, name) values ('fracfocus_csv', 'FracFocus')"
            " on conflict (source_id) do nothing"
        )
    manifest_id = seed_manifest(db, sha256="9" * 64, source_id="fracfocus_csv",
                                source_key="registryupload.zip")
    derivation_id = seed_derivation(db)
    with db.cursor() as cursor:
        cursor.execute(
            "insert into canonical.well_completion_design (disclosure_id, api10,"
            " base_water_volume, base_water_unit, base_water_null_semantics, source_id,"
            " report_vintage, source_manifest_id, derivation_id)"
            " values ('ff-migration-0001', '3305310451', 6342549, 'gal', 'reported',"
            " 'fracfocus_csv', %s, %s, %s)",
            (date(2026, 8, 1), manifest_id, derivation_id),
        )
    return manifest_id, derivation_id


def test_the_design_table_carries_the_columns_the_promotion_writes(db: psycopg.Connection):
    with db.cursor() as cursor:
        cursor.execute(
            "select column_name from information_schema.columns"
            " where table_schema = 'canonical' and table_name = 'well_completion_design'"
        )
        found = {row[0] for row in cursor.fetchall()}
    assert found >= DESIGN_COLUMNS


def test_the_design_table_refuses_an_update(db: psycopg.Connection, a_design_row):
    with pytest.raises(psycopg.errors.RestrictViolation), db.cursor() as cursor:
        cursor.execute(
            "update canonical.well_completion_design set base_water_volume = 1"
            " where disclosure_id = 'ff-migration-0001'"
        )
    db.rollback()


def test_the_design_table_refuses_a_delete(db: psycopg.Connection, a_design_row):
    with pytest.raises(psycopg.errors.RestrictViolation), db.cursor() as cursor:
        cursor.execute(
            "delete from canonical.well_completion_design"
            " where disclosure_id = 'ff-migration-0001'"
        )
    db.rollback()


def test_the_design_table_admits_only_the_four_canonical_null_semantics(
    db: psycopg.Connection, a_design_row
):
    manifest_id, derivation_id = a_design_row
    with pytest.raises(psycopg.errors.CheckViolation):
        with db.cursor() as cursor:
            cursor.execute(
                "insert into canonical.well_completion_design (disclosure_id, api10,"
                " base_water_volume, base_water_unit, base_water_null_semantics, source_id,"
                " report_vintage, source_manifest_id, derivation_id)"
                " values ('ff-migration-0002', '3305310451', null, 'gal', 'unknown',"
                " 'fracfocus_csv', %s, %s, %s)",
                (date(2026, 8, 1), manifest_id, derivation_id),
            )
    db.rollback()


def test_the_latest_view_ranks_one_row_per_disclosure_and_source(
    db: psycopg.Connection, a_design_row
):
    with db.cursor() as cursor:
        cursor.execute(
            "select base_water_volume from canonical.well_completion_design_latest"
            " where disclosure_id = 'ff-migration-0001'"
        )
        assert [row[0] for row in cursor.fetchall()] == [6342549]


def test_the_cumulative_marts_are_keyed_the_way_their_grains_differ(db: psycopg.Connection):
    """Two grains, two tables: ND withholding is month-grained, not stream-grained."""
    with db.cursor() as cursor:
        cursor.execute(
            "select conrelid::regclass::text, array_agg(attname order by attname)"
            "  from pg_constraint"
            "  join pg_attribute on attrelid = conrelid and attnum = any(conkey)"
            " where contype = 'p'"
            "   and conrelid in ('marts.well_cumulatives'::regclass,"
            "                    'marts.well_withholding'::regclass)"
            " group by conrelid"
        )
        keys = dict(cursor.fetchall())
    assert keys["marts.well_cumulatives"] == ["api10", "stream"]
    assert keys["marts.well_withholding"] == ["api10"]


# The three relations this migration adds, named rather than discovered: a schema-wide sweep
# would fail on 045_nd_neighbors, whose ^33 regex is a deliberate pre-existing scope.
_ADDED_RELATIONS = (
    "marts.well_cumulatives",
    "marts.well_withholding",
    "canonical.well_completion_design",
)


def test_the_relations_this_migration_adds_carry_no_single_state_regex(db: psycopg.Connection):
    """R14: Montana widens a Python constant, never an ALTER (045_nd_neighbors.sql:5,55).

    Constraints and indexes both: a partial index with a `^33` predicate scopes the relation
    just as hard as a CHECK does, and the earlier name claimed every new relation while the
    body read three tables' constraints (gate-v075 NIT-4).
    """
    relations = ", ".join(f"'{name}'::regclass" for name in _ADDED_RELATIONS)
    with db.cursor() as cursor:
        cursor.execute(
            "select conname, pg_get_constraintdef(oid) from pg_constraint"
            f" where conrelid in ({relations})"
        )
        definitions = [row[1] for row in cursor.fetchall()]
        cursor.execute(
            "select indexname, indexdef from pg_indexes"
            " where schemaname || '.' || tablename = any(%(names)s)",
            {"names": list(_ADDED_RELATIONS)},
        )
        definitions += [row[1] for row in cursor.fetchall()]
    assert definitions, "no constraint or index found: the query no longer sees the relations"
    assert not [item for item in definitions if "33" in item and "~" in item]


def test_the_api_role_reads_the_marts_but_cannot_write_them(db: psycopg.Connection):
    with db.cursor() as cursor:
        cursor.execute(
            "select has_table_privilege('glasswell_api', 'marts.well_cumulatives', 'SELECT'),"
            " has_table_privilege('glasswell_api', 'marts.well_cumulatives', 'INSERT'),"
            " has_table_privilege('glasswell_api', 'marts.well_withholding', 'SELECT'),"
            " has_table_privilege('glasswell_api', 'marts.well_withholding', 'INSERT')"
        )
        assert cursor.fetchone() == (True, False, True, False)


def test_the_pipeline_role_may_rebuild_the_marts(db: psycopg.Connection):
    with db.cursor() as cursor:
        cursor.execute(
            "select bool_and(has_table_privilege('glasswell_pipeline',"
            " 'marts.well_cumulatives', privilege))"
            " from unnest(array['SELECT', 'INSERT', 'DELETE', 'TRUNCATE']) as privilege"
        )
        assert cursor.fetchone()[0] is True


def test_neither_serving_role_may_mutate_the_design_table(db: psycopg.Connection):
    with db.cursor() as cursor:
        cursor.execute(
            "select has_table_privilege('glasswell_api',"
            " 'canonical.well_completion_design', 'SELECT'),"
            " has_table_privilege('glasswell_api', 'canonical.well_completion_design', 'UPDATE'),"
            " has_table_privilege('glasswell_api', 'canonical.well_completion_design', 'DELETE'),"
            " has_table_privilege('glasswell_pipeline',"
            " 'canonical.well_completion_design', 'UPDATE'),"
            " has_table_privilege('glasswell_pipeline',"
            " 'canonical.well_completion_design', 'DELETE')"
        )
        assert cursor.fetchone() == (True, False, False, False, False)


def test_the_selector_output_registry_holds_this_track_s_five_rows(db: psycopg.Connection):
    with db.cursor() as cursor:
        cursor.execute(
            "select operation, output_dataset, selector_profile"
            " from lineage.selector_output_registry"
            " where output_dataset in ('canonical.well_completion_design',"
            " 'marts.well_cumulatives', 'api.well_cumulatives', 'api.well_vintage_cohorts',"
            " 'api.well_completions')"
        )
        assert {tuple(row) for row in cursor.fetchall()} == REGISTRY_ROWS


def test_the_well_vintage_term_states_the_cohort_key_in_its_expanded_text(
    db: psycopg.Connection,
):
    """m5: the short definition keeps the industry meaning; the key choice is expanded text."""
    with db.cursor() as cursor:
        cursor.execute(
            "select short_definition, expanded_definition from canonical.glossary_terms"
            " where term_id = 'gt_vintage_well_vintage'"
        )
        short, expanded = cursor.fetchone()
    assert "spud" not in short.lower()
    assert "spud" in expanded.lower()


def test_the_new_glossary_terms_are_resident(db: psycopg.Connection):
    with db.cursor() as cursor:
        cursor.execute(
            "select term_id from canonical.glossary_terms"
            " where term_id in ('gt_fluid_intensity', 'gt_cumulative_production')"
        )
        assert {row[0] for row in cursor.fetchall()} == {
            "gt_fluid_intensity",
            "gt_cumulative_production",
        }


def test_the_ledger_head_is_the_last_migration_on_disk(db: psycopg.Connection):
    """A renumber at the merge train is a `git mv`, not a test edit (C10)."""
    with db.cursor() as cursor:
        cursor.execute("select max(version) from public.schema_migrations")
        assert cursor.fetchone()[0] == discover_migrations()[-1].version
