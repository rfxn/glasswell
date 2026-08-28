"""Typed records for the spine tables (SB-07 §1.4, §2.2, §3.2, §5.1, §6.2, §8.1)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Operation = Literal[
    "raw.fetch",
    "stage.parse",
    "canonical.promote",
    "features.build",
    "model.train",
    "model.calibrate",
    "forecast.batch",
    "forecast.scenario",
    "econ.value",
    "econ.sensitivity",
    "alloc.apply",
    "typecurve.build",
    "analog.index",
    "analog.query",
    "mart.refresh",
    "tiles.build",
    "ledger.grade",
    "inventory.run",
    "api.respond",
]
OutputStore = Literal["parquet", "postgres", "postgis", "duckdb_view", "file", "response"]
InputKind = Literal["derivation", "manifest", "rule", "model", "external"]
InputRole = Literal["primary", "crosswalk", "validator", "calibration", "grid"]
DeterminismClass = Literal["D1", "D2", "D3"]
TtlClass = Literal["permanent", "ephemeral"]
DerivationStatus = Literal["ok", "failed"]
AcquisitionMethod = Literal[
    "https_get", "ftp_anon", "mft_guid_resolve", "click_wall_accept", "arcgis_rest_paginate"
]
RuleStage = Literal["parse", "validate", "conform", "join"]
QuarantineState = Literal["open", "released", "accepted_loss", "superseded"]

PROMOTION_OPERATIONS: frozenset[str] = frozenset({"canonical.promote", "alloc.apply"})


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class OutputSpec(Frozen):
    store: OutputStore
    dataset: str
    partition: Mapping[str, str] = Field(default_factory=dict)
    locator: str = ""
    schema_version: str = ""


class InputRef(Frozen):
    kind: InputKind
    ref_id: str
    selector: str | None = None
    as_of_vintage: date | None = None
    role: InputRole = "primary"
    ord: int = 0


class RuleRef(Frozen):
    rule_id: str
    applied_rows: int | None = None


class DeriveEnvironment(Frozen):
    """The pinned build identity every derivation is stamped with (SB-07 §4.1)."""

    code_version: str
    code_dirty: bool
    env_id: str
    recipe_id: str | None = None


class DerivationRecord(Frozen):
    derivation_id: str
    operation: Operation
    output_store: OutputStore
    output_dataset: str
    output_partition: Mapping[str, str]
    output_locator: str
    output_sha256: str | None
    output_rows: int | None
    output_schema_version: str
    params: Mapping[str, Any]
    params_hash: str
    code_version: str
    code_dirty: bool
    env_id: str
    model_id: str | None
    recipe_id: str | None
    created_vintage: date | None
    created_at: datetime
    duration_ms: int
    correlation_id: str
    status: DerivationStatus
    determinism_class: DeterminismClass
    ttl_class: TtlClass
    inputs: Sequence[InputRef] = ()
    rules: Sequence[RuleRef] = ()


class ManifestRecord(Frozen):
    manifest_id: str
    sha256: str
    bytes: int
    source_id: str
    source_key: str
    acquisition_url: str
    acquisition_method: AcquisitionMethod
    acquisition_params: Mapping[str, Any] = Field(default_factory=dict)
    fetched_at: datetime
    fetch_vintage: date
    upstream_mtime: datetime | None = None
    upstream_etag: str | None = None
    media_type: str | None = None
    decompressed_inventory: Sequence[Mapping[str, Any]] = ()
    supersedes_manifest_id: str | None = None
    storage_uri: str = ""
    license_note: str | None = None
    redistributable: bool = False
    fetch_derivation_id: str | None = None
    staging_load_ref: str | None = None
    integrity_verified_at: datetime | None = None


class AuditEvent(Frozen):
    event_id: str
    occurred_at: datetime
    actor: str
    event_type: str
    subject_type: str
    subject_id: str
    correlation_id: str | None = None
    payload: Mapping[str, Any] = Field(default_factory=dict)


class ConformanceRule(BaseModel):
    """A `conformance_rules` row.

    `lookup` is not a column: it holds the registry table rows the loader materialized
    for lookup-backed kinds (SB-07 §6.1 `mapping_table` / `alias_table`).
    """

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    rule_family: str
    supersedes_rule_id: str | None = None
    source_id: str
    stage: RuleStage
    applies_to_fields: Sequence[str] = ()
    rule_kind: str
    spec: Mapping[str, Any] = Field(default_factory=dict)
    rule: str
    rationale: str
    evidence_url: str | None = None
    evidence_sha256: str | None = None
    published_vintage: date | None = None
    effective_from: date
    effective_to: date | None = None
    code_ref: str | None = None
    code_ref_sha256: str | None = None
    created_by_event_id: str | None = None
    lookup: Sequence[Mapping[str, Any]] = ()


class VintageRecord(Frozen):
    vintage_id: str
    source_id: str
    vintage_date: date
    manifest_ids: Sequence[str]
    opened_at: datetime
    promotion_derivation_id: str | None = None
    rows_examined: int = 0
    rows_appended: int = 0
    months_touched: Sequence[str] = ()
    restatement_summary: Mapping[str, int] = Field(default_factory=dict)
