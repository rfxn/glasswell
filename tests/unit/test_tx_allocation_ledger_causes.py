"""Why a Texas lease-month reached no well, as a closed vocabulary that can be written.

The hard rule is that a reject carries a reason code, and a wrong code is not a code. Two of
the four the ledger admitted were unreachable by construction -- `_cause` runs only where
nothing was eligible, so a code that describes a volume with an eligible well cannot be
written -- and a third was returned for the opposite fact: a lease whose wells were all
plugged in 2015 was filed under "all wells after month" (gate-tx H-14).
"""

from __future__ import annotations

from datetime import date

import pytest

from glasswell.allocation.v0 import Eligible
from glasswell.marts.tx_allocation import CAUSES, _cause

pytestmark = pytest.mark.unit

MONTH = date(2024, 6, 1)


def well(api10: str, *, completion: date | None = None, plug: date | None = None):
    return {"api10": api10, "completion_date": completion, "plug_date": plug}


def candidates(*api10s: str) -> list[Eligible]:
    return [Eligible(api10=api10, eligible=False) for api10 in api10s]


def test_a_lease_month_with_no_crosswalk_row_says_so() -> None:
    assert _cause([], [], MONTH) == "no_crosswalk_row"


def test_wells_completed_after_the_month_are_not_wells_plugged_before_it() -> None:
    wells = [well("4200300001", completion=date(2025, 1, 1))]

    assert _cause(candidates("4200300001"), wells, MONTH) == "all_wells_after_month"


def test_a_lease_whose_wells_were_all_plugged_gets_its_own_code() -> None:
    """The finding: this returned `all_wells_after_month`, which is the opposite fact."""
    wells = [
        well("4200300001", plug=date(2015, 3, 31)),
        well("4200300002", plug=date(2015, 4, 30)),
    ]

    assert (
        _cause(candidates("4200300001", "4200300002"), wells, MONTH)
        == "all_wells_plugged_before_month"
    )


def test_a_mixture_of_reasons_is_the_general_code_rather_than_either_specific_one() -> None:
    wells = [
        well("4200300001", completion=date(2025, 1, 1)),
        well("4200300002", plug=date(2015, 4, 30)),
    ]

    assert _cause(candidates("4200300001", "4200300002"), wells, MONTH) == "no_eligible_well"


def test_the_vocabulary_holds_no_code_this_function_cannot_return() -> None:
    """`negative_correction` was in the list, in the CHECK and in the served rule's spec, and
    nothing could ever write it: a negative lease-month with an eligible well allocates."""
    reachable = {
        _cause([], [], MONTH),
        _cause(candidates("4200300001"), [well("4200300001", completion=date(2025, 1, 1))], MONTH),
        _cause(candidates("4200300001"), [well("4200300001", plug=date(2015, 1, 1))], MONTH),
        _cause(
            candidates("4200300001", "4200300002"),
            [
                well("4200300001", completion=date(2025, 1, 1)),
                well("4200300002", plug=date(2015, 4, 30)),
            ],
            MONTH,
        ),
    }

    assert reachable == set(CAUSES)
