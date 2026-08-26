"""Pinned, leakage-resistant type-curve controls for the P3 benchmark."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal, cast
from uuid import uuid4

import polars as pl
import psycopg

from glasswell.ingest.base import resolve_environment
from glasswell.lineage.capture import derive, lineage_session
from glasswell.lineage.clock import Clock
from glasswell.lineage.ids import derivation_id
from glasswell.lineage.models import DeriveEnvironment, InputRef, OutputSpec
from glasswell.lineage.recipes import build_recipe
from glasswell.lineage.serialization import canonical_json, hash_payload, sha256_hex
from glasswell.lineage.store import PostgresRecorder
from glasswell.modeling.model_dataset import (
    MODEL_DATASET_VERSION,
    STREAM_UNITS,
    STREAMS,
    resolve_model_root,
)
from glasswell.modeling.model_dataset import (
    split_set_id as model_split_set_id,
)
from glasswell.modeling.split import SplitObject
from glasswell.staging.duck import PARTITION_FILENAME, file_sha256, write_partition

CONTROL_VERSION = "tcv1.0"
CONTROL_DATASET = "modeling.typecurve_control"
CONTROL_SCHEMA_VERSION = "1"
TC_MIN_N = 20
VINTAGE_WINDOW_MONTHS = 36
TC_RUNG1_SHARE_MIN = Decimal("0.60")
TC_UNAVAILABLE_SHARE_MAX = Decimal("0.05")
NORMALIZATIONS = ("typecurve_per_kft", "typecurve_absolute")
QUANTILE_CONVENTION = "statistical_ascending"
BATCH_ROWS = 50_000

Normalization = Literal["typecurve_per_kft", "typecurve_absolute"]
FallbackLevel = Literal[
    "formation_area_length", "formation_area", "formation_basin", "control_unavailable"
]
MonthStatus = Literal["ok", "insufficient", "control_unavailable"]
VintageBasis = Literal["strict_manifest_knowledge", "source_reconstructed_not_glasswell_history"]


class TypeCurveError(RuntimeError):
    """A type-curve control cannot satisfy its pinned contract."""


class ImmutableTypeCurveArtifactError(TypeCurveError):
    """A replay attempted to change a registered control artifact."""


@dataclass(frozen=True, slots=True)
class SubjectContext:
    api10: str
    basin: str | None
    formation_group: str | None
    formation_group_source_available_on: date | None
    area: str | None
    lateral_length_ft: float | None
    lateral_length_bucket: str | None
    first_production_month: date | None


@dataclass(frozen=True, slots=True)
class CurveObservation:
    volume: float | None
    source_available_on: date | None
    source_reconstructed_available_on: date | None


@dataclass(frozen=True, slots=True)
class Quantiles:
    p10: float
    p50: float
    p90: float


@dataclass(frozen=True, slots=True)
class AggregatedMonth:
    month_index: int
    peer_count: int
    cumulative_peer_count: int
    absolute_monthly: Quantiles | None
    absolute_cumulative: Quantiles | None
    per_kft_monthly: Quantiles | None
    per_kft_cumulative: Quantiles | None


@dataclass(frozen=True, slots=True)
class FallbackChoice:
    level: FallbackLevel
    key: tuple[str, ...] | None
    peer_api10s: tuple[str, ...]

    @property
    def peer_set_id(self) -> str | None:
        if not self.peer_api10s:
            return None
        return "peers_" + hash_payload(self.peer_api10s)[:20]


@dataclass(frozen=True, slots=True)
class PersistedSplitInput:
    split: SplitObject
    uri: str
    sha256: str


@dataclass(frozen=True, slots=True)
class TypeCurveBuild:
    type_curve_id: str
    derivation_id: str
    recipe_id: str
    artifact_uri: str
    artifact_sha256: str
    coverage_uri: str
    coverage_sha256: str
    control_version: str
    dataset_version: str
    feature_version: str
    split_set_id: str
    eval_vintage: date
    rows: int
    splits: tuple[PersistedSplitInput, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "type_curve_id": self.type_curve_id,
            "derivation_id": self.derivation_id,
            "recipe_id": self.recipe_id,
            "artifact_uri": self.artifact_uri,
            "artifact_sha256": self.artifact_sha256,
            "coverage_uri": self.coverage_uri,
            "coverage_sha256": self.coverage_sha256,
            "control_version": self.control_version,
            "dataset_version": self.dataset_version,
            "feature_version": self.feature_version,
            "split_set_id": self.split_set_id,
            "eval_vintage": self.eval_vintage.isoformat(),
            "rows": self.rows,
            "splits": [
                {
                    "split_id": item.split.split_id,
                    "origin": item.split.origin.isoformat(),
                    "horizon_months": item.split.horizon_months,
                    "sha256": item.sha256,
                    "uri": item.uri,
                }
                for item in self.splits
            ],
        }


@dataclass(slots=True)
class ControlStats:
    test_subject_instances: int = 0
    unavailable_subject_instances: int = 0
    subject_stream_instances: int = 0
    unavailable_subject_stream_instances: int = 0
    fallback_counts: Counter[str] = field(default_factory=Counter)
    unavailable_reason_counts: Counter[str] = field(default_factory=Counter)
    monthly_status_counts: Counter[str] = field(default_factory=Counter)
    cumulative_status_counts: Counter[str] = field(default_factory=Counter)
    split_subjects: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    split_unavailable_subjects: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    split_fallback_counts: dict[str, Counter[str]] = field(
        default_factory=lambda: defaultdict(Counter)
    )
    split_unavailable_reason_counts: dict[str, Counter[str]] = field(
        default_factory=lambda: defaultdict(Counter)
    )


CONTROL_SCHEMA = {
    "row_key": pl.String,
    "type_curve_id": pl.String,
    "control_version": pl.String,
    "dataset_version": pl.String,
    "dataset_derivation_id": pl.String,
    "control_derivation_id": pl.String,
    "feature_version": pl.String,
    "split_set_id": pl.String,
    "split_id": pl.String,
    "split_sha256": pl.String,
    "origin": pl.Date,
    "knowledge_cutoff": pl.Date,
    "eval_vintage": pl.Date,
    "subject_api10": pl.String,
    "stream": pl.String,
    "unit": pl.String,
    "horizon_months": pl.Int16,
    "month_index": pl.Int16,
    "normalization": pl.String,
    "fallback_level": pl.String,
    "control_unavailable_reasons": pl.String,
    "peer_set_id": pl.String,
    "peer_count": pl.Int32,
    "cumulative_peer_count": pl.Int32,
    "status": pl.String,
    "cumulative_status": pl.String,
    "monthly_p10": pl.Float64,
    "monthly_p50": pl.Float64,
    "monthly_p90": pl.Float64,
    "cumulative_p10": pl.Float64,
    "cumulative_p50": pl.Float64,
    "cumulative_p90": pl.Float64,
    "quantile_convention": pl.String,
    "formation_group": pl.String,
    "area": pl.String,
    "lateral_length_bucket": pl.String,
    "subject_lateral_length_ft": pl.Float64,
}


def empirical_quantile(values: Sequence[float], quantile: float) -> float:
    """Return percentile_cont-style linear interpolation over equal-weight observations."""
    if not values:
        raise ValueError("empirical quantile requires at least one observation")
    if not 0 <= quantile <= 1:
        raise ValueError("quantile must be between zero and one")
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def empirical_quantiles(values: Sequence[float]) -> Quantiles:
    return Quantiles(
        p10=empirical_quantile(values, 0.10),
        p50=empirical_quantile(values, 0.50),
        p90=empirical_quantile(values, 0.90),
    )


def aggregate_peer_curves(
    peer_api10s: Sequence[str],
    series_by_api: Mapping[str, Sequence[float | None]],
    lateral_length_by_api: Mapping[str, float],
    *,
    horizon_months: int,
    min_peers: int = TC_MIN_N,
) -> tuple[AggregatedMonth, ...]:
    """Aggregate one stream for one resolved peer set under both normalization arms."""
    if horizon_months <= 0:
        raise ValueError("horizon_months must be positive")
    if min_peers <= 0:
        raise ValueError("min_peers must be positive")
    ordered_peers = tuple(sorted(set(peer_api10s)))
    if any(api10 not in series_by_api for api10 in ordered_peers):
        raise TypeCurveError("resolved peer set lacks a curve series")
    if any(lateral_length_by_api.get(api10, 0) <= 0 for api10 in ordered_peers):
        raise TypeCurveError("both normalization arms require positive peer lateral lengths")

    result: list[AggregatedMonth] = []
    for month_index in range(1, horizon_months + 1):
        absolute_monthly: list[float] = []
        normalized_monthly: list[float] = []
        absolute_cumulative: list[float] = []
        normalized_cumulative: list[float] = []
        for api10 in ordered_peers:
            series = series_by_api[api10]
            value = series[month_index - 1] if month_index <= len(series) else None
            length_scale = lateral_length_by_api[api10] / 1000.0
            if value is not None:
                absolute_monthly.append(value)
                normalized_monthly.append(value / length_scale)
            prefix = series[:month_index]
            if len(prefix) == month_index and all(item is not None for item in prefix):
                cumulative = sum(float(item) for item in prefix if item is not None)
                absolute_cumulative.append(cumulative)
                normalized_cumulative.append(cumulative / length_scale)
        monthly_n = len(absolute_monthly)
        cumulative_n = len(absolute_cumulative)
        result.append(
            AggregatedMonth(
                month_index=month_index,
                peer_count=monthly_n,
                cumulative_peer_count=cumulative_n,
                absolute_monthly=(
                    empirical_quantiles(absolute_monthly) if monthly_n >= min_peers else None
                ),
                absolute_cumulative=(
                    empirical_quantiles(absolute_cumulative) if cumulative_n >= min_peers else None
                ),
                per_kft_monthly=(
                    empirical_quantiles(normalized_monthly) if monthly_n >= min_peers else None
                ),
                per_kft_cumulative=(
                    empirical_quantiles(normalized_cumulative)
                    if cumulative_n >= min_peers
                    else None
                ),
            )
        )
    return tuple(result)


def fallback_keys(context: SubjectContext) -> tuple[tuple[FallbackLevel, tuple[str, ...]], ...]:
    if context.formation_group is None or context.basin is None:
        return ()
    keys: list[tuple[FallbackLevel, tuple[str, ...]]] = []
    if context.area is not None and context.lateral_length_bucket is not None:
        keys.append(
            (
                "formation_area_length",
                (context.formation_group, context.area, context.lateral_length_bucket),
            )
        )
    if context.area is not None:
        keys.append(("formation_area", (context.formation_group, context.area)))
    keys.append(("formation_basin", (context.formation_group, context.basin)))
    return tuple(keys)


def resolve_fallback(
    context: SubjectContext,
    peer_indices: Mapping[FallbackLevel, Mapping[tuple[str, ...], Sequence[str]]],
    *,
    min_peers: int = TC_MIN_N,
    excluded_api10s: Iterable[str] = (),
) -> FallbackChoice:
    """Apply the ordered, closed peer ladder and never invent a fourth widening."""
    excluded = set(excluded_api10s)
    for level, key in fallback_keys(context):
        peers = tuple(
            api10
            for api10 in sorted(set(peer_indices.get(level, {}).get(key, ())))
            if api10 not in excluded
        )
        if len(peers) >= min_peers:
            return FallbackChoice(level=level, key=key, peer_api10s=peers)
    return FallbackChoice(level="control_unavailable", key=None, peer_api10s=())


def _shift_months(value: date, months: int) -> date:
    absolute = value.year * 12 + value.month - 1 + months
    year, zero_month = divmod(absolute, 12)
    return date(year, zero_month + 1, 1)


def _single_text(frame: pl.DataFrame, column: str) -> str:
    values = frame[column].drop_nulls().unique().to_list()
    if len(values) != 1:
        raise TypeCurveError(f"model dataset must carry one {column}, found {values}")
    return str(values[0])


def _single_date(frame: pl.DataFrame, column: str) -> date:
    values = frame[column].drop_nulls().unique().to_list()
    if len(values) != 1 or not isinstance(values[0], date):
        raise TypeCurveError(f"model dataset must carry one date-valued {column}, found {values}")
    return values[0]


def _load_model_bundle(
    labels_uri: Path | str, coverage_uri: Path | str
) -> tuple[pl.DataFrame, pl.DataFrame, Mapping[str, object], str, str, str]:
    labels_path = Path(labels_uri)
    coverage_path = Path(coverage_uri)
    labels_hash = file_sha256(labels_path)
    if labels_path.parent.name != f"sha256={labels_hash}":
        raise TypeCurveError("model labels path does not match its content hash")
    coverage_bytes = coverage_path.read_bytes()
    coverage_hash = sha256_hex(coverage_bytes)
    coverage = json.loads(coverage_bytes)
    if not isinstance(coverage, Mapping):
        raise TypeCurveError("model coverage must be a JSON object")
    artifacts = coverage.get("artifacts", {})
    if not isinstance(artifacts, Mapping):
        raise TypeCurveError("model coverage artifacts must be a JSON object")
    if artifacts.get("labels_sha256") != labels_hash:
        raise TypeCurveError("model coverage points at different label bytes")
    curves_path = labels_path.parent / "curves.parquet"
    curves_hash = file_sha256(curves_path)
    if artifacts.get("curves_sha256") != curves_hash:
        raise TypeCurveError("model coverage points at different curve bytes")

    labels = pl.read_parquet(labels_path)
    curves = pl.read_parquet(curves_path)
    required_labels = {
        "api10",
        "stream",
        "horizon_months",
        "dataset_version",
        "dataset_derivation_id",
        "feature_version",
        "feature_set_hash",
        "eval_vintage",
        "first_production_month",
        "formation_group",
        "formation_group_source_available_on",
        "basin",
        "area",
        "lateral_length_ft",
        "lateral_length_bucket",
    }
    required_curves = {
        "api10",
        "stream",
        "producing_month_index",
        "volume",
        "dataset_version",
        "source_available_on",
        "source_reconstructed_available_on",
        "feature_version",
        "feature_set_hash",
        "eval_vintage",
        "dataset_derivation_id",
    }
    if missing := required_labels - set(labels.columns):
        raise TypeCurveError(f"model labels lack columns {sorted(missing)}")
    if missing := required_curves - set(curves.columns):
        raise TypeCurveError(f"model curves lack columns {sorted(missing)}")
    if labels.is_empty() or curves.is_empty():
        raise TypeCurveError("model labels and curves must both be nonempty")
    if _single_text(labels, "dataset_version") != MODEL_DATASET_VERSION:
        raise TypeCurveError(f"{CONTROL_VERSION} requires {MODEL_DATASET_VERSION}")
    if _single_text(curves, "dataset_version") != MODEL_DATASET_VERSION:
        raise TypeCurveError("curve and label dataset versions differ")
    if coverage.get("dataset_version") != MODEL_DATASET_VERSION:
        raise TypeCurveError("coverage and label dataset versions differ")
    for column in (
        "dataset_derivation_id",
        "feature_version",
        "feature_set_hash",
        "eval_vintage",
    ):
        if column == "eval_vintage":
            label_value = _single_date(labels, column)
            curve_value = _single_date(curves, column)
        else:
            label_value = _single_text(labels, column)
            curve_value = _single_text(curves, column)
        if curve_value != label_value:
            raise TypeCurveError(f"curve and label {column} values differ")
    if coverage.get("derivation_id") != _single_text(labels, "dataset_derivation_id"):
        raise TypeCurveError("coverage and label derivation ids differ")
    if coverage.get("feature_version") != _single_text(labels, "feature_version"):
        raise TypeCurveError("coverage and label feature versions differ")
    if coverage.get("eval_vintage") != _single_date(labels, "eval_vintage").isoformat():
        raise TypeCurveError("coverage and label evaluation vintages differ")
    if labels.select(["api10", "stream", "horizon_months"]).is_duplicated().any():
        raise TypeCurveError("model labels contain duplicate api/stream/horizon rows")
    return labels, curves, coverage, labels_hash, curves_hash, coverage_hash


def _subject_contexts(labels: pl.DataFrame) -> Mapping[str, SubjectContext]:
    columns = [
        "api10",
        "basin",
        "formation_group",
        "formation_group_source_available_on",
        "area",
        "lateral_length_ft",
        "lateral_length_bucket",
        "first_production_month",
    ]
    context_frame = labels.select(columns).unique().sort("api10")
    if context_frame.height != labels["api10"].n_unique():
        raise TypeCurveError("model labels disagree on subject control context")
    contexts: dict[str, SubjectContext] = {}
    for row in context_frame.iter_rows(named=True):
        api10 = str(row["api10"])
        contexts[api10] = SubjectContext(
            api10=api10,
            basin=str(row["basin"]) if row["basin"] is not None else None,
            formation_group=(
                str(row["formation_group"]) if row["formation_group"] is not None else None
            ),
            formation_group_source_available_on=row["formation_group_source_available_on"],
            area=str(row["area"]) if row["area"] is not None else None,
            lateral_length_ft=(
                float(row["lateral_length_ft"]) if row["lateral_length_ft"] is not None else None
            ),
            lateral_length_bucket=(
                str(row["lateral_length_bucket"])
                if row["lateral_length_bucket"] is not None
                else None
            ),
            first_production_month=row["first_production_month"],
        )
    return contexts


CurveStore = dict[str, dict[str, list[CurveObservation | None]]]


def _curve_store(curves: pl.DataFrame) -> CurveStore:
    selected = curves.select(
        "api10",
        "stream",
        "producing_month_index",
        "volume",
        "source_available_on",
        "source_reconstructed_available_on",
    )
    store: CurveStore = {}
    for api10, stream, month_index, volume, strict_date, reconstructed_date in selected.iter_rows():
        index = int(month_index)
        if index < 1 or index > 24:
            raise TypeCurveError(f"curve month index {index} is outside 1..24")
        streams = store.setdefault(str(api10), {name: [None] * 24 for name in STREAMS})
        observations = streams.get(str(stream))
        if observations is None:
            raise TypeCurveError(f"unsupported curve stream {stream!r}")
        if observations[index - 1] is not None:
            raise TypeCurveError(f"duplicate curve row for {api10}/{stream}/{index}")
        observations[index - 1] = CurveObservation(
            volume=float(volume) if volume is not None else None,
            source_available_on=strict_date,
            source_reconstructed_available_on=reconstructed_date,
        )
    return store


def _load_splits(
    coverage: Mapping[str, object], split_root: Path | str, *, basin: str
) -> tuple[PersistedSplitInput, ...]:
    root = Path(split_root)
    persisted: list[PersistedSplitInput] = []
    seen: set[tuple[date, int]] = set()
    raw_splits = coverage.get("splits", [])
    if not isinstance(raw_splits, list):
        raise TypeCurveError("model coverage splits must be an array")
    for item in raw_splits:
        if not isinstance(item, Mapping):
            raise TypeCurveError("coverage split entry is not an object")
        if list(item.get("streams", [])) != list(STREAMS):
            raise TypeCurveError("every model split must declare the exact three-stream order")
        origin = date.fromisoformat(str(item["origin"]))
        horizon = int(item["horizon_months"])
        split_id = str(item["split_id"])
        expected_hash = str(item["sha256"])
        path = (
            root
            / f"basin={basin}"
            / f"origin={origin.isoformat()}"
            / f"horizon={horizon}"
            / f"split_id={split_id}"
            / "split.json"
        )
        if not path.exists():
            raise TypeCurveError(f"model split artifact is missing: {path}")
        payload = path.read_bytes()
        actual_hash = sha256_hex(payload)
        if actual_hash != expected_hash:
            raise TypeCurveError(f"split {split_id} hash does not match model coverage")
        split = SplitObject.model_validate_json(payload)
        if split.basin != basin:
            raise TypeCurveError(f"split {split_id} basin {split.basin!r} differs from {basin!r}")
        if (split.split_id, split.origin, split.horizon_months) != (
            split_id,
            origin,
            horizon,
        ):
            raise TypeCurveError(f"split {split_id} identity does not match its path")
        key = (origin, horizon)
        if key in seen:
            raise TypeCurveError(f"duplicate split for origin/horizon {key}")
        seen.add(key)
        persisted.append(PersistedSplitInput(split=split, uri=str(path), sha256=actual_hash))
    if not persisted:
        raise TypeCurveError("model coverage names no split objects")
    horizons_by_origin: dict[date, set[int]] = defaultdict(set)
    for item in persisted:
        horizons_by_origin[item.split.origin].add(item.split.horizon_months)
    if any(horizons != {12, 24} for horizons in horizons_by_origin.values()):
        raise TypeCurveError("each rolling origin must carry exactly cum12 and cum24 splits")
    if coverage.get("split_set_id") != model_split_set_id(tuple(horizons_by_origin)):
        raise TypeCurveError("model coverage split_set_id does not match its rolling origins")
    return tuple(sorted(persisted, key=lambda item: (item.split.origin, item.split.horizon_months)))


def _available_series(
    observations: Sequence[CurveObservation | None],
    *,
    horizon_months: int,
    knowledge_cutoff: date,
    vintage_basis: VintageBasis,
) -> tuple[float | None, ...]:
    values: list[float | None] = []
    for observation in observations[:horizon_months]:
        if observation is None:
            values.append(None)
            continue
        available_on = (
            observation.source_available_on
            if vintage_basis == "strict_manifest_knowledge"
            else observation.source_reconstructed_available_on
        )
        values.append(
            observation.volume
            if available_on is not None and available_on <= knowledge_cutoff
            else None
        )
    while len(values) < horizon_months:
        values.append(None)
    return tuple(values)


def _observation_available_on(
    observation: CurveObservation, vintage_basis: VintageBasis
) -> date | None:
    if vintage_basis == "strict_manifest_knowledge":
        return observation.source_available_on
    return observation.source_reconstructed_available_on


def _has_producing_month_at_cutoff(
    streams: Mapping[str, Sequence[CurveObservation | None]],
    *,
    knowledge_cutoff: date,
    vintage_basis: VintageBasis,
) -> bool:
    for observations in streams.values():
        for observation in observations:
            if observation is None:
                continue
            available_on = _observation_available_on(observation, vintage_basis)
            if available_on is not None and available_on <= knowledge_cutoff:
                return True
    return False


def _peer_indices(
    peer_api10s: Sequence[str], contexts: Mapping[str, SubjectContext]
) -> Mapping[FallbackLevel, Mapping[tuple[str, ...], tuple[str, ...]]]:
    mutable: dict[FallbackLevel, dict[tuple[str, ...], list[str]]] = {
        "formation_area_length": defaultdict(list),
        "formation_area": defaultdict(list),
        "formation_basin": defaultdict(list),
        "control_unavailable": {},
    }
    for api10 in sorted(peer_api10s):
        for level, key in fallback_keys(contexts[api10]):
            mutable[level][key].append(api10)
    return {
        level: {key: tuple(values) for key, values in groups.items()}
        for level, groups in mutable.items()
    }


def _scaled(values: Quantiles | None, factor: float) -> Quantiles | None:
    if values is None:
        return None
    return Quantiles(values.p10 * factor, values.p50 * factor, values.p90 * factor)


def _status(values: Quantiles | None, choice: FallbackChoice) -> MonthStatus:
    if choice.level == "control_unavailable":
        return "control_unavailable"
    return "ok" if values is not None else "insufficient"


def _quantile_values(values: Quantiles | None) -> tuple[float | None, float | None, float | None]:
    if values is None:
        return None, None, None
    return values.p10, values.p50, values.p90


def _context_unavailable_reasons(context: SubjectContext, basin: str) -> tuple[str, ...]:
    reasons: list[str] = []
    if context.formation_group is None:
        reasons.append("missing_formation")
    if context.basin != basin:
        reasons.append("basin_mismatch")
    if context.lateral_length_ft is None or context.lateral_length_ft <= 0:
        reasons.append("missing_lateral_length")
    return tuple(sorted(reasons))


def _control_rows(
    *,
    contexts: Mapping[str, SubjectContext],
    curves: CurveStore,
    splits: Sequence[PersistedSplitInput],
    vintage_basis: VintageBasis,
    eval_vintage: date,
    feature_version: str,
    split_set_id: str,
    dataset_derivation_id: str,
    control_derivation_id: str,
    type_curve_id: str,
    stats: ControlStats,
) -> Iterator[Mapping[str, object]]:
    for persisted in splits:
        split = persisted.split
        assignment_by_api = {item.api10: item for item in split.assignments}
        if len(assignment_by_api) != len(split.assignments):
            raise TypeCurveError(f"split {split.split_id} contains duplicate assignments")
        missing_context = set(assignment_by_api) - set(contexts)
        if missing_context:
            raise TypeCurveError(
                f"split {split.split_id} names unknown subject {min(missing_context)}"
            )
        partitions_by_pad: dict[str, set[str]] = defaultdict(set)
        for assignment in split.assignments:
            partitions_by_pad[assignment.pad_group_id].add(assignment.partition)
        if any(len(partitions) != 1 for partitions in partitions_by_pad.values()):
            raise TypeCurveError(f"split {split.split_id} divides a pad group")

        test_api10s = tuple(
            sorted(api10 for api10, item in assignment_by_api.items() if item.partition == "test")
        )
        non_test_api10s = tuple(
            sorted(api10 for api10, item in assignment_by_api.items() if item.partition != "test")
        )
        if not test_api10s or not non_test_api10s:
            raise TypeCurveError(f"split {split.split_id} lacks TEST or TRAIN/CAL subjects")
        stats.test_subject_instances += len(test_api10s)
        stats.split_subjects[split.split_id] += len(test_api10s)
        vintage_floor = _shift_months(split.origin, -VINTAGE_WINDOW_MONTHS)
        pad_members: dict[str, set[str]] = defaultdict(set)
        for api10, assignment in assignment_by_api.items():
            pad_members[assignment.pad_group_id].add(api10)

        available_by_stream: dict[str, dict[str, tuple[float | None, ...]]] = {
            stream: {} for stream in STREAMS
        }
        eligible_context_api10s: list[str] = []
        for api10 in non_test_api10s:
            context = contexts[api10]
            if (
                context.formation_group is None
                or context.basin != split.basin
                or context.first_production_month is None
                or not vintage_floor <= context.first_production_month < split.origin
                or context.lateral_length_ft is None
                or context.lateral_length_ft <= 0
                or context.formation_group_source_available_on is None
                or context.formation_group_source_available_on > split.holdout_def.knowledge_cutoff
            ):
                continue
            subject_curves = curves.get(api10)
            if subject_curves is None or not _has_producing_month_at_cutoff(
                subject_curves,
                knowledge_cutoff=split.holdout_def.knowledge_cutoff,
                vintage_basis=vintage_basis,
            ):
                continue
            eligible_context_api10s.append(api10)
            for stream in STREAMS:
                available_by_stream[stream][api10] = _available_series(
                    subject_curves[stream],
                    horizon_months=split.horizon_months,
                    knowledge_cutoff=split.holdout_def.knowledge_cutoff,
                    vintage_basis=vintage_basis,
                )

        peer_indices = _peer_indices(eligible_context_api10s, contexts)

        aggregate_cache: dict[tuple[str, str], tuple[AggregatedMonth, ...]] = {}
        for subject_api10 in test_api10s:
            subject = contexts[subject_api10]
            subject_pad = assignment_by_api[subject_api10].pad_group_id
            unavailable_reasons = _context_unavailable_reasons(subject, split.basin)
            if unavailable_reasons:
                choice = FallbackChoice(level="control_unavailable", key=None, peer_api10s=())
            else:
                choice = resolve_fallback(
                    subject,
                    peer_indices,
                    excluded_api10s=pad_members[subject_pad],
                )
                if choice.level == "control_unavailable":
                    unavailable_reasons = ("insufficient_peers",)
            peer_set_id = choice.peer_set_id
            stats.fallback_counts[choice.level] += 1
            stats.split_fallback_counts[split.split_id][choice.level] += 1
            if choice.level == "control_unavailable":
                if not unavailable_reasons:
                    raise TypeCurveError("unavailable control has no recorded reason")
                stats.unavailable_subject_instances += 1
                stats.split_unavailable_subjects[split.split_id] += 1
                for unavailable_reason in unavailable_reasons:
                    stats.unavailable_reason_counts[unavailable_reason] += 1
                    stats.split_unavailable_reason_counts[split.split_id][unavailable_reason] += 1
            for stream in STREAMS:
                stats.subject_stream_instances += 1
                if choice.level == "control_unavailable":
                    stats.unavailable_subject_stream_instances += 1
                    aggregated = tuple(
                        AggregatedMonth(
                            month_index=month_index,
                            peer_count=0,
                            cumulative_peer_count=0,
                            absolute_monthly=None,
                            absolute_cumulative=None,
                            per_kft_monthly=None,
                            per_kft_cumulative=None,
                        )
                        for month_index in range(1, split.horizon_months + 1)
                    )
                else:
                    cache_key = (stream, peer_set_id or "")
                    aggregated = aggregate_cache.get(cache_key)
                    if aggregated is None:
                        lengths = {
                            api10: float(contexts[api10].lateral_length_ft or 0)
                            for api10 in choice.peer_api10s
                        }
                        aggregated = aggregate_peer_curves(
                            choice.peer_api10s,
                            available_by_stream[stream],
                            lengths,
                            horizon_months=split.horizon_months,
                        )
                        aggregate_cache[cache_key] = aggregated

                for normalization in NORMALIZATIONS:
                    scale = (
                        float(subject.lateral_length_ft or 0) / 1000.0
                        if normalization == "typecurve_per_kft"
                        else 1.0
                    )
                    for month in aggregated:
                        if normalization == "typecurve_per_kft":
                            monthly = _scaled(month.per_kft_monthly, scale)
                            cumulative = _scaled(month.per_kft_cumulative, scale)
                        else:
                            monthly = month.absolute_monthly
                            cumulative = month.absolute_cumulative
                        monthly_status = _status(monthly, choice)
                        cumulative_status = _status(cumulative, choice)
                        stats.monthly_status_counts[
                            f"{stream}.{normalization}.{monthly_status}"
                        ] += 1
                        stats.cumulative_status_counts[
                            f"{stream}.{normalization}.{cumulative_status}"
                        ] += 1
                        monthly_values = _quantile_values(monthly)
                        cumulative_values = _quantile_values(cumulative)
                        yield {
                            "row_key": (
                                f"{split.split_id}|{subject_api10}|{stream}|"
                                f"{normalization}|{month.month_index:02d}"
                            ),
                            "type_curve_id": type_curve_id,
                            "control_version": CONTROL_VERSION,
                            "dataset_version": MODEL_DATASET_VERSION,
                            "dataset_derivation_id": dataset_derivation_id,
                            "control_derivation_id": control_derivation_id,
                            "feature_version": feature_version,
                            "split_set_id": split_set_id,
                            "split_id": split.split_id,
                            "split_sha256": persisted.sha256,
                            "origin": split.origin,
                            "knowledge_cutoff": split.holdout_def.knowledge_cutoff,
                            "eval_vintage": eval_vintage,
                            "subject_api10": subject_api10,
                            "stream": stream,
                            "unit": STREAM_UNITS[stream],
                            "horizon_months": split.horizon_months,
                            "month_index": month.month_index,
                            "normalization": normalization,
                            "fallback_level": choice.level,
                            "control_unavailable_reasons": ("|".join(unavailable_reasons) or None),
                            "peer_set_id": peer_set_id,
                            "peer_count": month.peer_count,
                            "cumulative_peer_count": month.cumulative_peer_count,
                            "status": monthly_status,
                            "cumulative_status": cumulative_status,
                            "monthly_p10": monthly_values[0],
                            "monthly_p50": monthly_values[1],
                            "monthly_p90": monthly_values[2],
                            "cumulative_p10": cumulative_values[0],
                            "cumulative_p50": cumulative_values[1],
                            "cumulative_p90": cumulative_values[2],
                            "quantile_convention": QUANTILE_CONVENTION,
                            "formation_group": subject.formation_group,
                            "area": subject.area,
                            "lateral_length_bucket": subject.lateral_length_bucket,
                            "subject_lateral_length_ft": subject.lateral_length_ft,
                        }


def _frames(rows: Iterable[Mapping[str, object]]) -> Iterator[pl.DataFrame]:
    batch: list[Mapping[str, object]] = []
    for row in rows:
        batch.append(row)
        if len(batch) == BATCH_ROWS:
            yield pl.from_dicts(batch, schema=CONTROL_SCHEMA)
            batch = []
    if batch:
        yield pl.from_dicts(batch, schema=CONTROL_SCHEMA)


def _persist_primary(
    frames: Iterable[pl.DataFrame],
    *,
    root: Path,
    basin: str,
    eval_vintage: date,
    feature_version: str,
    split_set_id: str,
    vintage_basis: VintageBasis,
) -> tuple[str, str, int]:
    partition = (
        root
        / "typecurve_control"
        / f"control_version={CONTROL_VERSION}"
        / f"dataset_version={MODEL_DATASET_VERSION}"
        / f"basin={basin}"
        / f"eval_vintage={eval_vintage.isoformat()}"
        / f"feature_version={feature_version}"
        / f"vintage_basis={vintage_basis}"
        / f"split_set_id={split_set_id}"
    )
    partition.mkdir(parents=True, exist_ok=True)
    pending = partition / f".pending-{uuid4().hex}.parquet"
    try:
        written = write_partition(frames, pending, sort_order="row_key", memory_limit="2GB")
        final = partition / f"sha256={written.sha256}" / PARTITION_FILENAME
        conflicts = [
            path for path in partition.glob(f"sha256=*/{PARTITION_FILENAME}") if path != final
        ]
        if conflicts:
            raise ImmutableTypeCurveArtifactError(
                f"{CONTROL_VERSION}/{eval_vintage}/{split_set_id} already resolves to "
                f"{conflicts[0].parent.name}"
            )
        final.parent.mkdir(parents=True, exist_ok=True)
        if final.exists():
            if file_sha256(final) != written.sha256:
                raise ImmutableTypeCurveArtifactError(f"stored control {final} failed its address")
            pending.unlink()
        else:
            os.replace(pending, final)
        return str(final), written.sha256, written.rows
    finally:
        pending.unlink(missing_ok=True)


def _persist_json(payload: bytes, destination: Path) -> str:
    digest = sha256_hex(payload)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.read_bytes() != payload:
            raise ImmutableTypeCurveArtifactError(
                f"stored type-curve coverage {destination} changed on replay"
            )
        return digest
    pending = destination.with_name(f".pending-{uuid4().hex}.json")
    try:
        pending.write_bytes(payload)
        os.replace(pending, destination)
    finally:
        pending.unlink(missing_ok=True)
    return digest


def _content_id(prefix: str, payload: object) -> str:
    digest = hashlib.sha256(canonical_json(payload)).digest()[:12]
    encoded = base64.b32encode(digest).decode("ascii").rstrip("=").lower()
    return prefix + encoded


def _merge_inputs(groups: Sequence[Sequence[InputRef]]) -> tuple[InputRef, ...]:
    merged: dict[tuple[str, str, str | None], InputRef] = {}
    for ref in (item for group in groups for item in group):
        key = (ref.kind, ref.ref_id, ref.selector)
        merged[key] = ref
    ordered = sorted(merged.values(), key=lambda ref: (ref.kind, ref.ref_id, ref.selector or ""))
    return tuple(ref.model_copy(update={"ord": index}) for index, ref in enumerate(ordered))


def _ratio(numerator: int, denominator: int) -> str:
    if not denominator:
        return "0.000000"
    return f"{Decimal(numerator) / Decimal(denominator):.6f}"


def _gate_status(numerator: int, denominator: int, *, threshold: Decimal, minimum: bool) -> str:
    if not denominator:
        return "not_evaluable"
    observed = Decimal(numerator) / Decimal(denominator)
    passed = observed >= threshold if minimum else observed <= threshold
    return "pass" if passed else "fail"


def _coverage_document(
    *,
    type_curve_id: str,
    derivation: str,
    artifact_sha256: str,
    rows: int,
    labels_sha256: str,
    curves_sha256: str,
    model_coverage_sha256: str,
    feature_version: str,
    split_set_id: str,
    eval_vintage: date,
    vintage_basis: VintageBasis,
    stats: ControlStats,
    splits: Sequence[PersistedSplitInput],
) -> Mapping[str, object]:
    rung1_instances = stats.fallback_counts["formation_area_length"]
    pooled_rung1_status = _gate_status(
        rung1_instances,
        stats.test_subject_instances,
        threshold=TC_RUNG1_SHARE_MIN,
        minimum=True,
    )
    pooled_unavailable_status = _gate_status(
        stats.unavailable_subject_instances,
        stats.test_subject_instances,
        threshold=TC_UNAVAILABLE_SHARE_MAX,
        minimum=False,
    )
    split_unavailable_statuses = {
        item.split.split_id: _gate_status(
            stats.split_unavailable_subjects[item.split.split_id],
            stats.split_subjects[item.split.split_id],
            threshold=TC_UNAVAILABLE_SHARE_MAX,
            minimum=False,
        )
        for item in splits
    }
    plausibility_flags: list[str] = []
    if pooled_rung1_status == "fail":
        plausibility_flags.append("pooled_rung1_share_below_0.60")
    if pooled_unavailable_status == "fail":
        plausibility_flags.append("pooled_control_unavailable_share_above_0.05")
    if "fail" in split_unavailable_statuses.values():
        plausibility_flags.append("split_control_unavailable_share_above_0.05")
    return {
        "schema_version": CONTROL_SCHEMA_VERSION,
        "dataset": CONTROL_DATASET,
        "control_version": CONTROL_VERSION,
        "dataset_version": MODEL_DATASET_VERSION,
        "type_curve_id": type_curve_id,
        "derivation_id": derivation,
        "artifact_sha256": artifact_sha256,
        "rows": rows,
        "feature_version": feature_version,
        "split_set_id": split_set_id,
        "eval_vintage": eval_vintage,
        "vintage_basis": vintage_basis,
        "inputs": {
            "labels_sha256": labels_sha256,
            "curves_sha256": curves_sha256,
            "model_coverage_sha256": model_coverage_sha256,
        },
        "counts": {
            "test_subject_instances": stats.test_subject_instances,
            "control_unavailable_subject_instances": stats.unavailable_subject_instances,
            "control_unavailable_share": _ratio(
                stats.unavailable_subject_instances, stats.test_subject_instances
            ),
            "subject_stream_instances": stats.subject_stream_instances,
            "control_unavailable_subject_stream_instances": (
                stats.unavailable_subject_stream_instances
            ),
            "control_unavailable_subject_stream_share": _ratio(
                stats.unavailable_subject_stream_instances, stats.subject_stream_instances
            ),
            "fallback_by_level": dict(sorted(stats.fallback_counts.items())),
            "control_unavailable_reason_mentions": dict(
                sorted(stats.unavailable_reason_counts.items())
            ),
            "monthly_rows_by_status": dict(sorted(stats.monthly_status_counts.items())),
            "cumulative_rows_by_status": dict(sorted(stats.cumulative_status_counts.items())),
        },
        "acceptance": {
            "scope": "subject_instances_across_identical_persisted_splits",
            "pooled_rung1_share": {
                "observed": _ratio(rung1_instances, stats.test_subject_instances),
                "minimum": f"{TC_RUNG1_SHARE_MIN:.6f}",
                "status": pooled_rung1_status,
            },
            "pooled_control_unavailable_share": {
                "observed": _ratio(
                    stats.unavailable_subject_instances, stats.test_subject_instances
                ),
                "maximum": f"{TC_UNAVAILABLE_SHARE_MAX:.6f}",
                "status": pooled_unavailable_status,
            },
        },
        "plausibility_flags": plausibility_flags,
        "control_contract": {
            "peer_population": "TRAIN_union_CAL_only",
            "pad_mates": "excluded_and_split_partition_indivisibility_enforced",
            "vintage_window_months": VINTAGE_WINDOW_MONTHS,
            "min_peers": TC_MIN_N,
            "fallback_ladder": [
                "formation_area_length",
                "formation_area",
                "formation_basin",
                "control_unavailable",
            ],
            "normalizations": list(NORMALIZATIONS),
            "quantiles": [0.10, 0.50, 0.90],
            "quantile_method": "equal_weight_percentile_cont_linear",
            "cumulative_quantiles": "empirical_quantile_of_each_peers_own_cumulative",
            "per_month_counts": ["peer_count", "cumulative_peer_count"],
            "quantile_convention": QUANTILE_CONVENTION,
            "unavailable_reason_format": "pipe_delimited_sorted_reason_set",
        },
        "determinism_gate": {
            "class": "D1",
            "requirement": "build_twice_same_environment_identical_artifact_and_coverage_hashes",
        },
        "splits": [
            {
                "split_id": item.split.split_id,
                "origin": item.split.origin,
                "horizon_months": item.split.horizon_months,
                "sha256": item.sha256,
                "test_subjects": stats.split_subjects[item.split.split_id],
                "control_unavailable_subjects": stats.split_unavailable_subjects[
                    item.split.split_id
                ],
                "control_unavailable_share": _ratio(
                    stats.split_unavailable_subjects[item.split.split_id],
                    stats.split_subjects[item.split.split_id],
                ),
                "control_unavailable_status": split_unavailable_statuses[item.split.split_id],
                "fallback_by_level": dict(
                    sorted(stats.split_fallback_counts[item.split.split_id].items())
                ),
                "control_unavailable_reason_mentions": dict(
                    sorted(stats.split_unavailable_reason_counts[item.split.split_id].items())
                ),
                "streams": list(STREAMS),
                "normalizations": list(NORMALIZATIONS),
            }
            for item in splits
        ],
    }


def _lockfile_sha256(connection: psycopg.Connection, env_id: str) -> str | None:
    with connection.cursor() as cursor:
        cursor.execute(
            "select lockfile_sha256 from lineage.environments where env_id = %s", (env_id,)
        )
        row = cursor.fetchone()
    if row is None:
        raise TypeCurveError(f"environment {env_id!r} is not registered")
    return row[0]


def build_type_curve_control(
    connection: psycopg.Connection,
    *,
    labels_uri: Path | str,
    model_coverage_uri: Path | str,
    split_root: Path | str,
    environment: DeriveEnvironment,
    root: Path | str | None = None,
    clock: Clock | None = None,
) -> TypeCurveBuild:
    """Build and register the pinned type-curve control for every model-dataset split."""
    labels, curve_frame, model_coverage, labels_hash, curves_hash, model_coverage_hash = (
        _load_model_bundle(labels_uri, model_coverage_uri)
    )
    contexts = _subject_contexts(labels)
    basins = {context.basin for context in contexts.values() if context.basin is not None}
    if len(basins) != 1:
        raise TypeCurveError(f"control bundle requires one non-null basin, found {sorted(basins)}")
    basin = next(iter(basins))
    curves = _curve_store(curve_frame)
    del curve_frame
    splits = _load_splits(model_coverage, split_root, basin=basin)
    feature_version = _single_text(labels, "feature_version")
    feature_set_hash = _single_text(labels, "feature_set_hash")
    dataset_derivation_id = _single_text(labels, "dataset_derivation_id")
    eval_vintage = _single_date(labels, "eval_vintage")
    split_set_id = str(model_coverage.get("split_set_id") or "")
    if not split_set_id:
        raise TypeCurveError("model coverage lacks split_set_id")
    retrospective_vintage = model_coverage.get("retrospective_vintage", {})
    if not isinstance(retrospective_vintage, Mapping):
        raise TypeCurveError("model retrospective_vintage contract must be an object")
    vintage_basis = str(retrospective_vintage.get("split_basis") or "")
    if vintage_basis not in {
        "strict_manifest_knowledge",
        "source_reconstructed_not_glasswell_history",
    }:
        raise TypeCurveError(f"unsupported model vintage basis {vintage_basis!r}")
    typed_vintage_basis = cast(VintageBasis, vintage_basis)
    if any(item.split.holdout_def.knowledge_cutoff > eval_vintage for item in splits):
        raise TypeCurveError("model split knowledge cutoff exceeds the evaluation vintage")

    split_inputs = tuple(
        InputRef(
            kind="external",
            ref_id="modeling.temporal_split",
            selector=f"sha256:{item.sha256}",
            as_of_vintage=item.split.holdout_def.knowledge_cutoff,
            role="validator",
        )
        for item in splits
    )
    inputs = _merge_inputs(
        (
            (
                InputRef(
                    kind="derivation",
                    ref_id=dataset_derivation_id,
                    selector=f"sha256:{labels_hash}",
                    as_of_vintage=eval_vintage,
                ),
                InputRef(
                    kind="external",
                    ref_id="modeling.model_ready_curves",
                    selector=f"sha256:{curves_hash}",
                    as_of_vintage=eval_vintage,
                ),
                InputRef(
                    kind="external",
                    ref_id="modeling.model_ready_coverage",
                    selector=f"sha256:{model_coverage_hash}",
                    as_of_vintage=eval_vintage,
                    role="validator",
                ),
            ),
            split_inputs,
        )
    )
    params = {
        "basin": basin,
        "control_version": CONTROL_VERSION,
        "dataset_version": MODEL_DATASET_VERSION,
        "eval_vintage": eval_vintage,
        "feature_version": feature_version,
        "feature_set_hash": feature_set_hash,
        "split_set_id": split_set_id,
        "split_ids": [item.split.split_id for item in splits],
        "streams": STREAMS,
        "normalizations": NORMALIZATIONS,
        "tc_min_n": TC_MIN_N,
        "rung1_share_min": str(TC_RUNG1_SHARE_MIN),
        "control_unavailable_share_max": str(TC_UNAVAILABLE_SHARE_MAX),
        "vintage_window_months": VINTAGE_WINDOW_MONTHS,
        "vintage_basis": typed_vintage_basis,
        "quantile_method": "equal_weight_percentile_cont_linear",
    }
    output_spec = OutputSpec(
        store="parquet",
        dataset=CONTROL_DATASET,
        partition={
            "basin": basin,
            "control_version": CONTROL_VERSION,
            "dataset_version": MODEL_DATASET_VERSION,
            "eval_vintage": eval_vintage.isoformat(),
            "feature_version": feature_version,
            "vintage_basis": typed_vintage_basis,
            "split_set_id": split_set_id,
        },
        schema_version=CONTROL_SCHEMA_VERSION,
    )
    planned_id = derivation_id(
        operation="typecurve.build",
        inputs=inputs,
        params=params,
        code_version=environment.code_version,
        env_id=environment.env_id,
        rule_ids=(),
        output=output_spec,
    )
    type_curve_id = _content_id(
        "tc_",
        {
            "params": params,
            "input_refs": [item.model_dump(mode="json") for item in inputs],
            "code_version": environment.code_version,
            "env_id": environment.env_id,
        },
    )
    model_root = resolve_model_root(root)
    stats = ControlStats()
    rows = _control_rows(
        contexts=contexts,
        curves=curves,
        splits=splits,
        vintage_basis=typed_vintage_basis,
        eval_vintage=eval_vintage,
        feature_version=feature_version,
        split_set_id=split_set_id,
        dataset_derivation_id=dataset_derivation_id,
        control_derivation_id=planned_id,
        type_curve_id=type_curve_id,
        stats=stats,
    )
    artifact_uri, artifact_hash, output_rows = _persist_primary(
        _frames(rows),
        root=model_root,
        basin=basin,
        eval_vintage=eval_vintage,
        feature_version=feature_version,
        split_set_id=split_set_id,
        vintage_basis=typed_vintage_basis,
    )
    if output_rows == 0:
        raise TypeCurveError("control build produced no rows")
    coverage = _coverage_document(
        type_curve_id=type_curve_id,
        derivation=planned_id,
        artifact_sha256=artifact_hash,
        rows=output_rows,
        labels_sha256=labels_hash,
        curves_sha256=curves_hash,
        model_coverage_sha256=model_coverage_hash,
        feature_version=feature_version,
        split_set_id=split_set_id,
        eval_vintage=eval_vintage,
        vintage_basis=typed_vintage_basis,
        stats=stats,
        splits=splits,
    )
    coverage_uri = Path(artifact_uri).parent / "coverage.json"
    coverage_hash = _persist_json(canonical_json(coverage), coverage_uri)
    recipe_id = build_recipe(
        connection,
        "typecurve.build",
        code_version=environment.code_version,
        lockfile_sha256=_lockfile_sha256(connection, environment.env_id),
        entry_point="glasswell.modeling.type_curve:build_type_curve_control",
        params=params,
        input_refs=inputs,
        determinism_class="D1",
        output={
            "dataset": CONTROL_DATASET,
            "partition": output_spec.partition,
            "sha256": artifact_hash,
            "rows": output_rows,
            "schema_version": CONTROL_SCHEMA_VERSION,
            "type_curve_id": type_curve_id,
            "coverage": {"filename": coverage_uri.name, "sha256": coverage_hash},
            "splits": [
                {
                    "split_id": item.split.split_id,
                    "sha256": item.sha256,
                    "origin": item.split.origin,
                    "horizon_months": item.split.horizon_months,
                }
                for item in splits
            ],
            "determinism_class": "D1",
        },
    )
    resolved_environment = environment.model_copy(update={"recipe_id": recipe_id})
    with (
        lineage_session(
            recorder=PostgresRecorder(connection), environment=resolved_environment, clock=clock
        ),
        derive(
            "typecurve.build",
            output=output_spec.model_copy(update={"locator": artifact_uri}),
            params=params,
            inputs=inputs,
            determinism_class="D1",
            ttl_class="permanent",
        ) as context,
    ):
        context.set_output_hash(artifact_hash)
        context.set_rows(output_rows)
    if context.derivation_id != planned_id:
        raise TypeCurveError(
            f"planned derivation {planned_id} became {context.derivation_id} during capture"
        )
    return TypeCurveBuild(
        type_curve_id=type_curve_id,
        derivation_id=context.derivation_id,
        recipe_id=recipe_id,
        artifact_uri=artifact_uri,
        artifact_sha256=artifact_hash,
        coverage_uri=str(coverage_uri),
        coverage_sha256=coverage_hash,
        control_version=CONTROL_VERSION,
        dataset_version=MODEL_DATASET_VERSION,
        feature_version=feature_version,
        split_set_id=split_set_id,
        eval_vintage=eval_vintage,
        rows=output_rows,
        splits=tuple(splits),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the pinned P3 type-curve control.")
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--labels", required=True)
    parser.add_argument("--model-coverage", required=True)
    parser.add_argument("--split-root", required=True)
    parser.add_argument("--root", default=None)
    parser.add_argument("--env-id", default=None)
    parser.add_argument("--code-version", default=None)
    arguments = parser.parse_args(argv)
    with psycopg.connect(arguments.dsn) as connection:
        environment = resolve_environment(
            connection, env_id=arguments.env_id, code_version=arguments.code_version
        )
        built = build_type_curve_control(
            connection,
            labels_uri=arguments.labels,
            model_coverage_uri=arguments.model_coverage,
            split_root=arguments.split_root,
            environment=environment,
            root=arguments.root,
        )
        connection.commit()
    print(json.dumps(built.to_dict(), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
