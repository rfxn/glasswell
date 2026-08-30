"""A CONTROL_SCHEMA-shaped control artifact and the publication that accepts it.

Building a real control in the contract tier is not possible: `seed_model_population` needs
sixty-odd wells and `TC_MIN_N` is twenty, while the contract fixture seeds eight, and adding
sixty would move `list_wells` paging, the status-summary counts and the neighbour tests. So
this writes a synthetic artifact in the real schema at the real partition layout and registers
it exactly as a real build would, which is what the served routes are pinned against.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import polars as pl
import psycopg
from psycopg.types.json import Jsonb

from glasswell.lineage.capture import derive, lineage_session
from glasswell.lineage.models import InputRef, OutputSpec
from glasswell.lineage.serialization import canonical_json, sha256_hex
from glasswell.lineage.store import PostgresRecorder
from glasswell.modeling.model_dataset import (
    MODEL_DATASET,
    MODEL_DATASET_VERSION,
    STREAM_UNITS,
    STREAMS,
)
from glasswell.modeling.type_curve import (
    CONTROL_DATASET,
    CONTROL_SCHEMA,
    CONTROL_VERSION,
    NORMALIZATIONS,
    QUANTILE_CONVENTION,
    TC_MIN_N,
    TC_RUNG1_SHARE_MIN,
    TC_UNAVAILABLE_SHARE_MAX,
    VINTAGE_WINDOW_MONTHS,
)
from glasswell.staging.duck import PARTITION_FILENAME, file_sha256, write_partition
from tests.support.fakes import FixedClock
from tests.support.seed import FIXTURE_ENV

FEATURE_VERSION = "fv2.0"
FEATURE_DATASET = "features.well_features"
EVAL_VINTAGE = date(2026, 8, 28)
VINTAGE_BASIS = "source_reconstructed_not_glasswell_history"
RECEIPT_SCHEMA = "p3-publication-receipt/1"


@dataclass(frozen=True, slots=True)
class ControlSubject:
    api10: str
    origin: date
    horizon_months: int
    fallback_level: str = "formation_area_length"
    formation_group: str | None = "bakken"
    area: str | None = "025"
    lateral_length_bucket: str | None = "8000_to_lt_10000"
    lateral_length_ft: float | None = 9500.0
    reasons: tuple[str, ...] = ()
    peer_count: int = 34
    streams: tuple[str, ...] = STREAMS
    base: float = 1200.0


@dataclass(frozen=True, slots=True)
class ControlArtifact:
    root: Path
    path: Path
    sha256: str
    coverage_path: Path
    coverage_sha256: str
    rows: int
    basin: str
    eval_vintage: date
    feature_version: str
    vintage_basis: str
    split_set_id: str
    splits: tuple[dict[str, object], ...]
    subjects: tuple[ControlSubject, ...]
    coverage: dict[str, object] = field(default_factory=dict)

    @property
    def partition(self) -> dict[str, str]:
        return {
            "basin": self.basin,
            "control_version": CONTROL_VERSION,
            "dataset_version": MODEL_DATASET_VERSION,
            "eval_vintage": self.eval_vintage.isoformat(),
            "feature_version": self.feature_version,
            "split_set_id": self.split_set_id,
            "vintage_basis": self.vintage_basis,
        }


def split_id_for(origin: date, horizon_months: int) -> str:
    return f"spl_{origin.strftime('%Y%m%d')}_{horizon_months:02d}"


def split_sha256_for(origin: date, horizon_months: int) -> str:
    return sha256_hex(split_id_for(origin, horizon_months).encode("utf-8"))


def write_control_artifact(
    root: Path,
    *,
    subjects: Sequence[ControlSubject],
    basin: str = "williston",
    eval_vintage: date = EVAL_VINTAGE,
    feature_version: str = FEATURE_VERSION,
    vintage_basis: str = VINTAGE_BASIS,
    control_derivation_id: str = "drv_fixture_control",
    dataset_derivation_id: str = "drv_fixture_labels",
) -> ControlArtifact:
    """Write one control partition in the real schema at the real layout, plus its coverage."""
    pairs = sorted({(subject.origin, subject.horizon_months) for subject in subjects})
    split_set_id = "sset_" + sha256_hex(
        canonical_json([[origin.isoformat(), horizon] for origin, horizon in pairs])
    )[:16]
    rows = list(
        _rows(
            subjects,
            eval_vintage=eval_vintage,
            feature_version=feature_version,
            split_set_id=split_set_id,
            control_derivation_id=control_derivation_id,
            dataset_derivation_id=dataset_derivation_id,
        )
    )
    frame = pl.from_dicts(rows, schema=CONTROL_SCHEMA)
    partition = (
        Path(root)
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
    pending = partition / ".pending.parquet"
    written = write_partition([frame], pending, sort_order="row_key", memory_limit="512MB")
    final = partition / f"sha256={written.sha256}" / PARTITION_FILENAME
    final.parent.mkdir(parents=True, exist_ok=True)
    pending.replace(final)

    splits = tuple(
        {
            "origin": origin.isoformat(),
            "horizon_months": horizon,
            "split_id": split_id_for(origin, horizon),
            "sha256": split_sha256_for(origin, horizon),
        }
        for origin, horizon in pairs
    )
    coverage = _coverage(
        subjects,
        artifact_sha256=written.sha256,
        rows=written.rows,
        feature_version=feature_version,
        split_set_id=split_set_id,
        eval_vintage=eval_vintage,
        vintage_basis=vintage_basis,
        control_derivation_id=control_derivation_id,
    )
    coverage_path = final.parent / "coverage.json"
    coverage_path.write_bytes(canonical_json(coverage))
    return ControlArtifact(
        root=Path(root),
        path=final,
        sha256=written.sha256,
        coverage_path=coverage_path,
        coverage_sha256=file_sha256(coverage_path),
        rows=written.rows,
        basin=basin,
        eval_vintage=eval_vintage,
        feature_version=feature_version,
        vintage_basis=vintage_basis,
        split_set_id=split_set_id,
        splits=splits,
        subjects=tuple(subjects),
        coverage=coverage,
    )


def register_pinned_control(
    connection: psycopg.Connection,
    artifact: ControlArtifact,
    *,
    manifest_id: str,
    code_version: str = "git:0000test",
) -> str:
    """Mint the three derivations the receipt names, then insert the receipt itself."""
    feature_id = _derive(
        connection,
        operation="features.build",
        dataset=FEATURE_DATASET,
        partition={"basin": artifact.basin, "feature_version": artifact.feature_version},
        locator=str(artifact.root / "well_features"),
        manifest_id=manifest_id,
        sha256="a" * 64,
        rows=8,
    )
    labels_id = _derive(
        connection,
        operation="features.build",
        dataset=MODEL_DATASET,
        partition={
            "basin": artifact.basin,
            "dataset_version": MODEL_DATASET_VERSION,
            "eval_vintage": artifact.eval_vintage.isoformat(),
        },
        locator=str(artifact.root / "model_ready_labels"),
        manifest_id=manifest_id,
        sha256="b" * 64,
        rows=64,
    )
    control_id = _derive(
        connection,
        operation="typecurve.build",
        dataset=CONTROL_DATASET,
        partition=artifact.partition,
        locator=str(artifact.path),
        manifest_id=manifest_id,
        sha256=artifact.sha256,
        rows=artifact.rows,
    )
    document = receipt_document(
        artifact,
        feature_derivation_id=feature_id,
        model_dataset_derivation_id=labels_id,
        control_derivation_id=control_id,
        code_version=code_version,
    )
    return insert_receipt(connection, document)


def receipt_document(
    artifact: ControlArtifact,
    *,
    feature_derivation_id: str,
    model_dataset_derivation_id: str,
    control_derivation_id: str,
    code_version: str = "git:0000test",
    environment_id: str | None = None,
) -> dict[str, object]:
    from tests.conftest import FIXTURE_ENV_ID

    return {
        "receipt_schema": RECEIPT_SCHEMA,
        "status": "published",
        "basin": artifact.basin,
        "eval_vintage": artifact.eval_vintage.isoformat(),
        "vintage_basis": artifact.vintage_basis,
        "code_version": code_version,
        "environment_id": environment_id or FIXTURE_ENV_ID,
        "isolation": "repeatable_read",
        "build_runs": 2,
        "byte_identical": True,
        "baseline": {
            "document_sha256": "c" * 64,
            "resident_recipe_id": "rcp_fixture",
            "migration_042_sha256": "d" * 64,
            "feature_set_hash": "e" * 64,
            "split_set_id": artifact.split_set_id,
        },
        "versions": {
            "feature": artifact.feature_version,
            "model_dataset": MODEL_DATASET_VERSION,
            "type_curve": CONTROL_VERSION,
        },
        "derivations": {
            "feature": feature_derivation_id,
            "model_dataset": model_dataset_derivation_id,
            "type_curve": control_derivation_id,
        },
        "recipes": {
            "feature": "rcp_fixture_feature",
            "model_dataset": "rcp_fixture_labels",
            "type_curve": "rcp_fixture_control",
        },
        "rows": {
            "feature": 8,
            "labels": 64,
            "curves": 64,
            "rejections": 0,
            "type_curve": artifact.rows,
        },
        "artifact_sha256": {
            "feature": "a" * 64,
            "model_dataset": "b" * 64,
            "type_curve": artifact.sha256,
            "type_curve_coverage": artifact.coverage_sha256,
        },
        "artifact_uri": {
            "feature": str(artifact.root / "well_features"),
            "feature_coverage": str(artifact.root / "well_features_coverage.json"),
            "model_dataset": str(artifact.root / "model_ready_labels"),
            "model_curves": str(artifact.root / "model_ready_curves"),
            "model_coverage": str(artifact.root / "model_coverage.json"),
            "model_rejections": str(artifact.root / "model_rejections"),
            "type_curve": str(artifact.path),
            "type_curve_coverage": str(artifact.coverage_path),
        },
        "environment": {
            "environment_id": environment_id or FIXTURE_ENV_ID,
            "lockfile_sha256": "f" * 64,
            "identity_basis": "deploy_stamp_and_installed_lock",
        },
        "coverage": {
            "feature": {"wells": 8},
            "model_rejections_by_reason": {},
            "pooled_control_unavailable": artifact.coverage["acceptance"][
                "pooled_control_unavailable_share"
            ],
            "split_control_unavailable": [],
            "residual_reason_mentions": artifact.coverage["counts"][
                "control_unavailable_reason_mentions"
            ],
        },
        "splits": [dict(item) for item in artifact.splits],
    }


def insert_receipt(connection: psycopg.Connection, document: dict[str, object]) -> str:
    canonical = canonical_json(document)
    digest = sha256_hex(canonical)
    publication_id = f"p3pub_{digest[:32]}"
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into lineage.p3_publication_receipts"
            " (publication_id, receipt_schema, document_sha256, document, document_canonical,"
            "  basin, eval_vintage, vintage_basis, feature_version, model_dataset_version,"
            "  control_version, split_set_id, code_version, environment_id, lockfile_sha256,"
            "  feature_derivation_id, model_dataset_derivation_id, control_derivation_id)"
            " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
            " on conflict (publication_id) do nothing",
            (
                publication_id,
                document["receipt_schema"],
                digest,
                Jsonb(document),
                canonical.decode("utf-8"),
                document["basin"],
                document["eval_vintage"],
                document["vintage_basis"],
                document["versions"]["feature"],
                document["versions"]["model_dataset"],
                document["versions"]["type_curve"],
                document["baseline"]["split_set_id"],
                document["code_version"],
                document["environment_id"],
                document["environment"]["lockfile_sha256"],
                document["derivations"]["feature"],
                document["derivations"]["model_dataset"],
                document["derivations"]["type_curve"],
            ),
        )
    return publication_id


def _derive(
    connection: psycopg.Connection,
    *,
    operation: str,
    dataset: str,
    partition: dict[str, str],
    locator: str,
    manifest_id: str,
    sha256: str,
    rows: int,
) -> str:
    with (
        lineage_session(
            recorder=PostgresRecorder(connection),
            environment=FIXTURE_ENV,
            clock=FixedClock(),
            correlation_id="run_typecurve_fixture",
        ),
        derive(
            operation,  # type: ignore[arg-type]
            output=OutputSpec(
                store="parquet",
                dataset=dataset,
                partition=partition,
                locator=locator,
                schema_version="1",
            ),
            params={"fixture": dataset},
            inputs=[InputRef(kind="manifest", ref_id=manifest_id, role="primary")],
            determinism_class="D1",
            ttl_class="permanent",
        ) as context,
    ):
        context.set_output_hash(sha256)
        context.set_rows(rows)
    return context.derivation_id


def _rows(
    subjects: Sequence[ControlSubject],
    *,
    eval_vintage: date,
    feature_version: str,
    split_set_id: str,
    control_derivation_id: str,
    dataset_derivation_id: str,
):
    for subject in subjects:
        split_id = split_id_for(subject.origin, subject.horizon_months)
        unavailable = subject.fallback_level == "control_unavailable"
        for stream in subject.streams:
            for normalization in NORMALIZATIONS:
                scale = (
                    (subject.lateral_length_ft or 0) / 1000.0
                    if normalization == "typecurve_per_kft"
                    else 1.0
                )
                cumulative = [0.0, 0.0, 0.0]
                for month_index in range(1, subject.horizon_months + 1):
                    monthly = [
                        subject.base * factor / month_index * (1.0 if scale == 1.0 else scale)
                        for factor in (0.6, 1.0, 1.6)
                    ]
                    cumulative = [
                        prior + value
                        for prior, value in zip(cumulative, monthly, strict=True)
                    ]
                    yield {
                        "row_key": (
                            f"{split_id}|{subject.api10}|{stream}|"
                            f"{normalization}|{month_index:02d}"
                        ),
                        "type_curve_id": f"tc_{split_set_id}",
                        "control_version": CONTROL_VERSION,
                        "dataset_version": MODEL_DATASET_VERSION,
                        "dataset_derivation_id": dataset_derivation_id,
                        "control_derivation_id": control_derivation_id,
                        "feature_version": feature_version,
                        "split_set_id": split_set_id,
                        "split_id": split_id,
                        "split_sha256": split_sha256_for(
                            subject.origin, subject.horizon_months
                        ),
                        "origin": subject.origin,
                        "knowledge_cutoff": subject.origin,
                        "eval_vintage": eval_vintage,
                        "subject_api10": subject.api10,
                        "stream": stream,
                        "unit": STREAM_UNITS[stream],
                        "horizon_months": subject.horizon_months,
                        "month_index": month_index,
                        "normalization": normalization,
                        "fallback_level": subject.fallback_level,
                        "control_unavailable_reasons": (
                            "|".join(sorted(subject.reasons)) or None
                        ),
                        "peer_set_id": None if unavailable else f"peer_{subject.api10}",
                        "peer_count": 0 if unavailable else subject.peer_count,
                        "cumulative_peer_count": 0 if unavailable else subject.peer_count,
                        "status": "control_unavailable" if unavailable else "ok",
                        "cumulative_status": "control_unavailable" if unavailable else "ok",
                        "monthly_p10": None if unavailable else round(monthly[0], 4),
                        "monthly_p50": None if unavailable else round(monthly[1], 4),
                        "monthly_p90": None if unavailable else round(monthly[2], 4),
                        "cumulative_p10": None if unavailable else round(cumulative[0], 4),
                        "cumulative_p50": None if unavailable else round(cumulative[1], 4),
                        "cumulative_p90": None if unavailable else round(cumulative[2], 4),
                        "quantile_convention": QUANTILE_CONVENTION,
                        "formation_group": subject.formation_group,
                        "area": subject.area,
                        "lateral_length_bucket": subject.lateral_length_bucket,
                        "subject_lateral_length_ft": subject.lateral_length_ft,
                    }


def _coverage(
    subjects: Sequence[ControlSubject],
    *,
    artifact_sha256: str,
    rows: int,
    feature_version: str,
    split_set_id: str,
    eval_vintage: date,
    vintage_basis: str,
    control_derivation_id: str,
) -> dict[str, object]:
    by_level: dict[str, int] = {}
    reason_mentions: dict[str, int] = {}
    stream_instances = 0
    for subject in subjects:
        by_level[subject.fallback_level] = by_level.get(subject.fallback_level, 0) + 1
        stream_instances += len(subject.streams)
        for reason in subject.reasons:
            reason_mentions[reason] = reason_mentions.get(reason, 0) + 1
    instances = len(subjects)
    unavailable = by_level.get("control_unavailable", 0)
    rung1 = by_level.get("formation_area_length", 0)
    return {
        "schema_version": "1",
        "dataset": CONTROL_DATASET,
        "control_version": CONTROL_VERSION,
        "dataset_version": MODEL_DATASET_VERSION,
        "type_curve_id": f"tc_{split_set_id}",
        "derivation_id": control_derivation_id,
        "artifact_sha256": artifact_sha256,
        "rows": rows,
        "feature_version": feature_version,
        "split_set_id": split_set_id,
        "eval_vintage": eval_vintage.isoformat(),
        "vintage_basis": vintage_basis,
        "counts": {
            "test_subject_instances": instances,
            "control_unavailable_subject_instances": unavailable,
            "control_unavailable_share": _ratio(unavailable, instances),
            "subject_stream_instances": stream_instances,
            "control_unavailable_subject_stream_instances": unavailable * len(STREAMS),
            "fallback_by_level": dict(sorted(by_level.items())),
            "control_unavailable_reason_mentions": dict(sorted(reason_mentions.items())),
        },
        "acceptance": {
            "scope": "subject_instances_across_identical_persisted_splits",
            "pooled_rung1_share": {
                "observed": _ratio(rung1, instances),
                "minimum": f"{TC_RUNG1_SHARE_MIN:.6f}",
                "status": "pass",
            },
            "pooled_control_unavailable_share": {
                "observed": _ratio(unavailable, instances),
                "maximum": f"{TC_UNAVAILABLE_SHARE_MAX:.6f}",
                "status": "pass",
            },
        },
        "plausibility_flags": [],
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
            "quantile_convention": QUANTILE_CONVENTION,
        },
    }


def _ratio(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "0.000000"
    return f"{numerator / denominator:.6f}"


def load_coverage(path: Path) -> dict[str, object]:
    return json.loads(Path(path).read_bytes())
