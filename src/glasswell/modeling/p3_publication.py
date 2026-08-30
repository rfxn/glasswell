"""Fail-closed publication gate for the repaired P3 context replay."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from importlib.resources import files
from pathlib import Path
from typing import Any

import psycopg
from psycopg.pq import TransactionStatus
from psycopg.types.json import Jsonb

from glasswell.db.migrate import discover_migrations
from glasswell.ingest.base import CODE_VERSION_ENV, LOCKFILE_SHA256_ENV
from glasswell.lineage.audit import emit
from glasswell.lineage.models import DeriveEnvironment
from glasswell.lineage.serialization import canonical_json, sha256_hex
from glasswell.modeling.feature_matrix import FeatureMatrixBuild, build_feature_matrix
from glasswell.modeling.model_dataset import (
    DEFAULT_ORIGINS,
    MODEL_DATASET_VERSION,
    ModelDatasetBuild,
    build_model_dataset,
)
from glasswell.modeling.split import SplitObject
from glasswell.modeling.type_curve import (
    CONTROL_VERSION,
    TypeCurveBuild,
    build_type_curve_control,
)
from glasswell.staging.duck import file_sha256

BASELINE_RESOURCE = "p3_context_baseline.json"
BASELINE_SHA256 = "9ea487f44460eb46a59958c0cc860834233acb765afc9c57d8c719a33c8030a0"
FEATURE_VERSION = "fv2.0"
VINTAGE_BASIS = "source_reconstructed_not_glasswell_history"
UNAVAILABLE_SHARE_MAX = Decimal("0.05")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_LOCK_NAME = "glasswell:p3-repaired-context-publication"
RECEIPT_SCHEMA = "p3-publication-receipt/1"

# The receipt's two artifact blocks are separate vocabularies, and a consumer that guesses one
# from the other serves 409s: `artifact_uri` keys the control `type_curve`, `artifact_sha256`
# keys the same artifact `typecurve_control`. Named here so a consumer imports rather than
# infers; tests/unit/test_receipt_key_spaces.py holds the emitters to these tuples.
CONTROL_URI_KEY = "type_curve"
CONTROL_COVERAGE_URI_KEY = "type_curve_coverage"
CONTROL_SHA256_KEY = "typecurve_control"
CONTROL_COVERAGE_SHA256_KEY = "typecurve_coverage"
ARTIFACT_URI_KEYS = (
    "feature",
    "feature_coverage",
    "model_dataset",
    "model_curves",
    "model_coverage",
    "model_rejections",
    CONTROL_URI_KEY,
    CONTROL_COVERAGE_URI_KEY,
)
ARTIFACT_SHA256_KEYS = (
    "feature_matrix",
    "feature_coverage",
    "model_labels",
    "model_curves",
    "model_coverage",
    "model_rejections",
    CONTROL_SHA256_KEY,
    CONTROL_COVERAGE_SHA256_KEY,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
REQUIREMENTS_LOCK = REPOSITORY_ROOT / "requirements.lock"
VERSION_FILE = REPOSITORY_ROOT / "VERSION"


class PublicationGateError(RuntimeError):
    """The candidate cannot be published under the sealed P3 contract."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class BaselineSplit:
    origin: date
    horizon_months: int
    split_id: str
    sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "origin": self.origin.isoformat(),
            "horizon_months": self.horizon_months,
            "split_id": self.split_id,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class PublicationBaseline:
    schema_version: str
    resident_eval_vintage: date
    resident_recipe_id: str
    migration_version: int
    migration_name: str
    migration_sha256: str
    basin: str
    feature_version: str
    feature_set_hash: str
    model_dataset_version: str
    control_version: str
    vintage_basis: str
    split_set_id: str
    splits: tuple[BaselineSplit, ...]
    allowed_residual_reasons: frozenset[str]
    document_sha256: str

    @property
    def origins(self) -> tuple[date, ...]:
        return tuple(sorted({item.origin for item in self.splits}))


@dataclass(frozen=True, slots=True)
class PublicationBuilds:
    feature: FeatureMatrixBuild
    model: ModelDatasetBuild
    control: TypeCurveBuild


@dataclass(frozen=True, slots=True)
class PublicationReceipt:
    eval_vintage: date
    code_version: str
    environment_id: str
    lockfile_sha256: str
    baseline: PublicationBaseline
    builds: PublicationBuilds
    artifact_sha256: Mapping[str, str]
    feature_coverage: Mapping[str, object]
    model_rejections: Mapping[str, int]
    pooled_unavailable: Mapping[str, object]
    split_unavailable: tuple[Mapping[str, object], ...]
    residual_reasons: Mapping[str, int]

    def evidence(self) -> dict[str, object]:
        return {
            "receipt_schema": RECEIPT_SCHEMA,
            "status": "published",
            "basin": self.baseline.basin,
            "eval_vintage": self.eval_vintage.isoformat(),
            "vintage_basis": self.baseline.vintage_basis,
            "code_version": self.code_version,
            "environment_id": self.environment_id,
            "isolation": "repeatable_read",
            "build_runs": 2,
            "byte_identical": True,
            "baseline": {
                "document_sha256": self.baseline.document_sha256,
                "resident_recipe_id": self.baseline.resident_recipe_id,
                "migration_042_sha256": self.baseline.migration_sha256,
                "feature_set_hash": self.baseline.feature_set_hash,
                "split_set_id": self.baseline.split_set_id,
            },
            "versions": {
                "feature": self.baseline.feature_version,
                "model_dataset": self.baseline.model_dataset_version,
                "type_curve": self.baseline.control_version,
            },
            "derivations": {
                "feature": self.builds.feature.derivation_id,
                "model_dataset": self.builds.model.derivation_id,
                "type_curve": self.builds.control.derivation_id,
            },
            "recipes": {
                "feature": self.builds.feature.recipe_id,
                "model_dataset": self.builds.model.recipe_id,
                "type_curve": self.builds.control.recipe_id,
            },
            "rows": {
                "feature": self.builds.feature.rows,
                "labels": self.builds.model.rows,
                "curves": self.builds.model.curve_rows,
                "rejections": self.builds.model.rejection_rows,
                "type_curve": self.builds.control.rows,
            },
            "artifact_sha256": dict(sorted(self.artifact_sha256.items())),
            "artifact_uri": {
                "feature": self.builds.feature.artifact_uri,
                "feature_coverage": self.builds.feature.coverage_uri,
                "model_dataset": self.builds.model.artifact_uri,
                "model_curves": self.builds.model.curves_uri,
                "model_coverage": self.builds.model.coverage_uri,
                "model_rejections": self.builds.model.rejections_uri,
                CONTROL_URI_KEY: self.builds.control.artifact_uri,
                CONTROL_COVERAGE_URI_KEY: self.builds.control.coverage_uri,
            },
            "environment": {
                "environment_id": self.environment_id,
                "lockfile_sha256": self.lockfile_sha256,
                "identity_basis": "deploy_stamp_and_installed_lock",
            },
            "coverage": {
                "feature": dict(self.feature_coverage),
                "model_rejections_by_reason": dict(sorted(self.model_rejections.items())),
                "pooled_control_unavailable": dict(self.pooled_unavailable),
                "split_control_unavailable": list(self.split_unavailable),
                "residual_reason_mentions": dict(sorted(self.residual_reasons.items())),
            },
            "splits": [item.to_dict() for item in self.baseline.splits],
        }

    @property
    def document_sha256(self) -> str:
        return sha256_hex(canonical_json(self.evidence()))

    @property
    def publication_id(self) -> str:
        return f"p3pub_{self.document_sha256[:32]}"

    def to_dict(self) -> dict[str, object]:
        return {
            "publication_id": self.publication_id,
            "document_sha256": self.document_sha256,
            **self.evidence(),
        }


def _fail(code: str) -> None:
    raise PublicationGateError(code)


def _mapping(value: object, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(code)
    return value


def _exact_keys(value: Mapping[str, object], expected: set[str], code: str) -> None:
    if set(value) != expected:
        _fail(code)


def _text(value: object, code: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(code)
    return value


def _integer(value: object, code: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _fail(code)
    return value


def _sha256(value: object, code: str) -> str:
    resolved = _text(value, code)
    if _SHA256_RE.fullmatch(resolved) is None:
        _fail(code)
    return resolved


def load_publication_baseline() -> PublicationBaseline:
    """Load and verify the packaged, review-pinned resident replay baseline."""
    payload = files("glasswell.modeling").joinpath(BASELINE_RESOURCE).read_bytes()
    if sha256_hex(payload) != BASELINE_SHA256:
        _fail("baseline_document_hash_mismatch")
    try:
        document = _mapping(json.loads(payload), "baseline_document_invalid")
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise PublicationGateError("baseline_document_invalid") from error
    _exact_keys(
        document,
        {
            "schema_version",
            "resident_eval_vintage",
            "resident_recipe_id",
            "migration",
            "basin",
            "feature_version",
            "feature_set_hash",
            "model_dataset_version",
            "control_version",
            "vintage_basis",
            "split_set_id",
            "splits",
            "allowed_residual_reasons",
        },
        "baseline_document_shape_mismatch",
    )
    migration = _mapping(document["migration"], "baseline_migration_invalid")
    _exact_keys(migration, {"version", "name", "sha256"}, "baseline_migration_invalid")
    raw_splits = document["splits"]
    if not isinstance(raw_splits, list):
        _fail("baseline_splits_invalid")
    splits: list[BaselineSplit] = []
    for raw in raw_splits:
        item = _mapping(raw, "baseline_split_invalid")
        _exact_keys(
            item,
            {"origin", "horizon_months", "split_id", "sha256"},
            "baseline_split_invalid",
        )
        try:
            origin = date.fromisoformat(_text(item["origin"], "baseline_split_invalid"))
        except ValueError as error:
            raise PublicationGateError("baseline_split_invalid") from error
        splits.append(
            BaselineSplit(
                origin=origin,
                horizon_months=_integer(
                    item["horizon_months"], "baseline_split_invalid", minimum=1
                ),
                split_id=_text(item["split_id"], "baseline_split_invalid"),
                sha256=_sha256(item["sha256"], "baseline_split_invalid"),
            )
        )
    reasons = document["allowed_residual_reasons"]
    if not isinstance(reasons, list) or any(not isinstance(item, str) for item in reasons):
        _fail("baseline_residual_reasons_invalid")
    try:
        resident_eval_vintage = date.fromisoformat(
            _text(document["resident_eval_vintage"], "baseline_eval_vintage_invalid")
        )
    except ValueError as error:
        raise PublicationGateError("baseline_eval_vintage_invalid") from error
    baseline = PublicationBaseline(
        schema_version=_text(document["schema_version"], "baseline_schema_invalid"),
        resident_eval_vintage=resident_eval_vintage,
        resident_recipe_id=_text(document["resident_recipe_id"], "baseline_recipe_invalid"),
        migration_version=_integer(migration["version"], "baseline_migration_invalid", minimum=1),
        migration_name=_text(migration["name"], "baseline_migration_invalid"),
        migration_sha256=_sha256(migration["sha256"], "baseline_migration_invalid"),
        basin=_text(document["basin"], "baseline_basin_invalid"),
        feature_version=_text(document["feature_version"], "baseline_feature_invalid"),
        feature_set_hash=_text(
            document["feature_set_hash"], "baseline_feature_set_hash_invalid"
        ),
        model_dataset_version=_text(
            document["model_dataset_version"], "baseline_model_version_invalid"
        ),
        control_version=_text(document["control_version"], "baseline_control_version_invalid"),
        vintage_basis=_text(document["vintage_basis"], "baseline_vintage_basis_invalid"),
        split_set_id=_text(document["split_set_id"], "baseline_split_set_invalid"),
        splits=tuple(splits),
        allowed_residual_reasons=frozenset(reasons),
        document_sha256=BASELINE_SHA256,
    )
    _validate_baseline_contract(baseline)
    return baseline


def _validate_baseline_contract(baseline: PublicationBaseline) -> None:
    if baseline.schema_version != "1":
        _fail("baseline_schema_unsupported")
    if baseline.feature_version != FEATURE_VERSION:
        _fail("baseline_feature_version_changed")
    if baseline.model_dataset_version != MODEL_DATASET_VERSION:
        _fail("baseline_model_version_changed")
    if baseline.control_version != CONTROL_VERSION:
        _fail("baseline_control_version_changed")
    if baseline.vintage_basis != VINTAGE_BASIS:
        _fail("baseline_vintage_basis_changed")
    expected_pairs = {(origin, horizon) for origin in DEFAULT_ORIGINS for horizon in (12, 24)}
    actual_pairs = {(item.origin, item.horizon_months) for item in baseline.splits}
    if len(baseline.splits) != 8 or actual_pairs != expected_pairs:
        _fail("baseline_split_matrix_changed")
    if tuple(baseline.splits) != tuple(
        sorted(baseline.splits, key=lambda item: (item.origin, item.horizon_months))
    ):
        _fail("baseline_split_order_changed")
    if len({item.split_id for item in baseline.splits}) != 8:
        _fail("baseline_split_ids_not_unique")
    if len({item.sha256 for item in baseline.splits}) != 8:
        _fail("baseline_split_hashes_not_unique")
    if baseline.allowed_residual_reasons != {
        "missing_lateral_length",
        "insufficient_peers",
    }:
        _fail("baseline_residual_reasons_changed")


def _resolve_root(value: Path | str, code: str) -> Path:
    supplied = Path(value).expanduser()
    if not supplied.is_absolute():
        _fail(code)
    resolved = supplied.resolve()
    if not resolved.is_dir():
        _fail(code)
    return resolved


def _candidate_partitions(
    baseline: PublicationBaseline,
    *,
    eval_vintage: date,
    feature_root: Path,
    model_root: Path,
) -> tuple[Path, Path, Path]:
    feature = (
        feature_root
        / "well_features"
        / f"feature_version={baseline.feature_version}"
        / f"as_of_vintage={eval_vintage.isoformat()}"
    )
    model = (
        model_root
        / "model_ready_labels"
        / f"dataset_version={baseline.model_dataset_version}"
        / f"basin={baseline.basin}"
        / f"eval_vintage={eval_vintage.isoformat()}"
        / f"feature_version={baseline.feature_version}"
        / f"vintage_basis={baseline.vintage_basis}"
        / f"split_set_id={baseline.split_set_id}"
    )
    control = (
        model_root
        / "typecurve_control"
        / f"control_version={baseline.control_version}"
        / f"dataset_version={baseline.model_dataset_version}"
        / f"basin={baseline.basin}"
        / f"eval_vintage={eval_vintage.isoformat()}"
        / f"feature_version={baseline.feature_version}"
        / f"vintage_basis={baseline.vintage_basis}"
        / f"split_set_id={baseline.split_set_id}"
    )
    return feature, model, control


def _require_fresh_partitions(partitions: Sequence[Path]) -> None:
    if any(path.exists() for path in partitions):
        _fail("candidate_partition_already_exists")


def _claim_candidate_partitions(partitions: Sequence[Path]) -> dict[Path, tuple[int, int]]:
    claims: dict[Path, tuple[int, int]] = {}
    try:
        for path in partitions:
            path.mkdir(parents=True, exist_ok=False)
            metadata = path.lstat()
            if not stat.S_ISDIR(metadata.st_mode) or path.is_symlink():
                _fail("candidate_partition_claim_failed")
            claims[path] = (metadata.st_dev, metadata.st_ino)
    except BaseException:
        _remove_candidate_partitions(claims)
        raise
    return claims


def _remove_candidate_partitions(claims: Mapping[Path, tuple[int, int]]) -> None:
    for path, identity in claims.items():
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            continue
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or path.is_symlink()
            or (metadata.st_dev, metadata.st_ino) != identity
        ):
            _fail("candidate_partition_cleanup_identity_changed")
        shutil.rmtree(path)


def _split_path(root: Path, basin: str, item: BaselineSplit) -> Path:
    return (
        root
        / "splits"
        / f"basin={basin}"
        / f"origin={item.origin.isoformat()}"
        / f"horizon={item.horizon_months}"
        / f"split_id={item.split_id}"
        / "split.json"
    )


def _verify_resident_splits(baseline: PublicationBaseline, model_root: Path) -> None:
    for expected in baseline.splits:
        path = _split_path(model_root, baseline.basin, expected)
        if not path.is_file() or path.is_symlink() or file_sha256(path) != expected.sha256:
            _fail("resident_split_bytes_mismatch")
        try:
            split = SplitObject.model_validate_json(path.read_bytes())
        except ValueError as error:
            raise PublicationGateError("resident_split_document_invalid") from error
        if (
            split.basin != baseline.basin
            or split.origin != expected.origin
            or split.horizon_months != expected.horizon_months
            or split.split_id != expected.split_id
            or split.plausibility_flags
        ):
            _fail("resident_split_identity_mismatch")


def _verify_migration(connection: psycopg.Connection, baseline: PublicationBaseline) -> None:
    local = next(
        (item for item in discover_migrations() if item.version == baseline.migration_version),
        None,
    )
    if (
        local is None
        or local.name != baseline.migration_name
        or local.sha256 != baseline.migration_sha256
    ):
        _fail("migration_042_local_hash_mismatch")
    with connection.cursor() as cursor:
        cursor.execute(
            "select name, sha256 from public.schema_migrations where version = %s",
            (baseline.migration_version,),
        )
        row = cursor.fetchone()
    if row != (baseline.migration_name, baseline.migration_sha256):
        _fail("migration_042_not_applied_exactly")


def _normalize_recipe_splits(raw: object) -> tuple[tuple[str, int, str, str], ...]:
    if not isinstance(raw, list):
        _fail("resident_recipe_splits_invalid")
    normalized: list[tuple[str, int, str, str]] = []
    for value in raw:
        item = _mapping(value, "resident_recipe_splits_invalid")
        normalized.append(
            (
                _text(item.get("origin"), "resident_recipe_splits_invalid"),
                _integer(item.get("horizon_months"), "resident_recipe_splits_invalid", minimum=1),
                _text(item.get("split_id"), "resident_recipe_splits_invalid"),
                _sha256(item.get("sha256"), "resident_recipe_splits_invalid"),
            )
        )
    return tuple(sorted(normalized))


def _verify_resident_recipe(connection: psycopg.Connection, baseline: PublicationBaseline) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "select operation, document from lineage.recipes where recipe_id = %s",
            (baseline.resident_recipe_id,),
        )
        row = cursor.fetchone()
    if row is None:
        _fail("resident_recipe_missing")
    operation, raw_document = row
    document = _mapping(raw_document, "resident_recipe_invalid")
    params = _mapping(document.get("params"), "resident_recipe_params_invalid")
    output = _mapping(document.get("output"), "resident_recipe_output_invalid")
    expected_splits = tuple(
        sorted(
            (
                item.origin.isoformat(),
                item.horizon_months,
                item.split_id,
                item.sha256,
            )
            for item in baseline.splits
        )
    )
    if (
        operation != "features.build"
        or document.get("recipe_id") != baseline.resident_recipe_id
        or document.get("entry_point")
        != "glasswell.modeling.model_dataset:build_model_dataset"
        or params.get("basin") != baseline.basin
        or params.get("dataset_version") != baseline.model_dataset_version
        or params.get("feature_version") != baseline.feature_version
        or params.get("feature_set_hash") != baseline.feature_set_hash
        or params.get("split_set_id") != baseline.split_set_id
        or params.get("vintage_basis") != baseline.vintage_basis
        or _normalize_recipe_splits(output.get("splits")) != expected_splits
    ):
        _fail("resident_recipe_contract_mismatch")


def _environment(connection: psycopg.Connection) -> tuple[DeriveEnvironment, str]:
    code_version = os.environ.get(CODE_VERSION_ENV, "")
    declared_lock_sha256 = os.environ.get(LOCKFILE_SHA256_ENV, "")
    if not code_version or _SHA256_RE.fullmatch(declared_lock_sha256) is None:
        _fail("build_identity_required")
    try:
        project_version = VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        _fail("version_identity_unavailable")
    if not re.fullmatch(r"[0-9]+\.[0-9]+", project_version):
        _fail("version_identity_invalid")
    expected_code = re.compile(rf"v{re.escape(project_version)}\+[0-9a-f]{{7,40}}")
    if expected_code.fullmatch(code_version) is None:
        _fail("code_version_not_release_identity")
    try:
        if REQUIREMENTS_LOCK.is_symlink() or not REQUIREMENTS_LOCK.is_file():
            _fail("lockfile_identity_unsafe")
        actual_lock_sha256 = file_sha256(REQUIREMENTS_LOCK)
    except OSError:
        _fail("lockfile_identity_unavailable")
    if actual_lock_sha256 != declared_lock_sha256:
        _fail("lockfile_stamp_mismatch")
    python_version = platform.python_version()
    fingerprint = hashlib.sha256(
        f"{python_version}|{actual_lock_sha256}".encode()
    ).hexdigest()
    environment_id = f"env_{fingerprint[:16]}"
    with connection.cursor() as cursor:
        cursor.execute(
            "select python_version, lockfile_sha256, threads"
            " from lineage.environments where env_id = %s",
            (environment_id,),
        )
        row = cursor.fetchone()
    if row != (python_version, actual_lock_sha256, 1):
        _fail("registered_environment_identity_mismatch")
    return (
        DeriveEnvironment(
            code_version=code_version,
            code_dirty=False,
            env_id=environment_id,
        ),
        actual_lock_sha256,
    )


def _persist_receipt(connection: psycopg.Connection, receipt: PublicationReceipt) -> None:
    document = receipt.evidence()
    document_canonical = canonical_json(document)
    if sha256_hex(document_canonical) != receipt.document_sha256:
        _fail("publication_receipt_hash_mismatch")
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into lineage.p3_publication_receipts"
            " (publication_id, receipt_schema, document_sha256, document, document_canonical,"
            " basin, eval_vintage,"
            " vintage_basis, feature_version, model_dataset_version, control_version,"
            " split_set_id, code_version, environment_id, lockfile_sha256,"
            " feature_derivation_id, model_dataset_derivation_id, control_derivation_id)"
            " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                receipt.publication_id,
                RECEIPT_SCHEMA,
                receipt.document_sha256,
                Jsonb(document),
                document_canonical.decode(),
                receipt.baseline.basin,
                receipt.eval_vintage,
                receipt.baseline.vintage_basis,
                receipt.baseline.feature_version,
                receipt.baseline.model_dataset_version,
                receipt.baseline.control_version,
                receipt.baseline.split_set_id,
                receipt.code_version,
                receipt.environment_id,
                receipt.lockfile_sha256,
                receipt.builds.feature.derivation_id,
                receipt.builds.model.derivation_id,
                receipt.builds.control.derivation_id,
            ),
        )
    emit(
        connection,
        "publication.accepted",
        subject_type="publication",
        subject_id=receipt.publication_id,
        payload={
            "document_sha256": receipt.document_sha256,
            "feature_derivation_id": receipt.builds.feature.derivation_id,
            "model_dataset_derivation_id": receipt.builds.model.derivation_id,
            "control_derivation_id": receipt.builds.control.derivation_id,
        },
    )


def _run_builders(
    connection: psycopg.Connection,
    *,
    baseline: PublicationBaseline,
    eval_vintage: date,
    environment: DeriveEnvironment,
    feature_root: Path,
    model_root: Path,
) -> PublicationBuilds:
    feature = build_feature_matrix(
        connection,
        as_of=eval_vintage,
        environment=environment,
        feature_version=baseline.feature_version,
        root=feature_root,
    )
    model = build_model_dataset(
        connection,
        feature_matrix_uri=feature.artifact_uri,
        feature_coverage_uri=feature.coverage_uri,
        eval_vintage=eval_vintage,
        environment=environment,
        basin=baseline.basin,
        origins=baseline.origins,
        vintage_basis=VINTAGE_BASIS,
        root=model_root,
    )
    control = build_type_curve_control(
        connection,
        labels_uri=model.artifact_uri,
        model_coverage_uri=model.coverage_uri,
        split_root=model_root / "splits",
        environment=environment,
        root=model_root,
    )
    return PublicationBuilds(feature=feature, model=model, control=control)


def _actual_splits(build: ModelDatasetBuild | TypeCurveBuild) -> tuple[BaselineSplit, ...]:
    return tuple(
        sorted(
            (
                BaselineSplit(
                    origin=item.split.origin,
                    horizon_months=item.split.horizon_months,
                    split_id=item.split.split_id,
                    sha256=item.sha256,
                )
                for item in build.splits
            ),
            key=lambda item: (item.origin, item.horizon_months),
        )
    )


def _validate_build_contract(
    builds: PublicationBuilds,
    *,
    baseline: PublicationBaseline,
    eval_vintage: date,
) -> None:
    feature, model, control = builds.feature, builds.model, builds.control
    if (
        feature.feature_version != baseline.feature_version
        or feature.feature_set_hash != baseline.feature_set_hash
        or feature.as_of_vintage != eval_vintage
    ):
        _fail("feature_contract_mismatch")
    if (
        model.dataset_version != baseline.model_dataset_version
        or model.feature_version != baseline.feature_version
        or model.split_set_id != baseline.split_set_id
        or model.eval_vintage != eval_vintage
        or _actual_splits(model) != baseline.splits
    ):
        _fail("model_contract_mismatch")
    if (
        control.control_version != baseline.control_version
        or control.dataset_version != baseline.model_dataset_version
        or control.feature_version != baseline.feature_version
        or control.split_set_id != baseline.split_set_id
        or control.eval_vintage != eval_vintage
        or _actual_splits(control) != baseline.splits
    ):
        _fail("typecurve_contract_mismatch")


def _verified_file(path_value: str, expected: str, root: Path, code: str) -> str:
    path = Path(path_value)
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (FileNotFoundError, ValueError) as error:
        raise PublicationGateError(code) from error
    if not path.is_absolute() or path != resolved:
        _fail(code)
    try:
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            _fail(code)
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as handle:
            opened = os.fstat(handle.fileno())
            if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
                _fail(code)
            digest = hashlib.sha256()
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
            observed = digest.hexdigest()
    except OSError as error:
        raise PublicationGateError(code) from error
    if observed != expected:
        _fail(code)
    return observed


def _artifact_fingerprint(
    builds: PublicationBuilds, *, feature_root: Path, model_root: Path
) -> dict[str, str]:
    feature, model, control = builds.feature, builds.model, builds.control
    fingerprints = {
        "feature_matrix": _verified_file(
            feature.artifact_uri,
            feature.artifact_sha256,
            feature_root,
            "feature_artifact_hash_mismatch",
        ),
        "feature_coverage": _verified_file(
            feature.coverage_uri,
            feature.coverage_sha256,
            feature_root,
            "feature_coverage_hash_mismatch",
        ),
        "model_labels": _verified_file(
            model.artifact_uri,
            model.artifact_sha256,
            model_root,
            "model_labels_hash_mismatch",
        ),
        "model_curves": _verified_file(
            model.curves_uri,
            model.curves_sha256,
            model_root,
            "model_curves_hash_mismatch",
        ),
        "model_coverage": _verified_file(
            model.coverage_uri,
            model.coverage_sha256,
            model_root,
            "model_coverage_hash_mismatch",
        ),
        "model_rejections": _verified_file(
            model.rejections_uri,
            model.rejections_sha256,
            model_root,
            "model_rejections_hash_mismatch",
        ),
        CONTROL_SHA256_KEY: _verified_file(
            control.artifact_uri,
            control.artifact_sha256,
            model_root,
            "typecurve_artifact_hash_mismatch",
        ),
        CONTROL_COVERAGE_SHA256_KEY: _verified_file(
            control.coverage_uri,
            control.coverage_sha256,
            model_root,
            "typecurve_coverage_hash_mismatch",
        ),
    }
    for item in model.splits:
        role = f"split:{item.split.origin.isoformat()}:{item.split.horizon_months}"
        fingerprints[role] = _verified_file(
            item.uri, item.sha256, model_root, "candidate_split_hash_mismatch"
        )
    return fingerprints


def _read_coverage(path_value: str, expected_sha256: str, code: str) -> Mapping[str, Any]:
    path = Path(path_value)
    try:
        payload = path.read_bytes()
        if sha256_hex(payload) != expected_sha256:
            _fail(code)
        return _mapping(json.loads(payload), code)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise PublicationGateError(code) from error


def _ratio(value: object, code: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        _fail(code)
    try:
        resolved = Decimal(str(value))
    except InvalidOperation as error:
        raise PublicationGateError(code) from error
    if not resolved.is_finite() or resolved < 0 or resolved > 1:
        _fail(code)
    return resolved


def _count_mapping(value: object, code: str) -> dict[str, int]:
    raw = _mapping(value, code)
    counts: dict[str, int] = {}
    for key, count in raw.items():
        if not isinstance(key, str):
            _fail(code)
        counts[key] = _integer(count, code)
    return counts


def _expected_ratio(numerator: int, denominator: int) -> Decimal:
    return Decimal(f"{Decimal(numerator) / Decimal(denominator):.6f}")


def _validate_coverage(
    builds: PublicationBuilds, baseline: PublicationBaseline
) -> tuple[
    Mapping[str, object],
    Mapping[str, int],
    Mapping[str, object],
    tuple[Mapping[str, object], ...],
    Mapping[str, int],
]:
    feature = _read_coverage(
        builds.feature.coverage_uri,
        builds.feature.coverage_sha256,
        "feature_coverage_invalid",
    )
    model = _read_coverage(
        builds.model.coverage_uri,
        builds.model.coverage_sha256,
        "model_coverage_invalid",
    )
    control = _read_coverage(
        builds.control.coverage_uri,
        builds.control.coverage_sha256,
        "typecurve_coverage_invalid",
    )
    if (
        feature.get("feature_version") != baseline.feature_version
        or feature.get("feature_set_hash") != baseline.feature_set_hash
    ):
        _fail("feature_coverage_contract_mismatch")
    feature_counts = _mapping(feature.get("counts"), "feature_coverage_counts_invalid")
    feature_receipt = {
        "subjects": _integer(feature_counts.get("subjects"), "feature_coverage_counts_invalid"),
        "resolved": _integer(feature_counts.get("resolved"), "feature_coverage_counts_invalid"),
        "missing": _integer(feature_counts.get("missing"), "feature_coverage_counts_invalid"),
        "conflicts": _integer(
            feature_counts.get("conflicts"), "feature_coverage_counts_invalid"
        ),
    }
    if (
        model.get("dataset_version") != baseline.model_dataset_version
        or model.get("feature_version") != baseline.feature_version
        or model.get("split_set_id") != baseline.split_set_id
    ):
        _fail("model_coverage_contract_mismatch")
    model_counts = _mapping(model.get("counts"), "model_coverage_counts_invalid")
    model_rejections = _count_mapping(
        model_counts.get("rejections_by_reason"), "model_rejection_counts_invalid"
    )
    if (
        control.get("control_version") != baseline.control_version
        or control.get("dataset_version") != baseline.model_dataset_version
        or control.get("feature_version") != baseline.feature_version
        or control.get("split_set_id") != baseline.split_set_id
    ):
        _fail("typecurve_coverage_contract_mismatch")
    if control.get("plausibility_flags") != []:
        _fail("typecurve_plausibility_gate_failed")
    counts = _mapping(control.get("counts"), "typecurve_coverage_counts_invalid")
    test_subjects = _integer(
        counts.get("test_subject_instances"), "typecurve_coverage_counts_invalid", minimum=1
    )
    unavailable = _integer(
        counts.get("control_unavailable_subject_instances"),
        "typecurve_coverage_counts_invalid",
    )
    observed = _ratio(
        counts.get("control_unavailable_share"), "typecurve_pooled_share_invalid"
    )
    if observed != _expected_ratio(unavailable, test_subjects):
        _fail("typecurve_pooled_share_inconsistent")
    acceptance = _mapping(control.get("acceptance"), "typecurve_acceptance_invalid")
    pooled = _mapping(
        acceptance.get("pooled_control_unavailable_share"),
        "typecurve_pooled_acceptance_invalid",
    )
    if (
        _ratio(pooled.get("observed"), "typecurve_pooled_acceptance_invalid") != observed
        or _ratio(pooled.get("maximum"), "typecurve_pooled_acceptance_invalid")
        != UNAVAILABLE_SHARE_MAX
        or pooled.get("status") != "pass"
        or observed > UNAVAILABLE_SHARE_MAX
    ):
        _fail("typecurve_pooled_unavailability_failed")
    residuals = _count_mapping(
        counts.get("control_unavailable_reason_mentions"),
        "typecurve_residual_reasons_invalid",
    )
    if not set(residuals) <= baseline.allowed_residual_reasons:
        _fail("typecurve_residual_reason_not_allowed")
    if residuals.get("missing_formation", 0) or residuals.get("formation_conflict", 0):
        _fail("typecurve_formation_context_unresolved")
    raw_splits = control.get("splits")
    if not isinstance(raw_splits, list):
        _fail("typecurve_split_coverage_invalid")
    expected = {item.split_id: item for item in baseline.splits}
    seen: set[str] = set()
    split_receipt: list[Mapping[str, object]] = []
    split_subject_total = 0
    split_unavailable_total = 0
    split_reason_totals: dict[str, int] = {}
    for raw in raw_splits:
        item = _mapping(raw, "typecurve_split_coverage_invalid")
        split_id = _text(item.get("split_id"), "typecurve_split_coverage_invalid")
        expected_split = expected.get(split_id)
        if expected_split is None or split_id in seen:
            _fail("typecurve_split_coverage_mismatch")
        seen.add(split_id)
        subjects = _integer(
            item.get("test_subjects"), "typecurve_split_coverage_invalid", minimum=1
        )
        split_unavailable = _integer(
            item.get("control_unavailable_subjects"), "typecurve_split_coverage_invalid"
        )
        split_share = _ratio(
            item.get("control_unavailable_share"), "typecurve_split_coverage_invalid"
        )
        split_reasons = _count_mapping(
            item.get("control_unavailable_reason_mentions"),
            "typecurve_split_coverage_invalid",
        )
        if (
            item.get("origin") != expected_split.origin.isoformat()
            or item.get("horizon_months") != expected_split.horizon_months
            or item.get("sha256") != expected_split.sha256
            or item.get("control_unavailable_status") != "pass"
            or split_share != _expected_ratio(split_unavailable, subjects)
            or split_share > UNAVAILABLE_SHARE_MAX
            or not set(split_reasons) <= baseline.allowed_residual_reasons
        ):
            _fail("typecurve_split_unavailability_failed")
        split_subject_total += subjects
        split_unavailable_total += split_unavailable
        for reason, count in split_reasons.items():
            split_reason_totals[reason] = split_reason_totals.get(reason, 0) + count
        split_receipt.append(
            {
                "split_id": split_id,
                "test_subjects": subjects,
                "control_unavailable_subjects": split_unavailable,
                "control_unavailable_share": f"{split_share:.6f}",
                "residual_reason_mentions": dict(sorted(split_reasons.items())),
            }
        )
    if (
        seen != set(expected)
        or split_subject_total != test_subjects
        or split_unavailable_total != unavailable
        or split_reason_totals != residuals
    ):
        _fail("typecurve_split_coverage_inconsistent")
    return (
        feature_receipt,
        model_rejections,
        {
            "test_subjects": test_subjects,
            "control_unavailable_subjects": unavailable,
            "control_unavailable_share": f"{observed:.6f}",
        },
        tuple(sorted(split_receipt, key=lambda item: str(item["split_id"]))),
        residuals,
    )


def publish_repaired_context(
    connection: psycopg.Connection,
    *,
    eval_vintage: date,
    feature_root: Path | str,
    model_root: Path | str,
) -> PublicationReceipt:
    """Build, replay, verify, and atomically register the repaired P3 artifact family."""
    if connection.info.transaction_status != TransactionStatus.IDLE:
        _fail("connection_must_be_idle")
    baseline = load_publication_baseline()
    if eval_vintage <= baseline.resident_eval_vintage:
        _fail("evaluation_vintage_must_advance")
    resolved_feature_root = _resolve_root(feature_root, "feature_root_invalid")
    resolved_model_root = _resolve_root(model_root, "model_root_invalid")
    partitions = _candidate_partitions(
        baseline,
        eval_vintage=eval_vintage,
        feature_root=resolved_feature_root,
        model_root=resolved_model_root,
    )
    _require_fresh_partitions(partitions)
    claims: dict[Path, tuple[int, int]] = {}
    try:
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute("set transaction isolation level repeatable read")
                cursor.execute(
                    "select pg_advisory_xact_lock(hashtextextended(%s, 0))", (_LOCK_NAME,)
                )
                cursor.execute("select current_date, current_setting('transaction_isolation')")
                database_date, isolation = cursor.fetchone()
            if isolation != "repeatable read":
                _fail("repeatable_read_not_active")
            if eval_vintage > database_date:
                _fail("evaluation_vintage_is_future")
            _require_fresh_partitions(partitions)
            _verify_migration(connection, baseline)
            environment, lockfile_sha256 = _environment(connection)
            _verify_resident_recipe(connection, baseline)
            _verify_resident_splits(baseline, resolved_model_root)
            claims = _claim_candidate_partitions(partitions)
            first = _run_builders(
                connection,
                baseline=baseline,
                eval_vintage=eval_vintage,
                environment=environment,
                feature_root=resolved_feature_root,
                model_root=resolved_model_root,
            )
            _validate_build_contract(first, baseline=baseline, eval_vintage=eval_vintage)
            first_fingerprint = _artifact_fingerprint(
                first, feature_root=resolved_feature_root, model_root=resolved_model_root
            )
            first_coverage = _validate_coverage(first, baseline)
            second = _run_builders(
                connection,
                baseline=baseline,
                eval_vintage=eval_vintage,
                environment=environment,
                feature_root=resolved_feature_root,
                model_root=resolved_model_root,
            )
            _validate_build_contract(second, baseline=baseline, eval_vintage=eval_vintage)
            second_fingerprint = _artifact_fingerprint(
                second, feature_root=resolved_feature_root, model_root=resolved_model_root
            )
            second_coverage = _validate_coverage(second, baseline)
            if first != second or first_fingerprint != second_fingerprint:
                _fail("two_run_identity_mismatch")
            if first_coverage != second_coverage:
                _fail("two_run_coverage_mismatch")
            feature_coverage, model_rejections, pooled, split_coverage, residuals = second_coverage
            receipt = PublicationReceipt(
                eval_vintage=eval_vintage,
                code_version=environment.code_version,
                environment_id=environment.env_id,
                lockfile_sha256=lockfile_sha256,
                baseline=baseline,
                builds=second,
                artifact_sha256=second_fingerprint,
                feature_coverage=feature_coverage,
                model_rejections=model_rejections,
                pooled_unavailable=pooled,
                split_unavailable=split_coverage,
                residual_reasons=residuals,
            )
            _persist_receipt(connection, receipt)
    except BaseException as error:
        try:
            _remove_candidate_partitions(claims)
        except (OSError, PublicationGateError) as cleanup_error:
            raise PublicationGateError("candidate_cleanup_failed") from cleanup_error
        raise error
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Publish the sealed P3 repaired-context artifact family."
    )
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--eval-vintage", required=True)
    parser.add_argument("--feature-root", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        eval_vintage = date.fromisoformat(arguments.eval_vintage)
    except ValueError:
        parser.error("--eval-vintage must be an ISO date")
    try:
        with psycopg.connect(arguments.dsn) as connection:
            receipt = publish_repaired_context(
                connection,
                eval_vintage=eval_vintage,
                feature_root=arguments.feature_root,
                model_root=arguments.model_root,
            )
    except PublicationGateError as error:
        print(
            canonical_json({"status": "failed", "reason": error.code}).decode(),
            file=sys.stderr,
        )
        return 1
    except Exception as error:
        print(
            canonical_json(
                {"status": "failed", "reason": "build_failed", "type": type(error).__name__}
            ).decode(),
            file=sys.stderr,
        )
        return 1
    print(canonical_json(receipt.to_dict()).decode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
