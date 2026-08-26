from __future__ import annotations

from datetime import date

import pytest

from glasswell.modeling.type_curve import (
    CurveObservation,
    SubjectContext,
    _available_series,
    aggregate_peer_curves,
    empirical_quantile,
    resolve_fallback,
)


def subject() -> SubjectContext:
    return SubjectContext(
        api10="3305300001",
        basin="williston",
        formation_group="middle_bakken",
        formation_group_source_available_on=date(2020, 1, 1),
        area="053",
        lateral_length_ft=10_000,
        lateral_length_bucket="10000_to_10500",
        first_production_month=date(2022, 1, 1),
    )


def test_empirical_quantile_uses_equal_weight_linear_interpolation():
    assert empirical_quantile([0, 10], 0.10) == pytest.approx(1)
    assert empirical_quantile([0, 10], 0.50) == pytest.approx(5)
    assert empirical_quantile([0, 10], 0.90) == pytest.approx(9)


def test_typecurve_cum_quantiles_not_summed_from_monthly():
    aggregated = aggregate_peer_curves(
        ("a", "b", "c"),
        {"a": (0, 100), "b": (100, 0), "c": (100, 100)},
        {"a": 1_000, "b": 1_000, "c": 1_000},
        horizon_months=2,
        min_peers=3,
    )

    monthly_median_sum = sum(month.absolute_monthly.p50 for month in aggregated)

    assert monthly_median_sum == 200
    assert aggregated[1].absolute_cumulative.p50 == 100


def test_typecurve_reports_decaying_monthly_and_cumulative_peer_counts():
    aggregated = aggregate_peer_curves(
        ("a", "b", "c"),
        {"a": (1, 2, None), "b": (1, None, None), "c": (1, 2, 3)},
        {"a": 1_000, "b": 1_000, "c": 1_000},
        horizon_months=3,
        min_peers=2,
    )

    assert [month.peer_count for month in aggregated] == [3, 2, 1]
    assert [month.cumulative_peer_count for month in aggregated] == [3, 2, 1]
    assert aggregated[1].absolute_monthly is not None
    assert aggregated[2].absolute_monthly is None
    assert aggregated[2].absolute_cumulative is None


def test_typecurve_runs_absolute_and_per_kft_arms_on_the_same_peers():
    aggregated = aggregate_peer_curves(
        ("short", "long"),
        {"short": (100,), "long": (100,)},
        {"short": 1_000, "long": 2_000},
        horizon_months=1,
        min_peers=2,
    )[0]

    assert aggregated.peer_count == 2
    assert aggregated.absolute_monthly.p50 == 100
    assert aggregated.per_kft_monthly.p50 == 75


def test_typecurve_fallback_is_ordered_closed_and_records_the_resolved_level():
    context = subject()
    indices = {
        "formation_area_length": {("middle_bakken", "053", "10000_to_10500"): ("rung1",)},
        "formation_area": {("middle_bakken", "053"): ("rung1", "rung2")},
        "formation_basin": {("middle_bakken", "williston"): ("rung1", "rung2", "rung3")},
        "control_unavailable": {},
    }

    resolved = resolve_fallback(context, indices, min_peers=3)
    unavailable = resolve_fallback(context, indices, min_peers=3, excluded_api10s=("rung3",))

    assert resolved.level == "formation_basin"
    assert resolved.peer_api10s == ("rung1", "rung2", "rung3")
    assert resolved.peer_set_id is not None
    assert unavailable.level == "control_unavailable"
    assert unavailable.peer_api10s == ()


def test_curve_availability_obeys_the_selected_retrospective_vintage_basis():
    observations = (
        CurveObservation(
            volume=10,
            source_available_on=date(2024, 2, 1),
            source_reconstructed_available_on=date(2024, 1, 15),
        ),
    )

    strict = _available_series(
        observations,
        horizon_months=1,
        knowledge_cutoff=date(2024, 1, 31),
        vintage_basis="strict_manifest_knowledge",
    )
    reconstructed = _available_series(
        observations,
        horizon_months=1,
        knowledge_cutoff=date(2024, 1, 31),
        vintage_basis="source_reconstructed_not_glasswell_history",
    )

    assert strict == (None,)
    assert reconstructed == (10,)
