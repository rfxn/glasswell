"""The half of `scripts/ops/nm_reregister_manifests.py` that only a database can falsify.

`--dry-run` committing nothing, a second run reporting the row it did not write, and a second
slot claiming the same bytes exiting rather than tracebacking are all statements about
`lineage.manifests`, not about the sidecar. The parsing half is `tests/unit/test_nm_reregister.py`;
this file exists because a fake connection would make every assertion here tautological.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import psycopg
import pytest

from tests.unit.test_nm_reregister import WCPRODUCTION_MANIFEST_ID, write_sidecar

pytestmark = pytest.mark.integration

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "nm_reregister_manifests.py"


def _load():
    spec = importlib.util.spec_from_file_location("nm_reregister_manifests_integration", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


tool = _load()


def harness_dsn(db: psycopg.Connection, password: str) -> str:
    """`info.dsn` masks the password, and the tool opens its own connection."""
    return f"postgresql://glasswell:{password}@{db.info.host}:{db.info.port}/{db.info.dbname}"


def manifest_count(db: psycopg.Connection) -> int:
    with db.cursor() as cursor:
        cursor.execute("select count(*) from lineage.manifests")
        return int(cursor.fetchone()[0])


def test_a_dry_run_reports_the_id_it_would_create_and_writes_nothing(
    db: psycopg.Connection, postgres_password: str, tmp_path: Path, capsys
):
    sidecar = write_sidecar(tmp_path)
    before = manifest_count(db)

    status = tool.main(
        ["--dsn", harness_dsn(db, postgres_password), "--dry-run", "--sidecar", str(sidecar)]
    )

    assert status == 0
    assert WCPRODUCTION_MANIFEST_ID in capsys.readouterr().out
    assert manifest_count(db) == before


def test_registration_creates_the_row_and_a_rerun_reports_it_as_already_present(
    db: psycopg.Connection, postgres_password: str, tmp_path: Path, capsys
):
    sidecar = write_sidecar(tmp_path)
    dsn = harness_dsn(db, postgres_password)

    assert tool.main(["--dsn", dsn, "--sidecar", str(sidecar)]) == 0
    first = capsys.readouterr().out
    assert tool.main(["--dsn", dsn, "--sidecar", str(sidecar)]) == 0
    second = capsys.readouterr().out

    assert "registered" in first
    assert "already present" in second
    with db.cursor() as cursor:
        cursor.execute(
            "select manifest_id, source_id, bytes from lineage.manifests where sha256 = %s",
            (tool.read_sidecar(sidecar)["sha256"],),
        )
        assert cursor.fetchall() == [(WCPRODUCTION_MANIFEST_ID, "nm_ocd_wcproduction", 968419426)]


def test_identical_bytes_under_a_second_slot_exit_one_rather_than_traceback(
    db: psycopg.Connection, postgres_password: str, tmp_path: Path, capsys
):
    dsn = harness_dsn(db, postgres_password)
    incumbent = write_sidecar(tmp_path, name="incumbent.json")
    assert tool.main(["--dsn", dsn, "--sidecar", str(incumbent)]) == 0
    capsys.readouterr()
    claimant = write_sidecar(
        tmp_path, name="claimant.json", source_id="nd_mpr_xlsx", source_key="stolen.zip"
    )

    status = tool.main(["--dsn", dsn, "--sidecar", str(claimant)])

    assert status == 1
    assert str(claimant) in capsys.readouterr().err
    assert manifest_count(db) == 1


def test_a_dry_run_surfaces_the_conflict_before_the_operator_writes(
    db: psycopg.Connection, postgres_password: str, tmp_path: Path, capsys
):
    dsn = harness_dsn(db, postgres_password)
    assert tool.main(["--dsn", dsn, "--sidecar", str(write_sidecar(tmp_path))]) == 0
    capsys.readouterr()
    claimant = write_sidecar(
        tmp_path, name="claimant.json", source_id="nd_mpr_xlsx", source_key="stolen.zip"
    )

    assert tool.main(["--dsn", dsn, "--dry-run", "--sidecar", str(claimant)]) == 1
    assert str(claimant) in capsys.readouterr().err


def test_the_target_database_is_named_on_every_run(
    db: psycopg.Connection, postgres_password: str, tmp_path: Path, capsys
):
    """glasswell and glasswell_d1 are one letter apart; the operator must see which one."""
    status = tool.main(
        [
            "--dsn",
            harness_dsn(db, postgres_password),
            "--dry-run",
            "--sidecar",
            str(write_sidecar(tmp_path)),
        ]
    )

    assert status == 0
    assert f"database={db.info.dbname}" in capsys.readouterr().out
