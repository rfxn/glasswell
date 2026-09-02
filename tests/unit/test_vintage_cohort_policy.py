"""The cohort key is a rule row, so a missing row is a refusal and never an assumed default."""

from __future__ import annotations

import pytest

from glasswell.marts.vintage_cohorts import (
    _KEY_COLUMNS,
    _KEY_EXPRESSIONS,
    COHORT_BANDS,
    COHORT_KEYS,
    CohortPolicyError,
    load_cohort_policy,
    policy_from_spec,
    support_distribution,
)

SPEC = {
    "module_function": "glasswell.marts.vintage_cohorts:load_cohort_policy",
    "version": "1",
    "cohort_key": "spud_year",
    "cohort_key_field": "canonical.wells_latest.spud_date",
    "null_cohort_label": "no_spud_date",
    "vintage_read_at": "wells_latest_effective_row",
}


class NoRows:
    def cursor(self, **_: object) -> NoRows:
        return self

    def __enter__(self) -> NoRows:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, *_: object, **__: object) -> None:
        return None

    def fetchall(self) -> list:
        return []


def test_a_valid_spec_yields_the_policy_the_serving_path_executes() -> None:
    policy = policy_from_spec(SPEC)

    assert policy.cohort_key == "spud_year"
    assert policy.cohort_key_field == "canonical.wells_latest.spud_date"
    assert policy.null_cohort_label == "no_spud_date"


def test_a_key_outside_the_vocabulary_is_refused() -> None:
    with pytest.raises(CohortPolicyError, match="cohort_key"):
        policy_from_spec({**SPEC, "cohort_key": "first_production_year"})
    assert COHORT_KEYS == ("completion_anchor_year", "spud_year")


def test_a_cohort_of_wells_with_no_key_must_be_labelled() -> None:
    """Never dropped and never folded into a year, so the label is not optional."""
    with pytest.raises(CohortPolicyError, match="null_cohort_label"):
        policy_from_spec({**SPEC, "null_cohort_label": ""})


def test_a_missing_rule_row_raises_rather_than_defaulting() -> None:
    with pytest.raises(CohortPolicyError, match="not registered"):
        load_cohort_policy(NoRows())  # type: ignore[arg-type]


def test_the_cohort_bands_are_an_order_of_magnitude_coarser_than_the_section_scale() -> None:
    """A cohort holds hundreds of wells where a PLSS section holds a handful (M4)."""
    assert [label for _, _, label in COHORT_BANDS] == ["0", "1-9", "10-99", "100-999", "1000+"]

    measured = [0, 1, 8, 13, 49, 64, 359, 909, 1244, 2553]
    assert support_distribution(measured, COHORT_BANDS) == {
        "0": 1,
        "1-9": 2,
        "10-99": 3,
        "100-999": 2,
        "1000+": 2,
    }


def test_a_support_band_set_covers_every_count_exactly_once() -> None:
    for value in (0, 1, 9, 10, 99, 100, 999, 1000, 10_000):
        hits = [label for low, high, label in COHORT_BANDS
                if low <= value and (high is None or value <= high)]
        assert hits == [hits[0]], value


def test_a_rule_naming_a_column_the_executor_does_not_read_is_refused() -> None:
    """gate-v075 MINOR-3: cohort_key_field was required and then never read, so the rule could
    publish `completion_date` while the served cohorts stayed keyed on the spud year — a
    published statement the executor does not honour. The load refuses instead."""
    repointed = {**SPEC, "cohort_key_field": "canonical.wells_latest.completion_date"}

    with pytest.raises(CohortPolicyError, match="disagrees with the column"):
        policy_from_spec(repointed)


def test_every_admitted_cohort_key_has_both_a_reader_and_a_column() -> None:
    """The two maps are the agreement; a key in one and not the other breaks it silently."""
    assert set(_KEY_EXPRESSIONS) == set(_KEY_COLUMNS) == set(COHORT_KEYS)
