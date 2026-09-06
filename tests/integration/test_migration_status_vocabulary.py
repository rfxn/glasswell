"""The status-vocabulary migration: the class domain, the registry-driven trigger, one clock.

Discovered by suffix rather than by number: the integrator assigns the digits at the merge
train, so nothing here spells one. What is pinned is the behaviour a renumber cannot change --
that the domain is a constraint on every registered map rather than a sixth copy of a list,
that a read-time map gets its refresh trigger from the registry rather than from a hand-written
migration, and that the resolver and the API now read the registry at one knowledge cut.
"""

from __future__ import annotations

import psycopg
import pytest
from psycopg.rows import dict_row

from glasswell.db.migrate import discover_migrations, migrate
from glasswell.lineage.status_classes import (
    StatusClassDomainError,
    absence_class,
    load_status_classes,
)
from glasswell.seed import seed_all, seed_sources
from glasswell.seed.jurisdictions import (
    GRAIN_JURISDICTION_RULES,
    GRAIN_RESTATED_CODES,
    GRAIN_RESTATED_ON,
    RESTATED_ON,
)
from glasswell.seed.status_classes import DOMAIN_EFFECTIVE_FROM, STATUS_CLASSES
from glasswell.status_resolution import UNMAPPED_CLASS

pytestmark = pytest.mark.integration

MIGRATION = "status_vocabulary"
REFRESH_TRIGGER = "status_map_refresh_status_resolution"


def migration(name: str):
    return next(item for item in discover_migrations() if item.name == name)


@pytest.fixture
def seeded(db: psycopg.Connection) -> psycopg.Connection:
    """The domain is a two-writer registry, as lineage.jurisdictions is: on a fresh database the
    migration runs before the seed that supplies its rows, so nothing here reads it unseeded."""
    seed_all(db)
    return db


def triggers_on(connection: psycopg.Connection) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            "select event_object_table from information_schema.triggers"
            " where trigger_name = %s",
            (REFRESH_TRIGGER,),
        )
        return {row[0] for row in cursor.fetchall()}


def test_the_migration_is_found_by_its_suffix_and_never_by_a_number() -> None:
    found = [item for item in discover_migrations() if item.name.endswith(MIGRATION)]

    assert len(found) == 1
    assert found[0].path.name.endswith(f"_{MIGRATION}.sql")


def test_the_domain_lands_twelve_rows_in_legend_order_citing_two_rules(
    seeded: psycopg.Connection,
) -> None:
    domain = load_status_classes(seeded)

    assert [row.status_canonical for row in domain] == [
        str(row["status_canonical"]) for row in STATUS_CLASSES
    ]
    assert [row.sort_order for row in domain] == sorted(row.sort_order for row in domain)
    assert len({row.rule_id for row in domain}) == 2
    assert {row.effective_from for row in domain} == {DOMAIN_EFFECTIVE_FROM}
    assert absence_class(seeded) == UNMAPPED_CLASS


def test_a_map_row_naming_a_class_outside_the_domain_is_refused(
    seeded: psycopg.Connection,
) -> None:
    """The foreign key is what makes this a domain rather than a second list."""
    with seeded.cursor() as cursor, pytest.raises(psycopg.errors.ForeignKeyViolation):
        cursor.execute(
            "insert into lineage.nd_status_map"
            " (status, status_canonical, published_vintage)"
            " values ('PLANTED', 'not_a_registered_class', current_date)"
        )


def test_a_quarantined_map_row_stays_legal_because_the_key_is_nullable(
    seeded: psycopg.Connection,
) -> None:
    """Montana's six unpromoted codes carry a null class, which means quarantined and not
    absent, so the domain constrains the values a map may name rather than forbidding silence."""
    with seeded.cursor() as cursor:
        cursor.execute(
            "insert into lineage.mt_status_map (status, status_canonical, promoted)"
            " values ('Planted', null, false)"
        )
        cursor.execute(
            "select count(*) from lineage.mt_status_map where status_canonical is null"
        )
        assert cursor.fetchone()[0] >= 1


def test_a_second_absence_class_is_refused(seeded: psycopg.Connection) -> None:
    with seeded.cursor() as cursor, pytest.raises(psycopg.errors.UniqueViolation):
        cursor.execute(
            "insert into lineage.status_classes (status_canonical, label, colour, glyph,"
            " min_zoom, sort_order, note, is_absence, rule_id, effective_from, published_at,"
            " rationale) values ('planted', 'Planted', '#111111', 'solid', 0, 999, 'planted',"
            " true, 'cr_status_absence_basis_1', %s, %s, 'planted')",
            (DOMAIN_EFFECTIVE_FROM, DOMAIN_EFFECTIVE_FROM),
        )


def test_a_second_class_claiming_an_existing_swatch_is_refused(
    seeded: psycopg.Connection,
) -> None:
    """Two classes with the same colour and glyph are indistinguishable on the canvas."""
    with seeded.cursor() as cursor, pytest.raises(psycopg.errors.UniqueViolation):
        cursor.execute(
            "insert into lineage.status_classes (status_canonical, label, colour, glyph,"
            " min_zoom, sort_order, note, rule_id, effective_from, published_at, rationale)"
            " values ('planted', 'Planted', '#3FA55E', 'solid', 4, 999, 'planted',"
            " 'cr_status_class_domain_1', %s, %s, 'planted')",
            (DOMAIN_EFFECTIVE_FROM, DOMAIN_EFFECTIVE_FROM),
        )


def test_the_domain_is_append_only(seeded: psycopg.Connection) -> None:
    with seeded.cursor() as cursor, pytest.raises(psycopg.errors.RestrictViolation):
        cursor.execute(
            "update lineage.status_classes set colour = '#000000' where status_canonical = 'dry'"
        )


def test_an_empty_domain_is_a_refusal_and_not_an_assumed_default(
    seeded: psycopg.Connection,
) -> None:
    """R8, mirroring load_jurisdictions: the definition is rows, so a missing definition is a
    service fault. A default here would be the class every well on the map is drawn by."""
    with seeded.cursor() as cursor:
        cursor.execute("truncate lineage.status_classes cascade")

    with pytest.raises(StatusClassDomainError) as refused:
        load_status_classes(seeded)

    assert "status_classes" in str(refused.value)


def test_the_registry_attaches_the_refresh_trigger_to_every_read_time_map(
    db: psycopg.Connection,
) -> None:
    """RES-1 and RES-2. 078 named one map literally and told the next jurisdiction to write
    another by hand; Colorado registered read-time resolution in that same train and shipped
    with no trigger at all, so an append to its map does not rebuild the resolver."""
    seed_all(db)

    assert {"nm_wellhistory_status_map", "co_facility_status_map"} <= triggers_on(db)

    with db.cursor() as cursor:
        cursor.execute(
            "drop trigger status_map_refresh_status_resolution"
            " on lineage.co_facility_status_map"
        )
    assert "co_facility_status_map" not in triggers_on(db)

    with db.cursor() as cursor:
        cursor.execute("select lineage.attach_status_map_refresh()")
        attached = cursor.fetchone()[0]

    assert attached >= 2
    assert "co_facility_status_map" in triggers_on(db)


def test_a_maps_own_append_does_not_re_attach_the_trigger_set(
    db: psycopg.Connection,
) -> None:
    """N-12. The attach is gated on the calling relation, so a map's own trigger never issues a
    drop-and-create pair per read-time map: that firing is the one that cannot change the
    registered set, and every drop takes ACCESS EXCLUSIVE on a map relation."""
    seed_all(db)
    with db.cursor() as cursor:
        cursor.execute(
            "drop trigger status_map_refresh_status_resolution"
            " on lineage.co_facility_status_map"
        )
        cursor.execute(
            "insert into lineage.nm_wellhistory_status_map"
            " (status, decode, status_canonical, published_vintage)"
            " values ('ZZ', 'planted', 'active', current_date)"
        )

    assert "co_facility_status_map" not in triggers_on(db)


def test_the_resolver_reads_the_registrys_own_knowledge_cut_and_records_it(
    db: psycopg.Connection,
) -> None:
    """RES-3. The refresh resolved the registry at the host's calendar while the API resolved it
    at max(published_at); the two already resolve different rule-row sets, and a class from one
    decision served beside the rule id of another is the naked-number failure R8 exists to
    prevent."""
    seed_all(db)
    with db.cursor(row_factory=dict_row) as cursor:
        cursor.execute("select max(published_at) as cut from lineage.jurisdictions")
        cut = cursor.fetchone()["cut"]
        cursor.execute(
            "select distinct knowledge_for, built_for from lineage.status_resolution_resolved"
        )
        recorded = cursor.fetchall()

    # The property and not the date, which is what V-4 asserts too: a date-specific assertion
    # goes red the day a track's clock moves and says nothing about the invariant. The two cuts
    # are recorded separately: knowledge_for is the registry's, built_for is the build's own
    # date -- which equals the registry cut on the day it is reached and passes it after.
    with db.cursor() as cursor:
        cursor.execute("select current_date")
        built_on = cursor.fetchone()[0]
    assert cut >= RESTATED_ON
    assert recorded
    for row in recorded:
        assert row["knowledge_for"] == cut
        assert row["built_for"] == built_on, "the build date is recorded as its own cut"


def test_the_grain_restatement_carries_its_registrations_rule_rows(
    db: psycopg.Connection,
) -> None:
    """A rule row joins its registration on the whole clock pair, so a decision appended at an
    instant that was already published would be an edit spelled as an append."""
    seed_all(db)
    with db.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "select jurisdiction_code, decision, rule_id from lineage.jurisdiction_rules"
            " where published_at = %s order by jurisdiction_code, decision, rule_id",
            (GRAIN_RESTATED_ON,),
        )
        landed = [
            (row["jurisdiction_code"], row["decision"], row["rule_id"])
            for row in cursor.fetchall()
        ]
        cursor.execute(
            "select jurisdiction_code from lineage.jurisdictions where published_at = %s"
            " order by jurisdiction_code",
            (GRAIN_RESTATED_ON,),
        )
        restated = [row["jurisdiction_code"] for row in cursor.fetchall()]

    assert restated == sorted(GRAIN_RESTATED_CODES)
    declared = sorted(
        (str(row["jurisdiction_code"]), str(row["decision"]), str(row["rule_id"]))
        for row in GRAIN_JURISDICTION_RULES
    )
    assert landed == declared


def test_the_rollup_mart_exists_and_only_the_pipeline_may_write_it(
    db: psycopg.Connection,
) -> None:
    """Layer boundaries: the mart reads canonical and writes marts, and the API only reads."""
    with db.cursor() as cursor:
        cursor.execute(
            "select privilege_type from information_schema.role_table_grants"
            " where table_schema = 'marts' and table_name = 'well_pool_rollup'"
            "   and grantee = 'glasswell_api'"
        )
        assert {row[0] for row in cursor.fetchall()} == {"SELECT"}
        cursor.execute(
            "select privilege_type from information_schema.role_table_grants"
            " where table_schema = 'marts' and table_name = 'well_pool_rollup'"
            "   and grantee = 'glasswell_pipeline'"
        )
        assert {"INSERT", "DELETE", "TRUNCATE"} <= {row[0] for row in cursor.fetchall()}


def test_seed_all_is_idempotent_over_two_runs(db: psycopg.Connection) -> None:
    first = seed_all(db)
    second = seed_all(db)

    assert first == second


def test_the_migration_is_the_writer_where_the_source_registry_is_already_resident(
    empty_db: psycopg.Connection,
) -> None:
    """The deployed path, which the shipped order never exercises.

    On a fresh database every guard in this file reads an empty registry, so the seed is the
    writer and the migration is a string of no-ops. On the deployed one lineage.sources is
    populated, so the migration writes the rules, the twelve rows and the six foreign keys
    itself, against map rows migrations 009 through 077 have already inserted.
    """
    directory = migration(MIGRATION).path.parent
    with empty_db.cursor() as cursor:
        cursor.execute(
            "create table if not exists public.schema_migrations"
            " (version integer primary key, name text not null, sha256 text not null,"
            "  applied_at timestamptz not null default now())"
        )
    empty_db.commit()
    for item in discover_migrations(directory):
        if item.name == MIGRATION:
            continue
        with empty_db.transaction(), empty_db.cursor() as cursor:
            cursor.execute(item.sql)
            cursor.execute(
                "insert into public.schema_migrations (version, name, sha256)"
                " values (%s, %s, %s)",
                (item.version, item.name, item.sha256),
            )
    seed_sources(empty_db)
    empty_db.commit()

    applied = migrate(empty_db)

    assert [item.name for item in applied] == [MIGRATION]
    assert len(load_status_classes(empty_db)) == len(STATUS_CLASSES)
    assert absence_class(empty_db) == UNMAPPED_CLASS
    with empty_db.cursor() as cursor:
        cursor.execute(
            "select count(*) from pg_constraint where conname = 'co_status_map_class_fk'"
        )
        assert cursor.fetchone()[0] == 1
        cursor.execute(
            "select jurisdiction_code from lineage.jurisdictions where published_at = %s"
            " order by 1",
            (GRAIN_RESTATED_ON,),
        )
        assert [row[0] for row in cursor.fetchall()] == sorted(GRAIN_RESTATED_CODES)


def test_a_second_apply_on_the_same_day_raises_instead_of_being_absorbed(
    seeded: psycopg.Connection,
) -> None:
    """There is deliberately no on-conflict clause on the restatement insert: an unrepointed
    clock would otherwise collide with the instant it restates, be absorbed in silence, and
    leave the production-grain decision unregistered while the migration reported success."""
    with seeded.cursor() as cursor, pytest.raises(psycopg.errors.UniqueViolation):
        cursor.execute(migration(MIGRATION).sql)
