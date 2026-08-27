"""The persisted status snapshot contract shared by the collector and API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

INVENTORY_REASON = (
    "Operational inventory from a timed status snapshot; its grain, precision and observation"
    " time are stated alongside."
)
SCHEMA_VERSION_REASON = "Database migration identity, not a measured petroleum quantity."
DATABASE_BYTES_REASON = "Physical PostgreSQL storage inventory, not a petroleum figure."

CheckState = Literal["ok", "degraded", "pending", "unavailable", "not_instrumented"]
DatasetState = Literal["available", "unavailable"]
Precision = Literal["exact", "estimated"]
DisclosureState = Literal["limited", "not_instrumented"]


class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    state: CheckState
    observed_at: datetime | None = None
    detail: str


class InventoryMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_id: str
    label: str
    value: int = Field(
        ge=0,
        json_schema_extra={"x-glasswell-not-a-figure": INVENTORY_REASON},
    )
    unit: str
    precision: Precision
    reason: str = INVENTORY_REASON


class DatasetInventory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    label: str
    scope: str
    grain: str
    state: DatasetState
    counted_at: datetime | None = None
    latest_knowledge_at: str | None = None
    metrics: list[InventoryMetric]
    valid_from: str | None = None
    valid_to: str | None = None
    detail: str


class JobStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    state: CheckState
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    detail: str


class PlatformStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code_version: str | None = None
    schema_version_reason: str = SCHEMA_VERSION_REASON
    schema_version: int | None = Field(
        default=None,
        ge=0,
        json_schema_extra={"x-glasswell-not-a-figure": SCHEMA_VERSION_REASON},
    )
    database_bytes: int | None = Field(
        default=None,
        ge=0,
        json_schema_extra={"x-glasswell-not-a-figure": DATABASE_BYTES_REASON},
    )
    database_bytes_reason: str = DATABASE_BYTES_REASON


class StatusDisclosure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    state: DisclosureState
    detail: str


class StatusSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_version: Literal[1] = 1
    observed_at: datetime
    checks: list[StatusCheck]
    datasets: list[DatasetInventory]
    jobs: list[JobStatus]
    platform: PlatformStatus
    disclosures: list[StatusDisclosure]
