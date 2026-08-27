"""Collector logic that turns service-manager evidence into cautious job states."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from psycopg import IsolationLevel
from psycopg.pq import TransactionStatus

from glasswell.status.collector import (
    _configure_inventory_connection,
    _job,
    _system_service,
    _systemd_properties,
)


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
