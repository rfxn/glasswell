from datetime import date

import pytest

from glasswell.ingest.fracfocus import parse_source_date

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
