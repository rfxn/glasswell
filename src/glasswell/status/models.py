"""The persisted status snapshot contract shared by the collector and API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
RestoreFailureDetail = Literal[
    "drill_interrupted",
    "unsafe_dump_directory",
    "unsafe_dump_candidate",
    "dump_stat_failed",
    "no_dump_found",
    "empty_dump",
    "dump_hash_failed",
    "dump_unreadable",
    "dump_archive_invalid",
    "no_dump_manifest",
    "unsafe_dump_manifest",
    "invalid_dump_manifest",
    "scratch_precleanup_failed",
    "scratch_create_failed",
    "restore_failed",
    "postgis_assertion_failed",
    "extension_assertion_failed",
    "owner_assertion_failed",
    "schema_head_query_failed",
    "schema_head_mismatch",
    "critical_count_query_failed",
    "critical_dataset_empty",
    "critical_count_mismatch",
    "representative_read_failed",
    "scratch_cleanup_failed",
]


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


class RestoreDumpIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^glasswell-\d{8}T\d{6}Z\.dump$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bytes: int = Field(gt=0)
    created_at: datetime


class RestoreRowComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset: Literal[
        "lineage.manifests",
        "canonical.wells_latest",
        "canonical.production_monthly",
        "marts.nd_wells_tile",
    ]
    source_rows: int = Field(ge=0)
    restored_rows: int = Field(ge=0)
    match: bool


class RestoreReadAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Literal[
        "postgis_available",
        "postgis_extension",
        "scratch_owner",
        "canonical_well",
        "production_observation",
        "lineage_manifest",
    ]
    passed: bool


class RestoreDrillResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result_version: Literal[1] = 1
    result: Literal["passed", "failed"]
    failure_detail: RestoreFailureDetail | None
    dump: RestoreDumpIdentity | None
    started_at: datetime
    completed_at: datetime
    duration_seconds: int = Field(ge=0)
    source_schema_version: int | None = Field(default=None, ge=0)
    restored_schema_version: int | None = Field(default=None, ge=0)
    schema_match: bool | None
    critical_row_counts: list[RestoreRowComparison]
    representative_reads: list[RestoreReadAssertion]
    scratch_removed: bool

    @model_validator(mode="after")
    def validate_proof(self) -> RestoreDrillResult:
        timestamps = (self.started_at, self.completed_at)
        if any(value.tzinfo is None for value in timestamps):
            raise ValueError("restore result timestamps require timezone offsets")
        if self.completed_at < self.started_at:
            raise ValueError("restore result completes before it starts")
        elapsed = int((self.completed_at - self.started_at).total_seconds())
        if abs(elapsed - self.duration_seconds) > 2:
            raise ValueError("restore result duration disagrees with its timestamps")
        if self.result == "failed":
            if self.failure_detail is None:
                raise ValueError("failed restore result requires failure_detail")
            return self
        if self.failure_detail is not None:
            raise ValueError("passed restore result cannot carry failure_detail")
        if self.dump is None:
            raise ValueError("passed restore result requires dump identity")
        if not self.scratch_removed:
            raise ValueError("passed restore result requires verified scratch cleanup")
        if (
            self.source_schema_version is None
            or self.restored_schema_version is None
            or self.schema_match is not True
            or self.source_schema_version != self.restored_schema_version
        ):
            raise ValueError("passed restore result requires a matching schema head")
        expected_datasets = {
            "lineage.manifests",
            "canonical.wells_latest",
            "canonical.production_monthly",
            "marts.nd_wells_tile",
        }
        comparisons = {item.dataset: item for item in self.critical_row_counts}
        if set(comparisons) != expected_datasets or len(comparisons) != len(
            self.critical_row_counts
        ):
            raise ValueError("passed restore result has incomplete critical row comparisons")
        if any(
            not item.match
            or item.source_rows <= 0
            or item.source_rows != item.restored_rows
            for item in comparisons.values()
        ):
            raise ValueError("passed restore result has a failed critical row comparison")
        expected_reads = {
            "postgis_available",
            "postgis_extension",
            "scratch_owner",
            "canonical_well",
            "production_observation",
            "lineage_manifest",
        }
        reads = {item.id: item for item in self.representative_reads}
        if set(reads) != expected_reads or len(reads) != len(self.representative_reads):
            raise ValueError("passed restore result has incomplete representative reads")
        if any(not item.passed for item in reads.values()):
            raise ValueError("passed restore result has a failed representative read")
        return self


class StatusSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_version: Literal[1] = 1
    observed_at: datetime
    checks: list[StatusCheck]
    datasets: list[DatasetInventory]
    jobs: list[JobStatus]
    platform: PlatformStatus
    disclosures: list[StatusDisclosure]
