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
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

import psycopg
from psycopg import IsolationLevel
from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row
from pydantic import BaseModel, ValidationError

from glasswell.status.models import (
    DATABASE_BYTES_REASON,
    INVENTORY_REASON,
    SCHEMA_VERSION_REASON,
    CheckState,
    CheckTier,
    DatasetInventory,
    InventoryMetric,
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
            " covering the generation's dump. Sending-side evidence only — the remote grant is"
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


def _storage_check(check_id: str, label: str, path: Path, observed_at: datetime) -> StatusCheck:
    try:
        stats = os.statvfs(path)
        available_ratio = stats.f_bavail / stats.f_blocks if stats.f_blocks else 0.0
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
    healthy = available_ratio >= 0.10
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


def _metric(metric_id: str, label: str, value: Any, unit: str) -> InventoryMetric:
    return InventoryMetric(
        metric_id=metric_id,
        label=label,
        value=int(value or 0),
        unit=unit,
        precision="exact",
        reason=INVENTORY_REASON,
    )


def _one(connection: psycopg.Connection, statement: str) -> dict[str, Any]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(statement)
        row = cursor.fetchone()
    return dict(row or {})


def _inventory(
    connection: psycopg.Connection, observed_at: datetime
) -> tuple[list[DatasetInventory], PlatformStatus]:
    platform = _one(
        connection,
        "select coalesce(max(version), 0) as schema_version,"
        " pg_database_size(current_database()) as database_bytes"
        " from public.schema_migrations",
    )
    wells = _one(
        connection,
        "select count(*) filter (where state_code = '33') as nd_rows,"
        " min(effective_from) filter (where state_code = '33') as nd_valid_from,"
        " max(effective_from) filter (where state_code = '33') as nd_valid_to,"
        " max(created_at) filter (where state_code = '33') as nd_latest_knowledge,"
        " count(*) filter (where state_code = '42') as tx_rows,"
        " min(effective_from) filter (where state_code = '42') as tx_valid_from,"
        " max(effective_from) filter (where state_code = '42') as tx_valid_to,"
        " max(created_at) filter (where state_code = '42') as tx_latest_knowledge,"
        " count(*) filter (where state_code = '30') as nm_rows,"
        " min(effective_from) filter (where state_code = '30') as nm_valid_from,"
        " max(effective_from) filter (where state_code = '30') as nm_valid_to,"
        " max(created_at) filter (where state_code = '30') as nm_latest_knowledge"
        " from canonical.wells_latest",
    )
    production = _one(
        connection,
        "select count(*) filter (where left(api10, 2) = '33') as nd_rows,"
        " count(distinct api10) filter (where left(api10, 2) = '33') as nd_wells,"
        " count(distinct production_month) filter (where left(api10, 2) = '33') as nd_months,"
        " min(production_month) filter (where left(api10, 2) = '33') as nd_valid_from,"
        " max(production_month) filter (where left(api10, 2) = '33') as nd_valid_to,"
        " max(created_at) filter (where left(api10, 2) = '33') as nd_latest_knowledge,"
        " count(*) filter (where left(api10, 2) = '30') as nm_rows,"
        " count(distinct api10) filter (where left(api10, 2) = '30') as nm_wells,"
        " count(distinct production_month) filter (where left(api10, 2) = '30') as nm_months,"
        " min(production_month) filter (where left(api10, 2) = '30') as nm_valid_from,"
        " max(production_month) filter (where left(api10, 2) = '30') as nm_valid_to,"
        " max(created_at) filter (where left(api10, 2) = '30') as nm_latest_knowledge"
        " from canonical.production_monthly",
    )
    completions = _one(
        connection,
        "select count(*) filter (where left(api10, 2) = '33') as nd_rows,"
        " count(distinct (source_id, completion_key))"
        "   filter (where left(api10, 2) = '33') as nd_completion_keys,"
        " min(coalesce(production_month, effective_from))"
        "   filter (where left(api10, 2) = '33') as nd_valid_from,"
        " max(coalesce(production_month, effective_from))"
        "   filter (where left(api10, 2) = '33') as nd_valid_to,"
        " max(created_at) filter (where left(api10, 2) = '33') as nd_latest_knowledge,"
        " count(*) filter (where left(api10, 2) = '30') as nm_rows,"
        " count(distinct (source_id, completion_key))"
        "   filter (where left(api10, 2) = '30') as nm_completion_keys,"
        " min(coalesce(production_month, effective_from))"
        "   filter (where left(api10, 2) = '30') as nm_valid_from,"
        " max(coalesce(production_month, effective_from))"
        "   filter (where left(api10, 2) = '30') as nm_valid_to,"
        " max(created_at) filter (where left(api10, 2) = '30') as nm_latest_knowledge"
        " from canonical.well_completions",
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
        " (select max(created_at) from lineage.derivations"
        "   where output_dataset = 'marts.nd_tiles' and status = 'ok') as nd_latest_knowledge,"
        " (select max(created_at) from lineage.derivations"
        "   where output_dataset = 'marts.tx_tiles' and status = 'ok') as tx_latest_knowledge,"
        " (select max(created_at) from lineage.derivations"
        "   where output_dataset = 'marts.nm_tiles' and status = 'ok') as nm_latest_knowledge",
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
    ) -> DatasetInventory:
        return DatasetInventory(
            dataset_id=dataset_id,
            label=label,
            scope=scope,
            grain=grain,
            state="available",
            counted_at=observed_at,
            latest_knowledge_at=latest_knowledge.isoformat() if latest_knowledge else None,
            metrics=metrics,
            valid_from=valid_from.isoformat() if valid_from else None,
            valid_to=valid_to.isoformat() if valid_to else None,
            detail=detail,
        )

    datasets = [
        dataset(
            "canonical.wells_latest/nd",
            "Current North Dakota wells",
            "North Dakota",
            "one latest effective row per API-10",
            [_metric("rows", "Current wells", wells["nd_rows"], "wells")],
            "Current effective-dated well entities, not accumulated source revisions.",
            wells["nd_valid_from"],
            wells["nd_valid_to"],
            wells["nd_latest_knowledge"],
        ),
        dataset(
            "canonical.wells_latest/tx",
            "Current Texas wells",
            "Texas",
            "one latest effective row per API-10",
            [_metric("rows", "Current wells", wells["tx_rows"], "wells")],
            "Current effective-dated well entities, not accumulated source revisions.",
            wells["tx_valid_from"],
            wells["tx_valid_to"],
            wells["tx_latest_knowledge"],
        ),
        dataset(
            "canonical.wells_latest/nm",
            "Current New Mexico wells",
            "New Mexico",
            "one latest effective row per API-10",
            [_metric("rows", "Current wells", wells["nm_rows"], "wells")],
            "Current effective-dated well entities, not accumulated source revisions.",
            wells["nm_valid_from"],
            wells["nm_valid_to"],
            wells["nm_latest_knowledge"],
        ),
        dataset(
            "canonical.production_monthly/nd",
            "North Dakota production observations",
            "North Dakota",
            "one append-only source revision per well, month and stream",
            [
                _metric("rows", "Observation rows", production["nd_rows"], "rows"),
                _metric("wells", "Distinct wells", production["nd_wells"], "wells"),
                _metric("months", "Distinct months", production["nd_months"], "months"),
            ],
            "Includes retained report vintages; it is not a count of physical wells.",
            production["nd_valid_from"],
            production["nd_valid_to"],
            production["nd_latest_knowledge"],
        ),
        dataset(
            "canonical.production_monthly/nm",
            "New Mexico production observations",
            "New Mexico",
            "one append-only source revision per well, completion pool, month and stream",
            [
                _metric("rows", "Observation rows", production["nm_rows"], "rows"),
                _metric("wells", "Distinct wells", production["nm_wells"], "wells"),
                _metric("months", "Distinct months", production["nm_months"], "months"),
            ],
            "Includes retained report vintages; it is not a count of physical wells.",
            production["nm_valid_from"],
            production["nm_valid_to"],
            production["nm_latest_knowledge"],
        ),
        dataset(
            "canonical.well_completions/nd",
            "North Dakota completion-pool observations",
            "North Dakota",
            "one source-vintage completion-month pool observation",
            [
                _metric("rows", "Observation rows", completions["nd_rows"], "rows"),
                _metric(
                    "completion_keys",
                    "Distinct source-scoped keys",
                    completions["nd_completion_keys"],
                    "keys",
                ),
            ],
            "Repeated source-month observations are not physical completion events.",
            completions["nd_valid_from"],
            completions["nd_valid_to"],
            completions["nd_latest_knowledge"],
        ),
        dataset(
            "canonical.well_completions/nm",
            "New Mexico completion observations",
            "New Mexico",
            "one source-vintage effective-dated completion dimension observation",
            [
                _metric("rows", "Observation rows", completions["nm_rows"], "rows"),
                _metric(
                    "completion_keys",
                    "Distinct source-scoped keys",
                    completions["nm_completion_keys"],
                    "keys",
                ),
            ],
            "Effective-dated completion dimensions; zero remains an exact unpromoted inventory.",
            completions["nm_valid_from"],
            completions["nm_valid_to"],
            completions["nm_latest_knowledge"],
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
        _storage_check("root_storage", "System storage", Path("/"), observed_at),
        _storage_check("data_storage", "Data storage", Path("/data"), observed_at),
    ]
    jobs = [
        _job(
            "nd_ingest",
            "North Dakota ingest",
            "glasswell-ingest.timer",
            "glasswell-ingest.service",
        ),
        _job(
            "nm_capture",
            "New Mexico capture",
            "glasswell-c115b.timer",
            "glasswell-c115b.service",
        ),
        _job(
            "status_snapshot",
            "Status snapshot",
            "glasswell-status.timer",
            "glasswell-status.service",
        ),
        _job(
            "cf_ranges",
            "Cloudflare range refresh",
            "glasswell-cf-ranges.timer",
            "glasswell-cf-ranges.service",
        ),
        _job(
            "lineage_retention",
            "Lineage retention",
            "glasswell-lineage-retention.timer",
            "glasswell-lineage-retention.service",
        ),
        _job("backup", "Nightly backup", "glasswell-backup.timer", "glasswell-backup.service"),
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
