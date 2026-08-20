"""The upgrade path a fresh database never takes: migration 014 against an already-seeded DB.

Migrations run before the seed, so on a new database 014's insert finds no ancestor row and
does nothing — the seed supplies both rules. On the VM the ancestor is already there, and this
is the statement that lands the successor. That path has to be exercised somewhere, and this
is also where the two copies of the rule are held to the same content.
"""

from __future__ import annotations

import psycopg
import pytest
from psycopg.rows import dict_row

from glasswell.db.migrate import discover_migrations
from glasswell.seed.conformance_nd import ND_RULES, seed_conformance_nd
from glasswell.seed.glossary import seed_glossary
from glasswell.seed.reference import seed_crs, seed_sources

RULE_ID = "cr_nd_compute_crs_2"
MIGRATION = "geodesic_lateral_length"


def migration_sql(name: str) -> str:
    return next(item.sql for item in discover_migrations() if item.name == name)


def rule_row(connection: psycopg.Connection, rule_id: str) -> dict | None:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "select rule_id, rule_family, supersedes_rule_id, source_id, stage,"
            "       applies_to_fields, rule_kind, spec, rule, rationale, evidence_url,"
            "       effective_from"
            "  from lineage.conformance_rules where rule_id = %s",
            (rule_id,),
        )
        return cursor.fetchone()


@pytest.fixture
def seeded_before_the_supersession(db: psycopg.Connection) -> psycopg.Connection:
    """The VM's state on the morning of the audit: every rule except the successor."""
    seed_sources(db)
    seed_crs(db)
    seed_glossary(db)
    original = tuple(rule for rule in ND_RULES if rule["rule_id"] != RULE_ID)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("glasswell.seed.conformance_nd.ND_RULES", original)
        seed_conformance_nd(db)
    db.commit()
    assert rule_row(db, RULE_ID) is None
    return db


def test_the_migration_lands_the_successor_on_a_database_that_was_already_seeded(
    seeded_before_the_supersession: psycopg.Connection,
) -> None:
    db = seeded_before_the_supersession
    with db.cursor() as cursor:
        cursor.execute(migration_sql(MIGRATION))

    landed = rule_row(db, RULE_ID)
    assert landed is not None
    assert landed["supersedes_rule_id"] == "cr_nd_compute_crs_1"
    assert landed["spec"]["length_method"] == "geodesic"
    assert "A3-F1" in landed["rationale"]


def test_the_migration_and_the_seed_write_the_same_row(
    seeded_before_the_supersession: psycopg.Connection,
) -> None:
    """Two copies of a rule is one drift away from a lie; this is the guard on that."""
    db = seeded_before_the_supersession
    with db.cursor() as cursor:
        cursor.execute(migration_sql(MIGRATION))
    from_migration = rule_row(db, RULE_ID)
    db.rollback()

    seed_conformance_nd(db)
    from_seed = rule_row(db, RULE_ID)

    assert from_migration == from_seed


def test_the_supersession_is_recorded_in_the_audit_stream(
    seeded_before_the_supersession: psycopg.Connection,
) -> None:
    db = seeded_before_the_supersession
    with db.cursor() as cursor:
        cursor.execute(migration_sql(MIGRATION))
        cursor.execute(
            "select event_type, subject_id, payload from lineage.audit_events"
            " where event_id = 'evt_migration_014_cr_nd_compute_crs_2'"
        )
        event = cursor.fetchone()

    assert event is not None
    event_type, subject_id, payload = event
    assert (event_type, subject_id) == ("conformance.rule_superseded", RULE_ID)
    assert payload["finding"] == "fp-audit A3-F1"


def test_running_the_migration_twice_changes_nothing(
    seeded_before_the_supersession: psycopg.Connection,
) -> None:
    db = seeded_before_the_supersession
    with db.cursor() as cursor:
        cursor.execute(migration_sql(MIGRATION))
        cursor.execute(migration_sql(MIGRATION))
        cursor.execute("select count(*) from lineage.conformance_rules where rule_id = %s",
                       (RULE_ID,))
        assert cursor.fetchone()[0] == 1


def test_the_registry_note_and_the_glossary_stop_claiming_a_zone(
    seeded_before_the_supersession: psycopg.Connection,
) -> None:
    db = seeded_before_the_supersession
    with db.cursor() as cursor:
        # The text the VM carries, so the UPDATE is exercised rather than the seed's rewrite.
        cursor.execute(
            "update lineage.crs_registry set note = 'UTM 14N; every ND distance, area and"
            " spacing computation runs projected, never in degrees' where basin = 'williston'"
        )
        cursor.execute(
            "update canonical.glossary_terms set expanded_definition = 'North Dakota computes"
            " in UTM 14N (EPSG:32614), the Permian in UTM 13N.'"
            " where term_id = 'gt_crs_compute_crs'"
        )
        cursor.execute(migration_sql(MIGRATION))
        cursor.execute("select note from lineage.crs_registry where basin = 'williston'")
        note = cursor.fetchone()[0]
        cursor.execute(
            "select expanded_definition from canonical.glossary_terms"
            " where term_id = 'gt_crs_compute_crs'"
        )
        definition = cursor.fetchone()[0]

    assert "geodesic" in note
    assert "geodesic" in definition
    assert "A3-F1" in definition


def test_the_invalidated_mart_is_named_with_the_command_that_rebuilds_it(
    seeded_before_the_supersession: psycopg.Connection,
) -> None:
    """SB-07 §6.5 step 3: a rule change names its downstream surface, not just itself."""
    db = seeded_before_the_supersession
    with db.cursor() as cursor:
        cursor.execute(migration_sql(MIGRATION))
        cursor.execute(
            "select payload from lineage.audit_events"
            " where event_type = 'mart.invalidated' and subject_id = %s",
            (RULE_ID,),
        )
        payload = cursor.fetchone()[0]

    assert payload["datasets"] == ["marts.nd_laterals_tile"]
    assert "glasswell.marts.nd_wells" in payload["rebuild_with"]
