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
    ("features", "feature_specs"),
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


def test_the_serving_migration_registers_the_modeling_selector_profiles(db) -> None:
    with db.cursor() as cursor:
        cursor.execute(
            "select output_dataset, selector_profile from lineage.selector_output_registry"
            " where operation = 'api.respond' order by output_dataset"
        )
        assert cursor.fetchall() == [
            ("api.modeling_publication", "response_output"),
            ("api.type_curve", "response_output"),
            ("api.type_curve_index", "response_output"),
            ("api.well_detail", "response_output"),
            ("api.well_status_summary", "response_output"),
        ]


def test_the_serving_migration_registers_publication_evidence_before_any_rule(db) -> None:
    """049 makes evidence a precondition; this migration follows 054's
    register-then-seed order."""
    with db.cursor() as cursor:
        cursor.execute(
            "select rule_id, published_vintage, evidence_tag from"
            " lineage.conformance_rule_publications where rule_id like 'cr\\_tc\\_%'"
            " order by rule_id"
        )
        rows = cursor.fetchall()
    assert [row[0] for row in rows] == [
        "cr_tc_normalization_1",
        "cr_tc_peer_ladder_1",
        "cr_tc_publication_scope_1",
        "cr_tc_quantile_convention_1",
        "cr_tc_unavailable_vocab_1",
    ]
    assert {row[1].isoformat() for row in rows} == {"2026-08-30"}
    # A placeholder the integrator repoints at the merge train, not a guessed tag: the table
    # is append-only, so a wrong first-publication vintage cannot be corrected afterwards.
    assert {row[2] for row in rows} == {"UNRELEASED"}


def test_the_migration_alone_seeds_no_conformance_rule(db) -> None:
    """The rule bodies need lineage.sources, which migrate() never populates."""
    with db.cursor() as cursor:
        cursor.execute(
            "select count(*) from lineage.conformance_rules where rule_id like 'cr\\_tc\\_%'"
        )
        assert cursor.fetchone()[0] == 0


def test_postgis_is_available(empty_db):
    migrate(empty_db)
    empty_db.commit()
    with empty_db.cursor() as cursor:
        cursor.execute("select postgis_version()")
        row = cursor.fetchone()
    assert row is not None


def test_status_runtime_role_can_read_only_the_migration_ledger(empty_db):
    migrate(empty_db)
    empty_db.commit()
    with empty_db.cursor() as cursor:
        cursor.execute(
            "select has_table_privilege('glasswell_api', 'public.schema_migrations', 'select'),"
            " has_table_privilege('glasswell_api', 'public.schema_migrations', 'insert'),"
            " has_table_privilege('glasswell_api', 'public.schema_migrations', 'update'),"
            " has_table_privilege('glasswell_api', 'public.schema_migrations', 'delete')"
        )
        privileges = cursor.fetchone()
    assert privileges == (True, False, False, False)


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
