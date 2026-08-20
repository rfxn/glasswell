"""Unit conversion, in one place, so two paths cannot compute one fact differently (M-2).

The name says which way the constant points. `0.3048` is metres per foot — naming it
`feet_per_metre` and dividing by it arrives at the right answer for the wrong stated reason,
and the next reader who moves it between modules introduces a 10.76x error.
"""

from __future__ import annotations

from decimal import Decimal

# Exact by definition (NIST SP 811 B.6): one international foot is 0.3048 m. The reciprocal
# is not exact, so any literal spelling of 3.280839... is a truncation, not a factor.
METRES_PER_FOOT = Decimal("0.3048")


def metres_to_feet(metres: Decimal) -> Decimal:
    """Unrounded on purpose: a converter that rounds cannot be summed back to a served figure."""
    return Decimal(metres) / METRES_PER_FOOT
