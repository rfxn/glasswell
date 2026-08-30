"""New Mexico's well-header mapping decisions, as registry rows rather than as parser literals.

Every row this file checks decides something the spine cannot get from the bytes alone: how the
header keys, what its status letters mean, which coordinate pairs become points and what the
pool grain implies for a served figure. R8 makes each of those a row with a rationale and a
date, so what is asserted here is the row's shape and the measurement inside it — not that a
seeder ran.
"""

from __future__ import annotations

import re

import psycopg
import pytest
from psycopg.rows import dict_row

from glasswell.seed import seed_all
from glasswell.seed.conformance_nm_wells import (
    COORDINATE_ABSENT,
    COORDINATE_SENTINEL,
    NM_WELLS_RULES,
    RECORDS_MEASURED,
    STATUS_DOMAIN,
    USABLE_PAIRS,
    WELL_TYPE_DOMAIN,
    seed_conformance_nm_wells,
)

pytestmark = pytest.mark.integration

RULE_IDS = tuple(str(rule["rule_id"]) for rule in NM_WELLS_RULES)


@pytest.fixture
def registry(db: psycopg.Connection) -> dict[str, dict]:
    seed_all(db)
    db.commit()
    with db.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "select rule_id, rule_family, source_id, stage, rule_kind, applies_to_fields, spec,"
            "       rule, rationale, evidence_url, code_ref, effective_from, published_vintage,"
            "       supersedes_rule_id"
            " from lineage.conformance_rules where rule_id = any(%s)",
            (list(RULE_IDS),),
        )
        return {row["rule_id"]: row for row in cursor.fetchall()}


def test_every_rule_the_module_declares_is_resident(registry: dict[str, dict]) -> None:
    assert set(registry) == set(RULE_IDS)


def test_every_rule_carries_the_columns_a_reader_of_conformance_needs(registry) -> None:
    admitted_stages = {"parse", "validate", "conform", "join"}
    for rule_id, row in sorted(registry.items()):
        assert row["source_id"], rule_id
        assert row["stage"] in admitted_stages, rule_id
        assert row["rationale"].strip(), rule_id
        assert row["rule"].strip(), rule_id
        assert row["effective_from"] is not None, rule_id
        assert row["published_vintage"] is not None, rule_id
        assert row["applies_to_fields"], rule_id
        assert row["rule_family"] == rule_id.rsplit("_", 1)[0], rule_id


def test_every_rule_kind_is_one_the_registry_check_admits(db, registry) -> None:
    """Read the vocabulary from the live constraint rather than restating it here."""
    with db.cursor() as cursor:
        cursor.execute(
            "select pg_get_constraintdef(oid) from pg_constraint"
            " where conrelid = 'lineage.conformance_rules'::regclass and contype = 'c'"
        )
        definitions = [row[0] for row in cursor.fetchall() if "rule_kind" in row[0]]
    assert len(definitions) == 1, definitions
    admitted = set(re.findall(r"'([a-z_]+)'::text", definitions[0]))

    assert admitted
    assert {row["rule_kind"] for row in registry.values()} <= admitted


def test_every_evidence_url_points_at_a_registry_known_form(registry) -> None:
    for rule_id, row in sorted(registry.items()):
        assert row["evidence_url"], rule_id
        assert row["evidence_url"].startswith("https://wwwapps.emnrd.nm.gov/OCD/"), rule_id


def test_the_header_api10_mirrors_the_spine_composition_per_segment(registry) -> None:
    spec = registry["cr_nm_wellhistory_api10_1"]["spec"]

    assert spec["pad"] == {"api_st_cde": 2, "api_cnty_cde": 3, "api_well_idn": 5}
    assert spec["separator"] == ""
    assert spec["mirrors_rule_id"] == "cr_nm_wcproduction_api10_1"
    # The one measured difference from the spine, and the reason the rule is worth a row.
    assert spec["measured"]["over_wide_api_well_idn"] == 0


def test_the_coordinate_rule_is_a_pair_rule_with_a_stated_precedence(registry) -> None:
    spec = registry["cr_nm_wellhistory_coordinate_1"]["spec"]

    assert spec["unit"] == "pair"
    assert spec["precedence"] == ["nil", "zero"]
    assert spec["number_format"] == "scientific"
    assert spec["header_is_promoted_regardless"] is True


def test_the_coordinate_populations_reconcile_to_the_record_count(registry) -> None:
    """Three counted populations, not two counted and one subtracted."""
    measured = registry["cr_nm_wellhistory_coordinate_1"]["spec"]["measured"]

    assert measured["usable_pair"] == USABLE_PAIRS == 318720
    assert measured["coordinate_absent"] == COORDINATE_ABSENT == 1893
    assert measured["coordinate_sentinel"] == COORDINATE_SENTINEL == 897
    assert (
        measured["usable_pair"] + measured["coordinate_absent"] + measured["coordinate_sentinel"]
        == measured["records"]
        == RECORDS_MEASURED
    )
    # The four Gulf-of-Guinea records: a good latitude and a longitude of exactly zero.
    assert measured["longitude_zero_only"] == 4
    assert measured["both_zero"] + measured["longitude_zero_only"] == COORDINATE_SENTINEL


def test_the_rationale_says_why_a_zero_longitude_is_undetectable_by_range(registry) -> None:
    rationale = registry["cr_nm_wellhistory_coordinate_1"]["rationale"]

    assert "0.0 is a valid longitude everywhere on Earth" in rationale
    assert "Greenwich" in rationale


def test_scientific_notation_is_recorded_as_universal_not_merely_present(registry) -> None:
    measured = registry["cr_nm_wellhistory_coordinate_1"]["spec"]["measured"]

    assert measured["scientific_notation_ordinates"] == 639237
    assert measured["plain_decimal_ordinates"] == 0


def test_the_status_rule_records_a_measured_domain_and_asserts_no_canonical_status(
    registry,
) -> None:
    """The OCD publishes no codebook for these letters; cr_nm_wchistory_status_domain_1 already
    ruled that measuring a domain does not produce a mapping, and this follows it."""
    spec = registry["cr_nm_wellhistory_status_vocab_1"]["spec"]

    assert spec["status_canonical"] is None
    assert spec["mapping_table"] is None
    assert spec["promoted_to"] == "status_reported"
    assert spec["measured_domain"] == STATUS_DOMAIN
    assert sum(STATUS_DOMAIN.values()) == RECORDS_MEASURED
    assert spec["follows_rule_id"] == "cr_nm_wchistory_status_domain_1"


def test_the_nm_status_map_stays_empty_and_this_rule_is_why(db, registry) -> None:
    with db.cursor() as cursor:
        cursor.execute("select count(*) from lineage.nm_status_map")
        assert cursor.fetchone()[0] == 0


def test_the_well_type_rule_promotes_verbatim_over_a_closed_measured_domain(registry) -> None:
    spec = registry["cr_nm_wellhistory_well_type_1"]["spec"]

    assert spec["canonical_mapping"] is None
    assert spec["measured_domain"] == WELL_TYPE_DOMAIN
    assert sum(WELL_TYPE_DOMAIN.values()) == RECORDS_MEASURED


def test_the_datum_rule_is_unconditional_because_the_domain_is_one_value(registry) -> None:
    spec = registry["cr_nm_wellhistory_datum_1"]["spec"]

    assert (spec["source_epsg"], spec["target_epsg"]) == (4269, 4326)
    assert spec["detect"] == {
        "column": "datum",
        "value": "NAD83",
        "lat_col": "latitude",
        "lon_col": "longitude",
    }
    assert spec["measured_datum_domain"] == {"NAD83": RECORDS_MEASURED}
    assert spec["on_unexpected_datum"] == "quarantine"


def test_the_geometry_scope_rule_forbids_reading_a_lateral_into_a_horizontal_well(
    registry,
) -> None:
    spec = registry["cr_nm_wellhistory_geometry_scope_1"]["spec"]

    assert spec["geom_types_produced"] == ["surface"]
    assert set(spec["geom_types_absent"]) == {"lateral", "bottomhole", "survey_trace"}
    assert spec["measured_directional_status"]["H"] == 43409
    assert spec["measured_directional_status"]["D"] == 3265
    assert sum(spec["measured_directional_status"].values()) == RECORDS_MEASURED


def test_the_pool_rollup_rule_says_new_mexico_does_not_roll_up(registry) -> None:
    """North Dakota's rule of the same shape answers the opposite way, which is the point.

    All 17,597,960 promoted New Mexico rows are entity_type well_completion_pool with a null
    aggregation and there is no entity_type = well row among them, so a New Mexico well's
    well-level series is absent rather than zero.
    """
    spec = registry["cr_nm_wcproduction_pool_rollup_1"]["spec"]

    assert spec["rolls_up_to_the_well"] is False
    assert spec["aggregation"] is None
    assert spec["entity_type"] == "well_completion_pool"
    assert spec["measured"]["entity_type_well_rows"] == 0
    assert spec["contrasts_rule_id"] == "cr_nd_pool_rollup_1"


def test_no_liquids_policy_row_is_invented_for_a_question_already_decided(registry, db) -> None:
    """The served `_basis` on a New Mexico oil figure resolves to a rule that already exists.

    cr_nm_wcproduction_liquids_1 measured 3,398 condensate filings and ruled that NM reports
    condensate as its own stream, so NM's oil is oil as filed. A second row deciding the same
    thing would be two answers to one question in a registry whose ids are immutable.
    """
    assert not any(rule_id.endswith("liquids_policy_1") for rule_id in RULE_IDS)
    with db.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "select spec from lineage.conformance_rules where rule_id = %s",
            ("cr_nm_wcproduction_liquids_1",),
        )
        spec = cursor.fetchone()["spec"]

    assert spec["oil_includes_condensate"] is False
    assert spec["condensate_stream"] == "condensate"


def test_the_header_precedence_row_is_seeded_with_one_authority(registry) -> None:
    """It is superseded, never edited, once the GIS parity has been measured."""
    row = registry["cr_nm_wellhistory_header_precedence_1"]

    assert row["supersedes_rule_id"] is None
    assert set(row["spec"]["authority"].values()) == {"nm_ocd_wellhistory"}
    assert row["spec"]["second_source"] is None


def test_the_seeder_count_is_stable_across_runs(db: psycopg.Connection) -> None:
    """It counts its own ids, so a sibling seeder adding an nm_ocd_ rule cannot move it."""
    seed_all(db)
    first = seed_conformance_nm_wells(db)
    second = seed_conformance_nm_wells(db)

    assert first == second == len(NM_WELLS_RULES)


def test_seed_all_stays_idempotent_with_this_seeder_registered(db: psycopg.Connection) -> None:
    """The count seed_conformance_nm returns is a registry total over the nm_ocd_ prefix, and
    every rule here carries one — so this seeder has to run before it, not after."""
    first = seed_all(db)
    db.commit()

    assert seed_all(db) == first
