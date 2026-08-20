"""M-2: one length conversion, in one module, with one name that says which way it points."""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import pytest

from glasswell.units import METRES_PER_FOOT, metres_to_feet

SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src" / "glasswell"
UNITS_MODULE = SOURCE_ROOT / "units.py"
# The reciprocal is irrational, so any literal spelling of it is a truncation, not a factor.
_RECIPROCAL_RE = re.compile(r"3\.2808\d*")


def test_the_foot_is_exactly_0_3048_metres():
    assert Decimal("0.3048") == METRES_PER_FOOT


def test_one_foot_of_metres_is_one_foot():
    assert metres_to_feet(METRES_PER_FOOT) == Decimal(1)


@pytest.mark.parametrize(
    ("metres", "feet"), [("304.8", "1000"), ("0", "0"), ("4593.336", "15070")]
)
def test_whole_feet_convert_without_a_remainder(metres, feet):
    assert metres_to_feet(Decimal(metres)) == Decimal(feet)


def test_the_conversion_does_not_round():
    """Rounding belongs at the serving edge; a converter that rounds cannot be summed."""
    converted = metres_to_feet(Decimal("1"))

    assert converted != converted.quantize(Decimal("0.01"))
    assert str(converted).startswith("3.28083989501312")


def test_no_other_module_spells_the_conversion_itself():
    offenders = [
        path.relative_to(SOURCE_ROOT).as_posix()
        for path in SOURCE_ROOT.rglob("*.py")
        if path != UNITS_MODULE
        and (_RECIPROCAL_RE.search(path.read_text()) or "0.3048" in path.read_text())
    ]

    assert offenders == [], f"a second length constant lives in {offenders} (M-2)"
