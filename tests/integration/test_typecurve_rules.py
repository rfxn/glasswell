from __future__ import annotations

from datetime import date

import psycopg
import pytest
from psycopg.rows import dict_row

from glasswell.seed import seed_all
from glasswell.seed.conformance_typecurve import TYPECURVE_RULES

RULE_IDS = tuple(sorted(str(rule["rule_id"]) for rule in TYPECURVE_RULES))
BUILD_TIME_RULES = (
    "cr_tc_normalization_1",
    "cr_tc_peer_ladder_1",
    "cr_tc_quantile_convention_1",
)


@pytest.fixture
def seeded(db: psycopg.Connection) -> dict[str, int]:
    counts = seed_all(db)
    db.commit()
    return counts


def typecurve_rows(connection: psycopg.Connection) -> list[dict]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "select rule_id, rule_kind, rule_family, source_id, stage, spec, rule, rationale,"
            "       evidence_url, code_ref, effective_from, published_vintage, applies_to_fields"
            " from lineage.conformance_rules where rule_id like 'cr\\_tc\\_%' order by rule_id"
        )
        return cursor.fetchall()


def test_the_five_type_curve_rules_reach_a_seeded_registry(db, seeded) -> None:
    rows = typecurve_rows(db)
    assert tuple(row["rule_id"] for row in rows) == RULE_IDS
    assert seeded["conformance_rules_typecurve"] == len(RULE_IDS)
    for row in rows:
        assert row["rule_kind"] == "code_ref"
        assert row["source_id"] == "nd_mpr_xlsx"
        assert row["stage"] == "conform"
        assert row["applies_to_fields"]


def test_the_build_time_rules_take_effect_when_tcv1_0_was_written(db, seeded) -> None:
    """effective_from is valid time; published_vintage is knowledge time (049's header)."""
    effective = {row["rule_id"]: row["effective_from"] for row in typecurve_rows(db)}
    for rule_id in BUILD_TIME_RULES:
        assert effective[rule_id] == date(2026, 8, 26)
    for rule_id in ("cr_tc_publication_scope_1", "cr_tc_unavailable_vocab_1"):
        assert effective[rule_id] == date(2026, 8, 30)
    assert {row["published_vintage"] for row in typecurve_rows(db)} == {date(2026, 8, 30)}


def test_every_type_curve_rule_carries_evidence_and_a_contract_note(db, seeded) -> None:
    for row in typecurve_rows(db):
        assert row["rationale"].strip()
        assert row["evidence_url"].strip()
        assert row["rule"].strip()
        assert row["spec"]["module_function"].startswith("glasswell.")
        assert row["spec"]["contract_note"].strip()
        assert row["code_ref"] == row["spec"]["module_function"]
        assert row["rule_family"] == row["rule_id"].rsplit("_", 1)[0]


def test_seeding_twice_does_not_move_the_nd_registry_count(db, seeded) -> None:
    assert seed_all(db) == seeded
    db.commit()


def test_the_quantile_convention_rule_states_which_convention_is_in_force(db, seeded) -> None:
    """The load-bearing one: statistical-ascending is the opposite of the reserves reading."""
    row = next(
        item for item in typecurve_rows(db) if item["rule_id"] == "cr_tc_quantile_convention_1"
    )
    assert row["spec"]["convention"] == "statistical_ascending"
    assert "reserves" in row["rationale"]
    assert "opposite" in row["spec"]["contract_note"]
