"""Collector logic that turns service-manager evidence into cautious job states."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from psycopg import Connection, IsolationLevel
from psycopg.pq import TransactionStatus

import glasswell.status.collector as status_collector
from glasswell.status.collector import (
    _configure_inventory_connection,
    _job,
    _restore_drill_job,
    _system_service,
    _systemd_properties,
)
from glasswell.status.models import JobStatus, PlatformStatus, StatusCheck


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


def test_collector_no_longer_discloses_attempt_or_cadence_as_uninstrumented(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, *_args):
            return None

    connection = SimpleNamespace(
        info=SimpleNamespace(transaction_status=TransactionStatus.IDLE),
        isolation_level=None,
        read_only=None,
        cursor=lambda: Cursor(),
    )
    check = StatusCheck(id="test", label="Test", state="ok", detail="Observed.")
    job = JobStatus(id="test", label="Test", state="ok", detail="Observed.")
    monkeypatch.setattr(status_collector, "_inventory", lambda *_args: ([], PlatformStatus()))
    monkeypatch.setattr(status_collector, "_system_service", lambda *_args: check)
    monkeypatch.setattr(status_collector, "_martin_check", lambda *_args: check)
    monkeypatch.setattr(status_collector, "_edge_check", lambda *_args: check)
    monkeypatch.setattr(status_collector, "_storage_check", lambda *_args: check)
    monkeypatch.setattr(status_collector, "_job", lambda *_args: job)
    monkeypatch.setattr(status_collector, "_restore_drill_job", lambda *_args: job)
    monkeypatch.setattr(status_collector, "_offsite_copy_job", lambda *_args: job)
    monkeypatch.setattr(status_collector, "_recovery_drill_job", lambda *_args: job)

    snapshot = status_collector.collect(cast(Connection, connection))

    assert [item.id for item in snapshot.disclosures] == [
        "remote_backup_copy",
        "replacement_host_recovery",
    ]
    # Both are `limited`, never `not_instrumented`: the offsite push is now recorded, and the
    # recovery path is mechanised. Each states the limit that remains rather than hiding it.
    assert {item.state for item in snapshot.disclosures} == {"limited"}
    assert [item.id for item in snapshot.jobs] == [
        "test",
        "test",
        "test",
        "test",
        "test",
        "test",
        "test",
    ]


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


def _offsite_payload(completed_at: datetime, **overrides) -> dict:
    payload = {
        "receipt_version": 1,
        "result": "passed",
        "failure_detail": None,
        "generation": "20260830T020825Z",
        "dump": {
            "name": "glasswell-20260830T020825Z.dump",
            "sha256": "b" * 64,
            "bytes": 1_493_358_179,
        },
        "destination": "root@192.168.2.205",
        "started_at": (completed_at - timedelta(minutes=3)).isoformat(),
        "completed_at": completed_at.isoformat(),
        "duration_seconds": 180,
        "streams": [
            {
                "id": "pgdump",
                "state": "transferred",
                "exit_status": 0,
                "files_transferred": 3,
                "bytes_transferred": 1_500_000_000,
                "bytes_on_sender": 7_466_790_895,
            },
            {
                "id": "raw",
                "state": "transferred",
                "exit_status": 0,
                "files_transferred": 1,
                "bytes_transferred": 2048,
                "bytes_on_sender": 2048,
            },
        ],
        "dump_bytes_covered": True,
        "verification": "send_side_only",
    }
    payload.update(overrides)
    return payload


def _backup_runner(**overrides: str):
    properties = {
        "glasswell-backup.timer": "ActiveState=active\n",
        "glasswell-backup.service": (
            "Result=success\nExecMainStatus=0\n"
            "ExecMainExitTimestamp=Thu 2026-08-27 02:09:24 UTC\n"
        ),
    }
    properties.update(overrides)
    return _runner(properties)


def test_offsite_job_reports_a_fresh_push_without_claiming_a_read_back(tmp_path: Path) -> None:
    completed_at = datetime(2026, 8, 30, 2, 11, tzinfo=UTC)
    path = tmp_path / "offsite.json"
    _write_restore_result(path, _offsite_payload(completed_at))

    status = status_collector._offsite_copy_job(
        completed_at + timedelta(hours=3),
        path=path,
        runner=_backup_runner(),
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )

    assert status.state == "ok"
    assert "write-only" in status.detail
    assert "no read-back" in status.detail
    # The served detail must not carry the remote host, address or any filesystem path.
    assert "192.168.2.205" not in status.detail
    assert "/hdd-pool" not in status.detail


def test_offsite_job_degrades_when_the_push_stops_being_republished(tmp_path: Path) -> None:
    completed_at = datetime(2026, 8, 25, 2, 11, tzinfo=UTC)
    path = tmp_path / "offsite.json"
    _write_restore_result(path, _offsite_payload(completed_at))

    status = status_collector._offsite_copy_job(
        completed_at + timedelta(days=3),
        path=path,
        runner=_backup_runner(),
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )

    assert status.state == "degraded"
    assert "stale" in status.detail


def test_offsite_job_degrades_when_the_volume_sent_misses_the_dump(tmp_path: Path) -> None:
    """rsync exiting 0 is a claim about a command, not about the generation leaving the host."""
    completed_at = datetime(2026, 8, 30, 2, 11, tzinfo=UTC)
    path = tmp_path / "offsite.json"
    _write_restore_result(path, _offsite_payload(completed_at, dump_bytes_covered=False))

    status = status_collector._offsite_copy_job(
        completed_at + timedelta(hours=1),
        path=path,
        runner=_backup_runner(),
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )

    assert status.state == "degraded"
    assert "does not account for the generation's dump" in status.detail


def test_offsite_job_degrades_on_a_failed_push(tmp_path: Path) -> None:
    completed_at = datetime(2026, 8, 30, 2, 11, tzinfo=UTC)
    path = tmp_path / "offsite.json"
    payload = _offsite_payload(completed_at, result="failed", failure_detail="raw_push_failed")
    payload["streams"][1]["state"] = "failed"
    payload["streams"][1]["exit_status"] = 23
    _write_restore_result(path, payload)

    status = status_collector._offsite_copy_job(
        completed_at + timedelta(hours=1),
        path=path,
        runner=_backup_runner(),
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )

    assert status.state == "degraded"
    assert "raw_push_failed" in status.detail


def test_offsite_job_refuses_a_receipt_a_reader_could_have_written(tmp_path: Path) -> None:
    completed_at = datetime(2026, 8, 30, 2, 11, tzinfo=UTC)
    path = tmp_path / "offsite.json"
    path.write_text(json.dumps(_offsite_payload(completed_at)), encoding="utf-8")
    path.chmod(0o666)

    status = status_collector._offsite_copy_job(
        completed_at + timedelta(hours=1),
        path=path,
        runner=_backup_runner(),
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )

    assert status.state == "degraded"
    assert "unsafe" in status.detail


def test_recovery_job_says_never_executed_rather_than_ok_or_silent(tmp_path: Path) -> None:
    """The honest default for a path nobody has ever run is pending, and it says why."""
    status = status_collector._recovery_drill_job(
        datetime(2026, 8, 30, tzinfo=UTC),
        path=tmp_path / "absent.json",
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )

    assert status.state == "pending"
    assert "never been executed" in status.detail
    assert status.last_run_at is None


def test_recovery_job_reports_a_real_proof_when_one_finally_exists(tmp_path: Path) -> None:
    completed_at = datetime(2026, 8, 29, tzinfo=UTC)
    path = tmp_path / "recovery.json"
    _write_restore_result(
        path,
        {
            "receipt_version": 1,
            "result": "passed",
            "failure_detail": None,
            "target_database": "glasswell_recovery",
            "dump": {
                "name": "glasswell-20260830T020825Z.dump",
                "sha256": "c" * 64,
                "bytes": 1_493_358_179,
            },
            "started_at": (completed_at - timedelta(hours=1)).isoformat(),
            "completed_at": completed_at.isoformat(),
            "duration_seconds": 3600,
            "source_schema_version": 54,
            "restored_schema_version": 54,
            "schema_match": True,
            "critical_row_counts": [
                {"dataset": "lineage.manifests", "source_rows": 197, "restored_rows": 197,
                 "match": True}
            ],
            "representative_reads": [{"id": "lineage_manifest", "passed": True}],
            "globals_restored": True,
            "raw_zone": {"files": 12, "bytes": 2_040_109_465},
        },
    )

    status = status_collector._recovery_drill_job(
        completed_at + timedelta(days=2),
        path=path,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )

    assert status.state == "ok"
    assert "schema 54" in status.detail


def test_a_healthy_weekly_drill_does_not_degrade_between_runs(tmp_path: Path) -> None:
    """The drill is weekly and the dump bound is two days; measured against `now` the job would
    go degraded every Tuesday and stay there until Sunday, refusing every deploy in between."""
    completed_at = datetime(2026, 8, 30, 4, 14, tzinfo=UTC)
    path = tmp_path / "restore.json"
    _write_restore_result(
        path,
        # Sunday's drill restored a dump taken two hours earlier: healthy by any reading.
        _restore_payload(completed_at, dump_created_at=completed_at - timedelta(hours=2)),
    )
    runner = _runner(
        {
            "glasswell-restore-drill.timer": "ActiveState=active\n",
            "glasswell-restore-drill.service": (
                "Result=success\nExecMainStatus=0\n"
                "ExecMainExitTimestamp=Thu 2026-08-27 02:09:24 UTC\n"
            ),
        }
    )

    # Wednesday: the receipt is three days old, well inside the eight-day proof bound, and the
    # dump it restored was two hours old at drill time.
    status = _restore_drill_job(
        completed_at + timedelta(days=3),
        path=path,
        runner=runner,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )

    assert status.state == "ok"
    assert "stale" not in status.detail


def test_a_drill_that_restored_an_old_dump_still_degrades(tmp_path: Path) -> None:
    """The check the dump bound exists for: backups stopped, so the drill had nothing fresh."""
    completed_at = datetime(2026, 8, 30, 4, 14, tzinfo=UTC)
    path = tmp_path / "restore.json"
    _write_restore_result(
        path,
        _restore_payload(completed_at, dump_created_at=completed_at - timedelta(days=5)),
    )

    status = _restore_drill_job(
        completed_at + timedelta(hours=1),
        path=path,
        runner=_runner({"glasswell-restore-drill.timer": "ActiveState=active\n"}),
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )

    assert status.state == "degraded"
    assert "backup dump is stale" in status.detail
    assert "when the drill ran" in status.detail
