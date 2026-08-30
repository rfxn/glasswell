"""cr_nd_vintage_cohort_1 is the cohort key, and a missing row is a refusal (R8)."""

from __future__ import annotations

import psycopg
import pytest

from glasswell.marts.vintage_cohorts import COHORT_RULE, CohortPolicyError, load_cohort_policy
from glasswell.seed import seed_all


@pytest.fixture
def seeded(db: psycopg.Connection) -> psycopg.Connection:
    seed_all(db)
    db.commit()
    return db


def test_the_seeded_policy_is_the_spud_year(seeded: psycopg.Connection):
    policy = load_cohort_policy(seeded)

    assert policy.cohort_key == "spud_year"
    assert policy.cohort_key_field == "canonical.wells_latest.spud_date"
    assert policy.null_cohort_label == "no_spud_date"


def test_an_unregistered_key_makes_the_serving_path_refuse(db: psycopg.Connection):
    """Nothing defaults: a cohort chart with no registered key is not served at all.

    The row is absent rather than deleted because conformance_rules is append-only — a rule
    id is immutable and is retired by a superseding row, never by a DELETE.
    """
    with pytest.raises(CohortPolicyError, match="not registered"):
        load_cohort_policy(db)


def test_the_coverage_argument_is_in_the_served_row_rather_than_only_in_the_plan(
    seeded: psycopg.Connection,
):
    with seeded.cursor() as cursor:
        cursor.execute(
            "select rationale, spec from lineage.conformance_rules where rule_id = %s",
            (COHORT_RULE,),
        )
        rationale, spec = cursor.fetchone()

    assert "36,847" in rationale
    assert "17,563" in rationale
    assert spec["rejected_alternatives"][0]["cohort_key"] == "completion_anchor_year"
    assert spec["coverage"]["null_cohort"] == 6970


def test_the_rule_carries_an_effective_date_and_a_publication_vintage(
    seeded: psycopg.Connection,
):
    with seeded.cursor() as cursor:
        cursor.execute(
            "select effective_from, published_vintage from lineage.conformance_rules"
            " where rule_id = %s",
            (COHORT_RULE,),
        )
        effective_from, published_vintage = cursor.fetchone()

    assert effective_from is not None
    assert published_vintage is not None
