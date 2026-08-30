"""The Montana parse and promotion decisions, tested where they are observable.

These cover the pure functions directly rather than through a promotion, because a rule whose
only effect is inside a frame that never reaches canonical cannot be proven by querying
canonical — an assertion that cannot fail is not a check.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import polars as pl
import pytest

from glasswell.ingest.mt_bogc import (
    _typed_well_frame,
    formation_promotion_records,
    is_end_of_month,
    month_from_report_date,
)
from glasswell.lineage.models import ConformanceRule

pytestmark = pytest.mark.unit

IDENTITY_RULE = ConformanceRule(
    rule_id="cr_mt_api_identity_1",
    rule_family="cr_mt_api_identity",
    supersedes_rule_id=None,
    source_id="mt_bogc_well_production",
    stage="parse",
    applies_to_fields=["api_wellno"],
    rule_kind="parse_directive",
    spec={"digits": 14, "api10_slice": [0, 10], "separators": []},
    rule="API-10 is the first ten digits.",
    rationale="measured",
    evidence_url=None,
    evidence_sha256=None,
    effective_from=date(2026, 1, 1),
    effective_to=None,
    published_vintage=date(2026, 8, 30),
    code_ref=None,
    code_ref_sha256=None,
    created_by_event_id=None,
)


@pytest.mark.parametrize(
    ("reported", "expected"),
    [
        ("12/31/2020", date(2020, 12, 1)),
        ("01/31/2021", date(2021, 1, 1)),
        ("02/28/2001", date(2001, 2, 1)),
        ("02/29/2024", date(2024, 2, 1)),
        ("08/31/2026", date(2026, 8, 1)),
    ],
)
def test_an_end_of_month_stamp_normalises_to_the_first_of_that_month(reported, expected):
    assert month_from_report_date(reported) == expected


@pytest.mark.parametrize("reported", ["", None, "not-a-date", "13/31/2020", "12/2020"])
def test_an_unparseable_report_date_yields_no_month_rather_than_a_guess(reported):
    assert month_from_report_date(reported) is None


def test_the_end_of_month_convention_is_checkable_so_a_source_drift_is_detectable():
    assert is_end_of_month("02/28/2001") is True
    assert is_end_of_month("02/29/2024") is True
    assert is_end_of_month("02/28/2024") is False
    assert is_end_of_month("06/30/2023") is True
    assert is_end_of_month("06/01/2023") is False


def _staged(**overrides: object) -> pl.DataFrame:
    row = {
        "source_row_ordinal": 1,
        "api_wellno": "25051211360000",
        "rpt_date": "12/31/2020",
        "st_fmtn_cd": "BAK",
        "lease_unit": "4711",
        "bbls_oil_cond": "10",
        "mcf_gas": "20",
        "bbls_wtr": "30",
        "days_prod": "31",
    }
    row.update(overrides)
    schema = {
        name: (pl.Int64 if name == "source_row_ordinal" else pl.String) for name in row
    }
    return pl.DataFrame([row], schema=schema)


def test_the_lease_unit_sentinel_becomes_null_and_a_real_unit_survives():
    """cr_mt_lease_unit_sentinel_1. -999 means no lease unit and must never become a key."""
    typed = _typed_well_frame(
        _staged(lease_unit="-999"), rules=[IDENTITY_RULE], sentinel="-999"
    )
    assert typed["lease_unit"].to_list() == [None]

    kept = _typed_well_frame(_staged(lease_unit="4711"), rules=[IDENTITY_RULE], sentinel="-999")
    assert kept["lease_unit"].to_list() == ["4711"]


def test_the_api10_slice_takes_ten_digits_of_the_fourteen_digit_key():
    typed = _typed_well_frame(_staged(), rules=[IDENTITY_RULE], sentinel="-999")
    assert typed["api10"].to_list() == ["2505121136"]


def _filing(**overrides: object) -> dict[str, object]:
    row = {
        "source_row_ordinal": 1,
        "api10": "2505121136",
        "production_month": date(2023, 6, 1),
        "stream_canonical": "oil",
        "st_fmtn_cd": "BAK",
        "volume": Decimal("100"),
        "unit": "bbl",
        "days_prod": 30,
    }
    row.update(overrides)
    return row


def _frame(rows: list[dict[str, object]]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema={
        "source_row_ordinal": pl.Int64,
        "api10": pl.String,
        "production_month": pl.Date,
        "stream_canonical": pl.String,
        "st_fmtn_cd": pl.String,
        "volume": pl.Decimal(18, 3),
        "unit": pl.String,
        "days_prod": pl.Int64,
    })


def test_a_single_formation_filing_promotes_as_the_well_with_no_aggregation():
    promoted = formation_promotion_records(_frame([_filing()]))

    assert len(promoted.records) == 1
    assert promoted.aggregates == []
    entry = promoted.records[0]
    assert entry["entity_type"] == "well"
    assert entry["entity_key"] == "2505121136"
    assert entry["aggregation"] is None
    assert entry["well_completion_pool"] == "BAK"


def test_two_formations_promote_as_two_pools_plus_their_exact_sum():
    promoted = formation_promotion_records(
        _frame([
            _filing(source_row_ordinal=1, st_fmtn_cd="BAK", volume=Decimal("100"), days_prod=30),
            _filing(source_row_ordinal=2, st_fmtn_cd="MAD", volume=Decimal("25"), days_prod=28),
        ])
    )

    assert {entry["entity_type"] for entry in promoted.records} == {"well_completion_pool"}
    assert sorted(entry["entity_key"] for entry in promoted.records) == [
        "2505121136:BAK",
        "2505121136:MAD",
    ]
    assert len(promoted.aggregates) == 1
    rollup = promoted.aggregates[0]
    assert rollup["entity_type"] == "well"
    assert rollup["volume"] == Decimal("125")
    assert rollup["aggregation"] == "sum_over_pools"
    assert rollup["well_completion_pool"] is None


def test_a_rollup_takes_the_maximum_of_its_days_and_never_their_sum():
    """A well producing 31 days from two formations produced for 31 days, not 62."""
    promoted = formation_promotion_records(
        _frame([
            _filing(source_row_ordinal=1, st_fmtn_cd="BAK", days_prod=31),
            _filing(source_row_ordinal=2, st_fmtn_cd="MAD", days_prod=28),
        ])
    )

    assert promoted.aggregates[0]["days_produced"] == 31


def test_two_filings_under_one_formation_leave_the_rest_for_quarantine():
    """The rule cannot say which is the well, so it never picks by file ordinal."""
    promoted = formation_promotion_records(
        _frame([
            _filing(source_row_ordinal=1, st_fmtn_cd="BAK", volume=Decimal("100")),
            _filing(source_row_ordinal=2, st_fmtn_cd="BAK", volume=Decimal("7")),
        ])
    )

    assert len(promoted.records) == 1
    assert promoted.aggregates == []
    assert promoted.records[0]["volume"] == Decimal("100")
    assert promoted.collided.height == 1
    assert promoted.collided["volume"].to_list() == [Decimal("7")]


def test_an_all_null_rollup_is_no_report_rather_than_a_reported_zero():
    promoted = formation_promotion_records(
        _frame([
            _filing(source_row_ordinal=1, st_fmtn_cd="BAK", volume=None),
            _filing(source_row_ordinal=2, st_fmtn_cd="MAD", volume=None),
        ])
    )

    assert promoted.aggregates[0]["null_semantics"] == "no_report"


def test_a_reported_zero_rollup_is_distinguished_from_an_absent_one():
    promoted = formation_promotion_records(
        _frame([
            _filing(source_row_ordinal=1, st_fmtn_cd="BAK", volume=Decimal("0")),
            _filing(source_row_ordinal=2, st_fmtn_cd="MAD", volume=Decimal("0")),
        ])
    )

    assert promoted.aggregates[0]["null_semantics"] == "reported_zero"
