"""The producing policy read from its rule rows, and the refusals that keep it honest."""

from __future__ import annotations

from datetime import date

import pytest

from glasswell.marts.producing import (
    NOT_PRODUCING,
    PRODUCING,
    PRODUCING_CLASSES,
    UNKNOWN,
    ProducingPolicy,
    ProducingPolicyError,
    class_expression,
    policy_from_specs,
    window_start,
)

WINDOW = {"window_months": 3, "anchor": "latest_available_production_month"}
STREAMS = {"qualifying_streams": ["oil", "gas"], "liquids_basis": "oil+condensate"}
EVIDENCE = {
    "qualifying_null_semantics": ["reported"],
    "min_volume_exclusive": "0",
    "absent_is_unknown": True,
    "withheld_is_unknown": True,
}


def build(*, window=None, streams=None, evidence=None) -> ProducingPolicy:
    return policy_from_specs(
        window=WINDOW | (window or {}),
        streams=STREAMS | (streams or {}),
        evidence=EVIDENCE | (evidence or {}),
    )


def test_the_policy_is_read_from_the_rule_specs_not_from_a_default() -> None:
    policy = build()

    assert policy.window_months == 3
    assert policy.streams == ("gas", "oil")
    assert policy.evidence_semantics == ("reported",)
    assert policy.liquids_basis == "oil+condensate"


def test_water_alone_never_qualifies_because_it_is_not_a_hydrocarbon() -> None:
    """The owner said Gas/Oil/Water; a well lifting only water is not producing in any sense
    an analyst means, and on the 2026-03 ND load exactly 9 active wells turn on it."""
    assert "water" not in build().streams


def test_a_stream_outside_the_canonical_vocabulary_is_refused() -> None:
    """The spec reaches SQL, so its values are held to the column's own check constraint
    rather than trusted because a registry row carried them."""
    with pytest.raises(ProducingPolicyError, match="helium"):
        build(streams={"qualifying_streams": ["oil", "helium"]})


def test_a_null_semantics_value_outside_the_column_vocabulary_is_refused() -> None:
    with pytest.raises(ProducingPolicyError, match="invented"):
        build(evidence={"qualifying_null_semantics": ["invented"]})


def test_a_reported_zero_is_never_evidence_of_producing() -> None:
    """reported_zero is a filed zero: the regulator says the well did not produce. Admitting
    it as qualifying evidence would read every filed zero as production."""
    with pytest.raises(ProducingPolicyError, match="reported_zero"):
        build(evidence={"qualifying_null_semantics": ["reported", "reported_zero"]})


def test_a_withheld_month_is_never_evidence_of_producing() -> None:
    with pytest.raises(ProducingPolicyError, match="withheld"):
        build(evidence={"qualifying_null_semantics": ["reported", "withheld"]})


def test_an_empty_stream_set_is_refused_rather_than_matching_everything() -> None:
    with pytest.raises(ProducingPolicyError, match="qualifying_streams"):
        build(streams={"qualifying_streams": []})


def test_a_window_of_zero_months_is_refused() -> None:
    with pytest.raises(ProducingPolicyError, match="window_months"):
        build(window={"window_months": 0})


def test_an_anchor_the_loader_cannot_compute_is_refused() -> None:
    """Anchoring on the wall clock would class every ND well not-producing: the MPR runs
    about five months behind, so 2026-08 asks for months nobody has filed yet."""
    with pytest.raises(ProducingPolicyError, match="today"):
        build(window={"anchor": "today"})


def test_the_window_starts_the_month_the_span_reaches_back_to() -> None:
    """Three months means the anchor and the two before it, not the anchor minus three."""
    assert window_start(date(2026, 3, 1), build()) == date(2026, 1, 1)


def test_the_window_spans_a_year_boundary_without_arithmetic_drift() -> None:
    assert window_start(date(2026, 1, 1), build(window={"window_months": 6})) == date(
        2025, 8, 1
    )


def test_a_window_with_no_production_at_all_has_no_start() -> None:
    """An empty database answers unknown for every well rather than producing for none."""
    assert window_start(None, build()) is None


def test_the_classes_are_the_three_the_data_can_distinguish() -> None:
    assert PRODUCING_CLASSES == (PRODUCING, NOT_PRODUCING, UNKNOWN)


def test_the_class_expression_names_the_columns_it_was_given() -> None:
    sql = class_expression(api10="ranked.api10", state_code="ranked.state_code")

    assert "ranked.api10" in sql
    assert "ranked.state_code" in sql
    # Every value the expression compares against arrives as a bound parameter.
    assert "'producing'" in sql
    assert "%(producing_streams)s" in sql
    assert "%(producing_evidence)s" in sql


def test_the_class_expression_reads_the_newest_vintage_of_a_restated_month() -> None:
    """DIR-2: a restatement is appended, so a month that was revised to zero must not still
    answer producing on the strength of the superseded row."""
    sql = class_expression(api10="ranked.api10", state_code="ranked.state_code")

    assert "report_vintage desc" in sql
    assert "distinct on (p.production_month, p.stream)" in sql
