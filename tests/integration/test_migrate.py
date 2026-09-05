from __future__ import annotations

import multiprocessing
import re
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from glasswell.db.migrate import MigrationError, discover_migrations, migrate
from tests.conftest import create_database, drop_database

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
            # The Texas validators: three residual ledgers, every count and share a figure, so
            # the response derivation records the selector each one addressed.
            ("api.allocation_validators", "response_output"),
            # 073: the jurisdiction registry serves every well count as a figure, so its
            # request derivation has to be able to prove the selector each one addressed.
            ("api.jurisdictions", "response_output"),
            ("api.modeling_publication", "response_output"),
            # The summed per-well Texas series is computed over a well's lease shares at
            # request time and is stored nowhere, so this is the only address it has.
            ("api.tx_production", "response_output"),
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
            # The per-lateral-foot arm divides a served volume by a served length, so the
            # point's own handle has to resolve both and the profile is what lets it.
            ("api.well_production", "response_output"),
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


# 063's own eight. Named rather than matched on the prefix: a later train appending a
# corrected successor under the same prefix publishes it on that train's evidence, and a
# prefix scan would read the two pairs as 063 having been half-repointed.
BOUNDARY_RULES = (
    "cr_eia_area_provenance_1",
    "cr_eia_basin_link_1",
    "cr_eia_boundary_datum_1",
    "cr_eia_boundary_overlap_1",
    "cr_eia_boundary_publisher_1",
    "cr_eia_boundary_taxonomy_1",
    "cr_eia_geometry_repair_1",
    "cr_eia_well_membership_1",
)


def test_the_boundary_migration_registers_publication_evidence_before_any_rule(db) -> None:
    """The same register-then-seed order for the eight cr_eia_* boundary decisions."""
    with db.cursor() as cursor:
        cursor.execute(
            "select rule_id, published_vintage, evidence_tag, evidence_commit from"
            " lineage.conformance_rule_publications where rule_id = any(%s) order by rule_id",
            (list(BOUNDARY_RULES),),
        )
        rows = cursor.fetchall()
    assert [row[0] for row in rows] == list(BOUNDARY_RULES)
    # Repoint-stable, for the reason the cr_tc_ block above states: pinning the placeholder
    # literal would turn the merge train's correct action red.
    assert len({row[1] for row in rows}) == 1, "the eight rules disagree about their vintage"
    pairs = {(row[2], row[3]) for row in rows}
    assert len(pairs) == 1, f"a half-repoint left mixed publication evidence: {pairs}"
    tag, commit = pairs.pop()
    assert (tag == "UNRELEASED") == (commit == "0" * 40), (
        f"evidence_tag and evidence_commit disagree about being repointed: {tag} / {commit}"
    )


def test_a_corrected_successor_is_published_on_its_own_trains_evidence(db) -> None:
    """The scoping above is honest only if the successors are actually there and actually
    carry a pair of their own: a rule id nobody publishes cannot be seeded at all (049)."""
    with db.cursor() as cursor:
        cursor.execute(
            "select rule_id from lineage.conformance_rule_publications"
            " where rule_id like 'cr\\_eia\\_%' and rule_id not like '%\\_1'"
            " order by rule_id"
        )
        successors = [row[0] for row in cursor.fetchall()]

    assert successors == ["cr_eia_basin_link_2", "cr_eia_geometry_repair_2"]




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


# Four sessions, the shard count, each migrating its own database against one cluster. Roles
# are cluster-global, so `if not exists (select 1 from pg_roles ...)` is a check and not a
# lock: all four pass it in the same instant and all four issue the CREATE. The first sharded
# CI run errored 843 tests on `pg_authid_rolname_index`.
RACE_SESSIONS = 4
RACE_ROUNDS = 6
ROLE_DECLARATION = re.compile(r"create role (\w+)")
DO_BLOCK = re.compile(r"do \$\$.*?\$\$;", re.DOTALL)


def role_creating_blocks() -> str:
    """The DO blocks 001, 026 and 076 ship, read out of the migrations rather than restated."""
    blocks = [
        block
        for migration in discover_migrations()
        for block in DO_BLOCK.findall(migration.sql)
        if "create role" in block
    ]
    assert blocks, "no migration creates a role; this test has lost its subject"
    return "\n".join(blocks)


def race_migration(marker: str) -> tuple[str, list[str]]:
    """The shipped blocks with role names this test owns, so the race is open every round."""
    sql = role_creating_blocks()
    names = []
    for index, declared in enumerate(dict.fromkeys(ROLE_DECLARATION.findall(sql))):
        name = f"gw_race_{marker}_{index}"
        sql = sql.replace(declared, name)
        names.append(name)
    return sql, names


def _migrate_in_a_race(dsn_template: str, sql: str, barrier, results, index: int) -> None:
    database = f"gw_race_db_{index}_{uuid4().hex[:8]}"
    directory = Path(tempfile.mkdtemp(prefix="gw-race-"))
    (directory / "001_race_probe.sql").write_text(sql, encoding="utf-8")
    dsn = create_database(dsn_template, database)
    barrier.wait()
    try:
        with psycopg.connect(dsn) as connection:
            migrate(connection, directory)
            connection.commit()
        results[index] = "ok"
    except Exception as error:  # the point of the case is which class arrives here
        results[index] = f"{type(error).__name__}({getattr(error, 'sqlstate', None)}): {error}"
    finally:
        shutil.rmtree(directory, ignore_errors=True)
        drop_database(dsn_template, database)


def test_four_sessions_migrating_one_cluster_do_not_collide_on_its_roles(
    postgres_server: str,
) -> None:
    """A migration that checks a cluster-global catalogue and then writes to it is racing
    every other session migrating a different database on the same cluster. The race is
    forced rather than waited for: every session starts on one barrier."""
    context = multiprocessing.get_context("fork")
    for _ in range(RACE_ROUNDS):
        sql, names = race_migration(uuid4().hex[:10])
        barrier = context.Barrier(RACE_SESSIONS)
        with context.Manager() as manager:
            outcomes = manager.list([""] * RACE_SESSIONS)
            workers = [
                context.Process(
                    target=_migrate_in_a_race,
                    args=(postgres_server, sql, barrier, outcomes, index),
                )
                for index in range(RACE_SESSIONS)
            ]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(180)
            failures = [outcome for outcome in outcomes if outcome != "ok"]

        with psycopg.connect(
            postgres_server.format(database="postgres"), autocommit=True
        ) as admin:
            created = {
                row[0]
                for row in admin.execute(
                    "select rolname from pg_roles where rolname = any(%s)", (names,)
                ).fetchall()
            }
            for name in names:
                admin.execute(f'drop role if exists "{name}"')

        assert not failures, failures
        assert created == set(names), sorted(set(names) - created)


def test_a_migration_that_always_loses_the_unique_index_still_fails(empty_db, tmp_path) -> None:
    """The retry is for a race another session already won. A migration whose own rows collide
    loses every attempt, and swallowing that would apply a version whose SQL never ran."""
    (tmp_path / "001_unique.sql").write_text(
        "create table public.one (id int primary key);\n"
        "insert into public.one values (1);\n"
        "insert into public.one values (1);\n"
    )

    with pytest.raises(psycopg.errors.UniqueViolation):
        migrate(empty_db, tmp_path)
    empty_db.rollback()

    with empty_db.cursor() as cursor:
        cursor.execute("select count(*) from public.schema_migrations")
        assert cursor.fetchone()[0] == 0
