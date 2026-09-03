"""Allocation v0: an equal share among the wells eligible in the month, sign-aware.

The lease volume is a fact and the per-well share is an estimate, so this module produces
estimates and says so: every share it returns carries the model id, its class and the count of
wells it was divided among. It reads no database and writes none — the Texas mart and the
Montana back-test both import it, so the bed and the consumer run identical code.

The rule this implements is `cr_tx_allocation_v0_1`, which cites it by name.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

MODEL_ID = "alloc_v0_2026_09"

OBSERVED_GAS_WELL = "observed_gas_well"
OBSERVED_SINGLE_WELL_LEASE = "observed_single_well_lease"
ALLOCATED_EQUAL_SHARE = "allocated_equal_share"
ALLOCATED_AFTER_STATUS_CHANGE = "allocated_after_status_change"
EXCLUDED_AFTER_PLUG = "excluded_after_plug"
UNALLOCATED = "unallocated"

WELL_OBSERVED = "well_observed"
LEASE_ALLOCATED = "lease_allocated"


@dataclass(frozen=True, slots=True)
class Eligible:
    """One candidate for a lease-month's volume, as the eligibility predicate resolved it."""

    api10: str
    eligible: bool
    plugged_without_date: bool = False


@dataclass(frozen=True, slots=True)
class Share:
    api10: str
    volume: Decimal
    allocation_class: str
    granularity: str
    eligible_wells: int


def _class_for(candidate: Eligible, eligible_wells: int, gas_lease: bool) -> tuple[str, str]:
    if not candidate.eligible:
        return EXCLUDED_AFTER_PLUG, LEASE_ALLOCATED
    if gas_lease:
        return OBSERVED_GAS_WELL, WELL_OBSERVED
    if eligible_wells == 1:
        return OBSERVED_SINGLE_WELL_LEASE, WELL_OBSERVED
    if candidate.plugged_without_date:
        return ALLOCATED_AFTER_STATUS_CHANGE, LEASE_ALLOCATED
    return ALLOCATED_EQUAL_SHARE, LEASE_ALLOCATED


def allocate_lease_month(
    volume: Decimal, candidates: list[Eligible], *, gas_lease: bool = False
) -> list[Share]:
    """The lease-month's volume as one share per candidate, summing back to it exactly.

    The split is computed on `abs(volume)` and the sign re-applied, because `floor` on a signed
    value gives each of two wells -4 for a -7 correction and hands the remainder well +1 bbl of
    production in a month the operator filed a correction for — which conservation would not
    catch, because it conserves. An ineligible candidate takes zero and its share is
    redistributed among the rest, so a well is excluded from months after its own filed
    plugging without the lease's volume going missing.
    """
    eligible = [candidate for candidate in candidates if candidate.eligible]
    if not eligible:
        return []

    count = len(eligible)
    magnitude = abs(volume)
    base = (magnitude // count).quantize(Decimal(1))
    remainder = magnitude - base * count
    sign = -1 if volume < 0 else 1
    remainder_holder = min(candidate.api10 for candidate in eligible)

    shares: list[Share] = []
    for candidate in candidates:
        allocation_class, granularity = _class_for(candidate, count, gas_lease)
        if not candidate.eligible:
            share = Decimal(0)
        elif count == 1 or gas_lease:
            share = volume
        else:
            share = base + (remainder if candidate.api10 == remainder_holder else Decimal(0))
            share *= sign
        shares.append(
            Share(
                api10=candidate.api10,
                volume=share,
                allocation_class=allocation_class,
                granularity=granularity,
                eligible_wells=count,
            )
        )
    return shares


def symmetric_error(allocated: Decimal, truth: Decimal) -> Decimal | None:
    """`(allocated - truth) / (allocated + truth)`, bounded on [-1, 1].

    None where both sides are zero, which is the commonest case rather than an edge: a well
    produced nothing in a month it was eligible for. A relative error would be unbounded above
    and undefined there, so the excluded share is served as its own figure instead of being
    folded into a statistic that cannot express it.
    """
    total = allocated + truth
    if total == 0:
        return None
    return (allocated - truth) / total
