from datetime import date
from decimal import Decimal

import pytest

from glasswell.ingest.fracfocus import (
    classify_base_water,
    exceeds_plausibility,
    parse_source_date,
)

# API-10 normalisation is one registry-driven decision shared with the ND loaders; it is
# exercised across all three of them in test_api10_identity.py.


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1/20/2012 12:00:00 AM", date(2012, 1, 20)),
        ("1/15/2015 10:58:00 PM", date(2015, 1, 15)),
        ("2/15/2020", date(2020, 2, 15)),
        ("2020-02-15", date(2020, 2, 15)),
        ("", None),
    ],
)
def test_fracfocus_source_dates_cover_the_measured_formats(raw, expected):
    assert parse_source_date(raw) == expected


def test_fracfocus_source_dates_reject_an_unmeasured_format():
    with pytest.raises(ValueError, match="unsupported FracFocus timestamp"):
        parse_source_date("15-Feb-2020")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, ("no_report", None)),
        ("", ("no_report", None)),
        ("   ", ("no_report", None)),
        ("0", ("reported_zero", Decimal("0"))),
        ("0.0", ("reported_zero", Decimal("0.0"))),
        ("6342549", ("reported", Decimal("6342549"))),
        ("6342549.25", ("reported", Decimal("6342549.25"))),
    ],
)
def test_a_base_water_literal_is_classified_before_it_is_valued(raw, expected):
    assert classify_base_water(raw) == expected


@pytest.mark.parametrize("raw", ["not-a-number", "12,345", "-1", "1e6", "1 000"])
def test_an_unparseable_base_water_literal_raises_so_it_reaches_quarantine(raw):
    """Promoting it as null would report an unreadable value as an absent one."""
    with pytest.raises(ValueError, match="unparseable"):
        classify_base_water(raw)


def test_the_plausibility_bound_is_inclusive_of_the_number_the_rule_states():
    bound = Decimal("50000000")

    assert exceeds_plausibility(Decimal("50000001"), bound) is True
    assert exceeds_plausibility(bound, bound) is False
    assert exceeds_plausibility(Decimal("0"), bound) is False
    assert exceeds_plausibility(None, bound) is False
