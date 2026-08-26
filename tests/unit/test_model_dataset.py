from __future__ import annotations

from datetime import date
from decimal import Decimal

from glasswell.modeling.model_dataset import lateral_length_bucket, materialize_labels


def month(
    api10: str,
    year: int,
    month_number: int,
    *,
    oil: str = "10",
    gas: str = "20",
    water: str = "30",
    semantics: str = "reported",
    days: int = 30,
    gas_semantics: str | None = None,
) -> dict[str, object]:
    production_month = date(year, month_number, 1)
    return {
        "api10": api10,
        "production_month": production_month,
        "oil_volume": Decimal(oil),
        "oil_unit": "bbl",
        "oil_days_produced": days,
        "oil_null_semantics": semantics,
        "gas_volume": None if gas_semantics in {"no_report", "withheld"} else Decimal(gas),
        "gas_unit": "mcf",
        "gas_days_produced": days,
        "gas_null_semantics": gas_semantics or semantics,
        "water_volume": Decimal(water),
        "water_unit": "bbl",
        "water_days_produced": days,
        "water_null_semantics": semantics,
        "source_vintage": date(2026, 8, 1),
        "oil_rows": 1,
        "gas_rows": 1,
        "water_rows": 1,
    }


def labels_for(materialized, api10: str, horizon: int) -> dict[str, dict[str, object]]:
    return {
        str(row["stream"]): dict(row)
        for row in materialized.labels
        if row["api10"] == api10 and row["horizon_months"] == horizon
    }


def test_cumulative_labels_count_producing_months_and_preserve_decimal_streams():
    api10 = "3305300001"
    rows = [month(api10, 2020, month_number) for month_number in range(1, 13)]
    rows.insert(
        5,
        month(
            api10,
            2020,
            6,
            oil="0",
            gas="0",
            water="0",
            semantics="reported",
            days=30,
        ),
    )
    for index, row in enumerate(rows[6:], start=7):
        row["production_month"] = date(2020 if index <= 12 else 2021, ((index - 1) % 12) + 1, 1)

    built = materialize_labels(rows)
    cum12 = labels_for(built, api10, 12)

    assert {row["label_status"] for row in cum12.values()} == {"complete"}
    assert cum12["oil"]["label_value"] == Decimal("120")
    assert cum12["gas"]["label_value"] == Decimal("240")
    assert cum12["water"]["label_value"] == Decimal("360")
    assert len([row for row in built.curves if row["stream"] == "oil"]) == 12
    assert built.curves[0]["source_reconstructed_available_on"] == date(2020, 2, 15)


def test_reported_zero_with_positive_days_advances_but_zero_day_shutdown_does_not():
    api10 = "3305300002"
    rows = [month(api10, 2020, month_number) for month_number in range(1, 11)]
    rows.extend(
        [
            month(
                api10,
                2020,
                11,
                oil="0",
                gas="0",
                water="0",
                semantics="reported_zero",
                days=20,
            ),
            month(
                api10,
                2020,
                12,
                oil="0",
                gas="0",
                water="0",
                semantics="reported_zero",
                days=0,
            ),
            month(api10, 2021, 1),
        ]
    )

    built = materialize_labels(rows)

    assert labels_for(built, api10, 12)["oil"]["label_status"] == "complete"
    assert len([row for row in built.curves if row["stream"] == "oil"]) == 12


def test_rows_without_a_producing_month_are_not_mislabeled_as_incomplete():
    api10 = "3305300006"
    rows = [
        month(
            api10,
            2020,
            1,
            oil="0",
            gas="0",
            water="0",
            semantics="reported",
            days=30,
        )
    ]

    built = materialize_labels(rows)

    assert {row["label_status"] for row in built.labels} == {"no_production"}
    assert built.curves == ()
    assert built.states[api10].first_production_month is None


def test_withheld_and_missing_stream_are_never_converted_to_zero():
    withheld_api = "3305300003"
    missing_api = "3305300004"
    withheld_rows = [month(withheld_api, 2020, month_number) for month_number in range(1, 13)]
    withheld_rows[4] = month(withheld_api, 2020, 5, gas_semantics="withheld")
    missing_rows = [month(missing_api, 2020, month_number) for month_number in range(1, 13)]
    missing_rows[4] = month(missing_api, 2020, 5, gas_semantics="no_report")

    built = materialize_labels([*withheld_rows, *missing_rows])

    assert {row["label_status"] for row in labels_for(built, withheld_api, 12).values()} == {
        "withheld"
    }
    missing = labels_for(built, missing_api, 12)
    assert missing["oil"]["label_status"] == "complete"
    assert missing["gas"]["label_status"] == "missing_stream_observation"
    assert missing["gas"]["label_value"] is None


def test_intermittency_uses_the_pinned_twelfth_month_rule_for_both_horizons():
    api10 = "3305300005"
    rows = []
    for index in range(24):
        absolute_month = index if index < 11 else index + 8
        year, zero_month = divmod(2020 * 12 + absolute_month, 12)
        rows.append(month(api10, year, zero_month + 1))

    built = materialize_labels(rows)

    assert labels_for(built, api10, 12)["oil"]["label_status"] == "intermittent"
    assert labels_for(built, api10, 24)["oil"]["label_status"] == "intermittent"


def test_lateral_bucket_edges_are_closed_exactly_as_documented():
    assert lateral_length_bucket(None) is None
    assert lateral_length_bucket(7999.999) == "lt_8000"
    assert lateral_length_bucket(8000) == "8000_to_lt_10000"
    assert lateral_length_bucket(9999.999) == "8000_to_lt_10000"
    assert lateral_length_bucket(10000) == "10000_to_10500"
    assert lateral_length_bucket(10500) == "10000_to_10500"
    assert lateral_length_bucket(10500.001) == "gt_10500"
