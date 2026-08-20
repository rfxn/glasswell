from __future__ import annotations

import psycopg
import pytest

from glasswell.db.migrate import MigrationError, discover_migrations, migrate

SPINE_TABLES = [
    ("lineage", "derivations"),
    ("lineage", "derivation_inputs"),
    ("lineage", "derivation_rules"),
    ("lineage", "manifests"),
    ("lineage", "audit_events"),
    ("lineage", "conformance_rules"),
    ("lineage", "crs_registry"),
    ("lineage", "formation_aliases"),
    ("lineage", "operator_aliases"),
    ("lineage", "models"),
    ("lineage", "forecast_grades"),
    ("lineage", "quarantine_rows"),
    ("lineage", "vintages"),
    ("lineage", "environments"),
    ("lineage", "recipes"),
    ("lineage", "sources"),
    ("canonical", "production_monthly"),
]


def table_exists(connection: psycopg.Connection, schema: str, table: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute("select to_regclass(%s)", (f"{schema}.{table}",))
        row = cursor.fetchone()
    return row is not None and row[0] is not None


def test_migrating_an_empty_database_applies_every_migration(empty_db):
    applied = migrate(empty_db)
    empty_db.commit()
    assert [m.version for m in applied] == [m.version for m in discover_migrations()]


def test_running_the_migrator_twice_is_a_no_op(empty_db):
    migrate(empty_db)
    empty_db.commit()
    assert migrate(empty_db) == []
    empty_db.commit()

    with empty_db.cursor() as cursor:
        cursor.execute("select count(*) from public.schema_migrations")
        row = cursor.fetchone()
    assert row is not None
    assert row[0] == len(discover_migrations())


def test_every_spine_table_and_view_exists_after_migration(empty_db):
    migrate(empty_db)
    empty_db.commit()
    expected = [
        *SPINE_TABLES,
        ("lineage", "manifest_head"),
        ("canonical", "production_monthly_latest"),
    ]
    missing = [f"{s}.{t}" for s, t in expected if not table_exists(empty_db, s, t)]
    assert missing == []


def test_postgis_is_available(empty_db):
    migrate(empty_db)
    empty_db.commit()
    with empty_db.cursor() as cursor:
        cursor.execute("select postgis_version()")
        row = cursor.fetchone()
    assert row is not None


def test_an_edited_applied_migration_is_refused(empty_db):
    migrate(empty_db)
    empty_db.commit()
    with empty_db.cursor() as cursor:
        cursor.execute("update public.schema_migrations set sha256 = 'tampered' where version = 1")
    empty_db.commit()

    with pytest.raises(MigrationError, match="changed after it was applied"):
        migrate(empty_db)


def test_a_failing_migration_leaves_no_partial_version_row(empty_db, tmp_path):
    (tmp_path / "001_good.sql").write_text("create table public.ok_marker (id int);")
    (tmp_path / "002_bad.sql").write_text("create table public.ok_marker (id int);")

    with pytest.raises(psycopg.errors.DuplicateTable):
        migrate(empty_db, tmp_path)
    empty_db.rollback()

    with empty_db.cursor() as cursor:
        cursor.execute("select version from public.schema_migrations order by version")
        assert [row[0] for row in cursor.fetchall()] == [1]
