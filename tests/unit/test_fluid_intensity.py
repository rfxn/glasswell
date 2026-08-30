"""cr_ff_fluid_intensity_1's executor: a value, or a reason — never a number with neither."""

from __future__ import annotations

from decimal import Decimal

import pytest

from glasswell.api.routers.completions import (
    ABSENT_VOLUME_SEMANTICS,
    INTENSITY_RULE_UNREGISTERED,
    IntensityPolicy,
    _fluid_intensity,
    _intensity_or_reason,
)
from glasswell.marts.producing import CANONICAL_NULL_SEMANTICS

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
    value, semantics = _fluid_intensity(volume, lateral, POLICY, "no_report")

    assert semantics == expected
    assert (value is None) == (expected != "reported")


def test_the_measured_live_minimum_is_withdrawn_rather_than_served() -> None:
    """0.24 ft is the real ND minimum, and it would serve 24 million gal/ft with a handle."""
    naive = Decimal("5917362") / MEASURED_MINIMUM_FT
    value, semantics = _fluid_intensity(
        Decimal("5917362"), MEASURED_MINIMUM_FT, POLICY, "reported"
    )

    assert naive > Decimal("20000000")
    assert (value, semantics) == (None, "lateral_length_implausible")


def test_the_bounds_are_inclusive_of_the_numbers_the_rule_states() -> None:
    at_floor, floor_semantics = _fluid_intensity(
        Decimal("1000"), POLICY.min_lateral_ft, POLICY, "reported"
    )
    at_ceiling, ceiling_semantics = _fluid_intensity(
        POLICY.max_gal_per_ft * POLICY.min_lateral_ft, POLICY.min_lateral_ft, POLICY, "reported"
    )

    assert (at_floor, floor_semantics) == (Decimal("1"), "reported")
    assert (at_ceiling, ceiling_semantics) == (POLICY.max_gal_per_ft, "reported")


def test_a_filed_zero_is_an_intensity_of_zero_and_not_an_absence() -> None:
    """37 ND disclosures filed a zero; that is a filing, and it survives the division."""
    value, semantics = _fluid_intensity(
        Decimal("0"), Decimal("9862.27"), POLICY, "reported_zero"
    )

    assert (value, semantics) == (Decimal("0"), "reported")


def test_an_unregistered_rule_is_reported_as_a_registry_gap_not_as_no_report() -> None:
    """no_report would say the source disclosed nothing; the source disclosed 5,917,362 gal.

    The precedent is wells.py:97-100, where an unregistered producing definition short-circuits
    rather than answering `unknown` for every well.
    """
    value, semantics = _intensity_or_reason(
        Decimal("5917362"), Decimal("9862.27"), None, "reported"
    )

    assert (value, semantics) == (None, INTENSITY_RULE_UNREGISTERED)
    assert semantics != "no_report"


def test_a_registered_rule_still_reaches_the_bounded_answer() -> None:
    """The wrapper adds one state and changes none of the five the rule declares."""
    assert _intensity_or_reason(
        Decimal("5917362"), Decimal("9862.27353475175"), POLICY, "reported"
    ) == _fluid_intensity(Decimal("5917362"), Decimal("9862.27353475175"), POLICY, "reported")
    assert _intensity_or_reason(None, Decimal("9862.27"), POLICY, "no_report")[1] == "no_report"


def _reasons_the_code_can_return() -> set[str]:
    """Every reason literal the two intensity functions return, read off their own source.

    Derived rather than hand-listed: a set built from example inputs proves only that those
    inputs' reasons are declared, so a branch nobody thought to call would not be in it. The
    walk is over `return` statements, so adding a branch adds a member without editing a test.
    """
    import ast
    import inspect

    from glasswell.api.routers import completions

    tree = ast.parse(inspect.getsource(completions))
    reasons: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name not in ("_fluid_intensity", "_intensity_or_reason"):
            continue
        for inner in ast.walk(node):
            # A tuple return is `(value, reason)`; `return _fluid_intensity(...)` is a Call and
            # delegates, so it contributes the callee's reasons rather than one of its own.
            if isinstance(inner, ast.Return) and isinstance(inner.value, ast.Tuple):
                reason = inner.value.elts[1]
                if isinstance(reason, ast.Constant) and isinstance(reason.value, str):
                    reasons.add(reason.value)
                elif isinstance(reason, ast.Name):
                    reasons.add(getattr(completions, reason.id))
    return reasons


def test_the_rule_declares_exactly_the_reasons_the_code_can_return() -> None:
    """R8: a served reason the rule does not admit is a mapping made in code — and a declared
    reason the code can never return is a vocabulary that describes something else.

    Equality, not containment, so both directions fail. This is a companion to the per-branch
    tests above, not a replacement for them: it would not have caught the defect it was written
    for, because `no_report` is a member the code may legitimately return — just not for the
    reason it was being returned. A vocabulary check cannot tell you a branch picked the wrong
    declared member; only a test of that branch can.

    ABSENT_VOLUME_SEMANTICS is unioned in because those reasons leave `_fluid_intensity`
    through a variable rather than a literal, so the source walk cannot see them. Reading the
    constant that names the pass-through is still derived — but the seam is real, and it is the
    one `test_every_class_the_source_can_record_survives_the_division` covers directly.
    """
    from glasswell.seed.conformance_fracfocus import FRACFOCUS_RULES

    rule = next(r for r in FRACFOCUS_RULES if r["rule_id"] == "cr_ff_fluid_intensity_1")
    declared = set(rule["spec"]["null_semantics_vocabulary"])
    returned = _reasons_the_code_can_return() | set(ABSENT_VOLUME_SEMANTICS)

    assert returned == declared
    assert INTENSITY_RULE_UNREGISTERED in returned, "the source walk found no derived reason"
    assert len(returned) == 7


@pytest.mark.parametrize("semantics", CANONICAL_NULL_SEMANTICS)
def test_every_class_the_source_can_record_survives_the_division(semantics: str) -> None:
    """Driven from the source's vocabulary, not the code's returns.

    The guard above compares the code and the rule to each other, so a class *both* are
    missing is invisible to it — which is how a withheld volume came to be served as
    `no_report`, one row under a Base fluid row that had it right. This drives the four classes
    canonical can record and asserts each survives the quotient as itself.
    """
    volume = None if semantics in ABSENT_VOLUME_SEMANTICS else Decimal("5917362")
    value, reason = _fluid_intensity(volume, Decimal("9862.27353475175"), POLICY, semantics)

    if semantics in ABSENT_VOLUME_SEMANTICS:
        assert (value, reason) == (None, semantics)
    else:
        assert (value, reason) == (Decimal("5917362") / Decimal("9862.27353475175"), "reported")


def test_a_withheld_volume_does_not_report_as_an_undisclosed_one() -> None:
    """The blocker, stated as its own test: these are two facts and must stay two."""
    withheld = _fluid_intensity(None, Decimal("9862.27"), POLICY, "withheld")
    undisclosed = _fluid_intensity(None, Decimal("9862.27"), POLICY, "no_report")

    assert withheld == (None, "withheld")
    assert undisclosed == (None, "no_report")
    assert withheld[1] != undisclosed[1]


def test_every_absent_class_the_source_records_is_one_the_rule_declares() -> None:
    """The pairing the guard above cannot make on its own: source vocabulary against rule."""
    from glasswell.seed.conformance_fracfocus import FRACFOCUS_RULES

    rule = next(r for r in FRACFOCUS_RULES if r["rule_id"] == "cr_ff_fluid_intensity_1")
    declared = set(rule["spec"]["null_semantics_vocabulary"])

    assert set(ABSENT_VOLUME_SEMANTICS) <= declared


def test_the_numerator_s_class_cannot_be_omitted_by_a_caller() -> None:
    """A default would hold the collapse one omitted argument away, and the resulting value —
    a declared member returned for the wrong reason — is the one shape the vocabulary guard
    above is blind to. Required, so a new call site cannot reinstate it silently."""
    import inspect

    for function in (_fluid_intensity, _intensity_or_reason):
        parameter = inspect.signature(function).parameters["volume_semantics"]
        assert parameter.default is inspect.Parameter.empty, function.__name__

    with pytest.raises(TypeError):
        _fluid_intensity(None, Decimal("9862.27"), POLICY)  # type: ignore[call-arg]
