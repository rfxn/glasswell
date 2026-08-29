"""A layout that stops declaring a measured column must stop the run, not null every well.

`_assert_layout` proves field count, the county prefix and the oil-gas domain, and not one of
those can see a column that is gone: read as an absence, a dropped or renamed TOTAL DEPTH nulls
the field on every well and the load still exits 0.
"""

from __future__ import annotations

from datetime import date

import pytest

from glasswell.ingest.tx_wellbore import _measured
from glasswell.lineage.errors import RuleSpecError

pytestmark = pytest.mark.unit

ROW = {
    "api10": "4231712345",
    "state_code": "42",
    "county_code": "317",
    "source_row_ordinal": 7,
    "total_depth_ft": "9120",
    "completion_date": "20240131",
}


def test_a_readable_row_parses_both_measures_and_rejects_nothing() -> None:
    parsed, unreadable = _measured(ROW)

    assert parsed["total_depth_ft"] == 9120.0
    assert parsed["completion_date"] == date(2024, 1, 31)
    assert unreadable == []


@pytest.mark.parametrize("dropped", ["total_depth_ft", "completion_date"])
def test_a_layout_missing_a_declared_measure_is_refused(dropped: str) -> None:
    row = {name: value for name, value in ROW.items() if name != dropped}

    with pytest.raises(RuleSpecError) as refusal:
        _measured(row)

    assert dropped in str(refusal.value)


def test_a_blank_measure_is_still_an_absence_and_not_a_reject() -> None:
    """The guard is about the column being gone, not about the value being empty."""
    parsed, unreadable = _measured({**ROW, "total_depth_ft": ""})

    assert parsed["total_depth_ft"] is None
    assert unreadable == []
