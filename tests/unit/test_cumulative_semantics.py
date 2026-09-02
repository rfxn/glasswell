"""The per-well cumulative's definition: what the total admits, and what the span holds.

The six month classes are the point. A total that cannot say how many months are behind it,
or that reports a filed zero and an absent filing as the same gap, is the defect this track
exists to close, so the parts are asserted to reconcile to the span in every case.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest import mock

import pytest

from glasswell.api.routers import production
from glasswell.marts import cumulatives
from glasswell.marts.cumulatives import (
    ADMITTED_NULL_SEMANTICS,
    CUMULATIVE_JURISDICTIONS,
    STATE_API_PREFIXES,
    WITHHOLDING_BY_PREFIX,
    cumulative_semantics_predicate,
    filed_span,
    month_class_counts,
)

JAN = date(2026, 1, 1)
FEB = date(2026, 2, 1)
MAR = date(2026, 3, 1)
APR = date(2026, 4, 1)


def test_the_predicate_names_what_the_total_admits() -> None:
    predicate = cumulative_semantics_predicate()

    assert "'reported'" in predicate
    assert "'reported_zero'" in predicate
    assert "no_report" not in predicate
    assert "withheld" not in predicate
    assert ADMITTED_NULL_SEMANTICS == ("reported", "reported_zero")


def test_the_admitted_set_excludes_everything_the_producing_rule_refuses_as_evidence() -> None:
    """marts.producing.NEVER_QUALIFYING_SEMANTICS is the same judgement, one layer up."""
    from glasswell.marts.producing import NEVER_QUALIFYING_SEMANTICS

    assert not set(ADMITTED_NULL_SEMANTICS) & set(NEVER_QUALIFYING_SEMANTICS) - {"reported_zero"}
    assert "no_report" not in ADMITTED_NULL_SEMANTICS
    assert "withheld" not in ADMITTED_NULL_SEMANTICS


def test_the_withholding_mapping_agrees_with_the_series_endpoint() -> None:
    """One ledger predicate: the mart and /production must read the same rows (M2)."""
    source_id, reason_code = WITHHOLDING_BY_PREFIX["33"][0]

    assert f"source_id = '{source_id}'" in production._WITHHELD_MONTHS
    assert f"reason_code = '{reason_code}'" in production._WITHHELD_MONTHS


def test_registering_a_withholding_source_does_not_widen_the_population_served() -> None:
    """The served scope is its own decision (gate-v075 MAJOR-1).

    STATE_API_PREFIXES scopes the mart refresh, `population_scope.states_served` on
    /v1/wells/vintage-cohorts, the cumulatives link on the well card and the per-well 404
    text. Deriving it from WITHHOLDING_SOURCES made all four move when someone registered a
    quarantine source — Texas is named two lines above the registry as the next entrant, and
    it has no production at all, so the mart would have claimed 359,421 wells as
    never_reported.
    """
    hypothetical = dict(WITHHOLDING_BY_PREFIX)
    hypothetical["42"] = (("tx_ewa_xlsx", "confidential_withheld"),)

    with mock.patch.object(cumulatives, "WITHHOLDING_BY_PREFIX", hypothetical):
        assert cumulatives.STATE_API_PREFIXES == ("33",)
        sources, reasons = cumulatives._withholding_pairs()

    # The ledger query stays scoped too: an out-of-scope state's source cannot reach it.
    assert sources == ["nd_mpr_xlsx"]
    assert reasons == ["confidential_withheld"]


def test_the_served_scope_is_its_own_declaration_and_not_a_view_of_the_withholding_registry(
) -> None:
    """Guards the shape, not just today's value: deriving the scope from either withholding
    mapping reintroduces MAJOR-1 while every value assertion above still passes.

    The declaration is jurisdiction codes resolved through the registry, so the scope moves
    only when someone edits it, and no API prefix is spelled in the module (P5's scan).
    """
    source = Path(cumulatives.__file__).read_text(encoding="utf-8")

    assert source.count("\nCUMULATIVE_JURISDICTIONS: tuple[str, ...] = (") == 1
    assert "for code in CUMULATIVE_JURISDICTIONS" in source
    assert "STATE_API_PREFIXES = tuple(WITHHOLDING_SOURCES)" not in source
    assert "for code in WITHHOLDING_SOURCES" not in source
    assert "tuple(WITHHOLDING_BY_PREFIX)" not in source
    assert CUMULATIVE_JURISDICTIONS == ("ND",)
    assert STATE_API_PREFIXES == ("33",)


def test_a_span_is_the_union_of_every_class_and_the_withheld_ledger() -> None:
    assert filed_span({FEB: "reported"}, [APR]) == (FEB, APR)
    assert filed_span({}, [JAN]) == (JAN, JAN)


def test_a_well_that_filed_nothing_and_had_nothing_withheld_has_no_span() -> None:
    """M5: a zero here would collapse a whole-well absence into a filed zero."""
    assert filed_span({}, []) == (None, None)
    assert month_class_counts((None, None), {}, []).span_months == 0


CASES = (
    (
        "a stored no_report sits inside the span and is not a gap",
        {JAN: "reported", FEB: "no_report", MAR: "reported"},
        [],
        {"reported": 2, "no_report_stored": 1, "absent": 0},
    ),
    (
        "a stored withheld is its own class",
        {JAN: "reported", FEB: "withheld", MAR: "reported"},
        [],
        {"reported": 2, "withheld_stored": 1, "absent": 0},
    ),
    (
        "a month with no row and no ledger entry is absent",
        {JAN: "reported", MAR: "reported"},
        [],
        {"reported": 2, "absent": 1},
    ),
    (
        "a ledger month is withheld, never absent and never stored",
        {JAN: "reported", MAR: "reported"},
        [FEB],
        {"reported": 2, "withheld_quarantined": 1, "absent": 0},
    ),
    (
        "a filed zero is a filing, counted apart from an absence",
        {JAN: "reported_zero", FEB: "reported_zero"},
        [],
        {"reported_zero": 2, "reported": 0, "absent": 0},
    ),
    (
        "all four stored classes and both absences coexist",
        {JAN: "reported", FEB: "reported_zero", MAR: "no_report"},
        [APR],
        {
            "reported": 1,
            "reported_zero": 1,
            "no_report_stored": 1,
            "withheld_stored": 0,
            "absent": 0,
            "withheld_quarantined": 1,
        },
    ),
)


@pytest.mark.parametrize(
    ("labelled", "withheld", "expected"),
    [case[1:] for case in CASES],
    ids=[case[0] for case in CASES],
)
def test_the_six_month_classes_are_counted_apart(labelled, withheld, expected) -> None:
    counts = month_class_counts(filed_span(labelled, withheld), labelled, withheld)

    for part, value in expected.items():
        assert getattr(counts, part) == value, part


@pytest.mark.parametrize(
    ("labelled", "withheld"),
    [case[1:3] for case in CASES],
    ids=[case[0] for case in CASES],
)
def test_the_six_parts_always_reconcile_to_the_span(labelled, withheld) -> None:
    """A definition that does not add up is a definition nobody can check."""
    counts = month_class_counts(filed_span(labelled, withheld), labelled, withheld)

    assert counts.span_months == (
        counts.reported
        + counts.reported_zero
        + counts.no_report_stored
        + counts.withheld_stored
        + counts.absent
        + counts.withheld_quarantined
    )


def test_a_ledger_month_is_never_double_counted_against_a_stored_row() -> None:
    """§5.1's grain: the regulator withheld the whole month, so no row of any class exists.

    ND cannot produce the overlap - the quarantine row is the filing - but the identity must
    hold even if a future jurisdiction does, so the ledger takes precedence here rather than
    letting the two counts both claim the month.
    """
    counts = month_class_counts((JAN, JAN), {JAN: "reported"}, [JAN])

    assert (counts.reported, counts.withheld_quarantined) == (0, 1)
    assert counts.span_months == 1
