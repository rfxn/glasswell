from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import psycopg
import pytest

from glasswell.modeling import served
from glasswell.modeling.model_dataset import MODEL_ROOT_ENV
from glasswell.modeling.type_curve import CONTROL_SCHEMA
from glasswell.seed import seed_all
from tests.support.seed import seed_manifest
from tests.support.typecurve_fixture import (
    ControlSubject,
    insert_receipt,
    receipt_document,
    register_pinned_control,
    write_control_artifact,
)

SUBJECTS = (
    ControlSubject(api10="3305310451", origin=date(2021, 1, 1), horizon_months=24),
    ControlSubject(
        api10="3305310452",
        origin=date(2021, 1, 1),
        horizon_months=24,
        fallback_level="formation_basin",
    ),
    ControlSubject(
        api10="3305310453",
        origin=date(2021, 1, 1),
        horizon_months=24,
        fallback_level="control_unavailable",
        lateral_length_ft=None,
        lateral_length_bucket=None,
        reasons=("missing_lateral_length",),
    ),
)


@pytest.fixture(autouse=True)
def _clear_caches() -> None:
    served.clear_caches()


@pytest.fixture
def pinned(db, tmp_path, monkeypatch):
    root = tmp_path / "models"
    monkeypatch.setenv(MODEL_ROOT_ENV, str(root))
    seed_all(db)
    manifest_id = seed_manifest(db, sha256="7" * 64)
    db.commit()
    artifact = write_control_artifact(root, subjects=SUBJECTS)
    publication_id = register_pinned_control(db, artifact, manifest_id=manifest_id)
    db.commit()
    return artifact, publication_id, manifest_id


def test_the_resolver_pins_the_accepted_publication(db, pinned) -> None:
    artifact, publication_id, _ = pinned
    pin = served.resolve_pinned_control(db)
    assert pin.publication_id == publication_id
    assert pin.artifact_path == artifact.path.resolve()
    assert pin.artifact_sha256 == artifact.sha256
    assert pin.split_set_id == artifact.split_set_id
    assert pin.control_version == "tcv1.0"
    assert pin.feature_version == "fv2.0"
    assert pin.rows == artifact.rows
    assert pin.superseded == ()


def test_the_pinned_frame_is_the_subject_instance_at_its_horizon(db, pinned) -> None:
    pin = served.resolve_pinned_control(db)
    frame = served.subject_frame(
        pin,
        api10="3305310451",
        stream="oil",
        normalization="typecurve_absolute",
        origin=date(2021, 1, 1),
        horizon_months=24,
    )
    assert frame.height == 24
    assert frame["month_index"].to_list() == list(range(1, 25))
    assert frame["unit"].unique().to_list() == ["bbl"]
    assert frame["quantile_convention"].unique().to_list() == ["statistical_ascending"]

    absent = served.subject_frame(
        pin,
        api10="3399999999",
        stream="oil",
        normalization="typecurve_absolute",
        origin=None,
        horizon_months=24,
    )
    assert absent.is_empty()


def test_the_control_unavailable_subject_keeps_its_rows_and_its_reasons(db, pinned) -> None:
    pin = served.resolve_pinned_control(db)
    frame = served.subject_frame(
        pin,
        api10="3305310453",
        stream="oil",
        normalization="typecurve_absolute",
        origin=None,
        horizon_months=24,
    )
    assert frame.height == 24
    assert frame["monthly_p50"].null_count() == 24
    assert frame["peer_count"].to_list() == [0] * 24
    assert served.reasons(frame["control_unavailable_reasons"][0]) == ("missing_lateral_length",)


def test_a_receipt_naming_an_absent_derivation_cannot_even_be_written(db, pinned) -> None:
    """Agreement 2's first leg is the FK: a receipt cannot name a derivation that is not there."""
    artifact, _, _ = pinned
    document = receipt_document(
        artifact,
        feature_derivation_id="drv_absent_feature",
        model_dataset_derivation_id="drv_absent_labels",
        control_derivation_id="drv_absent_control",
    )
    document["eval_vintage"] = "2026-08-27"
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        insert_receipt(db, document)
    db.rollback()
    with pytest.raises(served.UnregisteredArtifact, match="not registered"):
        served._registered_control(db, "drv_absent_control")


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("status", "failed", "status='failed'"),
        ("operation", "model.train", "operation='model.train'"),
        ("output_store", "postgres", "output_store='postgres'"),
        ("output_dataset", "modeling.model_ready_labels", "output_dataset="),
    ],
)
def test_a_derivation_that_is_not_the_registered_control_is_refused(
    db, pinned, column, value, message
) -> None:
    pin = served.resolve_pinned_control(db)
    with db.cursor() as cursor:
        cursor.execute(
            f"update lineage.derivations set {column} = %s where derivation_id = %s",
            (value, pin.control_derivation_id),
        )
    served.clear_caches()
    with pytest.raises(served.UnregisteredArtifact, match=message):
        served.resolve_pinned_control(db)


def test_a_receipt_whose_artifact_uri_disagrees_with_the_locator_is_refused(db, pinned) -> None:
    pin = served.resolve_pinned_control(db)
    with db.cursor() as cursor:
        cursor.execute(
            "update lineage.derivations set output_locator = %s where derivation_id = %s",
            ("/var/lib/glasswell/models/somewhere-else/part-0000.parquet",
             pin.control_derivation_id),
        )
    served.clear_caches()
    with pytest.raises(served.UnregisteredArtifact, match="was registered against"):
        served.resolve_pinned_control(db)


def test_a_file_whose_digest_disagrees_with_output_sha256_is_refused(db, pinned) -> None:
    artifact, _, _ = pinned
    Path(artifact.path).write_bytes(b"not the registered bytes")
    served.clear_caches()
    with pytest.raises(served.UnregisteredArtifact, match="does not hash to the registered"):
        served.resolve_pinned_control(db)


def test_no_accepted_publication_is_refused_not_defaulted(db, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(MODEL_ROOT_ENV, str(tmp_path / "models"))
    with pytest.raises(served.UnregisteredArtifact, match="no accepted P3 publication"):
        served.resolve_pinned_control(db)


def test_an_unknown_publication_is_refused_rather_than_falling_back(db, pinned) -> None:
    with pytest.raises(served.UnregisteredArtifact, match="is not an accepted P3 publication"):
        served.resolve_pinned_control(db, publication_id="p3pub_" + "0" * 32)


def test_a_second_receipt_selects_by_greatest_eval_vintage_then_publication_id(
    db, pinned, tmp_path, monkeypatch
) -> None:
    artifact, first_id, manifest_id = pinned
    root = tmp_path / "models"
    later = write_control_artifact(
        root,
        subjects=(
            ControlSubject(api10="3305310451", origin=date(2021, 7, 1), horizon_months=24),
        ),
        eval_vintage=date(2026, 8, 29),
    )
    second_id = register_pinned_control(db, later, manifest_id=manifest_id)
    db.commit()
    served.clear_caches()

    pin = served.resolve_pinned_control(db)
    assert pin.publication_id == second_id
    assert pin.superseded == (first_id,)

    prior = served.resolve_pinned_control(db, publication_id=first_id)
    assert prior.publication_id == first_id
    assert prior.artifact_sha256 == artifact.sha256
    assert prior.superseded == (second_id,)


def test_the_coverage_document_is_digest_checked_and_served(db, pinned) -> None:
    pin = served.resolve_pinned_control(db)
    coverage = served.control_coverage(pin)
    assert coverage["control_version"] == "tcv1.0"
    assert coverage["counts"]["fallback_by_level"]["control_unavailable"] == 1
    assert coverage["control_contract"]["min_peers"] == 20


def test_a_tampered_coverage_document_is_refused_not_degraded(db, pinned) -> None:
    artifact, _, _ = pinned
    pin = served.resolve_pinned_control(db)
    Path(artifact.coverage_path).write_bytes(b'{"counts": {}}')
    served.clear_caches()
    with pytest.raises(served.UnregisteredArtifact, match="does not hash to the digest"):
        served.control_coverage(pin)


def test_the_index_page_is_the_horizon_row_and_pages_by_api10(db, pinned) -> None:
    pin = served.resolve_pinned_control(db)
    page = served.index_page(
        pin,
        stream="oil",
        normalization="typecurve_absolute",
        horizon_months=24,
        origin=None,
        fallback_level=None,
        formation_group=None,
        after_api10=None,
        limit=2,
    )
    assert page["subject_api10"].to_list() == ["3305310451", "3305310452", "3305310453"]
    assert page["month_index"].unique().to_list() == [24]

    second = served.index_page(
        pin,
        stream="oil",
        normalization="typecurve_absolute",
        horizon_months=24,
        origin=None,
        fallback_level=None,
        formation_group=None,
        after_api10="3305310452",
        limit=2,
    )
    assert second["subject_api10"].to_list() == ["3305310453"]

    narrowed = served.index_page(
        pin,
        stream="oil",
        normalization="typecurve_absolute",
        horizon_months=24,
        origin=None,
        fallback_level="control_unavailable",
        formation_group=None,
        after_api10=None,
        limit=10,
    )
    assert narrowed["subject_api10"].to_list() == ["3305310453"]


def test_the_fixture_artifact_matches_the_real_control_schema(tmp_path) -> None:
    """A fixture that drifts from CONTROL_SCHEMA proves nothing about the real artifact."""
    artifact = write_control_artifact(tmp_path / "models", subjects=SUBJECTS)
    assert list(pl.read_parquet(artifact.path).schema) == list(CONTROL_SCHEMA)


def test_the_subject_origins_are_offered_for_navigation(db, pinned) -> None:
    pin = served.resolve_pinned_control(db)
    assert served.subject_origins(pin, api10="3305310451") == (
        (date(2021, 1, 1), 24, "spl_20210101_24"),
    )
    assert served.subject_origins(pin, api10="3399999999") == ()
