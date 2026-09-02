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
            # 073: the jurisdiction registry serves every well count as a figure, so its
            # request derivation has to be able to prove the selector each one addressed.
            ("api.jurisdictions", "response_output"),
            ("api.modeling_publication", "response_output"),
            ("api.type_curve", "response_output"),
            ("api.type_curve_index", "response_output"),
            # 072: the N2 figures are request-computed too — fluid intensity on the
            # completions record, the per-well cumulative and the cohort aggregates.
            ("api.well_completions", "response_output"),
            ("api.well_cumulatives", "response_output"),
            ("api.well_detail", "response_output"),
            # 070: every "wells by" bucket count, remainder and absence figure is
            # request-computed, so the profile is what keeps /v1/explain from answering 422 on
            # a handle the response carries.
            ("api.well_facets", "response_output"),
            ("api.well_status_summary", "response_output"),
            ("api.well_vintage_cohorts", "response_output"),
        ]


def test_the_serving_migration_registers_publication_evidence_before_any_rule(db) -> None:
    """049 makes evidence a precondition; this migration follows 054's
    register-then-seed order."""
    with db.cursor() as cursor:
        cursor.execute(
            "select rule_id, published_vintage, evidence_tag, evidence_commit from"
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
    # Repoint-stable by construction: the merge train rewrites all three evidence fields, so
    # pinning any placeholder literal here would make the correct action turn this red. What
    # survives the repoint is that every row carries one vintage and one evidence pair, and
    # that the tag and the commit agree about whether they have been repointed -- which is
    # what catches a half-repoint across the five rows.
    assert len({row[1] for row in rows}) == 1, "the five rules disagree about their vintage"
    pairs = {(row[2], row[3]) for row in rows}
    assert len(pairs) == 1, f"a half-repoint left mixed publication evidence: {pairs}"
    tag, commit = pairs.pop()
    assert (tag == "UNRELEASED") == (commit == "0" * 40), (
        f"evidence_tag and evidence_commit disagree about being repointed: {tag} / {commit}"
    )


def test_the_boundary_migration_registers_publication_evidence_before_any_rule(db) -> None:
    """The same register-then-seed order for the eight cr_eia_* boundary decisions."""
    with db.cursor() as cursor:
        cursor.execute(
            "select rule_id, published_vintage, evidence_tag, evidence_commit from"
            " lineage.conformance_rule_publications where rule_id like 'cr\\_eia\\_%'"
            " order by rule_id"
        )
        rows = cursor.fetchall()
    assert [row[0] for row in rows] == [
        "cr_eia_area_provenance_1",
        "cr_eia_basin_link_1",
        "cr_eia_boundary_datum_1",
        "cr_eia_boundary_overlap_1",
        "cr_eia_boundary_publisher_1",
        "cr_eia_boundary_taxonomy_1",
        "cr_eia_geometry_repair_1",
        "cr_eia_well_membership_1",
    ]
    # Repoint-stable, for the reason the cr_tc_ block above states: pinning the placeholder
    # literal would turn the merge train's correct action red.
    assert len({row[1] for row in rows}) == 1, "the eight rules disagree about their vintage"
    pairs = {(row[2], row[3]) for row in rows}
    assert len(pairs) == 1, f"a half-repoint left mixed publication evidence: {pairs}"
    tag, commit = pairs.pop()
    assert (tag == "UNRELEASED") == (commit == "0" * 40), (
        f"evidence_tag and evidence_commit disagree about being repointed: {tag} / {commit}"
    )


def test_the_boundary_migration_alone_seeds_no_conformance_rule(db) -> None:
    """The rule bodies need lineage.sources, which migrate() never populates."""
    with db.cursor() as cursor:
        cursor.execute(
            "select count(*) from lineage.conformance_rules where rule_id like 'cr\\_eia\\_%'"
        )
        assert cursor.fetchone()[0] == 0


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
