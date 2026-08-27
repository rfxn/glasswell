from __future__ import annotations

import json
from contextlib import nullcontext
from copy import deepcopy
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from glasswell.lineage.serialization import canonical_json, sha256_hex
from glasswell.modeling import p3_publication
from glasswell.modeling.p3_publication import (
    PublicationGateError,
    _validate_coverage,
    load_publication_baseline,
)


def test_packaged_baseline_seals_the_accepted_resident_splits() -> None:
    baseline = load_publication_baseline()

    assert baseline.document_sha256 == p3_publication.BASELINE_SHA256
    assert baseline.resident_recipe_id == "rcp_02a21056b98fce720f960d98d9e97d8c"
    assert baseline.feature_set_hash == (
        "sha256:b219de525e2a46c442fd8b480b1dadc25281ea4f051ad2411bb6e9a1912410ca"
    )
    assert baseline.split_set_id == "sset_c7bbb9a6932db76b"
    observed = [
        (item.origin, item.horizon_months, item.split_id, item.sha256)
        for item in baseline.splits
    ]
    assert observed == [
        (
            date(2021, 1, 1),
            12,
            "spl_wnhebb4rhlbb6st45oeq",
            "2f2b2a32f3fd552f9e2c114afdb40da721165a5c069c1fe40ae59dd0de3a23eb",
        ),
        (
            date(2021, 1, 1),
            24,
            "spl_4sja3wqwbvk5mct37rdq",
            "ddb2f874a1d008b2c53e3b3ee2612edc66cb9e35101a2279c8531811973d1400",
        ),
        (
            date(2022, 1, 1),
            12,
            "spl_fvom4i6tfuglim2h2dyq",
            "511d5af3a5c34daca300272773990d258718a4768e87299ad3ad2104070344c9",
        ),
        (
            date(2022, 1, 1),
            24,
            "spl_ehs3git43yhxc2n5ec4a",
            "d7fd6b3ea93ad4e3c1833a4fc2b1171e3d3609b4e5586fb2b5e9de69b3f68cd2",
        ),
        (
            date(2023, 1, 1),
            12,
            "spl_deyoqiivzwogce2sqnwq",
            "2025ef8de5dab23663b320f20654477e05b8a14ed45d96dd712c85140780246f",
        ),
        (
            date(2023, 1, 1),
            24,
            "spl_fzbqtnh3undvhjkelova",
            "7eaf0546d5c6b5128693cc507d03f9c4931df50ec4bdcc757e415deb2b0a4a5b",
        ),
        (
            date(2024, 1, 1),
            12,
            "spl_jjhppcl55r35b6j7kcya",
            "5818a9ff6d92c1bf0bced38cc474581367f8042dd6b649dbcb7cf40d963ed125",
        ),
        (
            date(2024, 1, 1),
            24,
            "spl_5srtehu3gyrmugm4rqqa",
            "7be2c0b82560dfe24536dea67e2232b6a5bb880d54b3633710d37a29e53c7e50",
        ),
    ]


def test_artifact_verifier_rejects_symlinked_files_and_components(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    target = root / "target.json"
    target.write_bytes(b"sealed")
    expected = sha256_hex(b"sealed")
    linked_file = root / "linked.json"
    linked_file.symlink_to(target)
    real_directory = root / "real"
    real_directory.mkdir()
    nested = real_directory / "nested.json"
    nested.write_bytes(b"sealed")
    linked_directory = root / "linked-directory"
    linked_directory.symlink_to(real_directory, target_is_directory=True)

    assert p3_publication._verified_file(str(target), expected, root, "unsafe") == expected
    for candidate in (linked_file, linked_directory / nested.name):
        with pytest.raises(PublicationGateError, match="unsafe"):
            p3_publication._verified_file(str(candidate), expected, root, "unsafe")


def test_candidate_cleanup_refuses_replaced_directory(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    claims = p3_publication._claim_candidate_partitions((candidate,))
    candidate.rmdir()
    replacement.rename(candidate)

    with pytest.raises(
        PublicationGateError, match="candidate_partition_cleanup_identity_changed"
    ):
        p3_publication._remove_candidate_partitions(claims)


def _write_document(root: Path, name: str, document: object) -> tuple[str, str]:
    path = root / name
    payload = canonical_json(document)
    path.write_bytes(payload)
    return str(path), sha256_hex(payload)


def _coverage_fixture(tmp_path: Path):
    baseline = load_publication_baseline()
    feature_uri, feature_hash = _write_document(
        tmp_path,
        "feature.json",
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
    model_uri, model_hash = _write_document(
        tmp_path,
        "model.json",
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
    splits = [
        {
            **item.to_dict(),
            "test_subjects": 100,
            "control_unavailable_subjects": 1,
            "control_unavailable_share": "0.010000",
            "control_unavailable_status": "pass",
            "control_unavailable_reason_mentions": {"missing_lateral_length": 1},
        }
        for item in baseline.splits
    ]
    control_document = {
        "control_version": baseline.control_version,
        "dataset_version": baseline.model_dataset_version,
        "feature_version": baseline.feature_version,
        "split_set_id": baseline.split_set_id,
        "counts": {
            "test_subject_instances": 800,
            "control_unavailable_subject_instances": 8,
            "control_unavailable_share": "0.010000",
            "control_unavailable_reason_mentions": {"missing_lateral_length": 8},
        },
        "acceptance": {
            "pooled_control_unavailable_share": {
                "observed": "0.010000",
                "maximum": "0.050000",
                "status": "pass",
            }
        },
        "plausibility_flags": [],
        "splits": splits,
    }
    control_uri, control_hash = _write_document(
        tmp_path, "control.json", control_document
    )
    builds = SimpleNamespace(
        feature=SimpleNamespace(coverage_uri=feature_uri, coverage_sha256=feature_hash),
        model=SimpleNamespace(coverage_uri=model_uri, coverage_sha256=model_hash),
        control=SimpleNamespace(coverage_uri=control_uri, coverage_sha256=control_hash),
    )
    return baseline, builds, control_document


def _replace_control(tmp_path: Path, builds, document: object) -> None:
    payload = canonical_json(document)
    Path(builds.control.coverage_uri).write_bytes(payload)
    builds.control.coverage_sha256 = sha256_hex(payload)


def test_coverage_gate_distinguishes_matrix_missing_from_test_unavailability(
    tmp_path: Path,
) -> None:
    baseline, builds, _ = _coverage_fixture(tmp_path)

    feature, rejections, pooled, splits, residuals = _validate_coverage(builds, baseline)

    assert feature["missing"] == 486
    assert rejections["missing_formation"] == 486
    assert pooled == {
        "test_subjects": 800,
        "control_unavailable_subjects": 8,
        "control_unavailable_share": "0.010000",
    }
    assert len(splits) == 8
    assert residuals == {"missing_lateral_length": 8}


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("pooled", "typecurve_pooled_unavailability_failed"),
        ("split", "typecurve_split_unavailability_failed"),
        ("formation", "typecurve_residual_reason_not_allowed"),
        ("aggregate", "typecurve_split_coverage_inconsistent"),
    ],
)
def test_coverage_gate_fails_closed_on_false_positive_acceptance(
    tmp_path: Path, mutation: str, reason: str
) -> None:
    baseline, builds, original = _coverage_fixture(tmp_path)
    document = deepcopy(original)
    if mutation == "pooled":
        document["counts"]["control_unavailable_subject_instances"] = 48
        document["counts"]["control_unavailable_share"] = "0.060000"
        document["acceptance"]["pooled_control_unavailable_share"]["observed"] = "0.060000"
    elif mutation == "split":
        document["splits"][0]["control_unavailable_subjects"] = 6
        document["splits"][0]["control_unavailable_share"] = "0.060000"
    elif mutation == "formation":
        document["counts"]["control_unavailable_reason_mentions"] = {
            "missing_formation": 8
        }
    else:
        document["counts"]["control_unavailable_reason_mentions"] = {
            "missing_lateral_length": 7
        }
    _replace_control(tmp_path, builds, document)

    with pytest.raises(PublicationGateError, match=reason):
        _validate_coverage(builds, baseline)


def test_cli_failure_never_echoes_dsn_or_exception_text(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    secret = "postgresql://owner:password@db.internal/glasswell"
    monkeypatch.setattr(p3_publication.psycopg, "connect", lambda _dsn: nullcontext(object()))

    def fail(*_args, **_kwargs):
        raise RuntimeError(f"unexpected failure involving {secret}")

    monkeypatch.setattr(p3_publication, "publish_repaired_context", fail)

    result = p3_publication.main(
        [
            "--dsn",
            secret,
            "--eval-vintage",
            "2026-08-27",
            "--feature-root",
            str(tmp_path),
                "--model-root",
                str(tmp_path),
            ]
    )

    captured = capsys.readouterr()
    assert result == 1
    assert secret not in captured.err
    assert "unexpected failure" not in captured.err
    assert json.loads(captured.err) == {
        "status": "failed",
        "reason": "build_failed",
        "type": "RuntimeError",
    }
