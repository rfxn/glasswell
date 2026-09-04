"""Collect exact dataset inventory and sanitized host observations into one atomic snapshot."""

from __future__ import annotations

import argparse
import json
import os
import socket
import ssl
import stat
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

import psycopg
from psycopg import IsolationLevel
from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row
from pydantic import BaseModel, ValidationError

from glasswell.lineage.jurisdictions import load_jurisdictions
from glasswell.lineage.schedules import (
    ScheduledJob,
    ScheduleRegistry,
    ScheduleRegistryError,
    load_schedules,
)
from glasswell.scheduler.plan import collect_evidence, next_due_at
from glasswell.status.models import (
    DATABASE_BYTES_REASON,
    INVENTORY_REASON,
    SCHEMA_VERSION_REASON,
    CheckState,
    CheckTier,
    DatasetInventory,
    InventoryMetric,
    JobSchedule,
    JobStatus,
    OffsiteCopyReceipt,
    PlatformStatus,
    RecoveryDrillResult,
    RestoreDrillResult,
    StatusCheck,
    StatusDisclosure,
    StatusSnapshot,
)

SNAPSHOT_ENV = "GLASSWELL_STATUS_SNAPSHOT"
DEFAULT_SNAPSHOT = Path("/var/lib/glasswell/status.json")
RESTORE_RESULT_ENV = "GLASSWELL_RESTORE_RESULT"
DEFAULT_RESTORE_RESULT = Path("/var/lib/glasswell-restore-drill/result.json")
OFFSITE_RECEIPT_ENV = "GLASSWELL_OFFSITE_RECEIPT"
DEFAULT_OFFSITE_RECEIPT = Path("/var/lib/glasswell-backup/offsite.json")
RECOVERY_RESULT_ENV = "GLASSWELL_RECOVERY_RESULT"
DEFAULT_RECOVERY_RESULT = Path("/var/lib/glasswell-recovery-drill/result.json")
DSN_ENV = "GLASSWELL_DSN"
FALLBACK_DSN_ENV = "DATABASE_URL"
CODE_VERSION_ENV = "GLASSWELL_CODE_VERSION"
EDGE_HOST_ENV = "GLASSWELL_STATUS_EDGE_HOST"
DEFAULT_EDGE_HOST = "glasswell.lab.rpx.sh"
PGDATA_ENV = "GLASSWELL_STATUS_PGDATA"
DEFAULT_PGDATA = Path("/var/lib/postgresql/16/main")
PGDATA_FLOOR_ENV = "GLASSWELL_STATUS_PGDATA_MIN_BYTES"
# 60 GiB: the 40 GiB per-year floor the Texas load stops at, plus the 20 GB a monthly restage
# rewrites. It governs at both filesystem sizes the platform spec plans for, where 10 % does not.
DEFAULT_PGDATA_FLOOR_BYTES = 64_424_509_440
MARTIN_HEALTH = "http://127.0.0.1:3000/health"
QUERY_TIMEOUT_MS = 120_000
MAX_RESTORE_RESULT_BYTES = 131_072
RESTORE_RESULT_STALE_AFTER = timedelta(days=8)
RESTORE_DUMP_STALE_AFTER = timedelta(days=2)
RESTORE_RESULT_FUTURE_TOLERANCE = timedelta(minutes=5)
# The push is nightly, so two missed nights is the signal. infra/verify.sh pins the same bound.
OFFSITE_RECEIPT_STALE_AFTER = timedelta(days=2)

Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def _run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, capture_output=True, text=True, timeout=10)


def _systemd_properties(unit: str, runner: Runner = _run) -> dict[str, str]:
    try:
        result = runner(
            (
                "systemctl",
                "show",
                unit,
                "--no-pager",
                (
                    "--property=ActiveState,Result,ExecMainStatus,ExecMainExitTimestamp,"
                    "LastTriggerUSec,NextElapseUSecRealtime"
                ),
            )
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if result.returncode != 0:
        return {}
    return {
        key: value
        for line in result.stdout.splitlines()
        if "=" in line
        for key, value in (line.split("=", 1),)
    }


def _system_service(
    check_id: str,
    label: str,
    unit: str,
    observed_at: datetime,
    runner: Runner = _run,
    tier: CheckTier = "serving",
) -> StatusCheck:
    properties = _systemd_properties(unit, runner)
    if not properties:
        return StatusCheck(
            id=check_id,
            label=label,
            state="unavailable",
            observed_at=observed_at,
            detail="Service-manager evidence is unavailable.",
            tier=tier,
            probe=unit,
        )
    active = properties.get("ActiveState") == "active"
    return StatusCheck(
        id=check_id,
        label=label,
        state="ok" if active else "degraded",
        observed_at=observed_at,
        detail=(
            "Service manager reports active."
            if active
            else "Service manager does not report active."
        ),
        tier=tier,
        probe=unit,
    )


def _parse_systemd_time(value: str | None, runner: Runner = _run) -> datetime | None:
    if not value or value == "n/a":
        return None
    try:
        result = runner(("date", "--utc", f"--date={value}", "+%Y-%m-%dT%H:%M:%SZ"))
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    try:
        return datetime.fromisoformat(result.stdout.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def _job(
    job_id: str,
    label: str,
    timer_unit: str,
    service_unit: str,
    runner: Runner = _run,
) -> JobStatus:
    timer = _systemd_properties(timer_unit, runner)
    service = _systemd_properties(service_unit, runner)
    last_run = _parse_systemd_time(service.get("ExecMainExitTimestamp"), runner)
    next_run = _parse_systemd_time(timer.get("NextElapseUSecRealtime"), runner)
    result = service.get("Result")
    exit_status = service.get("ExecMainStatus")
    failed = result not in {None, "", "success"} or exit_status not in {None, "", "0"}
    if not timer or not service:
        state = "unavailable"
        detail = "Timer or last-run service evidence is unavailable."
    elif timer.get("ActiveState") != "active":
        state = "pending"
        detail = "Timer is installed but not armed."
    elif failed:
        state = "degraded"
        detail = "The most recently completed run failed."
    elif last_run is None:
        state = "pending"
        detail = "Timer is armed and has no recorded completed run yet."
    elif result != "success" or exit_status != "0":
        state = "unavailable"
        detail = "The completed run lacks conclusive success evidence."
    else:
        state = "ok"
        detail = "Timer is armed and the most recently completed run succeeded."
    return JobStatus(
        id=job_id,
        label=label,
        state=state,
        last_run_at=last_run,
        next_run_at=next_run,
        detail=detail,
        unit=timer_unit,
        timer_armed=None if not timer else timer.get("ActiveState") == "active",
    )



_LAST_JOB_RUNS = """
select distinct on (job_id) job_id, outcome, started_at, completed_at, planned_at,
       refusal_code, failure_detail
  from lineage.job_runs
 order by job_id, planned_at desc, run_id desc
"""

# A systemd timer and the service it triggers differ only in suffix. That is a convention of
# systemd's own naming, not a mapping this project gets to decide, so deriving one from the
# other is not a decision hidden in code.
def _timer_for(service_unit: str) -> str:
    return service_unit.removesuffix(".service") + ".timer"


def _schedule_of(job: ScheduledJob) -> JobSchedule:
    return JobSchedule(
        job_id=job.job_id,
        effective_from=job.effective_from,
        published_at=job.published_at,
        rule_id=job.rule_id,
        rationale=job.rationale,
        external_timer_unit=job.external_timer_unit,
        external_service_unit=job.external_service_unit,
    )


def _state_of_run(
    registry: ScheduleRegistry, outcome: str | None, refusal_code: str | None
) -> tuple[str, str | None]:
    """The job's state and the refusal's severity class, read from the registry vocabulary.

    The class is a row, not a list in this function: a standing informational condition must
    not redden the deploy gate, and which conditions are standing is a decision that changes
    without a release.
    """
    severity = registry.severity_of(refusal_code)
    if outcome == "ran":
        return "ok", None
    if outcome in ("failed", "interrupted"):
        return "degraded", severity
    if outcome == "refused":
        return {"informational": "refused", "waiting": "pending"}.get(
            severity or "", "degraded"
        ), severity
    return "pending", None


def _detail_with_refusal(
    registry: ScheduleRegistry, detail: str, last: dict | None
) -> str:
    """The unit's sentence, and the plan's own reason where the plan had one."""
    code = registry.refusal_codes.get((last or {}).get("refusal_code") or "")
    return detail if code is None else f"{detail} {code.sentence}"


def _registry_jobs(
    connection: psycopg.Connection, observed_at: datetime, runner: Runner = _run
) -> list[JobStatus]:
    """One row per registered job, generated rather than typed out six times over."""
    try:
        registry = load_schedules(connection)
    except ScheduleRegistryError as refusal:
        return [
            JobStatus(
                id="job_registry",
                label="Scheduled job registry",
                state="unavailable",
                detail=str(refusal),
            )
        ]
    evidence = collect_evidence(
        connection,
        now=observed_at,
        source_ids=[source for job in registry for source in job.source_ids],
    )
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(_LAST_JOB_RUNS)
        last_runs = {row["job_id"]: row for row in cursor.fetchall()}

    jobs: list[JobStatus] = []
    for job in registry:
        last = last_runs.get(job.job_id)
        duration = (
            int((last["completed_at"] - last["started_at"]).total_seconds())
            if last and last["started_at"] and last["completed_at"]
            else None
        )
        due = next_due_at(job, evidence, observed_at)
        service_unit = job.external_service_unit or job.legacy_unit
        # The unit column reports whether a *timer* is armed, so it names the timer; the
        # service it triggers is what the run evidence is read from.
        unit = None if service_unit is None else _timer_for(service_unit)
        # The plan's own refusal survives whichever branch the state comes from. A job an
        # installed timer drives takes its state from that unit, but the reason its plan could
        # not run is still the row a reader came for, so the class travels with it.
        refusal_class = registry.severity_of(last["refusal_code"] if last else None)
        if service_unit is not None:
            # A row an installed timer still drives shows that unit's evidence beside the plan,
            # so the page never claims the scheduler ran something it did not.
            probed = _job(job.job_id, job.label, unit, service_unit, runner)
            # A fault the plan recorded outranks the unit's own state: the timer may be
            # perfectly armed and the reason this job cannot run is still the row a reader
            # came for, and a group that opened for it must show why on its face.
            state = "degraded" if refusal_class == "fault" else probed.state
            last_run_at, next_run_at = probed.last_run_at, probed.next_run_at
            detail = _detail_with_refusal(registry, probed.detail, last)
            timer_armed = probed.timer_armed
        else:
            state, refusal_class = _state_of_run(
                registry,
                last["outcome"] if last else None,
                last["refusal_code"] if last else None,
            )
            last_run_at = last["completed_at"] if last else None
            next_run_at = None
            # A failed run's own reason outranks the cadence, which answers a different
            # question; 076 CHECKs that a failed outcome carries one.
            detail = (
                registry.refusal_codes[last["refusal_code"]].sentence
                if last and last["refusal_code"] in registry.refusal_codes
                else (last or {}).get("failure_detail") or job.cadence_note
            )
            timer_armed = None
        jobs.append(
            JobStatus(
                id=job.job_id,
                label=job.label,
                state=state,
                last_run_at=last_run_at,
                next_run_at=next_run_at,
                detail=detail,
                unit=unit,
                timer_armed=timer_armed,
                kind=job.kind,
                jurisdiction=job.jurisdiction,
                cadence=job.cadence_note,
                next_due_at=due,
                duration_seconds=duration,
                last_outcome=last["outcome"] if last else None,
                refusal_code=last["refusal_code"] if last else None,
                refusal_class=refusal_class,
                launch_mode=job.launch_mode,
                schedule=_schedule_of(job),
            )
        )
    return jobs


def _load_receipt[Receipt: BaseModel](
    path: Path,
    model: type[Receipt],
    noun: str,
    *,
    expected_uid: int = 0,
    expected_gid: int | None = None,
) -> tuple[Receipt | None, str, CheckState | None]:
    """Read a root-published durability receipt, refusing anything a reader could have forged."""
    group = os.getgid() if expected_gid is None else expected_gid
    try:
        metadata = path.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or path.is_symlink()
            or metadata.st_nlink != 1
            or metadata.st_uid != expected_uid
            or metadata.st_gid != group
            or stat.S_IMODE(metadata.st_mode) != 0o640
        ):
            return None, f"Durable {noun} path, ownership or mode is unsafe.", "degraded"
        if metadata.st_size > MAX_RESTORE_RESULT_BYTES:
            return None, f"Durable {noun} exceeds the accepted size.", "degraded"
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
            opened = os.fstat(handle.fileno())
            if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
                return None, f"Durable {noun} changed while it was opened.", "degraded"
            payload = handle.read(MAX_RESTORE_RESULT_BYTES + 1)
        if len(payload.encode("utf-8")) > MAX_RESTORE_RESULT_BYTES:
            return None, f"Durable {noun} exceeds the accepted size.", "degraded"
        return model.model_validate_json(payload), "", None
    except FileNotFoundError:
        return None, f"No durable {noun} has been published yet.", "unavailable"
    except (OSError, UnicodeError, ValidationError):
        return None, f"Durable {noun} could not be validated.", "degraded"


def _restore_drill_job(
    observed_at: datetime,
    *,
    path: Path | None = None,
    runner: Runner = _run,
    expected_uid: int = 0,
    expected_gid: int | None = None,
) -> JobStatus:
    scheduled = _job(
        "restore_drill",
        "Weekly restore drill",
        "glasswell-restore-drill.timer",
        "glasswell-restore-drill.service",
        runner,
    )
    target = path or Path(os.environ.get(RESTORE_RESULT_ENV, DEFAULT_RESTORE_RESULT))
    proof, error, invalid_state = _load_receipt(
        target,
        RestoreDrillResult,
        "restore result",
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    if proof is None:
        if invalid_state == "unavailable" and scheduled.last_run_at is None:
            state = "pending" if scheduled.state == "pending" else scheduled.state
        else:
            state = invalid_state or "unavailable"
        return JobStatus(
            id="restore_drill",
            label="Weekly restore drill",
            state=state,
            last_run_at=scheduled.last_run_at,
            next_run_at=scheduled.next_run_at,
            detail=error,
            unit=scheduled.unit,
            timer_armed=scheduled.timer_armed,
        )

    completed_at = proof.completed_at.astimezone(UTC)
    age = observed_at - completed_at
    # Measured at drill time, not now: the question is whether the newest dump the drill could
    # find was recent *when it ran*. Against `now` this compares a 2-day bound to a weekly
    # cadence, so the job degrades every Tuesday and stays degraded until Sunday — which reds
    # verify.sh's snapshot check and refuses every deploy in between. A backup that stopped
    # producing generations is still caught, by the `backup` job and by `offsite_copy`'s own
    # 2-day bound against now.
    dump_age = completed_at - proof.dump.created_at.astimezone(UTC) if proof.dump else None
    age_hours = max(0, int(age.total_seconds() // 3600))
    age_detail = f"age {age_hours}h"
    if age < -RESTORE_RESULT_FUTURE_TOLERANCE:
        state = "degraded"
        detail = "Durable restore result completion time is implausibly in the future."
    elif proof.result == "failed":
        state = "degraded"
        cleanup = "verified" if proof.scratch_removed else "not verified"
        detail = (
            f"Latest durable restore drill failed ({proof.failure_detail}); {age_detail};"
            f" scratch cleanup {cleanup}."
        )
    elif age > RESTORE_RESULT_STALE_AFTER:
        state = "degraded"
        detail = f"Latest durable restore proof passed but is stale ({age_detail})."
    elif dump_age is not None and dump_age < -RESTORE_RESULT_FUTURE_TOLERANCE:
        state = "degraded"
        detail = "Restored dump was created after the drill that restored it completed."
    elif dump_age is not None and dump_age > RESTORE_DUMP_STALE_AFTER:
        state = "degraded"
        dump_age_hours = max(0, int(dump_age.total_seconds() // 3600))
        detail = (
            "Latest restore passed, but its backup dump is stale: it was already"
            f" {dump_age_hours}h old when the drill ran."
        )
    elif scheduled.state != "ok":
        state = scheduled.state
        detail = (
            f"Latest durable restore proof passed ({age_detail}), but schedule evidence is"
            f" {scheduled.state}."
        )
    else:
        state = "ok"
        detail = (
            f"Durable restore proof passed ({age_detail}) for {proof.dump.name};"
            f" schema {proof.restored_schema_version}, {len(proof.critical_row_counts)} critical"
            " row counts and representative reads matched; scratch cleanup verified."
        )
    return JobStatus(
        id="restore_drill",
        label="Weekly restore drill",
        state=state,
        last_run_at=completed_at,
        next_run_at=scheduled.next_run_at,
        detail=detail,
        unit=scheduled.unit,
        timer_armed=scheduled.timer_armed,
    )


def _offsite_copy_job(
    observed_at: datetime,
    *,
    path: Path | None = None,
    runner: Runner = _run,
    expected_uid: int = 0,
    expected_gid: int | None = None,
) -> JobStatus:
    """Offsite recency from the sending side only; the remote grant permits no read-back."""
    label = "Offsite backup copy"
    scheduled = _job(
        "offsite_copy", label, "glasswell-backup.timer", "glasswell-backup.service", runner
    )
    target = path or Path(os.environ.get(OFFSITE_RECEIPT_ENV, DEFAULT_OFFSITE_RECEIPT))
    receipt, error, invalid_state = _load_receipt(
        target,
        OffsiteCopyReceipt,
        "offsite copy receipt",
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    if receipt is None:
        if invalid_state == "unavailable" and scheduled.last_run_at is None:
            state = "pending" if scheduled.state == "pending" else scheduled.state
        else:
            state = invalid_state or "unavailable"
        return JobStatus(
            id="offsite_copy",
            label=label,
            state=state,
            last_run_at=scheduled.last_run_at,
            next_run_at=scheduled.next_run_at,
            detail=error,
            unit=scheduled.unit,
            timer_armed=scheduled.timer_armed,
        )

    completed_at = receipt.completed_at.astimezone(UTC)
    age = observed_at - completed_at
    age_hours = max(0, int(age.total_seconds() // 3600))
    pushed = next(item for item in receipt.streams if item.id == "pgdump")
    if age < -RESTORE_RESULT_FUTURE_TOLERANCE:
        state = "degraded"
        detail = "Offsite copy receipt completion time is implausibly in the future."
    elif receipt.result == "failed":
        state = "degraded"
        detail = f"Latest offsite push failed ({receipt.failure_detail}); age {age_hours}h."
    elif age > OFFSITE_RECEIPT_STALE_AFTER:
        state = "degraded"
        detail = f"Latest offsite push succeeded but is stale (age {age_hours}h)."
    elif not receipt.dump_bytes_covered:
        state = "degraded"
        detail = (
            f"Latest offsite push reported success (age {age_hours}h), but the volume it sent"
            " does not account for the generation's dump."
        )
    elif scheduled.state != "ok":
        state = scheduled.state
        detail = (
            f"Latest offsite push succeeded (age {age_hours}h), but schedule evidence is"
            f" {scheduled.state}."
        )
    else:
        state = "ok"
        # No host, address or path: this string is served, and the receipt that carries the
        # destination stays root-owned on disk.
        detail = (
            f"Offsite push recorded (age {age_hours}h) for generation {receipt.generation};"
            f" {pushed.files_transferred} files and {pushed.bytes_transferred} bytes sent,"
            " covering the generation's dump. Sending-side evidence only: the remote grant is"
            " write-only, so no read-back was performed."
        )
    return JobStatus(
        id="offsite_copy",
        label=label,
        state=state,
        last_run_at=completed_at,
        next_run_at=scheduled.next_run_at,
        detail=detail,
        unit=scheduled.unit,
        timer_armed=scheduled.timer_armed,
    )


def _recovery_drill_job(
    observed_at: datetime,
    *,
    path: Path | None = None,
    expected_uid: int = 0,
    expected_gid: int | None = None,
) -> JobStatus:
    """Replacement-host recovery. There is no timer: it is operator-run and has never been run."""
    label = "Replacement-host recovery"
    target = path or Path(os.environ.get(RECOVERY_RESULT_ENV, DEFAULT_RECOVERY_RESULT))
    receipt, error, invalid_state = _load_receipt(
        target,
        RecoveryDrillResult,
        "recovery result",
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    if receipt is None:
        if invalid_state == "unavailable":
            return JobStatus(
                id="recovery_drill",
                label=label,
                state="pending",
                detail=(
                    "The replacement-host recovery procedure is mechanised and has never been"
                    " executed. No recovery has been proven."
                ),
            )
        return JobStatus(id="recovery_drill", label=label, state=invalid_state, detail=error)

    completed_at = receipt.completed_at.astimezone(UTC)
    age = observed_at - completed_at
    age_days = max(0, int(age.total_seconds() // 86400))
    if age < -RESTORE_RESULT_FUTURE_TOLERANCE:
        state = "degraded"
        detail = "Recovery result completion time is implausibly in the future."
    elif receipt.result == "failed":
        state = "degraded"
        detail = f"Latest recovery drill failed ({receipt.failure_detail}); age {age_days}d."
    else:
        state = "ok"
        detail = (
            f"Recovery proven {age_days}d ago at schema {receipt.restored_schema_version}:"
            " cluster globals, logical dump and raw zone restored on a replacement host."
        )
    return JobStatus(id="recovery_drill", label=label, state=state, last_run_at=completed_at,
                     detail=detail)


def _martin_check(observed_at: datetime) -> StatusCheck:
    active = _systemd_properties("martin.service").get("ActiveState") == "active"
    reachable = False
    try:
        request = Request(MARTIN_HEALTH, headers={"Accept": "text/plain"})
        with urlopen(request, timeout=3) as response:
            reachable = response.status == 200
    except (OSError, URLError):
        pass
    ok = active and reachable
    return StatusCheck(
        id="tiles",
        label="Vector tiles",
        state="ok" if ok else "degraded",
        observed_at=observed_at,
        detail=(
            "Tile service is active and its health probe answered."
            if ok
            else "Tile service activity or its bounded health probe failed."
        ),
        tier="serving",
        probe="martin.service",
    )


def _edge_check(observed_at: datetime, host: str) -> StatusCheck:
    active = _systemd_properties("caddy.service").get("ActiveState") == "active"
    reachable = False
    try:
        context = ssl.create_default_context()
        with (
            socket.create_connection(("127.0.0.1", 443), timeout=4) as raw,
            context.wrap_socket(raw, server_hostname=host) as secure,
        ):
            secure.sendall(
                f"GET /healthz HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode()
            )
            with secure.makefile("rb") as response:
                status_line = response.readline(256)
            reachable = status_line.startswith(b"HTTP/") and b" 200 " in status_line
    except (OSError, ssl.SSLError):
        pass
    ok = active and reachable
    return StatusCheck(
        id="edge",
        label="HTTPS edge",
        state="ok" if ok else "degraded",
        observed_at=observed_at,
        detail=(
            "Edge service is active and a certificate-verified request answered."
            if ok
            else "Edge activity or its certificate-verified request failed."
        ),
        tier="edge",
        probe="caddy.service",
    )


def _storage_check(
    check_id: str,
    label: str,
    path: Path,
    observed_at: datetime,
    *,
    minimum_available: int | None = None,
) -> StatusCheck:
    try:
        stats = os.statvfs(path)
        available_ratio = stats.f_bavail / stats.f_blocks if stats.f_blocks else 0.0
        available = stats.f_bavail * stats.f_frsize
    except OSError:
        return StatusCheck(
            id=check_id,
            label=label,
            state="unavailable",
            observed_at=observed_at,
            detail="Capacity could not be observed.",
            tier="host",
            probe=str(path),
        )
    healthy = available_ratio >= 0.10 and (
        minimum_available is None or available >= minimum_available
    )
    return StatusCheck(
        id=check_id,
        label=label,
        state="ok" if healthy else "degraded",
        observed_at=observed_at,
        detail=(
            "Available capacity is above the configured guardrail."
            if healthy
            else "Available capacity is below the configured guardrail."
        ),
        tier="host",
        probe=str(path),
    )


# The root filesystem matters because PGDATA sits on it, so the check follows PGDATA rather
# than "/" and carries an absolute floor as well as the ratio: on the sizes this host is
# planned at, 10 % of the disk is well below the room a Texas-scale load or a restage needs.
def _root_storage_check(observed_at: datetime) -> StatusCheck:
    floor = os.environ.get(PGDATA_FLOOR_ENV, "")
    return _storage_check(
        "root_storage",
        "System storage",
        Path(os.environ.get(PGDATA_ENV, DEFAULT_PGDATA)),
        observed_at,
        # A malformed value keeps the default: this guard is lowered by setting a byte count,
        # never by mistyping one.
        minimum_available=int(floor) if floor.isdecimal() else DEFAULT_PGDATA_FLOOR_BYTES,
    )


def _metric(metric_id: str, label: str, value: Any, unit: str) -> InventoryMetric:
    return InventoryMetric(
        metric_id=metric_id,
        label=label,
        value=int(value or 0),
        unit=unit,
        precision="exact",
        reason=INVENTORY_REASON,
    )


def _one(
    connection: psycopg.Connection, statement: str, parameters: Any = None
) -> dict[str, Any]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(statement, parameters)
        row = cursor.fetchone()
    return dict(row or {})


# Which sources are inventoried as production is read from the rules that registered them, and
# the jurisdiction each is counted under from the source registry those rules name as their
# discriminator (R8). A new state registers a source and a rule; it does not edit this module.
# The registry is the row source and the rules are a predicate over it, so a source cannot be
# inventoried twice however many rules register it; a join emitted one row per rule, and two
# in-force rules for one source served the same dataset_id twice.
_PRODUCTION_SOURCES = """
select s.source_id, s.name, coalesce(s.jurisdiction, s.source_id) as jurisdiction
  from lineage.sources s
 where s.source_id in (
       select r.source_id
         from lineage.conformance_rules r
        where r.rule_kind = 'code_ref'
          and r.spec ->> 'module_function' = 'glasswell.status.collector:_production_inventory'
          and r.effective_from <= current_date
          and (r.effective_to is null or r.effective_to > current_date))
 order by jurisdiction, s.source_id
"""

# One bounded question per source. Each arm is index-only under migration 069: rows, months and
# the valid-time bounds ride (source_id, production_month), the entity count rides
# (source_id, entity_key), and the knowledge time is a one-row backward scan on
# (source_id, created_at desc). Asking them of the whole table with FILTER instead reads every
# row of every state and sorts all of it — that is the shape this replaced.
_PRODUCTION_METRICS = """
select m.rows, m.months, m.valid_from, m.valid_to, e.entities, k.latest_knowledge
  from (select count(*) as rows, count(distinct production_month) as months,
               min(production_month) as valid_from, max(production_month) as valid_to
          from canonical.production_monthly where source_id = %(source_id)s) m,
       (select count(distinct entity_key) as entities
          from canonical.production_monthly where source_id = %(source_id)s) e,
       (select max(created_at) as latest_knowledge
          from canonical.production_monthly where source_id = %(source_id)s) k
"""


@dataclass(frozen=True, slots=True)
class _ProductionPresentation:
    """How one source's production inventory is named and qualified.

    Prose only. Which sources are counted and under which jurisdiction is registry data; this
    carries the grain wording and the caveats that grain forces, which no registry row holds. A
    source without an entry is still counted, under its registered name.
    """

    dataset_id: str
    label: str
    grain: str
    entity_metric_id: str
    entity_label: str
    entity_unit: str
    detail: str
    show_months: bool = True


_VINTAGE_NOTE = "Includes retained report vintages; it is not a count of physical wells."


@dataclass(frozen=True, slots=True)
class _CompletionsPresentation:
    """How one jurisdiction's completion inventory is named and qualified.

    Prose only, and keyed by jurisdiction code rather than by API prefix. Which jurisdictions
    are counted is registry data; the grain wording and the caveats that grain forces are not
    in any registry row. A jurisdiction with no entry is still counted, under the default.
    """

    label_suffix: str
    grain: str
    detail: str


_DEFAULT_WELLS_DETAIL = (
    "Current effective-dated well entities, not accumulated source revisions."
)

_DEFAULT_COMPLETIONS = _CompletionsPresentation(
    label_suffix="completion observations",
    grain="one source-vintage effective-dated completion dimension observation",
    detail="Effective-dated completion dimensions; zero remains an exact unpromoted inventory.",
)

_COMPLETIONS_PRESENTATION: dict[str, _CompletionsPresentation] = {
    "ND": _CompletionsPresentation(
        label_suffix="completion-pool observations",
        grain="one source-vintage completion-month pool observation",
        detail="Repeated source-month observations are not physical completion events.",
    ),
}

_PRODUCTION_PRESENTATION: dict[str, _ProductionPresentation] = {
    "nd_mpr_xlsx": _ProductionPresentation(
        dataset_id="canonical.production_monthly/nd",
        label="North Dakota production observations",
        grain="one append-only source revision per well, month and stream",
        entity_metric_id="wells",
        entity_label="Distinct wells",
        entity_unit="wells",
        detail=_VINTAGE_NOTE,
    ),
    "nm_ocd_wcproduction": _ProductionPresentation(
        dataset_id="canonical.production_monthly/nm",
        label="New Mexico production observations",
        grain="one append-only source revision per well, completion pool, month and stream",
        entity_metric_id="entities",
        entity_label="Distinct completion-pool entities",
        entity_unit="entities",
        detail=(
            "Counted at the completion-pool grain the source files, not rolled up to the well"
            " (cr_nm_wcproduction_inventory_jurisdiction_1), so this is not a well count. "
            + _VINTAGE_NOTE
        ),
    ),
    "co_ecmc_monthly_prod": _ProductionPresentation(
        dataset_id="canonical.production_monthly/co",
        label="Colorado production observations",
        grain="one append-only source revision per completion, month and stream, plus the"
        " well row that sums them",
        entity_metric_id="entities",
        entity_label="Distinct completion and well entities",
        entity_unit="entities",
        detail=(
            "Two grains in one count, and they are not added to each other by anything served:"
            " ECMC files per completion, and cr_co_production_grain_1 writes a well row beside"
            " those carrying their exact sum, disclosed as sum_over_pools. Oil is oil plus"
            " condensate because ECMC files one liquid stream and no condensate column exists"
            " (cr_co_production_liquids_1). The rolling file is the source, so this covers the"
            " months it carries rather than a well's life. " + _VINTAGE_NOTE
        ),
    ),
    "mt_bogc_well_production": _ProductionPresentation(
        dataset_id="canonical.production_monthly/mt-well",
        label="Montana well-grain production observations",
        grain="one append-only source revision per well, pool, month and stream",
        entity_metric_id="wells",
        entity_label="Distinct wells",
        entity_unit="wells",
        detail=(
            "MBOGC files two grains and this is one of them; the lease grain is counted as its"
            " own dataset (canonical.production_monthly/mt-lease) and the two are never added."
            " Oil is oil plus condensate as published (cr_mt_liquids_policy_1). " + _VINTAGE_NOTE
        ),
        show_months=False,
    ),
    "mt_bogc_pru_production": _ProductionPresentation(
        dataset_id="canonical.production_monthly/mt-lease",
        label="Montana lease-grain production observations",
        grain="one append-only source revision per lease unit, month and stream",
        entity_metric_id="lease_units",
        entity_label="Distinct lease units",
        entity_unit="units",
        detail=(
            "The PRU grain. These rows carry a lease entity_key and no API-10, so they are"
            " invisible to any well-prefix filter and are counted by source instead. Never"
            " summed with the well grain (canonical.production_monthly/mt-well): the two are"
            " the same production reported at different levels, not two populations."
        ),
        show_months=False,
    ),
}


EMPTY_ARM = "unavailable"


def _by_state(connection: psycopg.Connection, statement: str) -> dict[str, dict[str, Any]]:
    """One grouped read indexed by API state code, so an arm per jurisdiction costs no query."""
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(statement)
        return {row["state_code"]: dict(row) for row in cursor.fetchall()}


def _production_presentation(source_id: str, name: str) -> _ProductionPresentation:
    known = _PRODUCTION_PRESENTATION.get(source_id)
    if known is not None:
        return known
    return _ProductionPresentation(
        dataset_id=f"canonical.production_monthly/{source_id}",
        label=f"{name} production observations",
        grain="one append-only source revision per reporting entity, month and stream",
        entity_metric_id="entities",
        entity_label="Distinct reporting entities",
        entity_unit="entities",
        detail=(
            "Counted at the grain this source files, by registered jurisdiction. No grain"
            " wording is registered for it yet, so nothing narrower is claimed here."
        ),
    )


def _production_inventory(
    connection: psycopg.Connection,
) -> list[tuple[_ProductionPresentation, dict[str, Any]]]:
    """Count canonical.production_monthly once per registered source, never once per table."""
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(_PRODUCTION_SOURCES)
        sources = [dict(row) for row in cursor.fetchall()]
    return [
        (
            _production_presentation(source["source_id"], source["name"]),
            {
                "jurisdiction": source["jurisdiction"],
                **_one(connection, _PRODUCTION_METRICS, {"source_id": source["source_id"]}),
            },
        )
        for source in sources
    ]


def _inventory(
    connection: psycopg.Connection, observed_at: datetime
) -> tuple[list[DatasetInventory], PlatformStatus]:
    platform = _one(
        connection,
        "select coalesce(max(version), 0) as schema_version,"
        " pg_database_size(current_database()) as database_bytes"
        " from public.schema_migrations",
    )
    # Grouped, not one filtered arm per state: a fifth jurisdiction is a registry row and this
    # query does not know how many there are.
    # R8: which jurisdictions exist, what they are called and which API prefix each owns are
    # rows, read at the registry's own latest publication. The collector runs as glasswell_api,
    # which holds select on the tables and execute on the resolver.
    registry = load_jurisdictions(connection)
    scopes = {row.jurisdiction_code: row.name for row in registry}
    wells = _by_state(
        connection,
        "select state_code, count(*) as rows,"
        " min(effective_from) as valid_from, max(effective_from) as valid_to,"
        " max(created_at) as latest_knowledge"
        " from canonical.wells_latest where state_code is not null group by state_code",
    )
    production = _production_inventory(connection)
    # 069 took the `left(api10, 2) = '<literal>'` filtered aggregate out of the production arm;
    # this is the same removal on the completions arm. The prefix is still derived in SQL, but
    # which prefix belongs to which jurisdiction is the registry's answer, not this query's.
    completions = _by_state(
        connection,
        "select left(api10, 2) as state_code, count(*) as rows,"
        " count(distinct (source_id, completion_key)) as completion_keys,"
        " min(coalesce(production_month, effective_from)) as valid_from,"
        " max(coalesce(production_month, effective_from)) as valid_to,"
        " max(created_at) as latest_knowledge"
        " from canonical.well_completions group by left(api10, 2)",
    )
    anchors = _one(
        connection,
        "select count(*) as rows, count(distinct api10) as wells,"
        " min(completion_date) as valid_from, max(completion_date) as valid_to,"
        " max(created_at) as latest_knowledge"
        " from canonical.well_completion_anchors",
    )
    formations = _one(
        connection,
        "select count(*) as aliases, count(distinct formation) as formations"
        " from lineage.formation_aliases",
    )
    map_rows = _one(
        connection,
        "select (select count(*) from marts.nd_wells_tile) as nd_wells,"
        " (select count(*) from marts.nd_laterals_tile) as nd_laterals,"
        " (select count(*) from marts.tx_wells_tile) as tx_wells,"
        " (select count(*) from marts.tx_laterals_tile) as tx_laterals,"
        " (select count(*) from marts.nm_wells_tile) as nm_wells,"
        " (select count(*) from marts.mt_wells_tile) as mt_wells,"
        " (select count(*) from marts.mt_paths_tile) as mt_paths,"
        " (select max(created_at) from lineage.derivations"
        "   where output_dataset = 'marts.nd_tiles' and status = 'ok') as nd_latest_knowledge,"
        " (select max(created_at) from lineage.derivations"
        "   where output_dataset = 'marts.tx_tiles' and status = 'ok') as tx_latest_knowledge,"
        " (select max(created_at) from lineage.derivations"
        "   where output_dataset = 'marts.nm_tiles' and status = 'ok') as nm_latest_knowledge,"
        " (select max(created_at) from lineage.derivations"
        "   where output_dataset = 'marts.mt_tiles' and status = 'ok') as mt_latest_knowledge",
    )
    neighbors = _one(
        connection,
        "select count(*) as subjects,"
        " count(*) filter (where completion_date is not null) as dated_subjects,"
        " (select count(*) from marts.nd_neighbor_edges) as directed_edges,"
        " (select max(d.created_at) from lineage.derivations d"
        "   where d.output_dataset = 'marts.nd_neighbors' and d.status = 'ok')"
        "   as latest_knowledge"
        " from marts.nd_neighbor_subjects",
    )
    quality = _one(
        connection,
        "select count(*) filter (where state = 'open') as open_rows,"
        " max(last_seen_at) filter (where state = 'open') as latest_knowledge"
        " from lineage.quarantine_rows",
    )
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "select reason_code, count(*) as rows from lineage.quarantine_rows"
            " where state = 'open' group by reason_code order by count(*) desc, reason_code"
        )
        quarantine_reasons = [dict(row) for row in cursor.fetchall()]
    conformance = _one(
        connection,
        "select count(*) as rules,"
        " count(*) filter (where effective_from <= current_date"
        "   and (effective_to is null or effective_to > current_date)) as in_force,"
        " count(distinct rule_family) as families,"
        " count(distinct source_id) as sources"
        " from lineage.conformance_rules",
    )
    raw = _one(
        connection,
        "select count(*) as manifests, coalesce(sum(bytes), 0) as bytes"
        " from lineage.manifests",
    )

    def dataset(
        dataset_id: str,
        label: str,
        scope: str,
        grain: str,
        metrics: list[InventoryMetric],
        detail: str,
        valid_from: Any = None,
        valid_to: Any = None,
        latest_knowledge: Any = None,
        state: str = "available",
    ) -> DatasetInventory:
        return DatasetInventory(
            dataset_id=dataset_id,
            label=label,
            scope=scope,
            grain=grain,
            state=state,
            counted_at=observed_at,
            latest_knowledge_at=latest_knowledge.isoformat() if latest_knowledge else None,
            metrics=metrics,
            valid_from=valid_from.isoformat() if valid_from else None,
            valid_to=valid_to.isoformat() if valid_to else None,
            detail=detail,
        )

    # Every jurisdiction arm, generated. A fifth registration yields a fifth wells dataset and a
    # fifth completions dataset with no edit here; an arm the tables hold nothing for reports
    # `unavailable` rather than a zero, because "not loaded" and "none" are different facts.
    registered = [row for row in registry if row.identity_prefix is not None]
    datasets = [
        *(
            dataset(
                f"canonical.wells_latest/{row.jurisdiction_code.lower()}",
                f"Current {row.name} wells",
                row.name,
                "one latest effective row per API-10",
                [_metric("rows", "Current wells", counted.get("rows", 0), "wells")],
                row.status_dataset_detail or _DEFAULT_WELLS_DETAIL,
                counted.get("valid_from"),
                counted.get("valid_to"),
                counted.get("latest_knowledge"),
                state="available" if counted else EMPTY_ARM,
            )
            for row in registered
            for counted in (wells.get(row.identity_prefix, {}),)
        ),
        *(
            dataset(
                shown.dataset_id,
                shown.label,
                scopes.get(counted["jurisdiction"], counted["jurisdiction"]),
                shown.grain,
                [
                    _metric("rows", "Observation rows", counted["rows"], "rows"),
                    _metric(
                        shown.entity_metric_id,
                        shown.entity_label,
                        counted["entities"],
                        shown.entity_unit,
                    ),
                    *(
                        [_metric("months", "Distinct months", counted["months"], "months")]
                        if shown.show_months
                        else []
                    ),
                ],
                shown.detail,
                counted["valid_from"],
                counted["valid_to"],
                counted["latest_knowledge"],
            )
            for shown, counted in production
        ),
        *(
            dataset(
                f"canonical.well_completions/{row.jurisdiction_code.lower()}",
                f"{row.name} {shown.label_suffix}",
                row.name,
                shown.grain,
                [
                    _metric("rows", "Observation rows", counted.get("rows", 0), "rows"),
                    _metric(
                        "completion_keys",
                        "Distinct source-scoped keys",
                        counted.get("completion_keys", 0),
                        "keys",
                    ),
                ],
                shown.detail,
                counted.get("valid_from"),
                counted.get("valid_to"),
                counted.get("latest_knowledge"),
                state="available" if counted else EMPTY_ARM,
            )
            for row in registered
            for shown in (
                _COMPLETIONS_PRESENTATION.get(row.jurisdiction_code, _DEFAULT_COMPLETIONS),
            )
            for counted in (completions.get(row.identity_prefix, {}),)
        ),
        dataset(
            "canonical.well_completion_anchors",
            "Completion anchor events",
            "North Dakota",
            "one append-only source-vintage hydraulic-fracture disclosure event",
            [
                _metric("rows", "Observed events", anchors["rows"], "events"),
                _metric("wells", "Distinct wells", anchors["wells"], "wells"),
            ],
            "Source-observed job-end events only; spud dates are never substituted.",
            anchors["valid_from"],
            anchors["valid_to"],
            anchors["latest_knowledge"],
        ),
        dataset(
            "lineage.formation_aliases",
            "Formation aliases",
            "Registered sources",
            "one source-scoped alias mapping per effective and knowledge vintage",
            [
                _metric("aliases", "Alias rows", formations["aliases"], "rows"),
                _metric(
                    "formations",
                    "Canonical formations",
                    formations["formations"],
                    "formations",
                ),
            ],
            (
                "Reference mappings are versioned context, not inferred well formations;"
                " per-source artifact age is reported separately below."
            ),
        ),
        dataset(
            "marts.published_map_layers/nd",
            "Published North Dakota map layers",
            "North Dakota",
            "one published feature per named North Dakota layer row; layers may overlap",
            [
                _metric("nd_wells", "ND well points", map_rows["nd_wells"], "features"),
                _metric("nd_laterals", "ND laterals", map_rows["nd_laterals"], "features"),
            ],
            "Layer rows are shown separately and are never summed as unique physical features.",
            latest_knowledge=map_rows["nd_latest_knowledge"],
        ),
        dataset(
            "marts.published_map_layers/tx",
            "Published Texas map layers",
            "Texas",
            "one published feature per named Texas layer row; layers may overlap",
            [
                _metric("tx_wells", "TX well points", map_rows["tx_wells"], "features"),
                _metric("tx_laterals", "TX laterals", map_rows["tx_laterals"], "features"),
            ],
            "Layer rows are shown separately and are never summed as unique physical features.",
            latest_knowledge=map_rows["tx_latest_knowledge"],
        ),
        dataset(
            "marts.published_map_layers/nm",
            "Published New Mexico map layers",
            "New Mexico",
            "one published feature per named New Mexico layer row",
            [_metric("nm_wells", "NM well points", map_rows["nm_wells"], "features")],
            (
                "A point layer only: no in-scope New Mexico source ships a lateral"
                " (cr_nm_wellhistory_geometry_scope_1), so none is drawn."
            ),
            latest_knowledge=map_rows["nm_latest_knowledge"],
        ),
        dataset(
            "marts.published_map_layers/mt",
            "Published Montana map layers",
            "Montana",
            "one published feature per named Montana layer row; layers may overlap",
            [
                _metric("mt_wells", "MT well points", map_rows["mt_wells"], "features"),
                _metric("mt_paths", "MT well paths", map_rows["mt_paths"], "features"),
            ],
            (
                "The paths are cartographic centrelines, never directional surveys"
                " (cr_mt_paths_geometry_class_1), and they cover a seventh of the wells that"
                " ever produced (cr_mt_paths_coverage_1). Absence is the normal case."
            ),
            latest_knowledge=map_rows["mt_latest_knowledge"],
        ),
        dataset(
            "marts.nd_neighbor_subjects",
            "North Dakota neighbour subjects",
            "North Dakota",
            "one current lateral-bearing subject well",
            [
                _metric("subjects", "Lateral-bearing subjects", neighbors["subjects"], "wells"),
                _metric(
                    "dated_subjects",
                    "Subjects with completion anchors",
                    neighbors["dated_subjects"],
                    "wells",
                ),
            ],
            (
                "Current geometry only. Completion-anchor coverage is an event-time inventory;"
                " no mart validity interval is implied."
            ),
            latest_knowledge=neighbors["latest_knowledge"],
        ),
        dataset(
            "marts.nd_neighbor_edges",
            "North Dakota physical-neighbour edges",
            "North Dakota",
            "one directed current-snapshot edge per subject and neighbour API-10 pair",
            [
                _metric(
                    "directed_edges",
                    "Directed physical-neighbour edges",
                    neighbors["directed_edges"],
                    "edges",
                )
            ],
            (
                "Edges extend through 26,400 feet and are counted as stored, not presented as"
                " unique undirected pairs."
            ),
            latest_knowledge=neighbors["latest_knowledge"],
        ),
        dataset(
            "lineage.conformance_rules",
            "Registered conformance rules",
            "All registered sources",
            "one registered mapping decision per rule id",
            [
                _metric("rules", "Registered rules", conformance["rules"], "rules"),
                _metric("in_force", "In force today", conformance["in_force"], "rules"),
                _metric("families", "Rule families", conformance["families"], "families"),
                _metric("sources", "Sources covered", conformance["sources"], "sources"),
            ],
            (
                "Every cross-source mapping decision is a registered row carrying a rationale"
                " and an effective date. A mapping that exists only in code is not counted"
                " here, because it does not exist. A registry has no validity interval of its"
                " own; 'in force today' is the temporal fact it does carry."
            ),
        ),
        dataset(
            "lineage.quarantine_rows",
            "Open quarantine",
            "All ingested sources",
            "one rejected row fingerprint per rule",
            [
                _metric("open_rows", "Open rows", quality["open_rows"], "rows"),
                *(
                    _metric(
                        f"reason_{row['reason_code']}", row["reason_code"], row["rows"], "rows"
                    )
                    for row in quarantine_reasons
                ),
            ],
            (
                "Counts only; no rejection rate is claimed without a matching input"
                " denominator. The per-reason rows partition the open population, so they sum"
                " to it."
            ),
            latest_knowledge=quality["latest_knowledge"],
        ),
        dataset(
            "lineage.manifests",
            "Registered raw artifacts",
            "All fetched sources",
            "one checksummed artifact per unique content hash",
            [
                _metric("manifests", "Artifacts", raw["manifests"], "artifacts"),
                _metric("bytes", "Registered bytes", raw["bytes"], "bytes"),
            ],
            (
                "Manifest storage inventory, not canonical dataset rows or fetch-attempt count;"
                " per-source registered-artifact age is reported separately below."
            ),
        ),
    ]
    return datasets, PlatformStatus(
        code_version=os.environ.get(CODE_VERSION_ENV),
        schema_version_reason=SCHEMA_VERSION_REASON,
        schema_version=platform["schema_version"],
        database_bytes=platform["database_bytes"],
        database_bytes_reason=DATABASE_BYTES_REASON,
        edge_host=os.environ.get(EDGE_HOST_ENV, DEFAULT_EDGE_HOST),
    )


def _configure_inventory_connection(connection: psycopg.Connection) -> None:
    if connection.info.transaction_status != TransactionStatus.IDLE:
        raise RuntimeError("status inventory collection requires an idle database connection")
    connection.isolation_level = IsolationLevel.REPEATABLE_READ
    connection.read_only = True


_ALLOCATION_RULE = "cr_tx_allocation_v0_1"
_ERROR_RULE = "cr_alloc_v0_error_bounds_1"
_CROSSWALK_RULE = "cr_tx_ewa_role_1"

_ALLOCATION_COVERAGE = """
select coalesce(sum(abs(a.volume)), 0) as allocated,
       coalesce((select sum(abs(lease_volume)) from marts.tx_allocation_ledger), 0)
           as unallocated,
       count(*) as shares
  from marts.tx_allocated_production a
"""

# The threshold is the rule's own; the jurisdiction is the registration that names the rule,
# because that is where a jurisdiction is declared and the rule itself is jurisdiction-neutral
# in everything but its id. Reading the code out of the rule's spec would have served a row
# labelled ": 0.0000" the first time a rule was written without one.
_DEGRADED_AT = """
select (c.spec ->> 'unallocated_share_degraded_at')::numeric as degraded_at,
       (select r.jurisdiction_code from lineage.jurisdiction_rules r
         where r.rule_id = c.rule_id and r.serving
         order by r.published_at desc limit 1) as jurisdiction
  from lineage.conformance_rules c where c.rule_id = %s
"""

_CROSSWALK_RESIDUAL = "select count(*) as districts from marts.tx_crosswalk_residual"

_METHOD_ERROR = """
select bed_jurisdiction, lease_months_scored, error_lo, error_hi
  from marts.allocation_method_error
"""


def _allocation_checks(
    connection: psycopg.Connection, observed_at: datetime
) -> list[StatusCheck]:
    """The three residuals an allocation publishes about itself, as data-tier rows.

    A failing check is degraded and drawn amber rather than absent: a row that vanishes reads
    as a surface nobody built, and these exist precisely so a reader can see that an estimate
    is being served and how far it can be out. The jurisdiction is named in every detail,
    because a second lease-grain state will register the same three.
    """
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(_DEGRADED_AT, (_ALLOCATION_RULE,))
        rule = cursor.fetchone()
        if rule is None:
            return []
        jurisdiction = str(rule["jurisdiction"] or "")
        if not jurisdiction:
            # No registration names this rule, so nothing is serving an allocation under it and
            # three rows about one would be three claims with no jurisdiction behind them.
            return []
        cursor.execute(_ALLOCATION_COVERAGE)
        coverage = cursor.fetchone() or {}
        cursor.execute(_CROSSWALK_RESIDUAL)
        crosswalk = cursor.fetchone() or {}
        cursor.execute(_METHOD_ERROR)
        study = cursor.fetchall()

    shares = int(coverage.get("shares") or 0)
    allocated = Decimal(coverage.get("allocated") or 0)
    unallocated = Decimal(coverage.get("unallocated") or 0)
    total = allocated + unallocated
    share = (unallocated / total) if total else Decimal(0)
    threshold = Decimal(rule["degraded_at"]) if rule["degraded_at"] is not None else None

    if shares == 0:
        conservation = StatusCheck(
            id="allocation_conservation",
            label="Allocation conservation",
            state="unavailable",
            observed_at=observed_at,
            detail=f"{jurisdiction}: the allocated mart holds no rows on this instance.",
            tier="data",
            probe=_ALLOCATION_RULE,
        )
    else:
        over = threshold is not None and share > threshold
        conservation = StatusCheck(
            id="allocation_conservation",
            label="Allocation conservation",
            state="degraded" if over else "ok",
            observed_at=observed_at,
            detail=(
                f"{jurisdiction}: {share:.4f} of lease volume has no eligible well to carry it"
                + (f", above the {threshold} {_ALLOCATION_RULE} records." if over else ".")
            ),
            tier="data",
            probe=_ALLOCATION_RULE,
        )

    if crosswalk.get("districts"):
        crosswalk_check = StatusCheck(
            id="crosswalk_agreement",
            label="Crosswalk agreement",
            state="ok",
            observed_at=observed_at,
            detail=(
                f"{jurisdiction}: the two published crosswalks are compared across"
                f" {int(crosswalk['districts'])} districts and the disagreement is served."
            ),
            tier="data",
            probe=_CROSSWALK_RULE,
        )
    else:
        crosswalk_check = StatusCheck(
            id="crosswalk_agreement",
            label="Crosswalk agreement",
            state="unavailable",
            observed_at=observed_at,
            detail=(
                f"{jurisdiction}: the crosswalk residual has not been measured on this"
                " instance. The two crosswalks are retained unmerged."
            ),
            tier="data",
            probe=_CROSSWALK_RULE,
        )

    if study:
        bed = study[0]
        bounds = StatusCheck(
            id="allocation_error_bounds",
            label="Allocation error bounds",
            state="ok",
            observed_at=observed_at,
            detail=(
                f"Measured on {bed['bed_jurisdiction']} over"
                f" {int(bed['lease_months_scored'])} lease-months; not yet transferable to"
                f" {jurisdiction}, so every allocated figure states not_measured."
            ),
            tier="data",
            probe=_ERROR_RULE,
        )
    else:
        bounds = StatusCheck(
            id="allocation_error_bounds",
            label="Allocation error bounds",
            state="degraded",
            observed_at=observed_at,
            detail=(
                "The method study has not been run, so no bed has been measured at all and"
                f" every {jurisdiction} figure states not_measured with nothing behind it."
            ),
            tier="data",
            probe=_ERROR_RULE,
        )
    return [conservation, crosswalk_check, bounds]


def collect(connection: psycopg.Connection, *, now: datetime | None = None) -> StatusSnapshot:
    _configure_inventory_connection(connection)
    observed_at = (now or datetime.now(UTC)).astimezone(UTC)
    with connection.cursor() as cursor:
        cursor.execute("select set_config('statement_timeout', %s, true)", (str(QUERY_TIMEOUT_MS),))
    datasets, platform = _inventory(connection, observed_at)
    checks = [
        _system_service("api_service", "API service", "glasswell-api.service", observed_at),
        _system_service(
            "database_service",
            "PostgreSQL service",
            "postgresql.service",
            observed_at,
            tier="data",
        ),
        _martin_check(observed_at),
        _edge_check(observed_at, os.environ.get(EDGE_HOST_ENV, DEFAULT_EDGE_HOST)),
        _system_service(
            "tunnel", "Cloudflare tunnel", "cloudflared.service", observed_at, tier="edge"
        ),
        _root_storage_check(observed_at),
        _storage_check("data_storage", "Data storage", Path("/data"), observed_at),
        *_allocation_checks(connection, observed_at),
    ]
    # Generated from the registry, so registering a job adds a row here and not a code edit.
    # The three receipt readers stay literals: none of them has a timer to probe -- the
    # recovery drill's own docstring says it is operator-run and has never been run -- so
    # there is no external unit pair for a registry row to name.
    jobs = [
        *_registry_jobs(connection, observed_at),
        _restore_drill_job(observed_at),
        _offsite_copy_job(observed_at),
        _recovery_drill_job(observed_at),
    ]
    disclosures = [
        StatusDisclosure(
            id="staging_inventory",
            label="Staging inventory",
            state="not_instrumented",
            detail=(
                "Parsers write staging and staging never serves, so this snapshot counts no"
                " staging rows. Staging volume is not observable from this page."
            ),
        ),
        StatusDisclosure(
            id="remote_backup_copy",
            label="Remote backup copy",
            state="limited",
            detail=(
                "The backup job records the offsite push from the sending side. The remote grant"
                " is write-only, so this host cannot list or read back what landed there; no"
                " byte-level round-trip proof exists."
            ),
        ),
        StatusDisclosure(
            id="replacement_host_recovery",
            label="Replacement-host recovery",
            state="limited",
            detail=(
                "Rebuilding onto a replacement host is mechanised and unit-tested, and has never"
                " been executed end to end. Treat it as an untested path."
            ),
        ),
    ]
    return StatusSnapshot(
        observed_at=observed_at,
        checks=checks,
        datasets=datasets,
        jobs=jobs,
        platform=platform,
        disclosures=disclosures,
    )


def write_snapshot(snapshot: StatusSnapshot, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = snapshot.model_dump_json(indent=2) + "\n"
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o640)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write glasswell's sanitized status snapshot.")
    parser.add_argument(
        "--dsn", default=os.environ.get(DSN_ENV) or os.environ.get(FALLBACK_DSN_ENV)
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(os.environ.get(SNAPSHOT_ENV, DEFAULT_SNAPSHOT)),
    )
    args = parser.parse_args(argv)
    if not args.dsn:
        parser.error(f"no database DSN: set {DSN_ENV} or {FALLBACK_DSN_ENV}")
    with psycopg.connect(args.dsn) as connection:
        snapshot = collect(connection)
        write_snapshot(snapshot, args.output)
    print(json.dumps({"observed_at": snapshot.observed_at.isoformat(), "state": "written"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
