from __future__ import annotations

from datetime import UTC, date, datetime

import polars as pl
import psycopg
import pytest

from glasswell.lineage.conformance import apply_registry_rules, load_rules
from glasswell.lineage.errors import RuleSpecError
from glasswell.lineage.quarantine import PAYLOAD_CAP_BYTES, quarantine
from tests.support.seed import seed_manifest

SEEN_AT = datetime(2026, 8, 1, 5, 2, 11, tzinfo=UTC)

RULES = [
    {
        "rule_id": "cr_nd_well_status_1",
        "rule_family": "cr_nd_well_status",
        "source_id": "nd_mpr_xlsx",
        "stage": "conform",
        "applies_to_fields": ["well_status"],
        "rule_kind": "vocab_map",
        "spec": {
            "key_col": "status_raw",
            "value_col": "well_status",
            "mapping_table": "vocab_well_status",
            "unmapped_action": "quarantine",
        },
        "rule": "Map NDIC well-status codes to the canonical vocabulary.",
        "rationale": "NDIC publishes two-letter status codes; the product serves four states.",
        "published_vintage": date(2026, 7, 1),
        "effective_from": date(2026, 1, 1),
    },
    {
        "rule_id": "cr_nd_formation_alias_1",
        "rule_family": "cr_nd_formation_alias",
        "source_id": "nd_mpr_xlsx",
        "stage": "join",
        "applies_to_fields": ["formation"],
        "rule_kind": "alias_join",
        "spec": {
            "alias_table": "formation_aliases",
            "key_cols": ["formation_raw"],
            "target_col": "formation",
            "min_confidence": "0.80",
            "unmatched_action": "quarantine",
        },
        "rule": "Resolve reported formation names against formation_aliases.",
        "rationale": "Operators report the same formation under several trade names.",
        "published_vintage": date(2026, 7, 1),
        "effective_from": date(2026, 1, 1),
    },
]


@pytest.fixture
def registry(db):
    with db.cursor() as cursor:
        cursor.execute(
            "create table lineage.vocab_well_status ("
            " status_raw text primary key, well_status text not null,"
            " published_vintage date)"
        )
        cursor.executemany(
            "insert into lineage.vocab_well_status"
            " (status_raw, well_status, published_vintage) values (%s, %s, %s)",
            [
                ("AC", "active", date(2026, 7, 1)),
                ("PA", "plugged", date(2026, 9, 1)),
            ],
        )
        cursor.executemany(
            "insert into lineage.formation_aliases"
            " (formation_raw, formation, confidence, effective_from, created_vintage)"
            " values (%s, %s, %s, %s, %s)",
            [
                (
                    "BAKKEN FM",
                    "bakken",
                    "0.990",
                    date(2026, 1, 1),
                    date(2026, 7, 1),
                ),
                (
                    "SANISH",
                    "bakken",
                    "0.400",
                    date(2026, 1, 1),
                    date(2026, 7, 1),
                ),
            ],
        )
        cursor.executemany(
            "insert into lineage.conformance_rule_publications"
            " (rule_id, published_vintage, evidence_tag, evidence_commit)"
            " values (%(rule_id)s, %(published_vintage)s, 'test-fixture',"
            " %(evidence_commit)s)",
            [{**rule, "evidence_commit": "f" * 40} for rule in RULES],
        )
        for rule in RULES:
            cursor.execute(
                "insert into lineage.conformance_rules (rule_id, rule_family, source_id, stage,"
                " applies_to_fields, rule_kind, spec, rule, rationale, effective_from)"
                " values (%(rule_id)s, %(rule_family)s, %(source_id)s, %(stage)s,"
                " %(applies_to_fields)s, %(rule_kind)s, %(spec)s, %(rule)s, %(rationale)s,"
                " %(effective_from)s)",
                {**rule, "spec": psycopg.types.json.Jsonb(rule["spec"])},
            )
    db.commit()


def test_rules_load_for_a_source_and_stage(db, registry):
    loaded = load_rules(db, source_id="nd_mpr_xlsx", stage="conform", as_of=date(2026, 8, 1))
    assert [rule.rule_id for rule in loaded] == ["cr_nd_well_status_1"]
    assert loaded[0].rationale.startswith("NDIC publishes")


def test_the_loader_materializes_the_mapping_table_named_in_the_spec(db, registry):
    loaded = load_rules(
        db,
        source_id="nd_mpr_xlsx",
        stage="conform",
        knowledge_at=date(2026, 9, 1),
        valid_at=date(2026, 9, 1),
    )
    assert sorted(row["status_raw"] for row in loaded[0].lookup) == ["AC", "PA"]


def test_lookup_rows_have_their_own_knowledge_clock(db, registry):
    loaded = load_rules(
        db,
        source_id="nd_mpr_xlsx",
        stage="conform",
        knowledge_at=date(2026, 8, 31),
        valid_at=date(2026, 8, 31),
    )

    assert [row["status_raw"] for row in loaded[0].lookup] == ["AC"]


def test_rules_not_yet_effective_are_not_loaded(db, registry):
    assert load_rules(db, source_id="nd_mpr_xlsx", as_of=date(2025, 12, 31)) == []


def test_a_superseded_rule_stops_loading_once_its_successor_exists(db, registry):
    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.conformance_rule_publications values"
            " ('cr_nd_well_status_2', '2026-09-01', 'test-fixture', %s)",
            ("e" * 40,),
        )
        cursor.execute(
            "insert into lineage.conformance_rules (rule_id, rule_family, supersedes_rule_id,"
            " source_id, stage, applies_to_fields, rule_kind, spec, rule, rationale,"
            " effective_from) values ('cr_nd_well_status_2', 'cr_nd_well_status',"
            " 'cr_nd_well_status_1', 'nd_mpr_xlsx', 'conform', '{well_status}', 'vocab_map',"
            " %s, 'v2', 'v2 rationale', '2026-09-01')",
            (psycopg.types.json.Jsonb(RULES[0]["spec"]),),
        )
    db.commit()

    loaded = load_rules(
        db,
        source_id="nd_mpr_xlsx",
        stage="conform",
        knowledge_at=date(2026, 10, 1),
        valid_at=date(2026, 10, 1),
    )
    assert [rule.rule_id for rule in loaded] == ["cr_nd_well_status_2"]
    # R8: retired, not erased. effective_to cannot carry this — the row is append-only.
    with db.cursor() as cursor:
        cursor.execute(
            "select count(*) from lineage.conformance_rules where rule_id = 'cr_nd_well_status_1'"
        )
        assert cursor.fetchone()[0] == 1


def test_supersession_happens_after_both_temporal_filters(db, registry):
    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.conformance_rule_publications values"
            " ('cr_nd_well_status_2', '2026-09-01', 'test-fixture', %s)",
            ("e" * 40,),
        )
        cursor.execute(
            "insert into lineage.conformance_rules (rule_id, rule_family, supersedes_rule_id,"
            " source_id, stage, applies_to_fields, rule_kind, spec, rule, rationale,"
            " effective_from) values ('cr_nd_well_status_2', 'cr_nd_well_status',"
            " 'cr_nd_well_status_1', 'nd_mpr_xlsx', 'conform', '{well_status}', 'vocab_map',"
            " %s, 'v2', 'v2 rationale', '2026-05-01')",
            (psycopg.types.json.Jsonb(RULES[0]["spec"]),),
        )
    db.commit()

    before_publication = load_rules(
        db,
        source_id="nd_mpr_xlsx",
        stage="conform",
        knowledge_at=date(2026, 8, 31),
        valid_at=date(2026, 10, 1),
    )
    before_validity = load_rules(
        db,
        source_id="nd_mpr_xlsx",
        stage="conform",
        knowledge_at=date(2026, 9, 1),
        valid_at=date(2026, 4, 30),
    )
    fully_eligible = load_rules(
        db,
        source_id="nd_mpr_xlsx",
        stage="conform",
        knowledge_at=date(2026, 9, 1),
        valid_at=date(2026, 5, 1),
    )

    assert [rule.rule_id for rule in before_publication] == ["cr_nd_well_status_1"]
    assert [rule.rule_id for rule in before_validity] == ["cr_nd_well_status_1"]
    assert [rule.rule_id for rule in fully_eligible] == ["cr_nd_well_status_2"]


def test_effective_to_is_an_exclusive_valid_time_boundary(db, registry):
    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.conformance_rule_publications values"
            " ('cr_nd_expiring_1', '2026-07-01', 'test-fixture', %s)",
            ("d" * 40,),
        )
        cursor.execute(
            "insert into lineage.conformance_rules (rule_id, rule_family, source_id, stage,"
            " applies_to_fields, rule_kind, rule, rationale, effective_from, effective_to)"
            " values ('cr_nd_expiring_1', 'cr_nd_expiring', 'nd_mpr_xlsx', 'validate', '{}',"
            " 'code_ref', 'expires', 'boundary fixture', '2026-01-01', '2026-08-01')"
        )
    db.commit()

    before = load_rules(
        db,
        source_id="nd_mpr_xlsx",
        stage="validate",
        knowledge_at=date(2026, 8, 1),
        valid_at=date(2026, 7, 31),
    )
    boundary = load_rules(
        db,
        source_id="nd_mpr_xlsx",
        stage="validate",
        knowledge_at=date(2026, 8, 1),
        valid_at=date(2026, 8, 1),
    )

    assert [rule.rule_id for rule in before] == ["cr_nd_expiring_1"]
    assert boundary == []


def test_registry_rules_conform_the_frame_and_report_their_ids(db, registry):
    frame = pl.DataFrame({"api10": ["33053012340000"], "status_raw": ["AC"]})
    result = apply_registry_rules(
        db, frame, source_id="nd_mpr_xlsx", stage="conform", as_of=date(2026, 8, 1)
    )

    assert result.applied_rule_ids == ["cr_nd_well_status_1"]
    assert result.frame["well_status"].to_list() == ["active"]


def test_a_failing_row_reaches_the_quarantine_table_with_its_rule_and_reason(db, registry):
    manifest = seed_manifest(db, sha256="a" * 64)
    frame = pl.DataFrame(
        {"api10": ["33053012340000", "33053012350000"], "status_raw": ["AC", "ZZ"]}
    )
    result = apply_registry_rules(db, frame, source_id="nd_mpr_xlsx", stage="conform")
    batch = result.quarantined[0]
    written = quarantine(
        db,
        batch.frame,
        reason_code=batch.reason_code,
        rule_id=batch.rule_id,
        manifest_id=manifest,
        source_id="nd_mpr_xlsx",
        staging_table="staging.nd_mpr",
        stage="conform",
        seen_at=SEEN_AT,
    )
    db.commit()

    assert (written.opened, written.reoccurred) == (1, 0)
    with db.cursor() as cursor:
        cursor.execute(
            "select reason_code, rule_id, state, occurrence_count, row_payload"
            " from lineage.quarantine_rows"
        )
        assert cursor.fetchall() == [
            ("unknown_vocab", "cr_nd_well_status_1", "open", 1,
             {"api10": "33053012350000", "status_raw": "ZZ"}),
        ]


def test_the_same_rejected_row_on_a_later_pull_increments_instead_of_duplicating(db, registry):
    manifest = seed_manifest(db, sha256="a" * 64)
    later = seed_manifest(
        db, sha256="b" * 64, fetched_at=datetime(2026, 8, 2, 5, tzinfo=UTC)
    )
    frame = pl.DataFrame({"api10": ["33053012350000"], "status_raw": ["ZZ"]})
    for manifest_id in (manifest, later):
        batch = apply_registry_rules(
            db, frame, source_id="nd_mpr_xlsx", stage="conform"
        ).quarantined[0]
        quarantine(
            db,
            batch.frame,
            reason_code=batch.reason_code,
            rule_id=batch.rule_id,
            manifest_id=manifest_id,
            source_id="nd_mpr_xlsx",
            staging_table="staging.nd_mpr",
            stage="conform",
            seen_at=SEEN_AT,
        )
    db.commit()

    with db.cursor() as cursor:
        cursor.execute(
            "select occurrence_count, first_seen_manifest_id, last_seen_manifest_id"
            " from lineage.quarantine_rows"
        )
        assert cursor.fetchall() == [(2, manifest, later)]


def test_the_alias_rule_quarantines_below_confidence_matches_from_the_registry(db, registry):
    frame = pl.DataFrame({"formation_raw": ["BAKKEN FM", "SANISH"]})
    result = apply_registry_rules(db, frame, source_id="nd_mpr_xlsx", stage="join")

    assert result.frame["formation"].to_list() == ["bakken"]
    assert result.quarantined[0].reason_code == "alias_unresolved"


def test_an_alias_without_knowledge_time_fails_closed(db, registry):
    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.formation_aliases"
            " (formation_raw, formation, confidence, effective_from, created_vintage)"
            " values ('FUTURE SHALE', 'future', 1.000, '2020-01-01', null)"
        )
    db.commit()

    loaded = load_rules(
        db,
        source_id="nd_mpr_xlsx",
        stage="join",
        knowledge_at=date(2026, 8, 1),
        valid_at=date(2026, 8, 1),
    )

    assert "FUTURE SHALE" not in {row["formation_raw"] for row in loaded[0].lookup}


def test_operator_aliases_use_knowledge_and_valid_time_independently(db, registry):
    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.conformance_rule_publications values"
            " ('cr_operator_clock_1', '2026-07-01', 'test-fixture', %s)",
            ("9" * 40,),
        )
        cursor.execute(
            "insert into lineage.conformance_rules (rule_id, rule_family, source_id, stage,"
            " applies_to_fields, rule_kind, spec, rule, rationale, effective_from)"
            " values ('cr_operator_clock_1', 'cr_operator_clock', 'tx_pdq_dsv', 'join',"
            " '{operator}', 'alias_join', %s, 'r', 'r', '2020-01-01')",
            (
                psycopg.types.json.Jsonb(
                    {
                        "alias_table": "operator_aliases",
                        "key_cols": ["operator_raw"],
                        "target_col": "operator",
                        "min_confidence": "0.800",
                    }
                ),
            ),
        )
        cursor.execute(
            "insert into lineage.operator_aliases"
            " (operator_raw, operator, confidence, effective_from, source_id,"
            " published_vintage) values"
            " ('007', 'Seven Oil', 1.000, '2020-01-01', 'tx_pdq_dsv', '2026-09-01')"
        )
    db.commit()

    before_publication = load_rules(
        db,
        source_id="tx_pdq_dsv",
        stage="join",
        knowledge_at=date(2026, 8, 31),
        valid_at=date(2026, 10, 1),
    )
    after_publication = load_rules(
        db,
        source_id="tx_pdq_dsv",
        stage="join",
        knowledge_at=date(2026, 9, 1),
        valid_at=date(2026, 10, 1),
    )

    assert before_publication[0].lookup == []
    assert [row["operator_raw"] for row in after_publication[0].lookup] == ["007"]


def test_a_conformance_rule_row_cannot_be_edited_in_place(db, registry):
    with pytest.raises(psycopg.errors.RestrictViolation, match="append_only_violation"), db.cursor() as cursor:  # noqa: E501
        cursor.execute(
            "update lineage.conformance_rules set rationale = 'rewritten' where rule_id = %s",
            ("cr_nd_well_status_1",),
        )
    db.rollback()


def test_a_registry_table_name_that_is_not_an_identifier_is_refused(db, registry):
    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.conformance_rule_publications values"
            " ('cr_injection_1', '2026-07-01', 'test-fixture', %s)",
            ("c" * 40,),
        )
        cursor.execute(
            "insert into lineage.conformance_rules (rule_id, rule_family, source_id, stage,"
            " applies_to_fields, rule_kind, spec, rule, rationale, effective_from)"
            " values ('cr_injection_1', 'cr_injection', 'tx_pdq_dsv', 'conform', '{x}',"
            " 'vocab_map', %s, 'r', 'r', '2026-01-01')",
            (psycopg.types.json.Jsonb({"mapping_table": "vocab; drop table lineage.manifests"}),),
        )
    db.commit()

    with pytest.raises(RuleSpecError, match="not a valid registry table name"):
        load_rules(db, source_id="tx_pdq_dsv", stage="conform")


def test_a_lookup_table_without_a_publication_clock_fails_closed(db, registry):
    with db.cursor() as cursor:
        cursor.execute("create table lineage.unclocked_map (raw text primary key, mapped text)")
        cursor.execute("insert into lineage.unclocked_map values ('x', 'future')")
        cursor.execute(
            "insert into lineage.conformance_rule_publications values"
            " ('cr_unclocked_1', '2026-07-01', 'test-fixture', %s)",
            ("b" * 40,),
        )
        cursor.execute(
            "insert into lineage.conformance_rules (rule_id, rule_family, source_id, stage,"
            " applies_to_fields, rule_kind, spec, rule, rationale, effective_from)"
            " values ('cr_unclocked_1', 'cr_unclocked', 'tx_pdq_dsv', 'conform', '{mapped}',"
            " 'vocab_map', %s, 'r', 'r', '2026-01-01')",
            (
                psycopg.types.json.Jsonb(
                    {
                        "key_col": "raw",
                        "value_col": "mapped",
                        "mapping_table": "unclocked_map",
                    }
                ),
            ),
        )
    db.commit()

    with pytest.raises(RuleSpecError, match="has no publication clock"):
        load_rules(db, source_id="tx_pdq_dsv", stage="conform")


def test_an_oversized_rejected_row_stores_a_pointer_instead_of_the_payload(db, registry):
    manifest = seed_manifest(db, sha256="a" * 64)
    frame = pl.DataFrame({"status_raw": ["ZZ"], "blob": ["x" * (PAYLOAD_CAP_BYTES + 1)]})
    batch = apply_registry_rules(
        db, frame, source_id="nd_mpr_xlsx", stage="conform"
    ).quarantined[0]
    quarantine(
        db,
        batch.frame,
        reason_code=batch.reason_code,
        rule_id=batch.rule_id,
        manifest_id=manifest,
        source_id="nd_mpr_xlsx",
        staging_table="staging.nd_mpr",
        stage="conform",
        seen_at=SEEN_AT,
    )
    db.commit()

    with db.cursor() as cursor:
        cursor.execute("select row_payload from lineage.quarantine_rows")
        row = cursor.fetchone()
    assert row is not None
    assert row[0] == {"oversized": True, "manifest_id": manifest, "columns": ["status_raw", "blob"]}
