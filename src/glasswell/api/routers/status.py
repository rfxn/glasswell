"""Operational status: a live API/DB signal plus a sanitized timed host snapshot."""

from __future__ import annotations

import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.responses import JSONResponse

from glasswell.api.deps import Connection, today
from glasswell.api.errors import problem_responses
from glasswell.api.examples import request_example
from glasswell.api.responses import EnvelopeModel, enveloped
from glasswell.api.routers.health import SourceHealth, source_health_data
from glasswell.status.collector import DEFAULT_SNAPSHOT, SNAPSHOT_ENV
from glasswell.status.models import (
    DATABASE_BYTES_REASON,
    CheckState,
    DatasetInventory,
    JobStatus,
    PlatformStatus,
    StatusCheck,
    StatusDisclosure,
    StatusSnapshot,
)

router = APIRouter(tags=["service"])

MAX_SNAPSHOT_BYTES = 1_048_576
STALE_AFTER = timedelta(minutes=30)
FUTURE_TOLERANCE = timedelta(minutes=5)
SnapshotState = Literal["current", "stale", "unavailable", "invalid"]
OverallState = Literal["ok", "degraded", "partial"]


class Status(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observed_at: datetime | None = Field(
        description="When the scheduled snapshot observed its host and dataset inventory."
    )
    snapshot_state: SnapshotState = Field(
        description="Whether the sanitized timed snapshot is current and valid."
    )
    state: OverallState = Field(
        description="degraded for a known failure, partial for an observability or coverage gap."
    )
    checks: list[StatusCheck] = Field(description="Application-plane infrastructure checks.")
    datasets: list[DatasetInventory] = Field(
        description="Timed dataset inventory whose grain and precision are explicit."
    )
    jobs: list[JobStatus] = Field(description="Scheduled ingest and protection jobs.")
    sources: list[SourceHealth] = Field(
        description="Registered-artifact age for every source; not last-checked time."
    )
    platform: PlatformStatus = Field(description="Build, schema and database storage identity.")
    disclosures: list[StatusDisclosure] = Field(
        description="Known limits that prevent a broader health claim."
    )


def _empty_platform() -> PlatformStatus:
    return PlatformStatus(database_bytes_reason=DATABASE_BYTES_REASON)


def load_snapshot(
    *, path: Path | None = None, now: datetime | None = None
) -> tuple[StatusSnapshot | None, SnapshotState, str]:
    target = path or Path(os.environ.get(SNAPSHOT_ENV, DEFAULT_SNAPSHOT))
    observed_now = (now or datetime.now(UTC)).astimezone(UTC)
    try:
        metadata = target.lstat()
        if not stat.S_ISREG(metadata.st_mode) or target.is_symlink():
            return None, "invalid", "Snapshot path is not a regular file."
        if metadata.st_size > MAX_SNAPSHOT_BYTES:
            return None, "invalid", "Snapshot exceeds the accepted size."
        snapshot = StatusSnapshot.model_validate_json(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "unavailable", "No scheduled snapshot has been published yet."
    except (OSError, UnicodeError, ValidationError):
        return None, "invalid", "The scheduled snapshot could not be validated."

    observed_at = snapshot.observed_at
    if observed_at.tzinfo is None:
        return None, "invalid", "Snapshot observation time has no timezone."
    age = observed_now - observed_at.astimezone(UTC)
    if age < -FUTURE_TOLERANCE:
        return None, "invalid", "Snapshot observation time is implausibly in the future."
    if age > STALE_AFTER:
        return snapshot, "stale", "The scheduled snapshot is older than its freshness window."
    return snapshot, "current", "The scheduled snapshot is inside its freshness window."


def _unavailable(check: StatusCheck, reason: str) -> StatusCheck:
    return check.model_copy(
        update={"state": "unavailable", "detail": f"{reason} Last detail: {check.detail}"}
    )


def _job_unavailable(job: JobStatus, reason: str) -> JobStatus:
    return job.model_copy(
        update={"state": "unavailable", "detail": f"{reason} Last detail: {job.detail}"}
    )


def _overall_state(
    snapshot_state: SnapshotState,
    checks: list[StatusCheck],
    jobs: list[JobStatus],
    sources: list[dict],
    disclosures: list[StatusDisclosure],
) -> OverallState:
    states: list[CheckState] = [item.state for item in checks] + [item.state for item in jobs]
    if (
        snapshot_state in {"stale", "invalid"}
        or "degraded" in states
        or any(source["state"] == "stale" for source in sources)
    ):
        return "degraded"
    if (
        snapshot_state != "current"
        or any(state in {"pending", "unavailable", "not_instrumented"} for state in states)
        or any(source["state"] == "pending" for source in sources)
        or disclosures
    ):
        return "partial"
    return "ok"


@router.get(
    "/status",
    operation_id="get_status",
    summary="Infrastructure, dataset inventory and source freshness",
    description=(
        "A live API/PostgreSQL signal joined to a sanitized scheduled snapshot of the tile"
        " service, HTTPS edge, storage, jobs and exact dataset inventory. Stale snapshots never"
        " preserve a green infrastructure state. Source freshness is explicitly the age of the"
        " newest registered artifact: unchanged and failed fetch attempts do not have a durable"
        " independent ledger yet and are disclosed rather than inferred. This is current"
        " operational telemetry, not a historical `as_of` surface."
    ),
    response_model=EnvelopeModel[Status],
    openapi_extra=request_example(),
    responses=problem_responses("service_degraded"),
)
def get_status(request: Request, connection: Connection) -> JSONResponse:
    now = datetime.now(UTC)
    snapshot, snapshot_state, snapshot_detail = load_snapshot(now=now)
    sources, freshness = source_health_data(connection, as_of_date=today())
    checks = [
        StatusCheck(
            id="api",
            label="API request",
            state="ok",
            observed_at=now,
            detail="This authenticated status request reached the application.",
        ),
        StatusCheck(
            id="postgres",
            label="PostgreSQL query",
            state="ok",
            observed_at=now,
            detail="The source-freshness query completed on this request.",
        ),
        StatusCheck(
            id="status_snapshot",
            label="Status telemetry",
            state=(
                "ok"
                if snapshot_state == "current"
                else "degraded"
                if snapshot_state in {"stale", "invalid"}
                else "unavailable"
            ),
            observed_at=snapshot.observed_at if snapshot else None,
            detail=snapshot_detail,
        ),
    ]
    datasets: list[DatasetInventory] = []
    jobs: list[JobStatus] = []
    platform = _empty_platform()
    disclosures: list[StatusDisclosure] = []
    if snapshot is not None:
        snapshot_checks = snapshot.checks
        snapshot_jobs = snapshot.jobs
        if snapshot_state != "current":
            snapshot_checks = [_unavailable(item, snapshot_detail) for item in snapshot_checks]
            snapshot_jobs = [_job_unavailable(item, snapshot_detail) for item in snapshot_jobs]
        checks.extend(snapshot_checks)
        datasets = snapshot.datasets
        jobs = snapshot_jobs
        platform = snapshot.platform
        disclosures = snapshot.disclosures
    else:
        disclosures = [
            StatusDisclosure(
                id="host_snapshot",
                label="Host and dataset telemetry",
                state="not_instrumented",
                detail=snapshot_detail,
            )
        ]

    state = _overall_state(snapshot_state, checks, jobs, sources, disclosures)
    data = Status(
        observed_at=snapshot.observed_at if snapshot else None,
        snapshot_state=snapshot_state,
        state=state,
        checks=checks,
        datasets=datasets,
        jobs=jobs,
        sources=[SourceHealth.model_validate(source) for source in sources],
        platform=platform,
        disclosures=disclosures,
    )
    return enveloped(
        request,
        data.model_dump(mode="json"),
        source_freshness=freshness,
    )
