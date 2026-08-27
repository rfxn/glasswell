"""Collector logic that turns service-manager evidence into cautious job states."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from psycopg import IsolationLevel
from psycopg.pq import TransactionStatus

from glasswell.status.collector import (
    _configure_inventory_connection,
    _job,
    _restore_drill_job,
    _system_service,
    _systemd_properties,
)


def _restore_payload(
    completed_at: datetime,
    *,
    result: str = "passed",
    failure_detail: str | None = None,
    dump_created_at: datetime | None = None,
) -> dict:
    started_at = completed_at - timedelta(minutes=1)
    return {
        "result_version": 1,
        "result": result,
        "failure_detail": failure_detail,
        "dump": {
            "name": "glasswell-20260827T020000Z.dump",
            "sha256": "a" * 64,
            "bytes": 123456,
            "created_at": (dump_created_at or completed_at - timedelta(minutes=9)).isoformat(),
        },
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "duration_seconds": 60,
        "source_schema_version": 44,
        "restored_schema_version": 44,
        "schema_match": True,
        "critical_row_counts": [
            {
                "dataset": dataset,
                "source_rows": 42,
                "restored_rows": 42,
                "match": True,
            }
            for dataset in (
                "lineage.manifests",
                "canonical.wells_latest",
                "canonical.production_monthly",
                "marts.nd_wells_tile",
            )
        ],
        "representative_reads": [
            {"id": assertion_id, "passed": True}
            for assertion_id in (
                "postgis_available",
                "postgis_extension",
                "scratch_owner",
                "canonical_well",
                "production_observation",
                "lineage_manifest",
            )
        ],
        "scratch_removed": True,
    }


def _write_restore_result(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(0o640)


def _runner(properties: dict[str, str]):
    def run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        if command[0] == "date":
            value = command[2].removeprefix("--date=")
            rendered = {
                "Thu 2026-08-27 02:09:24 UTC": "2026-08-27T02:09:24Z\n",
                "Fri 2026-08-28 02:08:19 UTC": "2026-08-28T02:08:19Z\n",
            }.get(value, "")
            return subprocess.CompletedProcess(command, 0 if rendered else 1, rendered, "")
        unit = command[2]
        return subprocess.CompletedProcess(command, 0, properties.get(unit, ""), "")

    return run


def test_armed_job_uses_the_completed_process_time_not_timer_activity() -> None:
    runner = _runner(
        {
            "job.timer": (
                "ActiveState=active\nNextElapseUSecRealtime=Fri 2026-08-28 02:08:19 UTC\n"
            ),
            "job.service": (
                "Result=success\nExecMainStatus=0\n"
                "ExecMainExitTimestamp=Thu 2026-08-27 02:09:24 UTC\n"
            ),
        }
    )

    status = _job("backup", "Backup", "job.timer", "job.service", runner)

    assert status.state == "ok"
    assert status.last_run_at.isoformat() == "2026-08-27T02:09:24+00:00"
    assert status.next_run_at.isoformat() == "2026-08-28T02:08:19+00:00"


def test_installed_but_unarmed_job_is_pending_not_failed() -> None:
    runner = _runner(
        {
            "job.timer": "ActiveState=inactive\n",
            "job.service": (
                "Result=success\nExecMainStatus=0\n"
                "ExecMainExitTimestamp=Thu 2026-08-27 02:09:24 UTC\n"
            ),
        }
    )

    status = _job("capture", "Capture", "job.timer", "job.service", runner)

    assert status.state == "pending"
    assert status.last_run_at is not None


def test_failed_completed_job_is_degraded() -> None:
    runner = _runner(
        {
            "job.timer": "ActiveState=active\n",
            "job.service": (
                "Result=exit-code\nExecMainStatus=1\n"
                "ExecMainExitTimestamp=Thu 2026-08-27 02:09:24 UTC\n"
            ),
        }
    )

    status = _job("backup", "Backup", "job.timer", "job.service", runner)

    assert status.state == "degraded"
    assert "failed" in status.detail


def test_failed_job_without_a_parseable_completion_time_is_still_degraded() -> None:
    runner = _runner(
        {
            "job.timer": "ActiveState=active\n",
            "job.service": "Result=exit-code\nExecMainStatus=1\n",
        }
    )

    status = _job("backup", "Backup", "job.timer", "job.service", runner)

    assert status.state == "degraded"
    assert status.last_run_at is None


def test_missing_job_evidence_is_unavailable_not_pending() -> None:
    status = _job("backup", "Backup", "job.timer", "job.service", _runner({}))

    assert status.state == "unavailable"
    assert "unavailable" in status.detail


def test_completed_job_requires_explicit_success_evidence() -> None:
    runner = _runner(
        {
            "job.timer": "ActiveState=active\n",
            "job.service": "ExecMainExitTimestamp=Thu 2026-08-27 02:09:24 UTC\n",
        }
    )

    status = _job("backup", "Backup", "job.timer", "job.service", runner)

    assert status.state == "unavailable"
    assert "conclusive" in status.detail


def test_missing_service_manager_evidence_is_unavailable() -> None:
    observed_at = datetime(2026, 8, 27, tzinfo=UTC)

    status = _system_service("api", "API", "glasswell-api.service", observed_at, _runner({}))

    assert status.state == "unavailable"


def test_systemd_timeout_is_treated_as_missing_evidence() -> None:
    def timeout(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(command, 10)

    assert _systemd_properties("glasswell-api.service", timeout) == {}


def test_inventory_collection_configures_one_coherent_read_only_snapshot() -> None:
    connection = SimpleNamespace(
        info=SimpleNamespace(transaction_status=TransactionStatus.IDLE),
        isolation_level=None,
        read_only=None,
    )

    _configure_inventory_connection(connection)  # type: ignore[arg-type]

    assert connection.isolation_level == IsolationLevel.REPEATABLE_READ
    assert connection.read_only is True


def test_inventory_collection_refuses_an_existing_incoherent_transaction() -> None:
    connection = SimpleNamespace(
        info=SimpleNamespace(transaction_status=TransactionStatus.INTRANS),
        isolation_level=None,
        read_only=None,
    )

    with pytest.raises(RuntimeError, match="idle database connection"):
        _configure_inventory_connection(connection)  # type: ignore[arg-type]


def test_restore_job_uses_current_durable_proof_not_only_systemd_success(tmp_path: Path) -> None:
    completed_at = datetime(2026, 8, 27, 2, 9, 24, tzinfo=UTC)
    observed_at = completed_at + timedelta(hours=2)
    path = tmp_path / "restore.json"
    _write_restore_result(path, _restore_payload(completed_at))
    runner = _runner(
        {
            "glasswell-restore-drill.timer": (
                "ActiveState=active\nNextElapseUSecRealtime=Fri 2026-08-28 02:08:19 UTC\n"
            ),
            "glasswell-restore-drill.service": (
                "Result=success\nExecMainStatus=0\n"
                "ExecMainExitTimestamp=Thu 2026-08-27 02:09:24 UTC\n"
            ),
        }
    )

    status = _restore_drill_job(
        observed_at,
        path=path,
        runner=runner,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )

    assert status.state == "ok"
    assert status.last_run_at == completed_at
    assert "age 2h" in status.detail
    assert "scratch cleanup verified" in status.detail
    assert "remote" not in status.detail.lower()


def test_failed_durable_restore_result_is_degraded_even_when_cleanup_succeeded(
    tmp_path: Path,
) -> None:
    completed_at = datetime(2026, 8, 27, 2, 9, 24, tzinfo=UTC)
    path = tmp_path / "restore.json"
    payload = _restore_payload(
        completed_at, result="failed", failure_detail="restore_failed"
    )
    _write_restore_result(path, payload)

    status = _restore_drill_job(
        completed_at + timedelta(minutes=1),
        path=path,
        runner=_runner({}),
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )

    assert status.state == "degraded"
    assert "restore_failed" in status.detail
    assert "cleanup verified" in status.detail


def test_stale_restore_proof_is_degraded(tmp_path: Path) -> None:
    completed_at = datetime(2026, 8, 18, 2, tzinfo=UTC)
    path = tmp_path / "restore.json"
    _write_restore_result(path, _restore_payload(completed_at))

    status = _restore_drill_job(
        datetime(2026, 8, 27, 3, tzinfo=UTC),
        path=path,
        runner=_runner({}),
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )

    assert status.state == "degraded"
    assert "stale" in status.detail


def test_fresh_drill_of_stale_dump_is_degraded(tmp_path: Path) -> None:
    completed_at = datetime(2026, 8, 27, 2, 9, 24, tzinfo=UTC)
    path = tmp_path / "restore.json"
    _write_restore_result(
        path,
        _restore_payload(completed_at, dump_created_at=completed_at - timedelta(days=3)),
    )

    status = _restore_drill_job(
        completed_at + timedelta(hours=1),
        path=path,
        runner=_runner(
            {
                "glasswell-restore-drill.timer": "ActiveState=active\n",
                "glasswell-restore-drill.service": (
                    "Result=success\nExecMainStatus=0\n"
                    "ExecMainExitTimestamp=Thu 2026-08-27 02:09:24 UTC\n"
                ),
            }
        ),
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )

    assert status.state == "degraded"
    assert "backup dump is stale" in status.detail


def test_missing_result_is_pending_only_before_any_completed_run(tmp_path: Path) -> None:
    runner = _runner(
        {
            "glasswell-restore-drill.timer": "ActiveState=active\n",
            "glasswell-restore-drill.service": "Result=\nExecMainStatus=\n",
        }
    )

    status = _restore_drill_job(
        datetime(2026, 8, 27, tzinfo=UTC),
        path=tmp_path / "missing.json",
        runner=runner,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )

    assert status.state == "pending"
    assert "No durable restore result" in status.detail


def test_completed_service_without_durable_result_is_unavailable(tmp_path: Path) -> None:
    runner = _runner(
        {
            "glasswell-restore-drill.timer": "ActiveState=active\n",
            "glasswell-restore-drill.service": (
                "Result=success\nExecMainStatus=0\n"
                "ExecMainExitTimestamp=Thu 2026-08-27 02:09:24 UTC\n"
            ),
        }
    )

    status = _restore_drill_job(
        datetime(2026, 8, 27, 3, tzinfo=UTC),
        path=tmp_path / "missing.json",
        runner=runner,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )

    assert status.state == "unavailable"


def test_symlink_or_forged_incomplete_success_result_is_degraded(tmp_path: Path) -> None:
    completed_at = datetime(2026, 8, 27, 2, 9, 24, tzinfo=UTC)
    target = tmp_path / "target.json"
    payload = _restore_payload(completed_at)
    payload["critical_row_counts"] = []
    _write_restore_result(target, payload)
    linked = tmp_path / "linked.json"
    linked.symlink_to(target)

    symlink_status = _restore_drill_job(
        completed_at,
        path=linked,
        runner=_runner({}),
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )
    forged_status = _restore_drill_job(
        completed_at,
        path=target,
        runner=_runner({}),
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )

    assert symlink_status.state == "degraded"
    assert "unsafe" in symlink_status.detail
    assert forged_status.state == "degraded"
    assert "validated" in forged_status.detail


def test_restore_result_replaced_between_metadata_and_open_is_degraded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    completed_at = datetime(2026, 8, 27, 2, 9, 24, tzinfo=UTC)
    path = tmp_path / "restore.json"
    _write_restore_result(path, _restore_payload(completed_at))
    metadata = path.lstat()
    changed_metadata = SimpleNamespace(
        st_mode=metadata.st_mode,
        st_nlink=metadata.st_nlink,
        st_uid=metadata.st_uid,
        st_gid=metadata.st_gid,
        st_size=metadata.st_size,
        st_dev=metadata.st_dev,
        st_ino=metadata.st_ino + 1,
    )
    monkeypatch.setattr(Path, "lstat", lambda _path: changed_metadata)

    status = _restore_drill_job(
        completed_at,
        path=path,
        runner=_runner({}),
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )

    assert status.state == "degraded"
    assert "changed while it was opened" in status.detail
