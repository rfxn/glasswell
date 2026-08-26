from __future__ import annotations

from datetime import date, timedelta

import pytest

from glasswell.modeling.split import (
    PAD_CRS_EPSG,
    PadGroupChainingError,
    WellTimeline,
    build_pad_groups,
    build_temporal_split,
)


def well(
    ordinal: int,
    first_production_month: date,
    *,
    x: float | None,
    y: float | None,
    completion_date: date | None = None,
    spacing_unit_id: str | None = None,
) -> WellTimeline:
    return WellTimeline(
        api10=f"33053{ordinal:05d}",
        first_production_month=first_production_month,
        completion_date=completion_date or first_production_month,
        label_completeness_date=first_production_month + timedelta(days=400),
        surface_x_m=x,
        surface_y_m=y,
        spacing_unit_id=spacing_unit_id,
    )


def split_population() -> list[WellTimeline]:
    population = [
        well(
            index,
            date(2022, 1, 1)
            if index <= 90
            else date(2023, 1, 1)
            if index == 91
            else date(2024, 2, 1),
            x=1000.0 * index,
            y=1000.0,
        )
        for index in range(1, 101)
    ]
    population.extend(
        [
            well(101, date(2023, 12, 1), x=0.0, y=0.0),
            well(102, date(2024, 1, 1), x=100.0, y=0.0),
        ]
    )
    return population


def test_pad_grouping_is_transitive_and_uses_the_pinned_projected_crs():
    population = [
        well(1, date(2023, 1, 1), x=0.0, y=0.0),
        well(2, date(2023, 1, 1), x=140.0, y=0.0),
        well(3, date(2023, 1, 1), x=280.0, y=0.0),
    ]

    groups = build_pad_groups(population)

    assert len(set(groups.values())) == 1
    assert PAD_CRS_EPSG == 5070


def test_missing_surface_points_fall_back_to_spacing_unit_and_completion_half_year():
    population = [
        well(
            1,
            date(2023, 1, 1),
            x=None,
            y=None,
            spacing_unit_id="su_a",
            completion_date=date(2023, 1, 1),
        ),
        well(
            2,
            date(2023, 2, 1),
            x=None,
            y=None,
            spacing_unit_id="su_a",
            completion_date=date(2023, 2, 1),
        ),
        well(
            3,
            date(2023, 8, 1),
            x=None,
            y=None,
            spacing_unit_id="su_a",
            completion_date=date(2023, 8, 1),
        ),
    ]

    groups = build_pad_groups(population)

    assert groups[population[0].api10] == groups[population[1].api10]
    assert groups[population[0].api10] != groups[population[2].api10]


def test_split_groups_do_not_span_boundary():
    split = build_temporal_split(
        split_population(),
        basin="nd",
        boundary=date(2024, 1, 1),
        horizon_months=12,
        reporting_lags={"nd_mpr_xlsx": 45},
    )
    partitions_by_group: dict[str, set[str]] = {}
    for assignment in split.assignments:
        partitions_by_group.setdefault(assignment.pad_group_id, set()).add(assignment.partition)

    assert all(len(partitions) == 1 for partitions in partitions_by_group.values())
    assert split.n_wells_reassigned_by_group_rule == 1


def test_train_cal_test_are_disjoint():
    split = build_temporal_split(
        split_population(),
        basin="nd",
        boundary=date(2024, 1, 1),
        horizon_months=12,
        reporting_lags={"nd_mpr_xlsx": 45},
    )
    by_partition = {
        partition: {
            item.api10 for item in split.assignments if item.partition == partition
        }
        for partition in ("train", "cal", "test")
    }

    assert by_partition["train"].isdisjoint(by_partition["cal"])
    assert by_partition["train"].isdisjoint(by_partition["test"])
    assert by_partition["cal"].isdisjoint(by_partition["test"])
    assert all(by_partition.values())
    assert "3305300091" in by_partition["cal"]
    assert "3305300092" in by_partition["test"]


def test_knowledge_cutoff_is_the_latest_non_test_label_completion():
    population = split_population()
    split = build_temporal_split(
        population,
        basin="nd",
        boundary=date(2024, 1, 1),
        horizon_months=12,
        reporting_lags={"nd_mpr_xlsx": 45},
    )
    partition_by_api = {item.api10: item.partition for item in split.assignments}
    expected = max(
        item.label_completeness_date
        for item in population
        if partition_by_api[item.api10] != "test"
    )

    assert split.holdout_def.knowledge_cutoff == expected
    assert max(
        item.label_completeness_date
        for item in population
        if partition_by_api[item.api10] == "test"
    ) > expected


def test_incomplete_wells_stay_in_split_without_moving_knowledge_cutoff():
    population = split_population()
    population[0] = population[0].model_copy(update={"label_completeness_date": None})

    split = build_temporal_split(
        population,
        basin="nd",
        boundary=date(2024, 1, 1),
        horizon_months=12,
        reporting_lags={"nd_mpr_xlsx": 45},
    )

    assert population[0].api10 in {item.api10 for item in split.assignments}
    assert split.holdout_def.knowledge_cutoff == max(
        item.label_completeness_date
        for item in population
        if item.label_completeness_date is not None
        and next(
            assignment.partition
            for assignment in split.assignments
            if assignment.api10 == item.api10
        )
        != "test"
    )


def test_split_id_is_deterministic_under_input_order():
    args = {
        "basin": "nd",
        "boundary": date(2024, 1, 1),
        "horizon_months": 12,
        "reporting_lags": {"nd_mpr_xlsx": 45},
    }
    population = split_population()

    assert build_temporal_split(population, **args).split_id == build_temporal_split(
        list(reversed(population)), **args
    ).split_id


def test_chained_field_sized_component_is_rejected():
    population = [
        well(index, date(2023, 1, 1), x=index * 100.0, y=0.0)
        for index in range(1, 101)
    ]

    with pytest.raises(PadGroupChainingError, match="largest pad group share"):
        build_temporal_split(
            population,
            basin="nd",
            boundary=date(2024, 1, 1),
            horizon_months=12,
            reporting_lags={"nd_mpr_xlsx": 45},
        )
