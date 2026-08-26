"""D1 model-ready labels, control curves, coverage, rejections, and DB-backed splits."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from itertools import groupby
from pathlib import Path
from typing import Literal
from uuid import uuid4

import polars as pl
import psycopg

from glasswell.ingest.base import resolve_environment
from glasswell.lineage.as_of import (
    read_model_context_snapshot,
    read_model_production_snapshot,
)
from glasswell.lineage.capture import derive, lineage_session
from glasswell.lineage.clock import Clock
from glasswell.lineage.ids import derivation_id
from glasswell.lineage.models import DeriveEnvironment, InputRef, OutputSpec
from glasswell.lineage.recipes import build_recipe
from glasswell.lineage.serialization import canonical_json, sha256_hex
from glasswell.lineage.store import PostgresRecorder
from glasswell.modeling.split import SplitObject, WellTimeline, build_temporal_split
from glasswell.staging.duck import PARTITION_FILENAME, file_sha256, write_partition

MODEL_ROOT_ENV = "GLASSWELL_MODEL_ROOT"
DEFAULT_MODEL_ROOT = Path("data/models")
MODEL_DATASET = "modeling.model_ready_labels"
MODEL_SCHEMA_VERSION = "1"
COVERAGE_SCHEMA_VERSION = "1"
REJECTION_SCHEMA_VERSION = "1"
CURVE_SCHEMA_VERSION = "1"
STREAMS = ("oil", "gas", "water")
STREAM_UNITS = {"oil": "bbl", "gas": "mcf", "water": "bbl"}
HORIZONS = (12, 24)
HORIZON_CALENDAR_GUARD_MONTHS = 16
PRODUCTION_SOURCE_ID = "nd_mpr_xlsx"
PRODUCTION_SOURCE_LAG_DAYS = 45
DEFAULT_ORIGINS = (
    date(2021, 1, 1),
    date(2022, 1, 1),
    date(2023, 1, 1),
    date(2024, 1, 1),
)

VintageBasis = Literal[
    "strict_manifest_knowledge", "source_reconstructed_not_glasswell_history"
]


class ModelDatasetError(RuntimeError):
    """The model-ready artifact cannot satisfy its declared contract."""


class ImmutableModelArtifactError(ModelDatasetError):
    """A content-addressed model artifact replayed to different bytes."""


@dataclass(frozen=True, slots=True)
class WellLabelState:
    api10: str
    first_production_month: date | None
    reconstructed_completeness: Mapping[int, date | None]
    strict_completeness: Mapping[int, date | None]
    withheld_by_horizon: Mapping[int, bool]


@dataclass(frozen=True, slots=True)
class LabelMaterialization:
    labels: tuple[Mapping[str, object], ...]
    curves: tuple[Mapping[str, object], ...]
    states: Mapping[str, WellLabelState]


@dataclass(frozen=True, slots=True)
class PersistedSplit:
    split: SplitObject
    uri: str
    sha256: str


@dataclass(frozen=True, slots=True)
class ModelDatasetBuild:
    derivation_id: str
    recipe_id: str
    artifact_uri: str
    artifact_sha256: str
    curves_uri: str
    curves_sha256: str
    coverage_uri: str
    coverage_sha256: str
    rejections_uri: str
    rejections_sha256: str
    eval_vintage: date
    feature_version: str
    rows: int
    curve_rows: int
    rejection_rows: int
    splits: tuple[PersistedSplit, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "derivation_id": self.derivation_id,
            "recipe_id": self.recipe_id,
            "artifact_uri": self.artifact_uri,
            "artifact_sha256": self.artifact_sha256,
            "curves_uri": self.curves_uri,
            "curves_sha256": self.curves_sha256,
            "coverage_uri": self.coverage_uri,
            "coverage_sha256": self.coverage_sha256,
            "rejections_uri": self.rejections_uri,
            "rejections_sha256": self.rejections_sha256,
            "eval_vintage": self.eval_vintage.isoformat(),
            "feature_version": self.feature_version,
            "rows": self.rows,
            "curve_rows": self.curve_rows,
            "rejection_rows": self.rejection_rows,
            "splits": [
                {
                    "split_id": item.split.split_id,
                    "origin": item.split.origin.isoformat(),
                    "horizon_months": item.split.horizon_months,
                    "uri": item.uri,
                    "sha256": item.sha256,
                }
                for item in self.splits
            ],
        }


def resolve_model_root(explicit: Path | str | None = None) -> Path:
    if explicit is not None:
        return Path(explicit)
    return Path(os.environ.get(MODEL_ROOT_ENV) or DEFAULT_MODEL_ROOT)


def lateral_length_bucket(length_ft: Decimal | float | int | None) -> str | None:
    """Apply the measured ND bucket boundaries, including their exact edge policy."""
    if length_ft is None:
        return None
    value = Decimal(str(length_ft))
    if value < 8000:
        return "lt_8000"
    if value < 10000:
        return "8000_to_lt_10000"
    if value <= 10500:
        return "10000_to_10500"
    return "gt_10500"


def _calendar_month_gap(later: date, earlier: date) -> int:
    return (later.year - earlier.year) * 12 + later.month - earlier.month


def _stream_value(row: Mapping[str, object], stream: str, field: str) -> object:
    return row[f"{stream}_{field}"]


def _is_producing(row: Mapping[str, object]) -> bool:
    for stream in STREAMS:
        volume = _stream_value(row, stream, "volume")
        semantics = _stream_value(row, stream, "null_semantics")
        days = _stream_value(row, stream, "days_produced")
        if volume is not None and Decimal(str(volume)) > 0:
            return True
        if semantics == "reported_zero" and days is not None and int(days) > 0:
            return True
    return False


def _stream_is_known(row: Mapping[str, object], stream: str) -> bool:
    return (
        _stream_value(row, stream, "volume") is not None
        and _stream_value(row, stream, "null_semantics") not in {None, "no_report", "withheld"}
    )


def _has_withheld(row: Mapping[str, object]) -> bool:
    return any(_stream_value(row, stream, "null_semantics") == "withheld" for stream in STREAMS)


def _validate_month_row(row: Mapping[str, object]) -> None:
    for stream in STREAMS:
        if int(row[f"{stream}_rows"]) > 1:
            raise ModelDatasetError(
                f"{row['api10']} {row['production_month']} has multiple {stream} source rows"
            )
        volume = _stream_value(row, stream, "volume")
        semantics = _stream_value(row, stream, "null_semantics")
        if (
            semantics in {"no_report", "withheld"}
            and volume is not None
            and Decimal(str(volume)) > 0
        ):
            raise ModelDatasetError(
                f"{row['api10']} {row['production_month']} {stream} is {semantics} with volume"
            )
        unit = _stream_value(row, stream, "unit")
        if unit is not None and unit != STREAM_UNITS[stream]:
            raise ModelDatasetError(
                f"{row['api10']} {row['production_month']} {stream} uses {unit}, not "
                f"{STREAM_UNITS[stream]}"
            )


def materialize_labels(
    rows: Iterable[Mapping[str, object]],
    *,
    source_lag_days: int = PRODUCTION_SOURCE_LAG_DAYS,
) -> LabelMaterialization:
    """Build cumulative labels and producing-month curves from API/month-sorted rows."""
    labels: list[Mapping[str, object]] = []
    curves: list[Mapping[str, object]] = []
    states: dict[str, WellLabelState] = {}
    for api10, grouped in groupby(rows, key=lambda row: str(row["api10"])):
        if api10 in states:
            raise ModelDatasetError("production rows are not globally sorted by api10")
        months = list(grouped)
        if any(str(row["api10"]) != api10 for row in months):
            raise ModelDatasetError("production rows are not grouped by api10")
        if months != sorted(months, key=lambda row: row["production_month"]):
            raise ModelDatasetError(f"production rows for {api10} are not month-sorted")
        for row in months:
            _validate_month_row(row)
        producing = [row for row in months if _is_producing(row)]
        first_month = (
            producing[0]["production_month"] if producing else None
        )
        if first_month is not None and not isinstance(first_month, date):
            raise ModelDatasetError(f"{api10} has a non-date production month")
        reconstructed: dict[int, date | None] = {}
        strict: dict[int, date | None] = {}
        withheld_by_horizon: dict[int, bool] = {}
        twelfth = producing[11]["production_month"] if len(producing) >= 12 else None
        intermittent = bool(
            first_month is not None
            and isinstance(twelfth, date)
            and _calendar_month_gap(twelfth, first_month) > HORIZON_CALENDAR_GUARD_MONTHS
        )
        for month_index, row in enumerate(producing[: max(HORIZONS)], start=1):
            production_month = row["production_month"]
            source_available_on = row["source_vintage"]
            for stream in STREAMS:
                known = _stream_is_known(row, stream)
                curves.append(
                    {
                        "row_key": f"{api10}|{month_index:02d}|{stream}",
                        "api10": api10,
                        "producing_month_index": month_index,
                        "production_month": production_month,
                        "stream": stream,
                        "volume": _stream_value(row, stream, "volume") if known else None,
                        "unit": STREAM_UNITS[stream],
                        "reported": known,
                        "null_semantics": _stream_value(row, stream, "null_semantics"),
                        "source_available_on": source_available_on,
                    }
                )
        for horizon in HORIZONS:
            complete = len(producing) >= horizon
            selected = producing[:horizon]
            horizon_end = (
                selected[-1]["production_month"]
                if complete
                else (months[-1]["production_month"] if months else None)
            )
            range_rows = [
                row
                for row in months
                if first_month is not None
                and horizon_end is not None
                and first_month <= row["production_month"] <= horizon_end
            ]
            withheld = any(_has_withheld(row) for row in range_rows)
            withheld_by_horizon[horizon] = withheld
            reconstructed[horizon] = (
                selected[-1]["production_month"] + timedelta(days=source_lag_days)
                if complete
                else None
            )
            strict[horizon] = (
                max(row["source_vintage"] for row in selected) if complete else None
            )
            for stream in STREAMS:
                status = "complete"
                if withheld:
                    status = "withheld"
                elif not complete:
                    status = "incomplete"
                elif intermittent:
                    status = "intermittent"
                elif any(not _stream_is_known(row, stream) for row in selected):
                    status = "missing_stream_observation"
                value = (
                    sum(
                        (Decimal(str(_stream_value(row, stream, "volume"))) for row in selected),
                        Decimal("0"),
                    )
                    if status == "complete"
                    else None
                )
                labels.append(
                    {
                        "row_key": f"{api10}|{horizon:02d}|{stream}",
                        "api10": api10,
                        "first_production_month": first_month,
                        "horizon_months": horizon,
                        "stream": stream,
                        "label_value": value,
                        "unit": STREAM_UNITS[stream],
                        "label_status": status,
                        "label_completed_on": reconstructed[horizon],
                        "label_source_available_on": strict[horizon],
                    }
                )
        states[api10] = WellLabelState(
            api10=api10,
            first_production_month=first_month,
            reconstructed_completeness=reconstructed,
            strict_completeness=strict,
            withheld_by_horizon=withheld_by_horizon,
        )
    return LabelMaterialization(labels=tuple(labels), curves=tuple(curves), states=states)


def _load_feature_matrix(
    artifact_uri: Path | str, coverage_uri: Path | str
) -> tuple[pl.DataFrame, Mapping[str, object], str, str]:
    artifact = Path(artifact_uri)
    coverage_path = Path(coverage_uri)
    artifact_hash = file_sha256(artifact)
    if artifact.parent.name != f"sha256={artifact_hash}":
        raise ModelDatasetError("feature matrix path does not match its content hash")
    coverage_bytes = coverage_path.read_bytes()
    coverage_hash = sha256_hex(coverage_bytes)
    coverage = json.loads(coverage_bytes)
    if coverage.get("artifact_sha256") != artifact_hash:
        raise ModelDatasetError("feature coverage points at a different matrix artifact")
    frame = pl.read_parquet(artifact)
    required = {
        "api10",
        "feature_version",
        "feature_set_hash",
        "as_of_vintage",
        "anchor",
        "derivation_id",
        "geology.formation_group",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ModelDatasetError(f"feature matrix lacks columns {sorted(missing)}")
    if frame.is_empty():
        raise ModelDatasetError("feature matrix is empty")
    if frame["api10"].n_unique() != frame.height:
        raise ModelDatasetError("feature matrix contains duplicate API-10 rows")
    return frame.sort("api10"), coverage, artifact_hash, coverage_hash


def _single_text(frame: pl.DataFrame, column: str) -> str:
    values = frame[column].drop_nulls().unique().to_list()
    if len(values) != 1:
        raise ModelDatasetError(f"feature matrix must carry one {column}, found {values}")
    return str(values[0])


def _merge_inputs(*groups: Sequence[InputRef]) -> tuple[InputRef, ...]:
    merged: dict[tuple[str, str, str | None], InputRef] = {}
    for ref in (item for group in groups for item in group):
        key = (ref.kind, ref.ref_id, ref.selector)
        current = merged.get(key)
        if current is None or (
            ref.as_of_vintage is not None
            and (current.as_of_vintage is None or ref.as_of_vintage > current.as_of_vintage)
        ):
            merged[key] = ref
    ordered = sorted(merged.values(), key=lambda ref: (ref.kind, ref.ref_id, ref.selector or ""))
    return tuple(ref.model_copy(update={"ord": index}) for index, ref in enumerate(ordered))


def _empty_labels(api10: str) -> Iterator[Mapping[str, object]]:
    for horizon in HORIZONS:
        for stream in STREAMS:
            yield {
                "row_key": f"{api10}|{horizon:02d}|{stream}",
                "api10": api10,
                "first_production_month": None,
                "horizon_months": horizon,
                "stream": stream,
                "label_value": None,
                "unit": STREAM_UNITS[stream],
                "label_status": "no_production",
                "label_completed_on": None,
                "label_source_available_on": None,
            }


def _context_by_api(rows: Sequence[Mapping[str, object]]) -> Mapping[str, Mapping[str, object]]:
    result: dict[str, Mapping[str, object]] = {}
    for row in rows:
        api10 = str(row["api10"])
        if api10 in result:
            raise ModelDatasetError(f"model context contains duplicate row for {api10}")
        result[api10] = row
    return result


def _rejection(
    api10: str, reason: str, scope: str, detail: str | None = None
) -> Mapping[str, object]:
    return {
        "row_key": f"{api10}|{scope}|{reason}",
        "api10": api10,
        "scope": scope,
        "reason": reason,
        "detail": detail,
    }


def _feature_context(
    matrix_row: Mapping[str, object], context: Mapping[str, object] | None
) -> Mapping[str, object]:
    return {
        "anchor": matrix_row["anchor"],
        "formation_group": matrix_row["geology.formation_group"],
        "basin": context["basin"] if context else None,
        "area": context["area"] if context else None,
        "lateral_length_ft": context["lateral_length_ft"] if context else None,
        "lateral_length_bucket": lateral_length_bucket(
            context["lateral_length_ft"] if context else None
        ),
    }


def _label_frame(rows: Sequence[Mapping[str, object]], derivation: str) -> pl.DataFrame:
    frame = pl.from_dicts(rows)
    return frame.with_columns(
        pl.col("horizon_months").cast(pl.Int16),
        pl.col("label_value").cast(pl.Decimal(18, 3)),
        pl.col("lateral_length_ft").cast(pl.Float64),
        pl.lit(derivation).alias("dataset_derivation_id"),
    ).sort("row_key")


def _curve_frame(rows: Sequence[Mapping[str, object]], derivation: str) -> pl.DataFrame:
    if rows:
        frame = pl.from_dicts(rows)
    else:
        frame = pl.DataFrame(
            schema={
                "row_key": pl.String,
                "api10": pl.String,
                "producing_month_index": pl.Int16,
                "production_month": pl.Date,
                "stream": pl.String,
                "volume": pl.Decimal(18, 3),
                "unit": pl.String,
                "reported": pl.Boolean,
                "null_semantics": pl.String,
                "source_available_on": pl.Date,
                "anchor": pl.Date,
                "formation_group": pl.String,
                "basin": pl.String,
                "area": pl.String,
                "lateral_length_ft": pl.Float64,
                "lateral_length_bucket": pl.String,
                "feature_version": pl.String,
                "feature_set_hash": pl.String,
                "eval_vintage": pl.Date,
                "first_production_month": pl.Date,
                "feature_derivation_id": pl.String,
            }
        )
    return frame.with_columns(
        pl.col("producing_month_index").cast(pl.Int16),
        pl.col("volume").cast(pl.Decimal(18, 3)),
        pl.col("lateral_length_ft").cast(pl.Float64),
        pl.lit(derivation).alias("dataset_derivation_id"),
    ).sort("row_key")


def _rejection_frame(rows: Sequence[Mapping[str, object]]) -> pl.DataFrame:
    schema = {
        "row_key": pl.String,
        "api10": pl.String,
        "scope": pl.String,
        "reason": pl.String,
        "detail": pl.String,
    }
    return pl.DataFrame(rows, schema=schema, orient="row").sort("row_key")


def _persist_primary(
    frame: pl.DataFrame,
    *,
    root: Path,
    basin: str,
    eval_vintage: date,
    feature_version: str,
) -> tuple[str, str]:
    partition = (
        root
        / "model_ready_labels"
        / f"basin={basin}"
        / f"eval_vintage={eval_vintage.isoformat()}"
        / f"feature_version={feature_version}"
    )
    partition.mkdir(parents=True, exist_ok=True)
    pending = partition / f".pending-{uuid4().hex}.parquet"
    try:
        written = write_partition([frame], pending, sort_order="row_key")
        final = partition / f"sha256={written.sha256}" / PARTITION_FILENAME
        conflicts = [
            path
            for path in partition.glob(f"sha256=*/{PARTITION_FILENAME}")
            if path != final
        ]
        if conflicts:
            raise ImmutableModelArtifactError(
                f"{basin}/{eval_vintage}/{feature_version} already resolves to "
                f"{conflicts[0].parent.name}"
            )
        final.parent.mkdir(parents=True, exist_ok=True)
        if final.exists():
            if file_sha256(final) != written.sha256:
                raise ImmutableModelArtifactError(f"stored artifact {final} failed its address")
            pending.unlink()
        else:
            os.replace(pending, final)
        return str(final), written.sha256
    finally:
        pending.unlink(missing_ok=True)


def _persist_frame_sidecar(frame: pl.DataFrame, destination: Path) -> str:
    pending = destination.with_name(f".pending-{uuid4().hex}.parquet")
    try:
        written = write_partition([frame], pending, sort_order="row_key")
        if destination.exists():
            if file_sha256(destination) != written.sha256:
                raise ImmutableModelArtifactError(f"stored sidecar {destination} changed on replay")
            pending.unlink()
        else:
            os.replace(pending, destination)
        return written.sha256
    finally:
        pending.unlink(missing_ok=True)


def _persist_json(payload: bytes, destination: Path) -> str:
    digest = sha256_hex(payload)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.read_bytes() != payload:
            raise ImmutableModelArtifactError(
                f"stored JSON artifact {destination} changed on replay"
            )
        return digest
    pending = destination.with_name(f".pending-{uuid4().hex}.json")
    try:
        pending.write_bytes(payload)
        os.replace(pending, destination)
    finally:
        pending.unlink(missing_ok=True)
    return digest


def _persist_splits(root: Path, splits: Sequence[SplitObject]) -> tuple[PersistedSplit, ...]:
    persisted: list[PersistedSplit] = []
    for split in sorted(splits, key=lambda item: (item.origin, item.horizon_months)):
        payload = canonical_json(split.model_dump(mode="json"))
        destination = (
            root
            / "splits"
            / f"basin={split.basin}"
            / f"origin={split.origin.isoformat()}"
            / f"horizon={split.horizon_months}"
            / f"split_id={split.split_id}"
            / "split.json"
        )
        persisted.append(
            PersistedSplit(
                split=split,
                uri=str(destination),
                sha256=_persist_json(payload, destination),
            )
        )
    return tuple(persisted)


def _ratio(numerator: int, denominator: int) -> str:
    if not denominator:
        return "0.000000"
    return f"{Decimal(numerator) / Decimal(denominator):.6f}"


def _coverage_document(
    *,
    derivation: str,
    eval_vintage: date,
    feature_version: str,
    feature_artifact_sha256: str,
    feature_coverage_sha256: str,
    artifact_sha256: str,
    curves_sha256: str,
    rejections_sha256: str,
    label_rows: Sequence[Mapping[str, object]],
    matrix_rows: Sequence[Mapping[str, object]],
    rejections: Sequence[Mapping[str, object]],
    persisted_splits: Sequence[PersistedSplit],
) -> Mapping[str, object]:
    status_counts: dict[str, Counter[str]] = defaultdict(Counter)
    matrix_by_api = {str(row["api10"]): row for row in matrix_rows}
    for row in label_rows:
        key = f"{row['stream']}.cum{row['horizon_months']}"
        status_counts[key][str(row["label_status"])] += 1
    rejection_counts = Counter(str(row["reason"]) for row in rejections)
    cohorts: dict[str, Counter[str]] = defaultdict(Counter)
    for row in matrix_rows:
        anchor = row["anchor"]
        cohort = str(anchor.year) if isinstance(anchor, date) else "missing"
        cohorts[cohort]["subjects"] += 1
    for row in rejections:
        if row["reason"] != "withheld_or_confidential":
            continue
        matrix = matrix_by_api[str(row["api10"])]
        anchor = matrix["anchor"]
        cohort = str(anchor.year) if isinstance(anchor, date) else "missing"
        cohorts[cohort]["withheld"] += 1
    return {
        "schema_version": COVERAGE_SCHEMA_VERSION,
        "dataset": MODEL_DATASET,
        "derivation_id": derivation,
        "eval_vintage": eval_vintage,
        "feature_version": feature_version,
        "feature_inputs": {
            "artifact_sha256": feature_artifact_sha256,
            "coverage_sha256": feature_coverage_sha256,
        },
        "artifacts": {
            "labels_sha256": artifact_sha256,
            "curves_sha256": curves_sha256,
            "rejections_sha256": rejections_sha256,
        },
        "counts": {
            "subjects": len(matrix_rows),
            "label_rows": len(label_rows),
            "rejection_rows": len(rejections),
            "rejections_by_reason": dict(sorted(rejection_counts.items())),
            "labels": {
                key: dict(sorted(counts.items()))
                for key, counts in sorted(status_counts.items())
            },
        },
        "withheld_share_by_completion_cohort": {
            cohort: {
                "subjects": counts["subjects"],
                "withheld": counts["withheld"],
                "share": _ratio(counts["withheld"], counts["subjects"]),
            }
            for cohort, counts in sorted(cohorts.items())
        },
        "label_policy": {
            "grain": "api10_stream_horizon",
            "streams": list(STREAMS),
            "horizons": list(HORIZONS),
            "producing_month": (
                "reported_zero_and_days_positive_or_volume_positive; no_report, withheld, "
                "and zero-day zero-volume months do not advance"
            ),
            "intermittent": (
                "twelfth producing month more than 16 calendar months after first; applied "
                "to cum12 and cum24 exactly as SB-02 section 2.2 defines the well class"
            ),
            "withheld": "excluded_from_all_split_partitions_and_counted",
            "censored": "retained_in_features_and_curves_but_label_value_is_null",
        },
        "retrospective_vintage": {
            "split_basis": "source_reconstructed_not_glasswell_history",
            "production_source_lag_days": PRODUCTION_SOURCE_LAG_DAYS,
            "strict_label_availability_field": "label_source_available_on",
            "reconstructed_label_availability_field": "label_completed_on",
        },
        "control_features": {
            "formation_group": "feature matrix value",
            "area": "county_code_at_permit",
            "lateral_length_ft": "sum of canonical geodesic lateral segments",
            "lateral_length_bucket": [
                "lt_8000",
                "8000_to_lt_10000",
                "10000_to_10500",
                "gt_10500",
            ],
            "first_production_month": "split and peer-window metadata, never an ML feature",
        },
        "splits": [
            {
                "split_id": item.split.split_id,
                "origin": item.split.origin,
                "horizon_months": item.split.horizon_months,
                "sha256": item.sha256,
                "streams": list(STREAMS),
            }
            for item in persisted_splits
        ],
    }


def _lockfile_sha256(connection: psycopg.Connection, env_id: str) -> str | None:
    with connection.cursor() as cursor:
        cursor.execute(
            "select lockfile_sha256 from lineage.environments where env_id = %s", (env_id,)
        )
        row = cursor.fetchone()
    if row is None:
        raise ModelDatasetError(f"environment {env_id!r} is not registered")
    return row[0]


def build_model_dataset(
    connection: psycopg.Connection,
    *,
    feature_matrix_uri: Path | str,
    feature_coverage_uri: Path | str,
    eval_vintage: date,
    environment: DeriveEnvironment,
    basin: str = "williston",
    origins: Sequence[date] = DEFAULT_ORIGINS,
    vintage_basis: VintageBasis = "source_reconstructed_not_glasswell_history",
    root: Path | str | None = None,
    clock: Clock | None = None,
) -> ModelDatasetBuild:
    """Build and register the complete model-ready artifact family."""
    if vintage_basis not in {
        "strict_manifest_knowledge",
        "source_reconstructed_not_glasswell_history",
    }:
        raise ValueError(f"unsupported vintage basis {vintage_basis!r}")
    if any(origin.day != 1 for origin in origins):
        raise ValueError("split origins must be first-of-month dates")
    matrix, matrix_coverage, matrix_hash, matrix_coverage_hash = _load_feature_matrix(
        feature_matrix_uri, feature_coverage_uri
    )
    feature_version = _single_text(matrix, "feature_version")
    feature_set_hash = _single_text(matrix, "feature_set_hash")
    matrix_derivation = _single_text(matrix, "derivation_id")
    matrix_as_of_values = matrix["as_of_vintage"].unique().to_list()
    if matrix_as_of_values != [eval_vintage]:
        raise ModelDatasetError(
            f"feature matrix vintage {matrix_as_of_values} does not equal eval {eval_vintage}"
        )
    api10s = [str(value) for value in matrix["api10"].to_list()]
    context_snapshot = read_model_context_snapshot(
        connection, api10s=api10s, basin=basin, as_of=eval_vintage
    )
    contexts = _context_by_api(context_snapshot.rows)
    matrix_rows = matrix.to_dicts()

    with read_model_production_snapshot(
        connection,
        api10s=api10s,
        source_id=PRODUCTION_SOURCE_ID,
        as_of=eval_vintage,
    ) as (production_rows, production_inputs):
        materialized = materialize_labels(production_rows)

    matrix_input = InputRef(
        kind="derivation",
        ref_id=matrix_derivation,
        selector=f"sha256:{matrix_hash}",
        as_of_vintage=eval_vintage,
    )
    coverage_input = InputRef(
        kind="external",
        ref_id="features.matrix_coverage",
        selector=f"sha256:{matrix_coverage_hash}",
        as_of_vintage=eval_vintage,
        role="validator",
    )
    inputs = _merge_inputs(
        (matrix_input, coverage_input), context_snapshot.inputs, production_inputs
    )

    conflict_api10s = {
        str(item["api10"]) for item in matrix_coverage.get("conflicts", [])
    }
    label_by_api: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in materialized.labels:
        label_by_api[str(row["api10"])].append(row)
    curve_by_api: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in materialized.curves:
        curve_by_api[str(row["api10"])].append(row)

    labels: list[Mapping[str, object]] = []
    curves: list[Mapping[str, object]] = []
    rejections: list[Mapping[str, object]] = []
    split_exclusions: set[str] = set()
    matrix_by_api = {str(row["api10"]): row for row in matrix_rows}
    for api10 in api10s:
        matrix_row = matrix_by_api[api10]
        context = contexts.get(api10)
        feature_context = _feature_context(matrix_row, context)
        state = materialized.states.get(api10)
        api_labels = label_by_api.get(api10, list(_empty_labels(api10)))
        if context is None:
            rejections.append(_rejection(api10, "missing_db_context", "split"))
            split_exclusions.add(api10)
        elif context["completion_date"] != matrix_row["anchor"]:
            raise ModelDatasetError(f"{api10} matrix anchor differs from canonical context")
        if state is None or state.first_production_month is None:
            rejections.append(_rejection(api10, "missing_first_production", "split"))
            split_exclusions.add(api10)
        if (
            context is not None
            and state is not None
            and state.first_production_month is not None
            and context["completion_date"] > state.first_production_month
        ):
            rejections.append(
                _rejection(api10, "completion_after_first_production", "split")
            )
            split_exclusions.add(api10)
        confidential = bool(context and context["confidential_flag"])
        withheld = bool(
            state and any(state.withheld_by_horizon.get(horizon, False) for horizon in HORIZONS)
        )
        if confidential or withheld:
            rejections.append(
                _rejection(api10, "withheld_or_confidential", "all_partitions")
            )
            split_exclusions.add(api10)
        if api10 in conflict_api10s:
            rejections.append(_rejection(api10, "formation_conflict", "typecurve_control"))
        elif feature_context["formation_group"] is None:
            rejections.append(_rejection(api10, "missing_formation", "typecurve_control"))
        if feature_context["area"] is None:
            rejections.append(_rejection(api10, "missing_area", "typecurve_control"))
        if feature_context["lateral_length_ft"] is None:
            rejections.append(_rejection(api10, "missing_lateral_length", "typecurve_control"))
        if context is not None and int(context["surface_count"]) > 1:
            rejections.append(
                _rejection(
                    api10,
                    "ambiguous_surface_geometry",
                    "pad_group",
                    detail=str(context["surface_count"]),
                )
            )
        for label in api_labels:
            resolved = dict(label)
            if confidential and resolved["label_status"] == "complete":
                resolved["label_status"] = "withheld"
                resolved["label_value"] = None
            labels.append(
                {
                    **resolved,
                    **feature_context,
                    "feature_version": feature_version,
                    "feature_set_hash": feature_set_hash,
                    "eval_vintage": eval_vintage,
                    "feature_derivation_id": matrix_derivation,
                }
            )
        for curve in curve_by_api.get(api10, []):
            curves.append(
                {
                    **curve,
                    **feature_context,
                    "feature_version": feature_version,
                    "feature_set_hash": feature_set_hash,
                    "eval_vintage": eval_vintage,
                    "first_production_month": state.first_production_month if state else None,
                    "feature_derivation_id": matrix_derivation,
                }
            )

    params = {
        "basin": basin,
        "eval_vintage": eval_vintage,
        "feature_version": feature_version,
        "feature_set_hash": feature_set_hash,
        "feature_artifact_sha256": matrix_hash,
        "feature_coverage_sha256": matrix_coverage_hash,
        "origins": sorted(origins),
        "streams": STREAMS,
        "horizons": HORIZONS,
        "horizon_calendar_guard_months": HORIZON_CALENDAR_GUARD_MONTHS,
        "production_source_id": PRODUCTION_SOURCE_ID,
        "production_source_lag_days": PRODUCTION_SOURCE_LAG_DAYS,
        "vintage_basis": vintage_basis,
        "length_buckets_ft": [8000, 10000, 10500],
    }
    output_spec = OutputSpec(
        store="parquet",
        dataset=MODEL_DATASET,
        partition={
            "basin": basin,
            "eval_vintage": eval_vintage.isoformat(),
            "feature_version": feature_version,
        },
        schema_version=MODEL_SCHEMA_VERSION,
    )
    planned_id = derivation_id(
        operation="features.build",
        inputs=inputs,
        params=params,
        code_version=environment.code_version,
        env_id=environment.env_id,
        rule_ids=(),
        output=output_spec,
    )

    label_frame = _label_frame(labels, planned_id)
    curve_frame = _curve_frame(curves, planned_id)
    rejection_frame = _rejection_frame(rejections)
    model_root = resolve_model_root(root)
    artifact_uri, artifact_hash = _persist_primary(
        label_frame,
        root=model_root,
        basin=basin,
        eval_vintage=eval_vintage,
        feature_version=feature_version,
    )
    artifact_dir = Path(artifact_uri).parent
    curves_uri = artifact_dir / "curves.parquet"
    curves_hash = _persist_frame_sidecar(curve_frame, curves_uri)
    rejections_uri = artifact_dir / "rejections.parquet"
    rejections_hash = _persist_frame_sidecar(rejection_frame, rejections_uri)

    split_objects: list[SplitObject] = []
    for horizon in HORIZONS:
        timelines: list[WellTimeline] = []
        for api10 in api10s:
            if api10 in split_exclusions:
                continue
            state = materialized.states[api10]
            context = contexts[api10]
            completeness = (
                state.strict_completeness[horizon]
                if vintage_basis == "strict_manifest_knowledge"
                else state.reconstructed_completeness[horizon]
            )
            timelines.append(
                WellTimeline(
                    api10=api10,
                    first_production_month=state.first_production_month,
                    completion_date=context["completion_date"],
                    label_completeness_date=completeness,
                    surface_x_m=(
                        float(context["surface_x_m"])
                        if int(context["surface_count"]) == 1
                        else None
                    ),
                    surface_y_m=(
                        float(context["surface_y_m"])
                        if int(context["surface_count"]) == 1
                        else None
                    ),
                )
            )
        for origin in sorted(set(origins)):
            split_objects.append(
                build_temporal_split(
                    timelines,
                    basin=basin,
                    boundary=origin,
                    horizon_months=horizon,
                    reporting_lags={PRODUCTION_SOURCE_ID: PRODUCTION_SOURCE_LAG_DAYS},
                )
            )
    persisted_splits = _persist_splits(model_root, split_objects)

    coverage = _coverage_document(
        derivation=planned_id,
        eval_vintage=eval_vintage,
        feature_version=feature_version,
        feature_artifact_sha256=matrix_hash,
        feature_coverage_sha256=matrix_coverage_hash,
        artifact_sha256=artifact_hash,
        curves_sha256=curves_hash,
        rejections_sha256=rejections_hash,
        label_rows=labels,
        matrix_rows=matrix_rows,
        rejections=rejections,
        persisted_splits=persisted_splits,
    )
    coverage_uri = artifact_dir / "coverage.json"
    coverage_hash = _persist_json(canonical_json(coverage), coverage_uri)
    lockfile_hash = _lockfile_sha256(connection, environment.env_id)
    recipe_id = build_recipe(
        connection,
        "features.build",
        code_version=environment.code_version,
        lockfile_sha256=lockfile_hash,
        entry_point="glasswell.modeling.model_dataset:build_model_dataset",
        params=params,
        input_refs=inputs,
        determinism_class="D1",
        output={
            "dataset": MODEL_DATASET,
            "partition": output_spec.partition,
            "sha256": artifact_hash,
            "rows": label_frame.height,
            "schema_version": MODEL_SCHEMA_VERSION,
            "curves": {
                "filename": curves_uri.name,
                "sha256": curves_hash,
                "rows": curve_frame.height,
                "schema_version": CURVE_SCHEMA_VERSION,
            },
            "coverage": {"filename": coverage_uri.name, "sha256": coverage_hash},
            "rejections": {
                "filename": rejections_uri.name,
                "sha256": rejections_hash,
                "rows": rejection_frame.height,
                "schema_version": REJECTION_SCHEMA_VERSION,
            },
            "splits": [
                {
                    "split_id": item.split.split_id,
                    "sha256": item.sha256,
                    "origin": item.split.origin,
                    "horizon_months": item.split.horizon_months,
                }
                for item in persisted_splits
            ],
            "determinism_class": "D1",
        },
    )
    resolved_environment = environment.model_copy(update={"recipe_id": recipe_id})
    with lineage_session(
        recorder=PostgresRecorder(connection), environment=resolved_environment, clock=clock
    ), derive(
        "features.build",
        output=output_spec.model_copy(update={"locator": artifact_uri}),
        params=params,
        inputs=inputs,
        determinism_class="D1",
        ttl_class="permanent",
    ) as context:
        context.set_output_hash(artifact_hash)
        context.set_rows(label_frame.height)
    if context.derivation_id != planned_id:
        raise ModelDatasetError(
            f"planned derivation {planned_id} became {context.derivation_id} during capture"
        )
    return ModelDatasetBuild(
        derivation_id=context.derivation_id,
        recipe_id=recipe_id,
        artifact_uri=artifact_uri,
        artifact_sha256=artifact_hash,
        curves_uri=str(curves_uri),
        curves_sha256=curves_hash,
        coverage_uri=str(coverage_uri),
        coverage_sha256=coverage_hash,
        rejections_uri=str(rejections_uri),
        rejections_sha256=rejections_hash,
        eval_vintage=eval_vintage,
        feature_version=feature_version,
        rows=label_frame.height,
        curve_rows=curve_frame.height,
        rejection_rows=rejection_frame.height,
        splits=persisted_splits,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the P3 model-ready artifact family.")
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--feature-matrix", required=True)
    parser.add_argument("--feature-coverage", required=True)
    parser.add_argument("--eval-vintage", required=True)
    parser.add_argument("--basin", default="williston")
    parser.add_argument("--origin", action="append", default=[])
    parser.add_argument(
        "--vintage-basis",
        choices=("strict_manifest_knowledge", "source_reconstructed_not_glasswell_history"),
        default="source_reconstructed_not_glasswell_history",
    )
    parser.add_argument("--root", default=None)
    parser.add_argument("--env-id", default=None)
    parser.add_argument("--code-version", default=None)
    arguments = parser.parse_args(argv)
    origins = tuple(date.fromisoformat(value) for value in arguments.origin) or DEFAULT_ORIGINS
    with psycopg.connect(arguments.dsn) as connection:
        environment = resolve_environment(
            connection, env_id=arguments.env_id, code_version=arguments.code_version
        )
        built = build_model_dataset(
            connection,
            feature_matrix_uri=arguments.feature_matrix,
            feature_coverage_uri=arguments.feature_coverage,
            eval_vintage=date.fromisoformat(arguments.eval_vintage),
            environment=environment,
            basin=arguments.basin,
            origins=origins,
            vintage_basis=arguments.vintage_basis,
            root=arguments.root,
        )
        connection.commit()
    print(json.dumps(built.to_dict(), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
