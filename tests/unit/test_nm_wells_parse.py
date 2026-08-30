"""The two readings that would be silently wrong at 321,510 records, tested at one.

Both live in `ingest/nm_wells.py` and neither needs a database: the ordinate parse, which every
record in the artifact depends on because every ordinate is scientific notation, and the
coordinate-pair classification, whose precedence is the only thing between four New Mexico wells
and a valid point in the Gulf of Guinea.
"""

from __future__ import annotations

import pytest

from glasswell.ingest.nm_wells import classify_pair, parse_ordinate

pytestmark = pytest.mark.unit

# A record verbatim from the sealed artifact.
LATITUDE = "3.516891893872920e+001"
LONGITUDE = "-1.065623232665890e+002"


def test_an_ordinate_parses_out_of_scientific_notation_to_its_value():
    """639,237 of 639,237 ordinates are scientific notation and none is a plain decimal, so a
    parser that slices characters is wrong on the whole file rather than on a subset."""
    assert parse_ordinate(LATITUDE) == pytest.approx(35.16891893872920)
    assert parse_ordinate(LONGITUDE) == pytest.approx(-106.5623232665890)


def test_a_string_slice_of_the_same_value_is_not_the_value():
    """The failure mode stated as an assertion rather than as a warning in a comment."""
    assert float(LATITUDE[:5]) != pytest.approx(parse_ordinate(LATITUDE))


@pytest.mark.parametrize("value", [None, "", "   ", "not a number"])
def test_an_unreadable_ordinate_is_absent_rather_than_zero(value):
    """Zero is a coordinate. Absent is not, and collapsing the two is how a sentinel is born."""
    assert parse_ordinate(value) is None


def test_a_zero_ordinate_parses_as_zero_and_is_judged_later():
    assert parse_ordinate("0.000000000000000e+000") == 0.0


PAIRS = [
    ("usable", 35.168, -106.562, "promote"),
    ("both_zero", 0.0, 0.0, "coordinate_sentinel"),
    ("longitude_zero_only", 35.168, 0.0, "coordinate_sentinel"),
    ("latitude_zero_only", 0.0, -106.562, "coordinate_sentinel"),
    ("both_nil", None, None, "coordinate_absent"),
    ("latitude_nil_longitude_present", None, -106.562, "coordinate_absent"),
    ("latitude_present_longitude_nil", 0.0, None, "coordinate_absent"),
]


@pytest.mark.parametrize(("name", "latitude", "longitude", "expected"), PAIRS)
def test_every_population_of_the_artifact_maps_to_its_declared_outcome(
    name, latitude, longitude, expected
):
    assert classify_pair(latitude, longitude) == expected, name


def test_the_pair_is_classified_and_not_each_ordinate_independently():
    """A good latitude beside a zero longitude is the case a latitude-only rule cannot see, and
    ST_MakePoint(0.0, 35.16...) is a perfectly valid geometry about 9,000 km from New Mexico."""
    assert classify_pair(35.168, None) == "coordinate_absent"
    assert classify_pair(35.168, 0.0) == "coordinate_sentinel"
    assert classify_pair(35.168, -106.562) == "promote"


def test_nil_takes_precedence_over_zero_on_the_mixed_record():
    """One real record is zero on one ordinate and nil on the other. Two independent
    per-ordinate rules cannot say which outcome it takes; the precedence can."""
    assert classify_pair(0.0, None) == "coordinate_absent"
    assert classify_pair(None, 0.0) == "coordinate_absent"


def test_the_precedence_is_read_from_the_rule_rather_than_fixed_in_the_code():
    """It is a registry decision, so reversing it in the rule reverses it in the classifier."""
    reversed_order = ("zero", "nil")

    assert classify_pair(0.0, None, precedence=reversed_order) == "coordinate_sentinel"
    assert classify_pair(0.0, None) == "coordinate_absent"


def test_no_promotable_pair_carries_a_zero_ordinate():
    """The property ST_MakePoint depends on, asserted directly over every population above."""
    promotable = [
        (latitude, longitude)
        for _, latitude, longitude, outcome in PAIRS
        if outcome == "promote"
    ]

    assert promotable
    for latitude, longitude in promotable:
        assert latitude not in (None, 0.0)
        assert longitude not in (None, 0.0)
