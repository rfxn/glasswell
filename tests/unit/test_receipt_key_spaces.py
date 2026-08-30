"""The receipt's key spaces, held to one definition at every end that reads or writes them.

`served.py` shipped reading `artifact_sha256.type_curve`, a key the P3 builder has never
written — the digest lives under `typecurve_control`, while `artifact_uri` really does say
`type_curve`. Every type-curve route answered 409 against the deployed receipt and the whole
suite stayed green, because `typecurve_fixture` invented the receipt document instead of
deriving it. The parquet was pinned against `CONTROL_SCHEMA`; the receipt was pinned against
nothing.

These tests run the real emitters and compare their key sets to the constants the consumers
import, so a rename fails here rather than in production.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

from glasswell.modeling import p3_publication, served
from glasswell.modeling.p3_publication import (
    ARTIFACT_SHA256_KEYS,
    ARTIFACT_URI_KEYS,
    CONTROL_COVERAGE_SHA256_KEY,
    CONTROL_COVERAGE_URI_KEY,
    CONTROL_SHA256_KEY,
    CONTROL_URI_KEY,
    PublicationBuilds,
    PublicationReceipt,
)
from tests.support.typecurve_fixture import (
    ControlSubject,
    receipt_document,
    write_control_artifact,
)


def _builds() -> PublicationBuilds:
    feature = SimpleNamespace(
        artifact_uri="feature.parquet",
        artifact_sha256="a" * 64,
        coverage_uri="feature_coverage.json",
        coverage_sha256="b" * 64,
        derivation_id="drv_feature",
        recipe_id="rcp_feature",
        rows=1,
    )
    model = SimpleNamespace(
        artifact_uri="labels.parquet",
        artifact_sha256="c" * 64,
        curves_uri="curves.parquet",
        curves_sha256="d" * 64,
        coverage_uri="model_coverage.json",
        coverage_sha256="e" * 64,
        rejections_uri="rejections.parquet",
        rejections_sha256="f" * 64,
        derivation_id="drv_model",
        recipe_id="rcp_model",
        rows=2,
        curve_rows=3,
        rejection_rows=0,
        splits=(),
    )
    control = SimpleNamespace(
        artifact_uri="control.parquet",
        artifact_sha256="0" * 64,
        coverage_uri="coverage.json",
        coverage_sha256="1" * 64,
        derivation_id="drv_control",
        recipe_id="rcp_control",
        rows=4,
    )
    return PublicationBuilds(feature=feature, model=model, control=control)


def test_the_builder_writes_exactly_the_digest_keys_the_constants_declare(monkeypatch) -> None:
    monkeypatch.setattr(
        p3_publication, "_verified_file", lambda uri, expected, root, code: expected
    )

    fingerprints = p3_publication._artifact_fingerprint(
        _builds(), feature_root=Path("/features"), model_root=Path("/models")
    )

    assert tuple(fingerprints) == ARTIFACT_SHA256_KEYS
    assert fingerprints[CONTROL_SHA256_KEY] == "0" * 64
    assert fingerprints[CONTROL_COVERAGE_SHA256_KEY] == "1" * 64


def test_the_builder_writes_exactly_the_locator_keys_the_constants_declare() -> None:
    builds = _builds()
    receipt = PublicationReceipt(
        eval_vintage=date(2026, 8, 28),
        code_version="git:0000test",
        environment_id="env_test",
        lockfile_sha256="2" * 64,
        baseline=SimpleNamespace(
            basin="williston",
            vintage_basis="source_reconstructed_not_glasswell_history",
            document_sha256="3" * 64,
            resident_recipe_id="rcp_resident",
            migration_sha256="4" * 64,
            feature_set_hash="5" * 64,
            split_set_id="sset_test",
            feature_version="fv2.0",
            model_dataset_version="mdv1.4",
            control_version="tcv1.0",
            splits=(),
        ),
        builds=builds,
        artifact_sha256={key: "6" * 64 for key in ARTIFACT_SHA256_KEYS},
        feature_coverage={},
        model_rejections={},
        pooled_unavailable={},
        split_unavailable=(),
        residual_reasons={},
    )

    document = receipt.evidence()

    assert tuple(document["artifact_uri"]) == ARTIFACT_URI_KEYS
    assert document["artifact_uri"][CONTROL_URI_KEY] == "control.parquet"
    assert document["artifact_uri"][CONTROL_COVERAGE_URI_KEY] == "coverage.json"


def test_the_key_literals_are_frozen_by_receipts_that_cannot_be_rewritten() -> None:
    """The constants are not free to move together.

    `lineage.p3_publication_receipts` is append-only and every accepted receipt already on disk
    carries these exact strings. A coherent rename across builder, consumer and fixture would
    keep every other test in this file green while making every published receipt unreadable,
    so the literals are pinned here rather than only compared to each other.
    """
    assert CONTROL_URI_KEY == "type_curve"
    assert CONTROL_COVERAGE_URI_KEY == "type_curve_coverage"
    assert CONTROL_SHA256_KEY == "typecurve_control"
    assert CONTROL_COVERAGE_SHA256_KEY == "typecurve_coverage"
    assert ARTIFACT_SHA256_KEYS == (
        "feature_matrix",
        "feature_coverage",
        "model_labels",
        "model_curves",
        "model_coverage",
        "model_rejections",
        "typecurve_control",
        "typecurve_coverage",
    )
    assert ARTIFACT_URI_KEYS == (
        "feature",
        "feature_coverage",
        "model_dataset",
        "model_curves",
        "model_coverage",
        "model_rejections",
        "type_curve",
        "type_curve_coverage",
    )


def test_the_two_key_spaces_really_are_different_vocabularies() -> None:
    """The trap in one line: the same artifact is named twice, and never the same way."""
    assert CONTROL_URI_KEY != CONTROL_SHA256_KEY
    assert CONTROL_URI_KEY not in ARTIFACT_SHA256_KEYS
    assert CONTROL_SHA256_KEY not in ARTIFACT_URI_KEYS
    assert CONTROL_COVERAGE_URI_KEY not in ARTIFACT_SHA256_KEYS
    assert CONTROL_COVERAGE_SHA256_KEY not in ARTIFACT_URI_KEYS


def test_the_contract_fixture_receipt_carries_the_builder_key_sets(tmp_path) -> None:
    """The guard the parquet had and the receipt did not."""
    artifact = write_control_artifact(
        tmp_path / "models",
        subjects=(ControlSubject(api10="3305310451", origin=date(2021, 1, 1), horizon_months=12),),
    )

    document = receipt_document(
        artifact,
        feature_derivation_id="drv_feature",
        model_dataset_derivation_id="drv_model",
        control_derivation_id="drv_control",
    )

    assert tuple(document["artifact_sha256"]) == ARTIFACT_SHA256_KEYS
    assert tuple(document["artifact_uri"]) == ARTIFACT_URI_KEYS
    assert document["artifact_sha256"][CONTROL_SHA256_KEY] == artifact.sha256
    assert document["artifact_uri"][CONTROL_URI_KEY] == str(artifact.path)


def test_the_resolver_reads_keys_the_builder_actually_writes() -> None:
    """served.py imports the names rather than spelling them, so this is a wiring check."""
    assert served.CONTROL_SHA256_KEY in ARTIFACT_SHA256_KEYS
    assert served.CONTROL_COVERAGE_SHA256_KEY in ARTIFACT_SHA256_KEYS
    assert served.CONTROL_URI_KEY in ARTIFACT_URI_KEYS
    assert served.CONTROL_COVERAGE_URI_KEY in ARTIFACT_URI_KEYS
