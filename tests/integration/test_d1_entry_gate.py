"""D1's entry gate (PLAN-NM rev 2 §0): nine checks against an ephemeral post-A1b container.

The gate never touches VM 111 — `db` is a throwaway database inside the session's PostGIS
container, so `CADENCE.md` §2.1 rule 2 holds by construction rather than by discipline. Every
check that *records* rather than asserts prints its finding, so `pytest -s` is the evidence the
phase status file quotes.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest

from glasswell.db.migrate import discover_migrations
from tests.support.seed import seed_derivation, seed_manifest, seed_production

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORK_OUTPUT = REPOSITORY_ROOT / "work-output"
# Wave-1 track artifacts were archived in place. A gate keyed on one hard-coded path skips
# itself the day the artifact moves, and the skip reason still reads as legitimate (F12).
A1B_STATUS_LOCATIONS = (
    Path("work-output") / "track-a1b-status.md",
    Path("work-output") / "archive" / "wave1" / "track-a1b-status.md",
)
A1B_MIGRATIONS = (20, 21, 22, 23, 24)


def a1b_status_path(root: Path) -> Path | None:
    return next((root / rel for rel in A1B_STATUS_LOCATIONS if (root / rel).is_file()), None)

MONTH = date(2026, 1, 1)
VINTAGE = date(2026, 8, 1)
ND_WELL = "3305303901"

# SB-01 §6.3 lists these on canonical.production_monthly. G7 asserts which A1b actually
# landed, because every one of them changes P4's insert statement.
SB01_OPTIONAL_COLUMNS = ("uom", "unit", "mod_dte", "liquids_policy", "conditions_ref", "rule_ids")


def scalar(connection: psycopg.Connection, sql: str, *parameters: object) -> object:
    with connection.cursor() as cursor:
        cursor.execute(sql, parameters or None)
        row = cursor.fetchone()
    return row[0] if row else None


def rows(connection: psycopg.Connection, sql: str, *parameters: object) -> list[tuple]:
    with connection.cursor() as cursor:
        cursor.execute(sql, parameters or None)
        return cursor.fetchall()


def check_constraints(connection: psycopg.Connection, table: str) -> dict[str, str]:
    return dict(
        rows(
            connection,
            "select conname, pg_get_constraintdef(oid) from pg_constraint"
            " where conrelid = %s::regclass and contype = 'c'",
            table,
        )
    )


@pytest.fixture
def promotable(db: psycopg.Connection) -> tuple[str, str]:
    return seed_manifest(db, sha256="a" * 64), seed_derivation(db)


def test_g1_the_primary_key_is_the_entity_key(db):
    key = [
        name
        for (name,) in rows(
            db,
            "select a.attname from pg_constraint c"
            " cross join lateral unnest(c.conkey) with ordinality as k(attnum, ord)"
            " join pg_attribute a on a.attrelid = c.conrelid and a.attnum = k.attnum"
            " where c.conrelid = 'canonical.production_monthly'::regclass and c.contype = 'p'"
            " order by k.ord",
        )
    ]
    print(f"\nG1 primary key: {key}")
    assert key == [
        "entity_type",
        "entity_key",
        "production_month",
        "stream",
        "source_id",
        "report_vintage",
    ]


def test_g2_the_entity_vocabulary_admits_a_well_completion_pool(db):
    constraints = check_constraints(db, "canonical.production_monthly")
    entity_type = constraints["production_monthly_entity_type_check"]
    print(f"\nG2 entity_type CHECK: {entity_type}")
    assert "well_completion_pool" in entity_type
    assert "lease" in entity_type


def test_g3_reporting_level_and_condensate_both_landed(db):
    columns = {
        name
        for (name,) in rows(
            db,
            "select column_name from information_schema.columns"
            " where table_schema = 'canonical' and table_name = 'production_monthly'",
        )
    }
    stream = check_constraints(db, "canonical.production_monthly")[
        "production_monthly_stream_check"
    ]
    print(f"\nG3 stream CHECK: {stream}")
    assert "reporting_level" in columns
    assert "condensate" in stream


def test_g4_well_completions_exists_with_the_columns_p5_reads(db):
    assert scalar(db, "select to_regclass('canonical.well_completions')") is not None
    columns = sorted(
        name
        for (name,) in rows(
            db,
            "select column_name from information_schema.columns"
            " where table_schema = 'canonical' and table_name = 'well_completions'",
        )
    )
    print(f"\nG4 canonical.well_completions columns: {columns}")
    # The completion identity is `completion_key`, not `entity_key`: P5's NM identifiers hang
    # off this name, and P5.1's conditional migration is decided against it.
    assert {"api10", "completion_key", "well_completion_pool", "pool_reported"} <= set(columns)


def test_g5_a_well_row_keeps_the_entity_the_old_key_implied(db, promotable):
    manifest, derivation = promotable
    seed_production(
        db,
        api10=ND_WELL,
        production_month=MONTH,
        report_vintage=VINTAGE,
        volume=Decimal("1234.000"),
        manifest_id=manifest,
        derivation_id=derivation,
    )
    landed = rows(
        db,
        "select entity_type, entity_key, reporting_level from canonical.production_monthly",
    )
    nullable = scalar(
        db,
        "select is_nullable from information_schema.columns"
        " where table_schema = 'canonical' and table_name = 'production_monthly'"
        "   and column_name = 'entity_type'",
    )
    print(f"\nG5 well row: {landed}, entity_type is_nullable={nullable}")
    assert landed == [("well", ND_WELL, "well")]
    assert nullable == "NO"


def test_g6_granularity_admits_the_token_p4_must_write(db, promotable):
    """Reconcile, do not assume: P4.2 writes whatever the CHECK admits (G6, B3)."""
    granularity = {
        name: definition
        for name, definition in check_constraints(db, "canonical.production_monthly").items()
        if "granularity" in definition
    }
    print(f"\nG6 granularity CHECKs: {granularity}")
    admitted = scalar(
        db,
        "select pg_get_constraintdef(oid) from pg_constraint"
        " where conname = 'production_monthly_granularity_check'",
    )
    print(f"G6 vocabulary (migration 012): {admitted}")

    manifest, derivation = promotable
    seed_production(
        db,
        api10="3002512345",
        production_month=MONTH,
        report_vintage=VINTAGE,
        volume=Decimal("42.000"),
        manifest_id=manifest,
        derivation_id=derivation,
        source_id="nm_ocd_wcproduction",
        entity_type="well_completion_pool",
        entity_key="3002512345:96032",
        reporting_level="well_completion_pool",
        well_completion_pool="96032",
        granularity="well_observed",
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        seed_production(
            db,
            api10="3002512346",
            production_month=MONTH,
            report_vintage=VINTAGE,
            volume=Decimal("42.000"),
            manifest_id=manifest,
            derivation_id=derivation,
            source_id="nm_ocd_wcproduction",
            entity_type="well_completion_pool",
            entity_key="3002512346:96032",
            reporting_level="well_completion_pool",
            well_completion_pool="96032",
            granularity="observed",
        )


def test_g7_the_column_inventory_is_what_p4_writes_into(db):
    inventory = rows(
        db,
        "select column_name, data_type, is_nullable from information_schema.columns"
        " where table_schema = 'canonical' and table_name = 'production_monthly'"
        " order by ordinal_position",
    )
    print("\nG7 canonical.production_monthly:")
    for column, data_type, nullable in inventory:
        print(f"  {column:<22} {data_type:<26} nullable={nullable}")
    present = {column for column, _, _ in inventory}
    landed = {name: name in present for name in SB01_OPTIONAL_COLUMNS}
    print(f"G7 SB-01 §6.3 optional columns: {landed}")

    nullability = {column: nullable for column, _, nullable in inventory}
    # api10 is nullable (a lease row has no well); volume is NOT NULL, so an absent NM volume
    # is a quarantine or a disclosed zero at P4, never a null canonical row.
    assert nullability["api10"] == "YES"
    assert nullability["volume"] == "NO"
    assert landed == {
        "unit": True,
        "uom": False,
        "mod_dte": False,
        "liquids_policy": False,
        "conditions_ref": False,
        "rule_ids": False,
    }


def test_g8_the_serving_path_partitions_on_the_key_it_is_promoted_under(db):
    """B2: a window still keyed on api10 makes Arm A.6 pass at the table and fail at the wire."""
    partition = "partition by entity_type, entity_key, production_month, stream, source_id"
    source = (REPOSITORY_ROOT / "src/glasswell/lineage/vintages.py").read_text(encoding="utf-8")
    assert partition in source
    assert "created_at desc" not in source

    view = str(scalar(db, "select pg_get_viewdef('canonical.production_monthly_latest', true)"))
    windowed = " ".join(view.split()).lower()
    window = re.search(r"partition by[^)]*", windowed).group(0)
    print(f"\nG8 view window: {window}")
    # 031 adds api10 to the window for predicate pushdown (DR-79); B2's property is that the
    # promoted entity key stays in the partition, not that it stands alone.
    for column in ("p.entity_type", "p.entity_key", "p.production_month", "p.stream",
                   "p.source_id"):
        assert column in window, window
    assert "created_at desc" not in windowed


def test_g9_the_a1b_migration_block_is_intact():
    """The half of G9 that reads the tree, and therefore has no reason ever to skip. This ran
    nowhere between the wave-1 archive move and F12."""
    versions = [migration.version for migration in discover_migrations()]
    a1b_block = [version for version in versions if version in A1B_MIGRATIONS]
    print(f"\nG9 A1b block on disk: {a1b_block}; tree carries {len(versions)} migrations")
    assert a1b_block == list(A1B_MIGRATIONS)
    # Wave-1 renumbering put A2 and O above A1b's block; D1 fills from the top (CADENCE §2.1).
    assert versions == list(range(1, len(versions) + 1))
    assert max(versions) >= max(A1B_MIGRATIONS)


def test_g9_a1bs_status_file_states_the_migration_count_the_tree_carries():
    if not WORK_OUTPUT.is_dir():
        pytest.skip("work-output/ is git-excluded; the gate runs where the merge artifacts live")
    # A linked worktree's .git is a file. Dispatched tracks write their own status files into a
    # work-output/ that never held the wave-1 archive, which turned a self-disabling gate red
    # and pointed at the wrong thing; three tracks reported it before this line existed.
    if (REPOSITORY_ROOT / ".git").is_file():
        pytest.skip("a linked worktree carries its own work-output/, never the wave-1 archive")
    status_path = a1b_status_path(REPOSITORY_ROOT)
    assert status_path is not None, (
        f"work-output/ is populated but track-a1b-status.md is in none of"
        f" {[str(rel) for rel in A1B_STATUS_LOCATIONS]} — add its new home rather than"
        f" letting the gate skip itself"
    )

    stated = re.search(
        r"[Ee]xact final count:\s*\*{0,2}(\d+)", status_path.read_text(encoding="utf-8")
    )
    assert stated is not None, f"{status_path} does not state an exact final migration count"
    print(f"\nG9 A1b status at {status_path.relative_to(REPOSITORY_ROOT)} states {stated.group(1)}")
    assert int(stated.group(1)) == len(A1B_MIGRATIONS)


@pytest.mark.parametrize("location", A1B_STATUS_LOCATIONS)
def test_g9_resolves_the_status_artifact_at_either_known_home(tmp_path: Path, location: Path):
    planted = tmp_path / location
    planted.parent.mkdir(parents=True)
    planted.write_text("Exact final count: 5", encoding="utf-8")

    assert a1b_status_path(tmp_path) == planted


def test_g9_resolves_nothing_when_the_artifact_is_absent(tmp_path: Path):
    (tmp_path / "work-output").mkdir()

    assert a1b_status_path(tmp_path) is None
