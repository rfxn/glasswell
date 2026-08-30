"""The persisted status snapshot contract shared by the collector and API."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from glasswell.lineage.fetch_attempts import sanitized_evidence_text

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
SourceState = Literal["current", "stale", "pending"]
RecordedFetchOutcome = Literal["new", "unchanged", "failed"]
SourceOutcome = Literal["attempted", "new", "unchanged", "failed", "interrupted"]
FUTURE_SOURCE_TOLERANCE = timedelta(minutes=5)
OffsiteStreamState = Literal["transferred", "failed", "absent", "not_attempted"]
OffsiteFailureDetail = Literal["pgdump_push_failed", "raw_push_failed"]
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


class SourceFreshness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: SourceState
    last_outcome: SourceOutcome | None
    next_expected_poll: datetime | None
    reason: str = Field(min_length=1, max_length=512)


def source_freshness(
    *,
    observed_at: datetime,
    artifact_at: datetime | None,
    attempted_at: datetime | None,
    completed_at: datetime | None,
    recorded_outcome: RecordedFetchOutcome | None,
    expected_interval: timedelta | None,
    attempt_timeout: timedelta | None,
    cadence: str | None,
    failure_code: str | None = None,
    failure_detail: str | None = None,
    unresolved_failed_keys: int = 0,
    unresolved_open_keys: int = 0,
    oldest_open_attempt_at: datetime | None = None,
    blocking_failure_code: str | None = None,
    blocking_failure_detail: str | None = None,
) -> SourceFreshness:
    """Combine durable poll evidence with artifact age; never infer a successful check."""
    if observed_at.tzinfo is None:
        raise ValueError("source freshness observation requires a timezone")
    now = observed_at
    if attempted_at is None:
        if cadence is None:
            return SourceFreshness(
                state="pending",
                last_outcome=None,
                next_expected_poll=None,
                reason="No cadence policy or durable poll attempt is registered for this source.",
            )
        if artifact_at is None:
            return SourceFreshness(
                state="pending",
                last_outcome=None,
                next_expected_poll=None,
                reason="No durable poll attempt or registered artifact exists yet.",
            )
        if _future(artifact_at, now):
            return SourceFreshness(
                state="stale",
                last_outcome=None,
                next_expected_poll=None,
                reason="The latest artifact timestamp is implausibly in the future.",
            )
        if expected_interval is not None and now - artifact_at > expected_interval:
            return SourceFreshness(
                state="stale",
                last_outcome=None,
                next_expected_poll=None,
                reason=(
                    "The artifact is older than the expected poll interval and no durable"
                    " attempt can prove that the source was checked unchanged."
                ),
            )
        return SourceFreshness(
            state="pending",
            last_outcome=None,
            next_expected_poll=None,
            reason=(
                "The artifact is inside the expected interval, but no durable attempt exists;"
                " current is not inferred from artifact age alone."
            ),
        )

    next_expected = _next_expected(
        attempted_at=attempted_at,
        completed_at=completed_at,
        expected_interval=expected_interval,
    )
    if _future(attempted_at, now) or (completed_at is not None and _future(completed_at, now)):
        return SourceFreshness(
            state="stale",
            last_outcome=recorded_outcome or "attempted",
            next_expected_poll=None,
            reason="The latest poll evidence has an implausible future timestamp.",
        )
    if completed_at is not None and completed_at < attempted_at:
        return SourceFreshness(
            state="stale",
            last_outcome=recorded_outcome or "attempted",
            next_expected_poll=None,
            reason="The latest poll completion predates its attempt and is invalid evidence.",
        )
    if artifact_at is not None and _future(artifact_at, now):
        return SourceFreshness(
            state="stale",
            last_outcome=recorded_outcome or "attempted",
            next_expected_poll=next_expected,
            reason="The latest artifact timestamp is implausibly in the future.",
        )
    if unresolved_failed_keys:
        evidence = _failure_evidence(blocking_failure_code, blocking_failure_detail)
        if recorded_outcome == "failed":
            reason = (
                f"The latest durable source-key poll failed{evidence}; an older artifact does"
                " not override a failed check."
            )
        else:
            noun = "source key has" if unresolved_failed_keys == 1 else "source keys have"
            reason = (
                f"{unresolved_failed_keys} {noun} a failed latest poll{evidence}; a later"
                " success for another key does not clear that failure."
            )
        return SourceFreshness(
            state="stale",
            last_outcome=recorded_outcome or "attempted",
            next_expected_poll=next_expected,
            reason=reason,
        )
    if unresolved_open_keys and oldest_open_attempt_at is not None:
        if _future(oldest_open_attempt_at, now):
            return SourceFreshness(
                state="stale",
                last_outcome=recorded_outcome or "interrupted",
                next_expected_poll=next_expected,
                reason="An unresolved source-key attempt has an implausible future timestamp.",
            )
        if attempt_timeout is not None and now - oldest_open_attempt_at > attempt_timeout:
            noun = (
                "source-key attempt is" if unresolved_open_keys == 1 else "source-key attempts are"
            )
            return SourceFreshness(
                state="stale",
                last_outcome=recorded_outcome or "interrupted",
                next_expected_poll=next_expected,
                reason=(
                    f"{unresolved_open_keys} unresolved {noun} beyond the registered timeout;"
                    " later keys cannot turn interrupted work into success."
                ),
            )
        noun = "source-key poll is" if unresolved_open_keys == 1 else "source-key polls are"
        return SourceFreshness(
            state="pending",
            last_outcome=recorded_outcome or "attempted",
            next_expected_poll=next_expected,
            reason=f"{unresolved_open_keys} {noun} still inside the registered attempt timeout.",
        )
    if recorded_outcome is None:
        if attempt_timeout is not None and now - attempted_at > attempt_timeout:
            return SourceFreshness(
                state="stale",
                last_outcome="interrupted",
                next_expected_poll=next_expected,
                reason=(
                    "The latest durable attempt has no outcome beyond its registered timeout;"
                    " it is treated as interrupted, not successful."
                ),
            )
        return SourceFreshness(
            state="pending",
            last_outcome="attempted",
            next_expected_poll=next_expected,
            reason="A durable source poll is still inside its registered attempt timeout.",
        )
    if recorded_outcome == "failed":
        evidence = _failure_evidence(failure_code, failure_detail)
        return SourceFreshness(
            state="stale",
            last_outcome="failed",
            next_expected_poll=next_expected,
            reason=(
                f"The latest durable poll failed{evidence}; an older artifact does not override"
                " a failed check."
            ),
        )
    if artifact_at is None:
        return SourceFreshness(
            state="stale",
            last_outcome=recorded_outcome,
            next_expected_poll=next_expected,
            reason="The successful poll references no registered artifact; freshness is refused.",
        )
    if next_expected is not None and now > next_expected:
        return SourceFreshness(
            state="stale",
            last_outcome=recorded_outcome,
            next_expected_poll=next_expected,
            reason="The last successful poll is beyond the source-specific expected interval.",
        )
    if recorded_outcome == "unchanged":
        reason = (
            "The latest poll completed unchanged inside cadence; the older artifact remains"
            " current because its bytes were rechecked successfully."
        )
    else:
        reason = "The latest poll committed a new artifact inside the expected cadence."
    return SourceFreshness(
        state="current",
        last_outcome=recorded_outcome,
        next_expected_poll=next_expected,
        reason=reason,
    )


def _future(value: datetime, observed_at: datetime) -> bool:
    return value > observed_at + FUTURE_SOURCE_TOLERANCE


def _next_expected(
    *,
    attempted_at: datetime,
    completed_at: datetime | None,
    expected_interval: timedelta | None,
) -> datetime | None:
    if expected_interval is None:
        return None
    return (completed_at or attempted_at) + expected_interval


def _failure_evidence(code: str | None, detail: str | None) -> str:
    parts = [value for value in (code, detail) if value]
    if not parts:
        return ""
    safe = sanitized_evidence_text(": ".join(parts))
    return f" ({safe})"


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


class OffsiteDumpIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^glasswell-\d{8}T\d{6}Z\.dump$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bytes: int = Field(gt=0)


class OffsiteStream(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Literal["pgdump", "raw"]
    state: OffsiteStreamState
    exit_status: int = Field(ge=0)
    files_transferred: int | None = Field(default=None, ge=0)
    bytes_transferred: int | None = Field(default=None, ge=0)
    bytes_on_sender: int | None = Field(default=None, ge=0)


class OffsiteCopyReceipt(BaseModel):
    """What the sender did. The remote grant is write-only, so nothing here saw the far side."""

    model_config = ConfigDict(extra="forbid")

    receipt_version: Literal[1] = 1
    result: Literal["passed", "failed"]
    failure_detail: OffsiteFailureDetail | None
    generation: str = Field(pattern=r"^\d{8}T\d{6}Z$")
    dump: OffsiteDumpIdentity
    destination: str = Field(min_length=1, max_length=256)
    started_at: datetime
    completed_at: datetime
    duration_seconds: int = Field(ge=0)
    streams: list[OffsiteStream]
    dump_bytes_covered: bool
    # Pinned to one value on purpose: a receipt cannot claim a stronger proof than the one this
    # host can make, because `rrsync -wo` gives it no way to read the far side back.
    verification: Literal["send_side_only"]

    @model_validator(mode="after")
    def validate_receipt(self) -> OffsiteCopyReceipt:
        if any(value.tzinfo is None for value in (self.started_at, self.completed_at)):
            raise ValueError("offsite receipt timestamps require timezone offsets")
        if self.completed_at < self.started_at:
            raise ValueError("offsite receipt completes before it starts")
        streams = {item.id: item for item in self.streams}
        if set(streams) != {"pgdump", "raw"} or len(streams) != len(self.streams):
            raise ValueError("offsite receipt must record both streams exactly once")
        if self.result == "failed":
            if self.failure_detail is None:
                raise ValueError("failed offsite receipt requires failure_detail")
            return self
        if self.failure_detail is not None:
            raise ValueError("passed offsite receipt cannot carry failure_detail")
        if any(item.state == "failed" for item in streams.values()):
            raise ValueError("passed offsite receipt cannot carry a failed stream")
        if streams["pgdump"].state != "transferred":
            raise ValueError("passed offsite receipt requires a transferred pgdump stream")
        # `dump_bytes_covered` is deliberately not a validity condition. It is a measurement the
        # consumers judge: a receipt whose stats did not parse must still be readable, or an
        # rsync output change would take the nightly backup down instead of degrading Status.
        return self


class RecoveryRawZone(BaseModel):
    model_config = ConfigDict(extra="forbid")

    files: int | None = Field(default=None, ge=0)
    bytes: int | None = Field(default=None, ge=0)


class RecoveryDrillResult(BaseModel):
    """A replacement-host rebuild from the off-box copy. Never yet produced by a real run."""

    model_config = ConfigDict(extra="forbid")

    receipt_version: Literal[1] = 1
    result: Literal["passed", "failed"]
    failure_detail: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,63}$")
    # Same plain-identifier allowlist the drill enforces, so a receipt cannot record a target
    # the script would have refused to build a statement from.
    target_database: str = Field(pattern=r"^[a-z][a-z0-9_]{0,62}$")
    dump: OffsiteDumpIdentity | None
    started_at: datetime
    completed_at: datetime
    duration_seconds: int = Field(ge=0)
    source_schema_version: int | None = Field(default=None, ge=0)
    restored_schema_version: int | None = Field(default=None, ge=0)
    schema_match: bool | None
    critical_row_counts: list[RestoreRowComparison]
    representative_reads: list[RestoreReadAssertion]
    globals_restored: bool
    raw_zone: RecoveryRawZone

    @model_validator(mode="after")
    def validate_receipt(self) -> RecoveryDrillResult:
        if any(value.tzinfo is None for value in (self.started_at, self.completed_at)):
            raise ValueError("recovery result timestamps require timezone offsets")
        if self.completed_at < self.started_at:
            raise ValueError("recovery result completes before it starts")
        # A recovery that wrote over the live database is a catastrophe, not a proof.
        if self.target_database == "glasswell":
            raise ValueError("recovery result cannot name the production database")
        if self.result == "failed":
            if self.failure_detail is None:
                raise ValueError("failed recovery result requires failure_detail")
            return self
        if self.failure_detail is not None:
            raise ValueError("passed recovery result cannot carry failure_detail")
        if self.dump is None:
            raise ValueError("passed recovery result requires dump identity")
        if not self.globals_restored:
            raise ValueError("passed recovery result requires restored cluster globals")
        if self.schema_match is not True or self.source_schema_version != (
            self.restored_schema_version
        ):
            raise ValueError("passed recovery result requires a matching schema head")
        if any(not item.match for item in self.critical_row_counts):
            raise ValueError("passed recovery result has a failed critical row comparison")
        if any(not item.passed for item in self.representative_reads):
            raise ValueError("passed recovery result has a failed representative read")
        if not self.raw_zone.files:
            raise ValueError("passed recovery result requires a restored raw zone")
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
