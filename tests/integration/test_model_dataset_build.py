from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import polars as pl

from glasswell.lineage.as_of import read_model_context_snapshot
from glasswell.modeling.feature_matrix import build_feature_matrix
from glasswell.modeling.model_dataset import build_model_dataset
from tests.support.modeling import seed_model_population
from tests.support.seed import seed_derivation, seed_manifest, seed_production, seed_well

AS_OF = date(2026, 8, 26)
ORIGIN = date(2022, 1, 1)


def test_model_dataset_registers_artifacts_and_replays_byte_identically(
    db, lineage_env, tmp_path: Path
):
    seed_model_population(db)
    feature = build_feature_matrix(
        db,
        as_of=AS_OF,
        environment=lineage_env,
        root=tmp_path / "features",
    )
    first = build_model_dataset(
        db,
        feature_matrix_uri=feature.artifact_uri,
        feature_coverage_uri=feature.coverage_uri,
        eval_vintage=AS_OF,
        environment=lineage_env,
        origins=(ORIGIN,),
        root=tmp_path / "models",
    )
    future_manifest = seed_manifest(
        db,
        sha256="8" * 64,
        source_key="2018_01_restatement.xlsx",
        fetched_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    future_derivation = seed_derivation(db, params={"source_key": "2018_01_restatement.xlsx"})
    seed_production(
        db,
        api10="3305300000",
        production_month=date(2018, 1, 1),
        report_vintage=date(2026, 9, 1),
        volume=Decimal("999.000"),
        stream="oil",
        manifest_id=future_manifest,
        derivation_id=future_derivation,
    )
    second = build_model_dataset(
        db,
        feature_matrix_uri=feature.artifact_uri,
        feature_coverage_uri=feature.coverage_uri,
        eval_vintage=AS_OF,
        environment=lineage_env,
        origins=(ORIGIN,),
        root=tmp_path / "models",
    )
    alternate = build_model_dataset(
        db,
        feature_matrix_uri=feature.artifact_uri,
        feature_coverage_uri=feature.coverage_uri,
        eval_vintage=AS_OF,
        environment=lineage_env,
        origins=(date(2021, 1, 1), ORIGIN),
        root=tmp_path / "models",
    )
    db.commit()

    assert first.derivation_id == second.derivation_id
    assert first.recipe_id == second.recipe_id
    assert first.artifact_sha256 == second.artifact_sha256
    assert first.curves_sha256 == second.curves_sha256
    assert first.coverage_sha256 == second.coverage_sha256
    assert first.rejections_sha256 == second.rejections_sha256
    assert first.split_set_id != alternate.split_set_id
    assert first.artifact_uri != alternate.artifact_uri
    assert first.rows == 60 * 2 * 3
    assert first.curve_rows == 60 * 24 * 3
    assert first.rejection_rows == 1
    assert len(first.splits) == 2

    labels = pl.read_parquet(first.artifact_uri)
    assert labels["dataset_version"].unique().to_list() == ["mdv1.4"]
    assert labels["formation_group_source_available_on"].null_count() == 0
    assert set(labels["label_status"].unique()) == {"complete", "withheld"}
    assert labels.filter(pl.col("api10") == "3305300059")["label_status"].unique().to_list() == [
        "withheld"
    ]
    assert labels.filter(
        (pl.col("stream") == "oil")
        & (pl.col("horizon_months") == 12)
        & (pl.col("label_status") == "complete")
    )["label_value"].unique().to_list() == [Decimal("1200.000")]
    curves = pl.read_parquet(first.curves_uri)
    assert curves["dataset_version"].unique().to_list() == ["mdv1.4"]
    assert curves["source_reconstructed_available_on"].null_count() == 0
    assert curves["producing_month_index"].max() == 24
    assert curves["reported"].all()

    coverage = json.loads(Path(first.coverage_uri).read_bytes())
    assert coverage["counts"]["subjects"] == 60
    assert coverage["counts"]["rejections_by_reason"] == {"withheld_or_confidential": 1}
    assert coverage["retrospective_vintage"]["split_basis"] == (
        "source_reconstructed_not_glasswell_history"
    )
    assert coverage["split_set_id"] == first.split_set_id
    assert all(item["streams"] == ["oil", "gas", "water"] for item in coverage["splits"])
    assert {
        assignment.partition
        for persisted in first.splits
        for assignment in persisted.split.assignments
    } == {"train", "cal", "test"}
    assert all(
        "3305300059" not in {assignment.api10 for assignment in persisted.split.assignments}
        for persisted in first.splits
    )

    with db.cursor() as cursor:
        cursor.execute(
            "select output_dataset, output_sha256, output_rows, recipe_id, determinism_class"
            " from lineage.derivations where derivation_id = %s",
            (first.derivation_id,),
        )
        derivation = cursor.fetchone()
        cursor.execute(
            "select document from lineage.recipes where recipe_id = %s", (first.recipe_id,)
        )
        recipe = cursor.fetchone()[0]
    assert derivation == (
        "modeling.model_ready_labels",
        first.artifact_sha256,
        first.rows,
        first.recipe_id,
        "D1",
    )
    assert recipe["output"]["curves"]["sha256"] == first.curves_sha256
    assert recipe["output"]["rejections"]["sha256"] == first.rejections_sha256
    assert {item["split_id"] for item in recipe["output"]["splits"]} == {
        item.split.split_id for item in first.splits
    }


def test_the_model_context_reads_a_blank_county_as_the_absence_it_is(db) -> None:
    """gate-cofix M-1: the fifth read of a SOURCE_REPORTED_TEXT_COLUMNS column, and the one the
    branch's sweep missed. `area` is a control feature, so an empty string there is a category
    of its own and would split one county's peers into two cohorts. The read is
    jurisdiction-blind by construction; Colorado is the only filer of blanks and cannot reach
    this read today, since a blank Api_County fails build_api10 and quarantines as
    key_incomplete, which is exactly why nothing here was red.
    """
    seed_well(db, api10="3305399001", county_code_at_permit="")
    db.commit()

    snapshot = read_model_context_snapshot(
        db, api10s=["3305399001"], basin="williston", as_of=AS_OF
    )

    assert [row["area"] for row in snapshot.rows] == [None]
