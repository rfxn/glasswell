from __future__ import annotations

import pytest
from pydantic import ValidationError

from glasswell.modeling.benchmark import BenchmarkArtifact, build_benchmark_artifact


def result(*, n: int = 200, ci_lo: float = -2.0, ci_hi: float = 1.0, delta: float = -0.5):
    verdict = "ml_better" if ci_hi < 0 else "control_better" if ci_lo > 0 else "tie"
    return {
        "stream": "oil",
        "horizon": 12,
        "slice": {"dim": "training_support_decile", "value": "d1"},
        "n": n,
        "status": "insufficient_n" if n < 50 else "ok",
        "by_arm": {}
        if n < 50
        else {
            "ml_cqr": {
                "interval_score": 10.0,
                "pinball": {"p10": 1.0, "p50": 2.0, "p90": 1.0},
                "coverage": {
                    "central": 0.8,
                    "lower_tail": 0.9,
                    "upper_tail": 0.9,
                    "ci_lo": 0.75,
                    "ci_hi": 0.85,
                },
                "sharpness_bbl": 100.0,
                "mae_bbl": 40.0,
                "medape": 0.2,
                "bias_bbl": -3.0,
            }
        },
        "ml_advantage": None
        if n < 50
        else {
            "metric": "interval_score",
            "delta": delta,
            "delta_pct": -0.03,
            "ci_lo": ci_lo,
            "ci_hi": ci_hi,
            "verdict": verdict,
        },
    }


def artifact(*results):
    return build_benchmark_artifact(
        recipe_id="rcp_fixture",
        derivation_id="drv_fixture",
        basin="nd",
        origin="2024-01",
        split_id="spl_fixture",
        knowledge_cutoff="2025-04-01",
        eval_vintage="2026-08-01",
        feature_version="fv1.3",
        feature_set_hash="sha256:" + "a" * 64,
        arms=[{"arm": "ml_cqr", "model_ids": {"oil.cum12": "mdl_fixture"}}],
        population={
            "n_train": 1000,
            "n_cal": 200,
            "n_test": 200,
            "n_reassigned_by_group_rule": 2,
            "censored_share": 0.1,
            "withheld_share": 0.0,
            "late_report_share": 0.02,
            "control_unavailable_share": 0.03,
        },
        results=results,
    )


def test_benchmark_artifact_has_losing_slices_field():
    built = artifact(result())

    assert "slices_where_ml_loses" in built.model_dump(mode="json")


def test_benchmark_flags_no_losing_slices():
    built = artifact(result(ci_lo=-3, ci_hi=-1, delta=-2))

    assert built.plausibility_flags == ("no_losing_slices",)


def test_reader_summary_is_generated_not_stored():
    built = artifact(result(ci_lo=1, ci_hi=3, delta=2))
    tampered = built.model_dump(mode="json")
    tampered["reader_summary"] = "ML was broadly comparable."

    with pytest.raises(ValidationError, match="reader_summary must be generated"):
        BenchmarkArtifact.model_validate(tampered)


def test_slice_below_min_n_reported_not_dropped():
    built = artifact(result(n=49))

    assert len(built.results) == 1
    assert built.results[0].status == "insufficient_n"


def test_control_unavailable_share_reported():
    built = artifact(result())

    assert built.population.control_unavailable_share == 0.03


def test_benchmark_id_changes_with_the_numbers():
    first = artifact(result(delta=-0.5))
    second = artifact(result(delta=0.5))

    assert first.benchmark_id != second.benchmark_id


def test_losing_slice_and_worst_case_summary_are_derived():
    built = artifact(result(ci_lo=1, ci_hi=3, delta=2))

    assert len(built.slices_where_ml_loses) == 1
    assert "training_support_decile=d1" in built.reader_summary


def test_sufficient_result_requires_metrics_for_every_declared_arm():
    built = artifact(result())
    malformed = built.model_dump(mode="json")
    malformed["results"][0]["by_arm"] = {}

    with pytest.raises(ValidationError, match="metrics for every arm"):
        BenchmarkArtifact.model_validate(malformed)
