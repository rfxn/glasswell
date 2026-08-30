from __future__ import annotations

import json
from pathlib import Path

import pytest

from glasswell.modeling import served
from glasswell.modeling.model_dataset import MODEL_ROOT_ENV
from glasswell.modeling.p3_publication import (
    CONTROL_COVERAGE_SHA256_KEY,
    CONTROL_COVERAGE_URI_KEY,
    CONTROL_SHA256_KEY,
    CONTROL_URI_KEY,
)


@pytest.fixture(autouse=True)
def _clear_caches() -> None:
    served.clear_caches()


def _artifact(root: Path, payload: bytes = b"control-bytes") -> Path:
    path = root / "typecurve_control" / "sha256=aa" / "part-0000.parquet"
    path.parent.mkdir(parents=True)
    path.write_bytes(payload)
    return path


def test_a_locator_outside_the_model_root_is_refused(tmp_path, monkeypatch) -> None:
    root = tmp_path / "models"
    root.mkdir()
    monkeypatch.setenv(MODEL_ROOT_ENV, str(root))
    outside = tmp_path / "elsewhere" / "part-0000.parquet"
    outside.parent.mkdir()
    outside.write_bytes(b"x")
    with pytest.raises(served.UnregisteredArtifact, match="outside the registered model root"):
        served._contained_regular_file(str(outside))


def test_a_symlinked_component_is_refused(tmp_path, monkeypatch) -> None:
    root = tmp_path / "models"
    real = _artifact(root)
    link = root / "typecurve_control" / "sha256=link"
    link.symlink_to(real.parent)
    monkeypatch.setenv(MODEL_ROOT_ENV, str(root))
    with pytest.raises(served.UnregisteredArtifact, match="through symlink"):
        served._contained_regular_file(str(link / "part-0000.parquet"))


def test_a_relative_model_root_refuses_every_absolute_locator(tmp_path, monkeypatch) -> None:
    """DEFAULT_MODEL_ROOT is relative, so an unset variable is fail-closed by construction."""
    monkeypatch.delenv(MODEL_ROOT_ENV, raising=False)
    path = _artifact(tmp_path / "models")
    with pytest.raises(served.UnregisteredArtifact, match="outside the registered model root"):
        served._contained_regular_file(str(path))


def test_a_directory_is_not_a_regular_file(tmp_path, monkeypatch) -> None:
    root = tmp_path / "models"
    root.mkdir()
    monkeypatch.setenv(MODEL_ROOT_ENV, str(root))
    with pytest.raises(served.UnregisteredArtifact, match="not a regular file"):
        served._contained_regular_file(str(root))


def test_the_digest_cache_rehashes_when_the_stat_tuple_moves(tmp_path, monkeypatch) -> None:
    root = tmp_path / "models"
    path = _artifact(root, b"first")
    monkeypatch.setenv(MODEL_ROOT_ENV, str(root))
    first = served._digest_of(path)
    assert served.cache_state()[0] == 1
    assert served._digest_of(path) == first

    path.write_bytes(b"second-and-longer")
    assert served._digest_of(path) != first
    assert served.cache_state()[0] == 2


def test_the_digest_cache_is_capped(tmp_path, monkeypatch) -> None:
    root = tmp_path / "models"
    root.mkdir()
    monkeypatch.setenv(MODEL_ROOT_ENV, str(root))
    for index in range(served._DIGEST_CACHE_LIMIT + 4):
        path = root / f"part-{index}.parquet"
        path.write_bytes(str(index).encode())
        served._digest_of(path)
    assert served.cache_state()[0] == served._DIGEST_CACHE_LIMIT


def test_a_stat_tuple_that_moves_during_the_read_is_refused(tmp_path, monkeypatch) -> None:
    """m-4: scan_parquet takes a path, so the read is detected rather than prevented."""
    root = tmp_path / "models"
    path = _artifact(root, b"first")
    monkeypatch.setenv(MODEL_ROOT_ENV, str(root))
    pin = _pin(path)

    class MovingFrame:
        def collect(self):
            path.write_bytes(b"a different artifact entirely")
            return "collected"

    with pytest.raises(served.UnregisteredArtifact, match="changed while it was being read"):
        served._collect(pin, MovingFrame())


def test_a_stable_file_reads_through(tmp_path, monkeypatch) -> None:
    root = tmp_path / "models"
    path = _artifact(root)
    monkeypatch.setenv(MODEL_ROOT_ENV, str(root))

    class StillFrame:
        def collect(self):
            return "collected"

    assert served._collect(_pin(path), StillFrame()) == "collected"


def test_quantise_is_round_half_up_at_two_places() -> None:
    assert served.decimal_text(1.005) == "1.01"
    assert served.decimal_text(2.675) == "2.68"
    assert served.decimal_text(0) == "0.00"
    assert served.decimal_text(None) is None
    assert served.decimal_text(12345.6789, "1") == "12346"


def test_the_reason_set_is_sorted_and_never_a_bare_string() -> None:
    assert served.reasons(None) == ()
    assert served.reasons("") == ()
    assert served.reasons("missing_lateral_length") == ("missing_lateral_length",)
    assert served.reasons("insufficient_peers|missing_lateral_length|insufficient_peers") == (
        "insufficient_peers",
        "missing_lateral_length",
    )


def test_a_coverage_document_whose_digest_disagrees_is_refused(tmp_path, monkeypatch) -> None:
    root = tmp_path / "models"
    path = _artifact(root)
    coverage = path.parent / "coverage.json"
    coverage.write_text(json.dumps({"counts": {}}))
    monkeypatch.setenv(MODEL_ROOT_ENV, str(root))
    pin = _pin(path, coverage_sha256="0" * 64)
    with pytest.raises(served.UnregisteredArtifact, match="does not hash to the digest"):
        served.control_coverage(pin)


def test_a_missing_coverage_document_is_refused_not_degraded(tmp_path, monkeypatch) -> None:
    root = tmp_path / "models"
    path = _artifact(root)
    monkeypatch.setenv(MODEL_ROOT_ENV, str(root))
    with pytest.raises(served.UnregisteredArtifact, match="not a regular file"):
        served.control_coverage(_pin(path))


def _pin(path: Path, *, coverage_sha256: str = "0" * 64) -> served.PinnedControl:
    from datetime import date

    return served.PinnedControl(
        publication_id="p3pub_" + "0" * 32,
        receipt={
            "artifact_uri": {
                CONTROL_URI_KEY: str(path),
                CONTROL_COVERAGE_URI_KEY: str(path.parent / "coverage.json"),
            },
            "artifact_sha256": {
                CONTROL_SHA256_KEY: "1" * 64,
                CONTROL_COVERAGE_SHA256_KEY: coverage_sha256,
            },
        },
        superseded=(),
        in_force="p3pub_" + "0" * 32,
        control_derivation_id="drv_control",
        model_dataset_derivation_id="drv_model",
        feature_derivation_id="drv_feature",
        artifact_path=path,
        artifact_sha256="1" * 64,
        coverage_path=path.parent / "coverage.json",
        rows=0,
        control_version="tcv1.0",
        dataset_version="mdv1.4",
        feature_version="fv2.0",
        split_set_id="sset_test",
        eval_vintage=date(2026, 8, 28),
        basin="williston",
        vintage_basis="source_reconstructed_not_glasswell_history",
        code_version="v0.65",
        environment_id="env_test",
    )
