"""Collect exact dataset inventory and sanitized host observations into one atomic snapshot."""

from __future__ import annotations

import argparse
import json
import os
import socket
import ssl
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

import psycopg
from psycopg import IsolationLevel
from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row

from glasswell.status.models import (
    DATABASE_BYTES_REASON,
    INVENTORY_REASON,
    SCHEMA_VERSION_REASON,
    DatasetInventory,
    InventoryMetric,
    JobStatus,
    PlatformStatus,
    StatusCheck,
    StatusDisclosure,
    StatusSnapshot,
)

SNAPSHOT_ENV = "GLASSWELL_STATUS_SNAPSHOT"
DEFAULT_SNAPSHOT = Path("/var/lib/glasswell/status.json")
DSN_ENV = "GLASSWELL_DSN"
FALLBACK_DSN_ENV = "DATABASE_URL"
CODE_VERSION_ENV = "GLASSWELL_CODE_VERSION"
EDGE_HOST_ENV = "GLASSWELL_STATUS_EDGE_HOST"
DEFAULT_EDGE_HOST = "glasswell.lab.rpx.sh"
MARTIN_HEALTH = "http://127.0.0.1:3000/health"
QUERY_TIMEOUT_MS = 120_000

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
    check_id: str, label: str, unit: str, observed_at: datetime, runner: Runner = _run
) -> StatusCheck:
    properties = _systemd_properties(unit, runner)
    if not properties:
        return StatusCheck(
            id=check_id,
            label=label,
            state="unavailable",
            observed_at=observed_at,
            detail="Service-manager evidence is unavailable.",
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
    )


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
        "select count(*) filter (where state_code = '38') as nd_rows,"
        " min(effective_from) filter (where state_code = '38') as nd_valid_from,"
        " max(effective_from) filter (where state_code = '38') as nd_valid_to,"
        " max(created_at) filter (where state_code = '38') as nd_latest_knowledge,"
        " count(*) filter (where state_code = '42') as tx_rows,"
        " min(effective_from) filter (where state_code = '42') as tx_valid_from,"
        " max(effective_from) filter (where state_code = '42') as tx_valid_to,"
        " max(created_at) filter (where state_code = '42') as tx_latest_knowledge"
        " from canonical.wells_latest",
    )
    production = _one(
        connection,
        "select count(*) as rows, count(distinct api10) as wells,"
        " min(production_month) as valid_from, max(production_month) as valid_to,"
        " max(created_at) as latest_knowledge"
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
        " (select max(created_at) from lineage.derivations"
        "   where output_dataset = 'marts.nd_tiles' and status = 'ok') as nd_latest_knowledge,"
        " (select max(created_at) from lineage.derivations"
        "   where output_dataset = 'marts.tx_tiles' and status = 'ok') as tx_latest_knowledge",
    )
    quality = _one(
        connection,
        "select count(*) filter (where state = 'open') as open_rows,"
        " max(last_seen_at) filter (where state = 'open') as latest_knowledge"
        " from lineage.quarantine_rows",
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
            "canonical.production_monthly",
            "Production observations",
            "North Dakota",
            "one append-only source revision per well, month and stream",
            [
                _metric("rows", "Observation rows", production["rows"], "rows"),
                _metric("wells", "Distinct wells", production["wells"], "wells"),
            ],
            "Includes retained report vintages; it is not a count of physical wells.",
            production["valid_from"],
            production["valid_to"],
            production["latest_knowledge"],
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
            "lineage.quarantine_rows",
            "Open quarantine",
            "All ingested sources",
            "one rejected row fingerprint per rule",
            [_metric("open_rows", "Open rows", quality["open_rows"], "rows")],
            "A count only; no rejection rate is claimed without a matching input denominator.",
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
            "database_service", "PostgreSQL service", "postgresql.service", observed_at
        ),
        _martin_check(observed_at),
        _edge_check(observed_at, os.environ.get(EDGE_HOST_ENV, DEFAULT_EDGE_HOST)),
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
        _job("backup", "Nightly backup", "glasswell-backup.timer", "glasswell-backup.service"),
    ]
    disclosures = [
        StatusDisclosure(
            id="source_check_attempts",
            label="Source check attempts",
            state="limited",
            detail=(
                "Unchanged and failed fetch attempts are not persisted independently yet; source"
                " freshness below is registered-artifact age, not last-checked time."
            ),
        ),
        StatusDisclosure(
            id="source_cadence",
            label="Source-specific cadence",
            state="limited",
            detail=(
                "The registry carries no source cadence yet; current/stale uses the existing"
                " conservative shared artifact-age policy."
            ),
        ),
        StatusDisclosure(
            id="restore_drill",
            label="Restore drill execution",
            state="not_instrumented",
            detail="A restore script exists, but no durable execution result is recorded.",
        ),
        StatusDisclosure(
            id="remote_backup_copy",
            label="Remote backup copy",
            state="not_instrumented",
            detail="The backup job does not persist remote-copy success as separate telemetry.",
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
