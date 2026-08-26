from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from glasswell.modeling.feature_matrix import build_feature_matrix
from glasswell.modeling.model_dataset import build_model_dataset
from glasswell.modeling.type_curve import TypeCurveError, build_type_curve_control
from tests.support.modeling import seed_model_population

AS_OF = date(2026, 8, 26)
ORIGIN = date(2022, 1, 1)


def test_typecurve_control_registers_identical_split_arms_and_replays_d1(
    db, lineage_env, tmp_path: Path
):
    seed_model_population(db, extra_recent_peers=10, one_peer_gas_gap=True)
    feature = build_feature_matrix(
        db,
        as_of=AS_OF,
        environment=lineage_env,
        root=tmp_path / "features",
    )
    model = build_model_dataset(
        db,
        feature_matrix_uri=feature.artifact_uri,
        feature_coverage_uri=feature.coverage_uri,
        eval_vintage=AS_OF,
        environment=lineage_env,
        origins=(ORIGIN,),
        root=tmp_path / "models",
    )
    first = build_type_curve_control(
        db,
        labels_uri=model.artifact_uri,
        model_coverage_uri=model.coverage_uri,
        split_root=tmp_path / "models" / "splits",
        environment=lineage_env,
        root=tmp_path / "controls",
    )
    second = build_type_curve_control(
        db,
        labels_uri=model.artifact_uri,
        model_coverage_uri=model.coverage_uri,
        split_root=tmp_path / "models" / "splits",
        environment=lineage_env,
        root=tmp_path / "controls",
    )
    db.commit()

    assert first.type_curve_id == second.type_curve_id
    assert first.derivation_id == second.derivation_id
    assert first.recipe_id == second.recipe_id
    assert first.artifact_sha256 == second.artifact_sha256
    assert first.coverage_sha256 == second.coverage_sha256
    assert first.rows == 3_024
    assert first.control_version == "tcv1.0"

    control = pl.read_parquet(first.artifact_uri)
    expected_split_hashes = {item.split.split_id: item.sha256 for item in model.splits}
    assert set(control["split_id"].unique()) == set(expected_split_hashes)
    assert control["split_sha256"].n_unique() == len(expected_split_hashes)
    for split_id, split_hash in expected_split_hashes.items():
        split_rows = control.filter(pl.col("split_id") == split_id)
        assert split_rows["split_sha256"].unique().to_list() == [split_hash]
        assert set(split_rows["stream"].unique()) == {"oil", "gas", "water"}
        assert set(split_rows["normalization"].unique()) == {
            "typecurve_per_kft",
            "typecurve_absolute",
        }
    peer_sets = control.group_by(["split_id", "subject_api10", "stream"]).agg(
        pl.col("peer_set_id").n_unique().alias("peer_sets"),
        pl.col("normalization").n_unique().alias("arms"),
    )
    assert peer_sets["peer_sets"].unique().to_list() == [1]
    assert peer_sets["arms"].unique().to_list() == [2]
    assert control["fallback_level"].unique().to_list() == ["formation_area_length"]
    assert set(control["peer_count"].unique()) == {24, 25}
    assert set(control["cumulative_peer_count"].unique()) == {24, 25}
    gas_month_one = control.filter((pl.col("stream") == "gas") & (pl.col("month_index") == 1))
    assert gas_month_one["peer_count"].unique().to_list() == [24]
    assert gas_month_one["fallback_level"].unique().to_list() == ["formation_area_length"]
    assert control["status"].unique().to_list() == ["ok"]
    assert control["cumulative_status"].unique().to_list() == ["ok"]
    assert control.filter(pl.col("monthly_p10") > pl.col("monthly_p50")).is_empty()
    assert control.filter(pl.col("monthly_p50") > pl.col("monthly_p90")).is_empty()

    coverage = json.loads(Path(first.coverage_uri).read_bytes())
    assert coverage["counts"]["test_subject_instances"] == 28
    assert coverage["counts"]["control_unavailable_subject_instances"] == 0
    assert coverage["counts"]["fallback_by_level"] == {"formation_area_length": 28}
    assert coverage["control_contract"]["normalizations"] == [
        "typecurve_per_kft",
        "typecurve_absolute",
    ]
    assert coverage["determinism_gate"]["class"] == "D1"
    assert {item["split_id"] for item in coverage["splits"]} == set(expected_split_hashes)

    with db.cursor() as cursor:
        cursor.execute(
            "select operation, output_dataset, output_sha256, output_rows, recipe_id,"
            " determinism_class from lineage.derivations where derivation_id = %s",
            (first.derivation_id,),
        )
        derivation = cursor.fetchone()
        cursor.execute(
            "select document from lineage.recipes where recipe_id = %s", (first.recipe_id,)
        )
        recipe = cursor.fetchone()[0]
        cursor.execute(
            "select selector from lineage.derivation_inputs"
            " where derivation_id = %s and ref_id = 'modeling.temporal_split' order by ord",
            (first.derivation_id,),
        )
        split_selectors = {row[0] for row in cursor.fetchall()}
    assert derivation == (
        "typecurve.build",
        "modeling.typecurve_control",
        first.artifact_sha256,
        first.rows,
        first.recipe_id,
        "D1",
    )
    assert recipe["output"]["type_curve_id"] == first.type_curve_id
    assert recipe["output"]["coverage"]["sha256"] == first.coverage_sha256
    assert split_selectors == {f"sha256:{value}" for value in expected_split_hashes.values()}

    corrupt_split_root = tmp_path / "corrupt-splits"
    shutil.copytree(tmp_path / "models" / "splits", corrupt_split_root)
    split_path = next(corrupt_split_root.rglob("split.json"))
    split_path.write_bytes(split_path.read_bytes() + b"\n")
    with pytest.raises(TypeCurveError, match="hash does not match model coverage"):
        build_type_curve_control(
            db,
            labels_uri=model.artifact_uri,
            model_coverage_uri=model.coverage_uri,
            split_root=corrupt_split_root,
            environment=lineage_env,
            root=tmp_path / "rejected-control",
        )
