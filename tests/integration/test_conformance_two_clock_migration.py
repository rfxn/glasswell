from __future__ import annotations

from datetime import date
from pathlib import Path

import psycopg
import pytest

from glasswell.lineage.clock import utc_today
from glasswell.seed import (
    C115B_RULES,
    FRACFOCUS_RULES,
    LAND_RULES,
    ND_RULES,
    NM_RULES,
    NM_WELLS_RULES,
    PRODUCING_RULES,
    TX_RULES,
    TYPECURVE_RULES,
    seed_crs,
)

MIGRATION = (
    Path(__file__).parents[2]
    / "src/glasswell/db/migrations/049_conformance_two_clock.sql"
)


def _seeded_rule_ids() -> set[str]:
    return {
        str(rule["rule_id"])
        for registry in (
            C115B_RULES,
            FRACFOCUS_RULES,
            LAND_RULES,
            ND_RULES,
            NM_RULES,
            NM_WELLS_RULES,
            PRODUCING_RULES,
            TX_RULES,
            TYPECURVE_RULES,
        )
        for rule in registry
    }


def test_publication_catalog_exactly_covers_the_shipped_rule_registry(db):
    with db.cursor() as cursor:
        cursor.execute(
            "select rule_id, published_vintage, evidence_tag, evidence_commit"
            " from lineage.conformance_rule_publications"
        )
        publications = {
            row[0]: {"date": row[1], "tag": row[2], "commit": row[3]}
            for row in cursor.fetchall()
        }

    assert set(publications) == _seeded_rule_ids()
    assert publications["cr_nd_status_vocab_1"] == {
        "date": date(2026, 8, 20),
        "tag": "pre-inc3-train",
        "commit": "efa39772c2877a6c4ba333fade7fa446695c1f39",
    }
    assert publications["cr_nm_wcproduction_stream_vocab_1"]["tag"] == "v0.20"
    assert publications["cr_nd_neighbor_context_1"]["tag"] == "v0.57"
    assert all(len(item["commit"]) == 40 for item in publications.values())


def test_rule_publication_is_required_matched_and_immutable(db):
    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.conformance_rules (rule_id, rule_family, source_id, stage,"
            " rule_kind, rule, rationale, effective_from) values"
            " ('cr_nd_status_vocab_1', 'cr_nd_status_vocab', 'nd_mpr_xlsx', 'conform',"
            " 'vocab_map', 'r', 'r', '2026-01-01') returning published_vintage"
        )
        assert cursor.fetchone()[0] == date(2026, 8, 20)
    db.commit()

    with pytest.raises(psycopg.errors.CheckViolation, match="must be"), db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.conformance_rules (rule_id, rule_family, source_id, stage,"
            " rule_kind, rule, rationale, published_vintage, effective_from) values"
            " ('cr_nd_compute_crs_1', 'cr_nd_compute_crs', 'nd_mpr_xlsx', 'conform',"
            " 'code_ref', 'r', 'r', '2026-08-21', '2026-01-01')"
        )
    db.rollback()

    with (
        pytest.raises(psycopg.errors.CheckViolation, match="no publication evidence"),
        db.cursor() as cursor,
    ):
        cursor.execute(
            "insert into lineage.conformance_rules (rule_id, rule_family, source_id, stage,"
            " rule_kind, rule, rationale, effective_from) values"
            " ('cr_unpublished_1', 'cr_unpublished', 'nd_mpr_xlsx', 'conform',"
            " 'code_ref', 'r', 'r', '2026-01-01')"
        )
    db.rollback()

    with (
        pytest.raises(psycopg.errors.RestrictViolation, match="append_only_violation"),
        db.cursor() as cursor,
    ):
        cursor.execute(
            "update lineage.conformance_rules set published_vintage = '2026-08-21'"
            " where rule_id = 'cr_nd_status_vocab_1'"
        )
    db.rollback()


def test_static_lookup_clocks_are_not_nullable_and_are_indexed(db):
    tables = (
        "nd_status_map",
        "nd_stream_map",
        "nd_segment_map",
        "nd_survey_segment_map",
        "tx_status_map",
        "nm_stream_map",
        "nm_waste_type_map",
        "operator_aliases",
        "crs_registry",
    )
    with db.cursor() as cursor:
        cursor.execute(
            "select table_name from information_schema.columns"
            " where table_schema = 'lineage' and column_name = 'published_vintage'"
            " and is_nullable = 'NO' and table_name = any(%s)",
            (list(tables),),
        )
        nonnull = {row[0] for row in cursor.fetchall()}
        cursor.execute(
            "select tablename from pg_indexes where schemaname = 'lineage'"
            " and indexname like '%%publication_idx'"
        )
        indexed = {row[0] for row in cursor.fetchall()}

    assert nonnull == set(tables)
    assert set(tables) - {"operator_aliases", "crs_registry"} <= indexed
    assert "crs_registry" in {
        row[0]
        for row in db.execute(
            "select tablename from pg_indexes where schemaname = 'lineage'"
            " and indexname = 'crs_registry_two_clock_idx'"
        ).fetchall()
    }

    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.operator_aliases"
            " (operator_raw, operator, confidence, effective_from, source_id)"
            " values ('123', 'Clocked Operator', 1.000, '1980-01-01', 'nd_mpr_xlsx')"
            " returning effective_from, published_vintage"
        )
        effective_from, published_vintage = cursor.fetchone()

    assert effective_from == date(1980, 1, 1)
    # PostgreSQL stamps this with its own current_date, so the comparison is UTC's day.
    assert published_vintage == utc_today()

    with pytest.raises(psycopg.errors.RestrictViolation, match="append_only_violation"):
        db.execute(
            "update lineage.crs_registry set note = 'rewritten' where basin = 'williston'"
        )
    db.rollback()


def test_crs_seeding_reuses_the_proven_publication_identity(db):
    seed_crs(db)
    seed_crs(db)

    rows = db.execute(
        "select basin, effective_from, published_vintage from lineage.crs_registry"
        " where basin = 'williston' order by effective_from, published_vintage"
    ).fetchall()

    assert rows == [("williston", date(2026, 1, 1), date(2026, 8, 20))]


def test_migration_replays_without_changing_publication_evidence(db):
    with db.cursor() as cursor:
        cursor.execute(
            "select md5(string_agg(rule_id || ':' || published_vintage::text || ':'"
            " || evidence_tag || ':' || evidence_commit, ',' order by rule_id))"
            " from lineage.conformance_rule_publications"
        )
        before = cursor.fetchone()[0]
        cursor.execute(MIGRATION.read_text())
        cursor.execute(
            "select md5(string_agg(rule_id || ':' || published_vintage::text || ':'"
            " || evidence_tag || ':' || evidence_commit, ',' order by rule_id))"
            " from lineage.conformance_rule_publications"
        )
        after = cursor.fetchone()[0]

    assert after == before
