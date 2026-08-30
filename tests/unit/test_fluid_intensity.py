"""cr_ff_fluid_intensity_1's executor: a value, or a reason — never a number with neither."""

from __future__ import annotations

from decimal import Decimal

import pytest

from glasswell.api.routers.completions import IntensityPolicy, _fluid_intensity

POLICY = IntensityPolicy(
    min_lateral_ft=Decimal("1000"),
    max_gal_per_ft=Decimal("5000"),
    rule_id="cr_ff_fluid_intensity_1",
)

MEASURED_MINIMUM_FT = Decimal("0.24")


@pytest.mark.parametrize(
    ("volume", "lateral", "expected"),
    [
        (Decimal("5917362"), Decimal("9862.27353475175"), "reported"),
        (None, Decimal("9862.27"), "no_report"),
        (Decimal("5917362"), None, "lateral_length_unavailable"),
        (Decimal("5917362"), MEASURED_MINIMUM_FT, "lateral_length_implausible"),
        (Decimal("5917362"), Decimal("999.99"), "lateral_length_implausible"),
        (Decimal("60000000"), Decimal("9862.27"), "intensity_out_of_range"),
        (Decimal("0"), Decimal("9862.27"), "reported"),
    ],
    ids=[
        "an-ordinary-completion",
        "no-disclosure",
        "no-geometry",
        "the-measured-live-minimum",
        "just-under-the-floor",
        "over-the-ceiling",
        "a-filed-zero-is-a-filing",
    ],
)
def test_every_outcome_is_named(volume, lateral, expected) -> None:
    value, semantics = _fluid_intensity(volume, lateral, POLICY)

    assert semantics == expected
    assert (value is None) == (expected != "reported")


def test_the_measured_live_minimum_is_withdrawn_rather_than_served() -> None:
    """0.24 ft is the real ND minimum, and it would serve 24 million gal/ft with a handle."""
    naive = Decimal("5917362") / MEASURED_MINIMUM_FT
    value, semantics = _fluid_intensity(Decimal("5917362"), MEASURED_MINIMUM_FT, POLICY)

    assert naive > Decimal("20000000")
    assert (value, semantics) == (None, "lateral_length_implausible")


def test_the_bounds_are_inclusive_of_the_numbers_the_rule_states() -> None:
    at_floor, floor_semantics = _fluid_intensity(
        Decimal("1000"), POLICY.min_lateral_ft, POLICY
    )
    at_ceiling, ceiling_semantics = _fluid_intensity(
        POLICY.max_gal_per_ft * POLICY.min_lateral_ft, POLICY.min_lateral_ft, POLICY
    )

    assert (at_floor, floor_semantics) == (Decimal("1"), "reported")
    assert (at_ceiling, ceiling_semantics) == (POLICY.max_gal_per_ft, "reported")


def test_a_filed_zero_is_an_intensity_of_zero_and_not_an_absence() -> None:
    """37 ND disclosures filed a zero; that is a filing, and it survives the division."""
    value, semantics = _fluid_intensity(Decimal("0"), Decimal("9862.27"), POLICY)

    assert (value, semantics) == (Decimal("0"), "reported")
