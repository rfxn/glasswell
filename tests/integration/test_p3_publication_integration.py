from __future__ import annotations

import hashlib
import platform
from copy import deepcopy
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import psycopg
import pytest
from psycopg.types.json import Jsonb

from glasswell.ingest.base import CODE_VERSION_ENV, LOCKFILE_SHA256_ENV
from glasswell.lineage.serialization import canonical_json, sha256_hex
from glasswell.modeling import p3_publication
from glasswell.modeling.feature_matrix import FeatureMatrixBuild
from glasswell.modeling.model_dataset import ModelDatasetBuild, PersistedSplit
from glasswell.modeling.p3_publication import (
    BaselineSplit,
    PublicationBaseline,
    PublicationGateError,
    load_publication_baseline,
    publish_repaired_context,
)
from glasswell.modeling.split import (
    HoldoutDefinition,
    PadGroupStats,
    SplitAssignment,
    SplitObject,
)
from glasswell.modeling.type_curve import PersistedSplitInput, TypeCurveBuild
from glasswell.staging.duck import PARTITION_FILENAME


def _split(origin: date, horizon: int) -> SplitObject:
    api10 = f"33053{origin.year % 100:02d}{horizon:03d}"
    return SplitObject(
        split_id=f"spl_test_{origin.year}_{horizon}",
        basin="williston",
        origin=origin,
        horizon_months=horizon,
        holdout_def=HoldoutDefinition(
            boundary=origin,
            knowledge_cutoff=date(2025, 1, 1),
            reporting_lags={"nd_mpr_xlsx": 45},
        ),
        assignments=(
            SplitAssignment(
                api10=api10,
                pad_group_id=f"pad_{origin.year}_{horizon}",
                partition="test",
                ungrouped_partition="test",
            ),
        ),
        n_wells_reassigned_by_group_rule=0,
        pad_group_stats=PadGroupStats(
            component_size_max=1,
            component_size_p99=1,
            component_size_mean=1.0,
            pad_group_max_share=0.01,
        ),
    )


def _install_baseline(
    db, model_root: Path, database_date: date
) -> tuple[PublicationBaseline, tuple[SplitObject, ...]]:
    packaged = load_publication_baseline()
    split_objects = tuple(
        _split(origin, horizon)
        for origin in packaged.origins
        for horizon in (12, 24)
    )
    baseline_splits: list[BaselineSplit] = []
    for split in split_objects:
        payload = canonical_json(split.model_dump(mode="json"))
        item = BaselineSplit(
            origin=split.origin,
            horizon_months=split.horizon_months,
            split_id=split.split_id,
            sha256=sha256_hex(payload),
        )
        path = p3_publication._split_path(model_root, split.basin, item)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        baseline_splits.append(item)
    baseline = replace(
        packaged,
        resident_eval_vintage=database_date - timedelta(days=1),
        resident_recipe_id="rcp_" + "1" * 32,
        feature_set_hash="sha256:" + "2" * 64,
        split_set_id="sset_integration",
        splits=tuple(baseline_splits),
        document_sha256="3" * 64,
    )
    recipe = {
        "recipe_id": baseline.resident_recipe_id,
        "entry_point": "glasswell.modeling.model_dataset:build_model_dataset",
        "params": {
            "basin": baseline.basin,
            "dataset_version": baseline.model_dataset_version,
            "feature_version": baseline.feature_version,
            "feature_set_hash": baseline.feature_set_hash,
            "split_set_id": baseline.split_set_id,
            "vintage_basis": baseline.vintage_basis,
        },
        "output": {"splits": [item.to_dict() for item in baseline.splits]},
    }
    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.recipes (recipe_id, operation, document)"
            " values (%s, 'features.build', %s)",
            (baseline.resident_recipe_id, Jsonb(recipe)),
        )
    db.commit()
    return baseline, split_objects


def _write(path: Path, payload: bytes) -> tuple[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return str(path), sha256_hex(payload)


def _write_json(path: Path, document: object) -> tuple[str, str]:
    return _write(path, canonical_json(document))


def _fake_builders(
    monkeypatch: pytest.MonkeyPatch,
    *,
    baseline: PublicationBaseline,
    split_objects: tuple[SplitObject, ...],
    eval_vintage: date,
    feature_root: Path,
    model_root: Path,
    mutate_second_control: bool = False,
) -> list[tuple[str, int, str]]:
    calls: list[tuple[str, int, str]] = []
    run_counts = {"feature": 0, "model": 0, "control": 0}
    feature_partition, model_partition, control_partition = p3_publication._candidate_partitions(
        baseline,
        eval_vintage=eval_vintage,
        feature_root=feature_root,
        model_root=model_root,
    )
    persisted_splits = tuple(
        PersistedSplit(
            split=split,
            uri=str(p3_publication._split_path(model_root, baseline.basin, expected)),
            sha256=expected.sha256,
        )
        for split, expected in zip(split_objects, baseline.splits, strict=True)
    )

    def record(connection, name: str, environment) -> None:
        run_counts[name] += 1
        with connection.cursor() as cursor:
            cursor.execute("select txid_current(), current_setting('transaction_isolation')")
            transaction_id, isolation = cursor.fetchone()
            cursor.execute(
                "insert into lineage.recipes (recipe_id, operation, document)"
                " values (%s, 'features.build', '{}'::jsonb) on conflict do nothing",
                (f"rcp_{name}_integration",),
            )
            cursor.execute(
                "insert into lineage.derivations"
                " (derivation_id, operation, output_store, output_dataset, output_partition,"
                " output_locator, output_schema_version, params, params_hash, code_version,"
                " code_dirty, env_id, created_vintage, created_at, duration_ms, correlation_id,"
                " status, determinism_class, ttl_class) values"
                " (%s, %s, 'file', %s, '{}'::jsonb, '', '1', '{}'::jsonb, %s, %s, false,"
                " %s, %s, now(), 0, 'run_p3_integration', 'ok', 'D1', 'permanent')"
                " on conflict (derivation_id) do nothing",
                (
                    f"drv_{name}_integration",
                    "typecurve.build" if name == "control" else "features.build",
                    f"integration.{name}",
                    "0" * 64,
                    environment.code_version,
                    environment.env_id,
                    eval_vintage,
                ),
            )
        calls.append((name, transaction_id, isolation))

    def feature_builder(connection, **kwargs):
        record(connection, "feature", kwargs["environment"])
        assert kwargs == {
            "as_of": eval_vintage,
            "environment": kwargs["environment"],
            "feature_version": baseline.feature_version,
            "root": feature_root,
        }
        artifact_uri, artifact_hash = _write(
            feature_partition / "sha256=feature" / PARTITION_FILENAME,
            b"feature-matrix",
        )
        coverage_uri, coverage_hash = _write_json(
            feature_partition / "sha256=feature" / "coverage.json",
            {
                "feature_version": baseline.feature_version,
                "feature_set_hash": baseline.feature_set_hash,
                "counts": {
                    "subjects": 17_563,
                    "resolved": 17_077,
                    "missing": 486,
                    "conflicts": 0,
                },
            },
        )
        return FeatureMatrixBuild(
            derivation_id="drv_feature_integration",
            recipe_id="rcp_feature_integration",
            feature_version=baseline.feature_version,
            feature_set_hash=baseline.feature_set_hash,
            as_of_vintage=eval_vintage,
            artifact_uri=artifact_uri,
            artifact_sha256=artifact_hash,
            coverage_uri=coverage_uri,
            coverage_sha256=coverage_hash,
            rows=17_563,
            columns=("api10",),
        )

    def model_builder(connection, **kwargs):
        record(connection, "model", kwargs["environment"])
        assert kwargs["eval_vintage"] == eval_vintage
        assert kwargs["basin"] == baseline.basin
        assert kwargs["origins"] == baseline.origins
        assert kwargs["vintage_basis"] == baseline.vintage_basis
        assert kwargs["root"] == model_root
        artifact_dir = model_partition / "sha256=model"
        artifact_uri, artifact_hash = _write(
            artifact_dir / PARTITION_FILENAME, b"model-labels"
        )
        curves_uri, curves_hash = _write(artifact_dir / "curves.parquet", b"model-curves")
        rejections_uri, rejections_hash = _write(
            artifact_dir / "rejections.parquet", b"model-rejections"
        )
        coverage_uri, coverage_hash = _write_json(
            artifact_dir / "coverage.json",
            {
                "dataset_version": baseline.model_dataset_version,
                "feature_version": baseline.feature_version,
                "split_set_id": baseline.split_set_id,
                "counts": {
                    "rejections_by_reason": {
                        "missing_formation": 486,
                        "missing_lateral_length": 388,
                    }
                },
            },
        )
        return ModelDatasetBuild(
            derivation_id="drv_model_integration",
            recipe_id="rcp_model_integration",
            artifact_uri=artifact_uri,
            artifact_sha256=artifact_hash,
            curves_uri=curves_uri,
            curves_sha256=curves_hash,
            coverage_uri=coverage_uri,
            coverage_sha256=coverage_hash,
            rejections_uri=rejections_uri,
            rejections_sha256=rejections_hash,
            eval_vintage=eval_vintage,
            dataset_version=baseline.model_dataset_version,
            split_set_id=baseline.split_set_id,
            feature_version=baseline.feature_version,
            rows=105_378,
            curve_rows=1_172_586,
            rejection_rows=2_943,
            splits=persisted_splits,
        )

    def control_builder(connection, **kwargs):
        record(connection, "control", kwargs["environment"])
        assert kwargs["split_root"] == model_root / "splits"
        assert kwargs["root"] == model_root
        artifact_dir = control_partition / "sha256=control"
        payload = (
            b"typecurve-control-mutated"
            if mutate_second_control and run_counts["control"] == 2
            else b"typecurve-control"
        )
        artifact_uri, artifact_hash = _write(artifact_dir / PARTITION_FILENAME, payload)
        coverage_uri, coverage_hash = _write_json(
            artifact_dir / "coverage.json",
            {
                "control_version": baseline.control_version,
                "dataset_version": baseline.model_dataset_version,
                "feature_version": baseline.feature_version,
                "split_set_id": baseline.split_set_id,
                "counts": {
                    "test_subject_instances": 800,
                    "control_unavailable_subject_instances": 0,
                    "control_unavailable_share": "0.000000",
                    "control_unavailable_reason_mentions": {},
                },
                "acceptance": {
                    "pooled_control_unavailable_share": {
                        "observed": "0.000000",
                        "maximum": "0.050000",
                        "status": "pass",
                    }
                },
                "plausibility_flags": [],
                "splits": [
                    {
                        **item.to_dict(),
                        "test_subjects": 100,
                        "control_unavailable_subjects": 0,
                        "control_unavailable_share": "0.000000",
                        "control_unavailable_status": "pass",
                        "control_unavailable_reason_mentions": {},
                    }
                    for item in baseline.splits
                ],
            },
        )
        return TypeCurveBuild(
            type_curve_id="tc_integration",
            derivation_id="drv_control_integration",
            recipe_id="rcp_control_integration",
            artifact_uri=artifact_uri,
            artifact_sha256=artifact_hash,
            coverage_uri=coverage_uri,
            coverage_sha256=coverage_hash,
            control_version=baseline.control_version,
            dataset_version=baseline.model_dataset_version,
            feature_version=baseline.feature_version,
            split_set_id=baseline.split_set_id,
            eval_vintage=eval_vintage,
            rows=123_456,
            splits=tuple(
                PersistedSplitInput(split=item.split, uri=item.uri, sha256=item.sha256)
                for item in persisted_splits
            ),
        )

    monkeypatch.setattr(p3_publication, "load_publication_baseline", lambda: baseline)
    monkeypatch.setattr(p3_publication, "build_feature_matrix", feature_builder)
    monkeypatch.setattr(p3_publication, "build_model_dataset", model_builder)
    monkeypatch.setattr(p3_publication, "build_type_curve_control", control_builder)
    return calls


def _database_date(db) -> date:
    with db.cursor() as cursor:
        cursor.execute("select current_date")
        return cursor.fetchone()[0]


def _install_identity(db, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    lock_path = tmp_path / "requirements.lock"
    lock_path.write_text("pinned==1\n", encoding="utf-8")
    lock_sha256 = sha256_hex(lock_path.read_bytes())
    version_path = tmp_path / "VERSION"
    version_path.write_text("0.57\n", encoding="utf-8")
    code_version = "v0.57+abcdef1"
    monkeypatch.setattr(p3_publication, "REQUIREMENTS_LOCK", lock_path)
    monkeypatch.setattr(p3_publication, "VERSION_FILE", version_path)
    monkeypatch.setenv(CODE_VERSION_ENV, code_version)
    monkeypatch.setenv(LOCKFILE_SHA256_ENV, lock_sha256)
    python_version = platform.python_version()
    fingerprint = hashlib.sha256(f"{python_version}|{lock_sha256}".encode()).hexdigest()
    environment_id = f"env_{fingerprint[:16]}"
    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.environments"
            " (env_id, python_version, lockfile_sha256, threads) values (%s, %s, %s, 1)"
            " on conflict (env_id) do nothing",
            (environment_id, python_version, lock_sha256),
        )
    db.commit()
    return environment_id


def test_publication_identity_refuses_a_nonrelease_code_stamp(
    db, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_identity(db, tmp_path, monkeypatch)
    monkeypatch.setenv(CODE_VERSION_ENV, "git:integration")

    with pytest.raises(PublicationGateError, match="code_version_not_release_identity"):
        p3_publication._environment(db)


def test_publication_identity_hashes_the_installed_lock(
    db, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_identity(db, tmp_path, monkeypatch)
    monkeypatch.setenv(LOCKFILE_SHA256_ENV, "f" * 64)

    with pytest.raises(PublicationGateError, match="lockfile_stamp_mismatch"):
        p3_publication._environment(db)


def test_publication_uses_one_repeatable_snapshot_and_commits_once(
    db, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    feature_root, model_root = tmp_path / "features", tmp_path / "models"
    feature_root.mkdir()
    model_root.mkdir()
    database_date = _database_date(db)
    baseline, split_objects = _install_baseline(db, model_root, database_date)
    environment_id = _install_identity(db, tmp_path, monkeypatch)
    calls = _fake_builders(
        monkeypatch,
        baseline=baseline,
        split_objects=split_objects,
        eval_vintage=database_date,
        feature_root=feature_root,
        model_root=model_root,
    )

    receipt = publish_repaired_context(
        db,
        eval_vintage=database_date,
        feature_root=feature_root,
        model_root=model_root,
    )

    assert [name for name, _, _ in calls] == [
        "feature",
        "model",
        "control",
        "feature",
        "model",
        "control",
    ]
    assert len({transaction_id for _, transaction_id, _ in calls}) == 1
    assert {isolation for _, _, isolation in calls} == {"repeatable read"}
    assert receipt.to_dict()["byte_identical"] is True
    assert receipt.environment_id == environment_id
    assert receipt.feature_coverage["missing"] == 486
    assert all(path.is_dir() for path in p3_publication._candidate_partitions(
        baseline,
        eval_vintage=database_date,
        feature_root=feature_root,
        model_root=model_root,
    ))
    with db.cursor() as cursor:
        cursor.execute(
            "select count(*) from lineage.recipes where recipe_id like 'rcp_%_integration'"
        )
        assert cursor.fetchone()[0] == 3
        cursor.execute(
            "select document_sha256, document from lineage.p3_publication_receipts"
            " where publication_id = %s",
            (receipt.publication_id,),
        )
        document_sha256, document = cursor.fetchone()
        assert document_sha256 == receipt.document_sha256
        assert document == receipt.evidence()
        cursor.execute(
            "select count(*) from lineage.audit_events"
            " where event_type = 'publication.accepted' and subject_id = %s",
            (receipt.publication_id,),
        )
        assert cursor.fetchone()[0] == 1

    next_vintage = database_date + timedelta(days=1)
    mismatched_document = deepcopy(receipt.evidence())
    mismatched_document["eval_vintage"] = next_vintage.isoformat()
    mismatched_document["code_version"] = "v0.57+badc0de"
    canonical = canonical_json(mismatched_document)
    digest = sha256_hex(canonical)
    with pytest.raises(psycopg.errors.CheckViolation):
        with db.transaction(), db.cursor() as cursor:
            cursor.execute(
                "insert into lineage.p3_publication_receipts"
                " (publication_id, receipt_schema, document_sha256, document,"
                " document_canonical, basin, eval_vintage, vintage_basis, feature_version,"
                " model_dataset_version, control_version, split_set_id, code_version,"
                " environment_id, lockfile_sha256, feature_derivation_id,"
                " model_dataset_derivation_id, control_derivation_id)"
                " select %s, receipt_schema, %s, %s, %s, basin, %s, vintage_basis,"
                " feature_version, model_dataset_version, control_version, split_set_id,"
                " code_version, environment_id, lockfile_sha256, feature_derivation_id,"
                " model_dataset_derivation_id, control_derivation_id"
                " from lineage.p3_publication_receipts where publication_id = %s",
                (
                    f"p3pub_{digest[:32]}",
                    digest,
                    Jsonb(mismatched_document),
                    canonical.decode(),
                    next_vintage,
                    receipt.publication_id,
                ),
            )

    with pytest.raises(psycopg.errors.CheckViolation):
        with db.transaction(), db.cursor() as cursor:
            cursor.execute(
                "insert into lineage.p3_publication_receipts"
                " (publication_id, receipt_schema, document_sha256, document,"
                " document_canonical, basin, eval_vintage, vintage_basis, feature_version,"
                " model_dataset_version, control_version, split_set_id, code_version,"
                " environment_id, lockfile_sha256, feature_derivation_id,"
                " model_dataset_derivation_id, control_derivation_id)"
                " select %s, receipt_schema, %s, %s, %s, basin, %s, vintage_basis,"
                " feature_version, model_dataset_version, control_version, split_set_id,"
                " code_version, environment_id, lockfile_sha256, feature_derivation_id,"
                " model_dataset_derivation_id, control_derivation_id"
                " from lineage.p3_publication_receipts where publication_id = %s",
                (
                    "p3pub_" + "0" * 32,
                    "0" * 64,
                    Jsonb(mismatched_document),
                    canonical.decode(),
                    next_vintage,
                    receipt.publication_id,
                ),
            )


def test_failed_second_run_rolls_back_and_removes_only_candidate_partitions(
    db, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    feature_root, model_root = tmp_path / "features", tmp_path / "models"
    feature_root.mkdir()
    model_root.mkdir()
    database_date = _database_date(db)
    baseline, split_objects = _install_baseline(db, model_root, database_date)
    _install_identity(db, tmp_path, monkeypatch)
    _fake_builders(
        monkeypatch,
        baseline=baseline,
        split_objects=split_objects,
        eval_vintage=database_date,
        feature_root=feature_root,
        model_root=model_root,
        mutate_second_control=True,
    )

    with pytest.raises(PublicationGateError, match="two_run_identity_mismatch"):
        publish_repaired_context(
            db,
            eval_vintage=database_date,
            feature_root=feature_root,
            model_root=model_root,
        )

    assert not any(path.exists() for path in p3_publication._candidate_partitions(
        baseline,
        eval_vintage=database_date,
        feature_root=feature_root,
        model_root=model_root,
    ))
    assert all(
        p3_publication._split_path(model_root, baseline.basin, item).is_file()
        for item in baseline.splits
    )
    with db.cursor() as cursor:
        cursor.execute(
            "select count(*) from lineage.recipes where recipe_id like 'rcp_%_integration'"
        )
        assert cursor.fetchone()[0] == 0
