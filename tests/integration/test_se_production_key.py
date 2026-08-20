"""S-E: `canonical.production_monthly` keyed by entity, not by API-10.

`reconciliation.md` §S-E rules the key to
`(entity_type, entity_key, production_month, stream, source_id, report_vintage)` with
`reporting_level` alongside and `api10` retained as a denormalised nullable column. Migration
008's `api10` key cannot represent a TX lease row and cannot hold two pools of one well in one
month, which is what made 78 ND wells serve as zero-producers (fp-audit D1).

The widening runs against a database that already holds rows under the old key, so the
backfill is exercised here the way the deployer will meet it: migrate to 019, load old-key
rows, migrate the rest, and prove nothing the old key wrote was rewritten.
"""

from __future__ import annotations

import shutil
from datetime import date
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest

from glasswell.db.migrate import MIGRATIONS_DIR, discover_migrations, migrate

OLD_KEY_HEAD = 19
API10 = "3305302532"
MONTH = date(2026, 1, 1)
VINTAGE = date(2026, 8, 1)

_OLD_KEY_INSERT = """
insert into canonical.production_monthly (api10, production_month, stream, source_id,
    report_vintage, volume, unit, days_produced, granularity, value_hash, source_manifest_id,
    derivation_id, null_semantics)
values (%(api10)s, %(production_month)s, %(stream)s, 'nd_mpr_xlsx', %(report_vintage)s,
        %(volume)s, 'bbl', 31, 'well_observed', %(value_hash)s, %(manifest_id)s,
        %(derivation_id)s, 'reported')
"""

PRESERVED_COLUMNS = (
    "api10, production_month, stream, source_id, report_vintage, volume, unit, days_produced,"
    " granularity, value_hash, source_manifest_id, derivation_id, created_at, null_semantics"
)


def _migrations_through(tmp_path: Path, version: int) -> Path:
    staged = tmp_path / f"through_{version:03d}"
    staged.mkdir()
    for migration in discover_migrations():
        if migration.version <= version:
            shutil.copy(migration.path, staged / migration.path.name)
    return staged


def columns(connection: psycopg.Connection, schema: str, table: str) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            "select column_name from information_schema.columns"
            " where table_schema = %s and table_name = %s",
            (schema, table),
        )
        return {row[0] for row in cursor.fetchall()}


def primary_key(connection: psycopg.Connection, schema: str, table: str) -> list[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            "select k.column_name from information_schema.table_constraints c"
            "  join information_schema.key_column_usage k"
            "    on k.constraint_name = c.constraint_name"
            "   and k.constraint_schema = c.constraint_schema"
            " where c.table_schema = %s and c.table_name = %s"
            "   and c.constraint_type = 'PRIMARY KEY'"
            " order by k.ordinal_position",
            (schema, table),
        )
        return [row[0] for row in cursor.fetchall()]


def constraint(connection: psycopg.Connection, name: str) -> str:
    with connection.cursor() as cursor:
        cursor.execute(
            "select pg_get_constraintdef(oid) from pg_constraint where conname = %s", (name,)
        )
        row = cursor.fetchone()
    return "" if row is None else row[0]


def seed_row(connection: psycopg.Connection, **overrides: object) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into lineage.sources (source_id, name) values ('nd_mpr_xlsx', 'ND MPR')"
            " on conflict do nothing"
        )
        cursor.execute(
            "insert into lineage.environments (env_id, python_version, threads)"
            " values ('env_se', '3.12.10', 1) on conflict do nothing"
        )
        cursor.execute(
            "insert into lineage.manifests (manifest_id, sha256, bytes, source_id, source_key,"
            " acquisition_url, acquisition_method, fetched_at, fetch_vintage)"
            " values ('man_se', %s, 10, 'nd_mpr_xlsx', '2026_01.xlsx', 'https://x.invalid',"
            " 'https_get', now(), %s) on conflict do nothing",
            ("a" * 64, VINTAGE),
        )
        cursor.execute(
            "insert into lineage.derivations (derivation_id, operation, output_store,"
            " output_dataset, output_partition, output_locator, output_schema_version, params,"
            " params_hash, code_version, code_dirty, env_id, created_at, duration_ms,"
            " correlation_id, status, determinism_class, ttl_class)"
            " values ('drv_se', 'canonical.promote', 'postgres',"
            " 'canonical.production_monthly', '{}', '', '', '{}', %s, 'git:0000test', false,"
            " 'env_se', now(), 1, 'run_se', 'ok', 'D1', 'permanent') on conflict do nothing",
            ("b" * 64,),
        )
        payload = {
            "api10": API10,
            "production_month": MONTH,
            "stream": "oil",
            "report_vintage": VINTAGE,
            "volume": Decimal("120.000"),
            "value_hash": "c" * 64,
            "manifest_id": "man_se",
            "derivation_id": "drv_se",
            **overrides,
        }
        cursor.execute(_OLD_KEY_INSERT, payload)


@pytest.fixture
def widened(empty_db: psycopg.Connection, tmp_path: Path) -> psycopg.Connection:
    """A database that met the old key first, exactly as VM 111 will."""
    migrate(empty_db, _migrations_through(tmp_path, OLD_KEY_HEAD))
    empty_db.commit()
    seed_row(empty_db)
    seed_row(empty_db, stream="gas", value_hash="d" * 64, volume=Decimal("980.000"))
    empty_db.commit()
    migrate(empty_db, MIGRATIONS_DIR)
    empty_db.commit()
    return empty_db


def test_the_key_is_the_entity_not_the_api10(widened):
    assert primary_key(widened, "canonical", "production_monthly") == [
        "entity_type",
        "entity_key",
        "production_month",
        "stream",
        "source_id",
        "report_vintage",
    ]


def test_the_widening_rewrote_none_of_the_columns_the_old_key_wrote(widened):
    """DIR-2: a re-promotion adds a vintage. A migration may add columns; it rewrites nothing."""
    with widened.cursor() as cursor:
        cursor.execute(
            f"select {PRESERVED_COLUMNS} from canonical.production_monthly order by stream"
        )
        rows = cursor.fetchall()

    assert [(row[0], row[2], row[5], row[8], row[9]) for row in rows] == [
        (API10, "gas", Decimal("980.000"), "well_observed", "d" * 64),
        (API10, "oil", Decimal("120.000"), "well_observed", "c" * 64),
    ]


def test_every_backfilled_row_carries_the_entity_the_old_key_implied(widened):
    with widened.cursor() as cursor:
        cursor.execute(
            "select distinct entity_type, entity_key, reporting_level, well_completion_pool,"
            " aggregation from canonical.production_monthly"
        )
        assert cursor.fetchall() == [("well", API10, "well", None, None)]


def test_no_row_survives_the_widening_without_a_reporting_level(widened):
    with widened.cursor() as cursor:
        cursor.execute(
            "select count(*) from canonical.production_monthly"
            " where reporting_level is null or entity_key is null or entity_type is null"
        )
        assert cursor.fetchone()[0] == 0


def test_the_append_only_trigger_is_still_armed_after_the_backfill(widened):
    with pytest.raises(psycopg.errors.RestrictViolation, match="append_only_violation"):
        with widened.cursor() as cursor:
            cursor.execute("update canonical.production_monthly set volume = 1")
    widened.rollback()

    with widened.cursor() as cursor:
        cursor.execute(
            "select tgenabled from pg_trigger where tgname = 'production_monthly_append_only'"
        )
        assert cursor.fetchone()[0] == "O"


def test_the_two_pools_that_used_to_collide_now_both_have_a_row(widened):
    with widened.cursor() as cursor:
        for pool in ("BIRDBEAR", "DUPEROW"):
            cursor.execute(
                "insert into canonical.production_monthly (entity_type, entity_key,"
                " reporting_level, well_completion_pool, api10, production_month, stream,"
                " source_id, report_vintage, volume, unit, days_produced, granularity,"
                " value_hash, source_manifest_id, derivation_id, null_semantics)"
                " values ('well_completion_pool', %s, 'well_completion_pool', %s, %s, %s, 'oil',"
                " 'nd_mpr_xlsx', %s, 3585, 'bbl', 31, 'well_observed', %s, 'man_se', 'drv_se',"
                " 'reported')",
                (f"{API10}:{pool}", pool, API10, MONTH, VINTAGE, pool),
            )
        cursor.execute(
            "select count(*) from canonical.production_monthly"
            " where entity_type = 'well_completion_pool'"
        )
        assert cursor.fetchone()[0] == 2
    widened.rollback()


def test_a_pool_row_must_name_the_pool_it_reports(widened):
    with pytest.raises(psycopg.errors.CheckViolation, match="entity_pool"):
        with widened.cursor() as cursor:
            cursor.execute(
                "insert into canonical.production_monthly (entity_type, entity_key,"
                " reporting_level, api10, production_month, stream, source_id, report_vintage,"
                " volume, unit, granularity, value_hash, source_manifest_id, derivation_id)"
                " values ('well_completion_pool', 'x', 'well_completion_pool', %s, %s, 'oil',"
                " 'nd_mpr_xlsx', %s, 1, 'bbl', 'well_observed', 'e', 'man_se', 'drv_se')",
                (API10, MONTH, VINTAGE),
            )
    widened.rollback()


def test_a_lease_reported_row_cannot_claim_it_was_observed_at_the_well(widened):
    """S-B / DIR-3: the composed token is a function of the level, not a free label."""
    with pytest.raises(psycopg.errors.CheckViolation, match="granularity_composition"):
        with widened.cursor() as cursor:
            cursor.execute(
                "insert into canonical.production_monthly (entity_type, entity_key,"
                " reporting_level, production_month, stream, source_id, report_vintage, volume,"
                " unit, granularity, value_hash, source_manifest_id, derivation_id)"
                " values ('lease', 'O:08:12345', 'lease', %s, 'oil', 'nd_mpr_xlsx', %s, 1,"
                " 'bbl', 'well_observed', 'f', 'man_se', 'drv_se')",
                (MONTH, VINTAGE),
            )
    widened.rollback()


def test_canonical_refuses_an_allocated_row_because_allocation_is_a_derived_artifact(widened):
    with pytest.raises(psycopg.errors.CheckViolation, match="granularity_composition"):
        with widened.cursor() as cursor:
            cursor.execute(
                "insert into canonical.production_monthly (entity_type, entity_key,"
                " reporting_level, production_month, stream, source_id, report_vintage, volume,"
                " unit, granularity, value_hash, source_manifest_id, derivation_id)"
                " values ('well', '3305399999', 'well', %s, 'oil', 'nd_mpr_xlsx', %s, 1,"
                " 'bbl', 'lease_allocated', 'g', 'man_se', 'drv_se')",
                (MONTH, VINTAGE),
            )
    widened.rollback()


def test_condensate_enters_the_stream_vocabulary_for_nm_and_tx(widened):
    assert "condensate" in constraint(widened, "production_monthly_stream_check")


def test_the_serving_view_partitions_by_the_entity_key(widened):
    with widened.cursor() as cursor:
        cursor.execute("select pg_get_viewdef('canonical.production_monthly_latest'::regclass)")
        definition = cursor.fetchone()[0]
    assert "entity_type" in definition
    assert "entity_key" in definition
    assert set(columns(widened, "canonical", "production_monthly_latest")) >= {
        "entity_type",
        "entity_key",
        "reporting_level",
        "well_completion_pool",
        "aggregation",
    }


def test_the_vintage_tiebreak_is_the_derivation_not_the_wall_clock(widened):
    """S-E / SB-01 H2: created_at is not replay-stable, so it cannot order a re-promotion."""
    with widened.cursor() as cursor:
        cursor.execute("select pg_get_viewdef('canonical.production_monthly_latest'::regclass)")
        definition = cursor.fetchone()[0]
    assert "derivation_id DESC" in definition
    assert "created_at DESC" not in definition


def test_a_well_level_insert_that_names_no_entity_columns_still_keys_itself(widened):
    """The API-10 is the entity key of a well by definition, so the old insert shape survives."""
    seed_row(widened, stream="water", value_hash="h" * 64, volume=Decimal("4.000"))
    with widened.cursor() as cursor:
        cursor.execute(
            "select entity_type, entity_key, reporting_level from canonical.production_monthly"
            " where stream = 'water'"
        )
        assert cursor.fetchone() == ("well", API10, "well")
    widened.rollback()


def test_an_entity_key_cannot_be_inferred_for_a_non_well_entity(widened):
    with pytest.raises(psycopg.errors.RaiseException, match="entity_key is required"):
        with widened.cursor() as cursor:
            cursor.execute(
                "insert into canonical.production_monthly (entity_type, reporting_level,"
                " production_month, stream, source_id, report_vintage, volume, unit,"
                " granularity, value_hash, source_manifest_id, derivation_id)"
                " values ('lease', 'lease', %s, 'oil', 'nd_mpr_xlsx', %s, 1, 'bbl',"
                " 'lease_reported', 'i', 'man_se', 'drv_se')",
                (MONTH, VINTAGE),
            )
    widened.rollback()


def test_well_completions_records_the_pool_entity_the_enum_named(widened):
    assert set(columns(widened, "canonical", "well_completions")) >= {
        "completion_key",
        "api10",
        "well_completion_pool",
        "pool_reported",
        "source_id",
        "production_month",
        "report_vintage",
        "derivation_id",
    }


def test_a_well_completion_row_cannot_be_edited_in_place(widened):
    with widened.cursor() as cursor:
        cursor.execute(
            "insert into canonical.well_completions (completion_key, api10,"
            " well_completion_pool, source_id, production_month, report_vintage,"
            " source_manifest_id, derivation_id)"
            " values (%s, %s, 'DUPEROW', 'nd_mpr_xlsx', %s, %s, 'man_se', 'drv_se')",
            (f"{API10}:DUPEROW", API10, MONTH, VINTAGE),
        )
    widened.commit()
    with pytest.raises(psycopg.errors.RestrictViolation, match="append_only_violation"):
        with widened.cursor() as cursor:
            cursor.execute("update canonical.well_completions set well_completion_pool = 'X'")
    widened.rollback()
