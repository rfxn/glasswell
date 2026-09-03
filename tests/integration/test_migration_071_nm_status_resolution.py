"""New Mexico's status class, landed on a database that was already seeded.

Migrations run before the seed, so on a fresh database 071's rule insert finds no ancestor and
does nothing — the seed supplies both rows. On the VM the ancestor is resident and this is the
statement that lands the successor. That path has to be exercised somewhere, and this is also
where the migration's copy of the rule is held to the seed's.
"""

from __future__ import annotations

import psycopg
import pytest
from psycopg.rows import dict_row

from glasswell.db.migrate import discover_migrations
from glasswell.seed import seed_all
from glasswell.seed.conformance_nm_wells import (
    DOCUMENTED_UNMAPPED_CLASS,
    NM_WELLS_RULES,
    STATUS_CANONICAL_MAP,
    STATUS_DECODES,
    STATUS_DOMAIN_WELLS_LATEST,
    seed_conformance_nm_wells,
)
from glasswell.status_resolution import resolver_rules

pytestmark = pytest.mark.integration

RULE_ID = "cr_nm_wellhistory_status_vocab_2"
ANCESTOR = "cr_nm_wellhistory_status_vocab_1"
MIGRATION = "nm_status_resolution"
PLACEHOLDER_TAG = "UNRELEASED"


def migration_sql(name: str) -> str:
    return next(item.sql for item in discover_migrations() if item.name == name)


def rule_row(connection: psycopg.Connection, rule_id: str) -> dict | None:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "select rule_id, rule_family, supersedes_rule_id, source_id, stage,"
            "       applies_to_fields, rule_kind, spec, rule, rationale, evidence_url,"
            "       code_ref, effective_from"
            "  from lineage.conformance_rules where rule_id = %s",
            (rule_id,),
        )
        return cursor.fetchone()


@pytest.fixture
def seeded(db: psycopg.Connection) -> psycopg.Connection:
    """A fresh database, where the seed rather than the migration supplies the rule."""
    seed_all(db)
    db.commit()
    return db


def rule_spec(connection: psycopg.Connection) -> dict:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute("select spec from lineage.conformance_rules where rule_id = %s", (RULE_ID,))
        return cursor.fetchone()["spec"]


@pytest.fixture
def seeded_before_the_supersession(db: psycopg.Connection) -> psycopg.Connection:
    """The VM's state: every New Mexico header rule except the successor."""
    original = tuple(rule for rule in NM_WELLS_RULES if rule["rule_id"] != RULE_ID)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("glasswell.seed.conformance_nm_wells.NM_WELLS_RULES", original)
        seed_all(db)
        patch.setattr("glasswell.seed.conformance_nm_wells.NM_WELLS_RULES", original)
        seed_conformance_nm_wells(db)
    db.commit()
    assert rule_row(db, RULE_ID) is None
    assert rule_row(db, ANCESTOR) is not None
    return db


def test_the_migration_lands_the_successor_on_a_database_that_was_already_seeded(
    seeded_before_the_supersession: psycopg.Connection,
) -> None:
    db = seeded_before_the_supersession
    with db.cursor() as cursor:
        cursor.execute(migration_sql(MIGRATION))

    landed = rule_row(db, RULE_ID)
    assert landed is not None
    assert landed["supersedes_rule_id"] == ANCESTOR
    assert landed["rule_kind"] == "vocab_map"
    assert landed["spec"]["mapping_table"] == "nm_wellhistory_status_map"
    assert landed["spec"]["resolved_at"] == "read_time"


def test_the_migration_and_the_seed_write_the_same_row(
    seeded_before_the_supersession: psycopg.Connection,
) -> None:
    """Two copies of a rule is one drift away from a lie; this is the guard on that."""
    db = seeded_before_the_supersession
    with db.cursor() as cursor:
        cursor.execute(migration_sql(MIGRATION))
    from_migration = rule_row(db, RULE_ID)
    db.rollback()

    seed_conformance_nm_wells(db)
    from_seed = rule_row(db, RULE_ID)

    assert from_migration == from_seed


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
        cursor.execute("select count(*) from lineage.nm_wellhistory_status_map")
        assert cursor.fetchone()[0] == len(STATUS_DECODES)


def test_the_mapping_table_is_the_rule_the_seed_declares(db: psycopg.Connection) -> None:
    """The table and the rule spec are two copies of one decision, written in two languages."""
    with db.cursor() as cursor:
        cursor.execute(
            "select status, decode, status_canonical from lineage.nm_wellhistory_status_map"
        )
        resident = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}

    assert resident == {
        code: (STATUS_DECODES[code], STATUS_CANONICAL_MAP[code]) for code in STATUS_DECODES
    }


def test_the_four_documented_codes_carry_a_class_of_their_own_and_never_a_null(
    db: psycopg.Connection,
) -> None:
    """Condition 2 of the ratification: a documented code glasswell has no word for is not the
    same fact as a code nobody filed, and collapsing them erases the difference."""
    with db.cursor() as cursor:
        cursor.execute(
            "select status from lineage.nm_wellhistory_status_map"
            " where status_canonical = %s order by status",
            (DOCUMENTED_UNMAPPED_CLASS,),
        )
        assert [row[0] for row in cursor.fetchall()] == ["I", "J", "Q", "Z"]
        cursor.execute(
            "select count(*) from lineage.nm_wellhistory_status_map"
            " where status_canonical is null"
        )
        assert cursor.fetchone()[0] == 0


def test_the_resolver_answers_for_new_mexico_and_for_no_state_nobody_registered(
    seeded: psycopg.Connection,
) -> None:
    """Seeded rather than migrate-only, because the resolver reads the registry now.

    Which jurisdictions resolve at read time is a `jurisdiction_rules` row joined to its rule's
    spec, and 073's own comment says those rows are the seed's on a fresh database -- so a
    migrate-only database has no read-time jurisdiction at all, which is already what
    `status_resolution.resolver_rules()` and therefore the tile mart answer there. The view used
    to disagree with them by carrying a hard-coded jurisdiction; it no longer does.

    The second half was `for_state_code <> '30'` is empty, which was the same claim as this one
    only while New Mexico was the only registered read-time map. Colorado registers one now and
    a sixth jurisdiction will, so the set is derived from the registry: the resolver answers for
    exactly the jurisdictions registered for read-time resolution, and never for one nobody
    registered -- which is the property a hard-coded resolver would have broken.
    """
    db = seeded
    with db.cursor() as cursor:
        cursor.execute(
            "select for_status_reported, resolved_status from canonical.status_resolution"
            " where for_state_code = '30'"
        )
        assert dict(cursor.fetchall()) == STATUS_CANONICAL_MAP
        cursor.execute("select distinct for_state_code from canonical.status_resolution")
        resolving = {row[0] for row in cursor.fetchall()}

    registered = set(resolver_rules(db))
    assert registered, "no jurisdiction registers read-time resolution; the check is vacuous"
    assert resolving == registered
    assert "30" in resolving


def test_new_mexico_passes_an_unmapped_letter_through_rather_than_quarantining_it(
    seeded: psycopg.Connection,
) -> None:
    """Condition 3: the action is New Mexico's own. Inherited from North Dakota or Montana it
    would be `quarantine`, which drops the row from the identity spine production joins to."""
    spec = rule_spec(seeded)

    assert spec["unmapped_action"] == "passthrough"
    assert spec["writes_canonical_column"] is False


def test_the_publication_evidence_is_registered_and_has_not_half_repointed(
    db: psycopg.Connection,
) -> None:
    """049 makes evidence a precondition; the tag and the commit must agree about the repoint."""
    with db.cursor() as cursor:
        cursor.execute(
            "select evidence_tag, evidence_commit from"
            " lineage.conformance_rule_publications where rule_id = %s",
            (RULE_ID,),
        )
        tag, commit = cursor.fetchone()

    assert (tag == PLACEHOLDER_TAG) == (commit == "0" * 40), (
        f"evidence_tag and evidence_commit disagree about being repointed: {tag} / {commit}"
    )


def test_the_invalidated_mart_is_named_with_the_command_that_rebuilds_it(
    seeded_before_the_supersession: psycopg.Connection,
) -> None:
    """SB-07 6.5 step 3: a rule change names its downstream surface, not just itself."""
    db = seeded_before_the_supersession
    with db.cursor() as cursor:
        cursor.execute(migration_sql(MIGRATION))
        cursor.execute(
            "select payload from lineage.audit_events"
            " where event_type = 'mart.invalidated' and subject_id = %s",
            (RULE_ID,),
        )
        payload = cursor.fetchone()[0]

    assert payload["datasets"] == ["marts.nm_wells_tile"]
    assert "glasswell.marts.nm_wells" in payload["rebuild_with"]


def test_the_measured_wells_latest_domain_sums_to_the_wells_the_map_serves(
    seeded: psycopg.Connection,
) -> None:
    """A record-level count would have been wrong by a factor of four; this is the guard."""
    spec = rule_spec(seeded)

    assert spec["measured_domain_wells_latest"] == STATUS_DOMAIN_WELLS_LATEST
    assert sum(STATUS_DOMAIN_WELLS_LATEST.values()) == spec["measured_wells"]
    assert sum(spec["measured_domain"].values()) == spec["measured_rows"]
    assert spec["measured_rows"] > spec["measured_wells"]
