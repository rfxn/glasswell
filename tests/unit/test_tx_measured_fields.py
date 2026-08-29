"""The TX withholding policy is `cr_tx_ewa_measures_1`'s to state, and the layout's to declare.

Two failures the loader could not see before: a layout that stops declaring a measured column
passes `_assert_layout` — field count, county prefix and oil-gas domain all still hold — and
would null the field on every well at exit 0; and a rule asking for an action this promotion
cannot execute would be read as a withholding it never performs.
"""

from __future__ import annotations

from datetime import date

import pytest

from glasswell.ingest.tx_wellbore import MEASURES_RULE, _measure_policy, _measured
from glasswell.lineage.errors import RuleSpecError
from glasswell.lineage.models import ConformanceRule
from glasswell.seed.conformance_tx import TX_RULES

pytestmark = pytest.mark.unit

ROW = {
    "api10": "4231712345",
    "state_code": "42",
    "county_code": "317",
    "source_row_ordinal": 7,
    "total_depth_ft": "9120",
    "completion_date": "20240131",
}


def measures(**overrides: object) -> ConformanceRule:
    declared = next(row for row in TX_RULES if row["rule_id"] == MEASURES_RULE)
    return ConformanceRule(
        rule_id=str(declared["rule_id"]),
        rule_family=str(declared["rule_id"])[:-2],
        source_id=str(declared["source_id"]),
        stage=str(declared["stage"]),
        rule_kind=str(declared["rule_kind"]),
        applies_to_fields=list(declared["applies_to_fields"]),  # type: ignore[arg-type]
        spec={**declared["spec"], **overrides},  # type: ignore[dict-item]
        rule=str(declared["rule"]),
        rationale=str(declared["rationale"]),
        effective_from=date(2026, 8, 20),
    )


def test_the_registry_states_the_policy_the_loader_applies() -> None:
    """R8: the fields, the action and the reason codes are the rule row's, not the module's."""
    action, declared = _measure_policy(measures())

    assert action == "null_field"
    assert {name: reason for name, _, reason in declared} == {
        "total_depth_ft": "unreliable_numeric",
        "completion_date": "out_of_range_date",
    }


def test_an_unreadable_measure_is_withheld_under_the_rules_own_action() -> None:
    _, unreadable = _measured({**ROW, "total_depth_ft": "9,120"}, _measure_policy(measures()))

    assert [reject["reason_code"] for reject in unreadable] == ["unreliable_numeric"]
    assert unreadable[0]["field_action"] == "null_field"
    assert unreadable[0]["filed_as"] == "9,120"


def test_a_readable_row_parses_both_measures_and_rejects_nothing() -> None:
    parsed, unreadable = _measured(ROW, _measure_policy(measures()))

    assert parsed["total_depth_ft"] == 9120.0
    assert parsed["completion_date"] == date(2024, 1, 31)
    assert unreadable == []


def test_a_blank_measure_is_still_an_absence_and_not_a_reject() -> None:
    parsed, unreadable = _measured({**ROW, "total_depth_ft": ""}, _measure_policy(measures()))

    assert parsed["total_depth_ft"] is None
    assert unreadable == []


@pytest.mark.parametrize("dropped", ["total_depth_ft", "completion_date"])
def test_a_layout_missing_a_declared_measure_is_refused(dropped: str) -> None:
    row = {name: value for name, value in ROW.items() if name != dropped}

    with pytest.raises(RuleSpecError) as refusal:
        _measured(row, _measure_policy(measures()))

    assert dropped in str(refusal.value)


def test_an_action_this_promotion_cannot_execute_is_refused() -> None:
    """`drop_row` is in ND's vocabulary and not in this loader's; reading it as a withholding
    would perform a decision the rule did not ask for."""
    with pytest.raises(RuleSpecError) as refusal:
        _measure_policy(measures(field_action="drop_row"))

    assert "drop_row" in str(refusal.value)


def test_a_rule_that_does_not_rule_on_every_measured_field_is_refused() -> None:
    """Silence about a field the promotion measures is not permission to promote it unruled."""
    with pytest.raises(RuleSpecError) as refusal:
        _measure_policy(
            measures(fields=[{"field": "total_depth_ft", "reason_code": "unreliable_numeric"}])
        )

    assert "completion_date" in str(refusal.value)
