from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import polars as pl

from glasswell.modeling.feature_matrix import build_feature_matrix
from glasswell.modeling.model_dataset import build_model_dataset
from glasswell.seed import seed_all
from tests.support.seed import (
    seed_derivation,
    seed_manifest,
    seed_production,
    seed_well,
    seed_well_spatial,
)

AS_OF = date(2026, 8, 27)
ORIGIN = date(2022, 1, 1)


def shift_month(value: date, months: int) -> date:
    absolute = value.year * 12 + value.month - 1 + months
    year, zero_month = divmod(absolute, 12)
    return date(year, zero_month + 1, 1)


def seed_population(db) -> None:
    seed_all(db)
    manifest_id = seed_manifest(db, sha256="7" * 64)
    derivation_id = seed_derivation(db)
    for ordinal in range(60):
        api10 = f"33053{ordinal:05d}"
        first_production = (
            date(2018, 1, 1)
            if ordinal < 30
            else date(2021, 2, 1)
            if ordinal < 45
            else date(2022, 2, 1)
        )
        completion = shift_month(first_production, -1)
        seed_well(
            db,
            api10=api10,
            completion_date=completion,
            confidential_flag=ordinal == 59,
            manifest_id=manifest_id,
            derivation_id=derivation_id,
        )
        longitude = -103.8 + ordinal * 0.01
        seed_well_spatial(
            db,
            api10=api10,
            geom_type="surface",
            wkt=f"POINT({longitude} 47.5)",
            manifest_id=manifest_id,
            derivation_id=derivation_id,
        )
        seed_well_spatial(
            db,
            api10=api10,
            geom_type="lateral",
            wkt=f"LINESTRING({longitude} 47.5, {longitude + 0.025} 47.5)",
            manifest_id=manifest_id,
            derivation_id=derivation_id,
        )
        with db.cursor() as cursor:
            cursor.execute(
                "insert into canonical.well_completions"
                " (completion_key, api10, well_completion_pool, pool_reported, source_id,"
                " production_month, report_vintage, source_manifest_id, derivation_id)"
                " values (%s, %s, 'BAKKEN', 'BAKKEN', 'nd_mpr_xlsx', %s, %s, %s, %s)",
                (
                    f"{api10}:BAKKEN",
                    api10,
                    first_production,
                    date(2026, 8, 1),
                    manifest_id,
                    derivation_id,
                ),
            )
        for month_index in range(24):
            production_month = shift_month(first_production, month_index)
            for stream, volume in (
                ("oil", Decimal("100.000")),
                ("gas", Decimal("200.000")),
                ("water", Decimal("30.000")),
            ):
                seed_production(
                    db,
                    api10=api10,
                    production_month=production_month,
                    report_vintage=date(2026, 8, 1),
                    volume=volume,
                    stream=stream,
                    manifest_id=manifest_id,
                    derivation_id=derivation_id,
                )


def test_model_dataset_registers_artifacts_and_replays_byte_identically(
    db, lineage_env, tmp_path: Path
):
    seed_population(db)
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
    assert labels["dataset_version"].unique().to_list() == ["mdv1.3"]
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
    assert curves["dataset_version"].unique().to_list() == ["mdv1.3"]
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
