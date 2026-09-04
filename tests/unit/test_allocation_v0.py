"""The split, and the two cases that would be wrong without it.

Conservation is the invariant, so every case here asserts the shares sum back to the lease
volume exactly. That is not a rounding tolerance: the remainder is placed deliberately, so a
non-zero difference is a defect rather than a residual.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from glasswell.allocation.v0 import (
    ALLOCATED_AFTER_STATUS_CHANGE,
    ALLOCATED_EQUAL_SHARE,
    EXCLUDED_AFTER_PLUG,
    LEASE_ALLOCATED,
    MODEL_ID,
    OBSERVED_GAS_WELL,
    OBSERVED_SINGLE_WELL_LEASE,
    WELL_OBSERVED,
    Eligible,
    allocate_lease_month,
    symmetric_error,
)


def wells(*api10s: str) -> list[Eligible]:
    return [Eligible(api10=api10, eligible=True) for api10 in api10s]


def test_the_model_id_is_the_versioned_artifact_and_not_the_rule() -> None:
    """The rule is the R8 decision with a rationale and a date; the model is what computed the
    number, and a figure carries both because they answer different questions."""
    assert MODEL_ID == "alloc_v0_2026_09"


def test_an_exact_division_gives_every_well_the_same_share() -> None:
    shares = allocate_lease_month(Decimal(900), wells("4200300001", "4200300002", "4200300003"))

    assert [share.volume for share in shares] == [Decimal(300)] * 3
    assert sum(share.volume for share in shares) == Decimal(900)


def test_the_remainder_goes_to_the_lowest_api10() -> None:
    """Deterministic on purpose: a remainder placed by row order would move the figure when
    the crosswalk's row order moved, and nothing would say so."""
    shares = allocate_lease_month(Decimal(901), wells("4200300003", "4200300001", "4200300002"))
    by_api = {share.api10: share.volume for share in shares}

    assert by_api == {
        "4200300001": Decimal(301),
        "4200300002": Decimal(300),
        "4200300003": Decimal(300),
    }
    assert sum(by_api.values()) == Decimal(901)


@pytest.mark.parametrize(
    ("volume", "count"), [(Decimal(-7), 2), (Decimal(-1), 3), (Decimal(-100), 4)]
)
def test_a_negative_correction_gives_no_well_a_positive_barrel(
    volume: Decimal, count: int
) -> None:
    """M-14. floor(-7/2) is -4 twice and the remainder needed to conserve is +1, so a split on
    the signed value hands the lowest-API-10 well production in a correction month — and
    conservation would not catch it, because it conserves."""
    shares = allocate_lease_month(
        volume, wells(*(f"420030000{index}" for index in range(1, count + 1)))
    )

    assert sum(share.volume for share in shares) == volume
    assert all(share.volume <= 0 for share in shares)


def test_a_single_well_oil_lease_is_observed_and_not_allocated() -> None:
    """granularity cannot tell the two observed classes apart, because both are well_observed;
    allocation_class is what does."""
    shares = allocate_lease_month(Decimal(500), wells("4200300001"))

    assert shares[0].allocation_class == OBSERVED_SINGLE_WELL_LEASE
    assert shares[0].granularity == WELL_OBSERVED
    assert shares[0].volume == Decimal(500)


def test_a_gas_lease_passes_the_lease_volume_through() -> None:
    shares = allocate_lease_month(Decimal(12000), wells("4200300010"), gas_lease=True)

    assert shares[0].allocation_class == OBSERVED_GAS_WELL
    assert shares[0].granularity == WELL_OBSERVED


def test_a_gas_lease_with_two_eligible_wells_allocates_rather_than_multiplying() -> None:
    """H-13. The pass-through rests on 4F.3's premise -- one gas well per lease -- and the
    crosswalk is not asserted to honour it. Passing the volume through to each of two wells
    returned 24,000 mcf for a 12,000 mcf lease-month, labelled observed on both.
    """
    shares = allocate_lease_month(
        Decimal(12000), wells("4200300001", "4200300002"), gas_lease=True
    )

    assert sum(share.volume for share in shares) == Decimal(12000)
    assert {share.allocation_class for share in shares} == {ALLOCATED_EQUAL_SHARE}
    assert {share.granularity for share in shares} == {LEASE_ALLOCATED}
    assert {share.eligible_wells for share in shares} == {2}
    assert [share.volume for share in shares] == [Decimal(6000), Decimal(6000)]


def test_a_gas_lease_whose_second_well_is_ineligible_still_passes_through() -> None:
    """The premise holds again once the second well is out of the month: one eligible well is
    one eligible well, whatever the lease's other wellbores are doing."""
    candidates = [
        Eligible(api10="4200300001", eligible=True),
        Eligible(api10="4200300002", eligible=False),
    ]

    shares = allocate_lease_month(Decimal(12000), candidates, gas_lease=True)

    passed = next(share for share in shares if share.api10 == "4200300001")
    assert passed.allocation_class == OBSERVED_GAS_WELL
    assert passed.volume == Decimal(12000)


def test_a_multi_well_share_is_labelled_allocated_and_counts_its_divisor() -> None:
    shares = allocate_lease_month(Decimal(900), wells("4200300001", "4200300002"))

    assert {share.allocation_class for share in shares} == {ALLOCATED_EQUAL_SHARE}
    assert {share.granularity for share in shares} == {LEASE_ALLOCATED}
    assert {share.eligible_wells for share in shares} == {2}


def test_an_undated_plugged_well_stays_eligible_and_is_labelled() -> None:
    """M-18. Refusing to filter on a today-snapshot and refusing to label with one are two
    different decisions, and v0 makes only the first."""
    candidates = [
        Eligible(api10="4200300001", eligible=True),
        Eligible(api10="4200300002", eligible=True, plugged_without_date=True),
    ]

    shares = allocate_lease_month(Decimal(640), candidates)
    by_api = {share.api10: share for share in shares}

    assert by_api["4200300002"].allocation_class == ALLOCATED_AFTER_STATUS_CHANGE
    assert by_api["4200300002"].volume == Decimal(320)
    assert sum(share.volume for share in shares) == Decimal(640)


def test_a_well_past_its_filed_plug_date_takes_zero_and_its_share_is_redistributed() -> None:
    """Excluding a well from months after its own filed plugging is correctness, not
    retro-deletion — and V-1 still conserves exactly because the share moves rather than
    vanishing."""
    candidates = [
        Eligible(api10="4200300001", eligible=True),
        Eligible(api10="4200300002", eligible=False),
    ]

    shares = allocate_lease_month(Decimal(500), candidates)
    by_api = {share.api10: share for share in shares}

    assert by_api["4200300002"].allocation_class == EXCLUDED_AFTER_PLUG
    assert by_api["4200300002"].volume == Decimal(0)
    assert by_api["4200300001"].volume == Decimal(500)
    assert sum(share.volume for share in shares) == Decimal(500)


def test_a_lease_month_with_no_eligible_well_allocates_nothing() -> None:
    """Volume with no well to carry it is a ledger row with a cause, never a share."""
    assert allocate_lease_month(Decimal(120), []) == []
    assert allocate_lease_month(
        Decimal(120), [Eligible(api10="4200300001", eligible=False)]
    ) == []


def test_the_error_statistic_is_bounded_and_says_nothing_where_nothing_happened() -> None:
    """N-7. Both sides zero is the commonest case rather than an edge, and the excluded share
    is served as its own figure instead of being folded into a statistic that cannot hold it."""
    assert symmetric_error(Decimal(3), Decimal(1)) == Decimal("0.5")
    assert symmetric_error(Decimal(1), Decimal(3)) == Decimal("-0.5")
    assert symmetric_error(Decimal(0), Decimal(5)) == Decimal(-1)
    assert symmetric_error(Decimal(5), Decimal(0)) == Decimal(1)
    assert symmetric_error(Decimal(0), Decimal(0)) is None


def test_the_statistic_refuses_a_pair_it_cannot_bound() -> None:
    """H-15. `(a - t) / (a + t)` is bounded on [-1, 1] only where both sides carry the same
    sign: `symmetric_error(3, -1)` is 2 and `symmetric_error(-5, 1)` is 1.5, and the rule this
    feeds publishes a range of [-1, 1] into a numeric(5, 4) column that would store either.
    """
    assert symmetric_error(Decimal(3), Decimal(-1)) is None
    assert symmetric_error(Decimal(-5), Decimal(1)) is None
    assert symmetric_error(Decimal(-3), Decimal(-1)) is None


def test_the_statistic_is_unchanged_inside_its_domain() -> None:
    assert symmetric_error(Decimal(0), Decimal(0)) is None
    assert symmetric_error(Decimal(300), Decimal(300)) == Decimal(0)
    assert symmetric_error(Decimal(600), Decimal(200)) == Decimal("0.5")
    assert symmetric_error(Decimal(0), Decimal(400)) == Decimal(-1)
