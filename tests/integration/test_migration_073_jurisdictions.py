"""The jurisdictions migration: the registry's DDL, its two clocks, and its grants.

Every refusal here has to be proved in the commit that lands the DDL, not later:
`migrate.py:90` raises on a hash change once a migration has been applied, so a constraint that
turns out to be inert is a new migration, never an edit to this one.

Migrations run before the seed, so on a fresh database the rule rows find no conformance rule
and do nothing; `seed/jurisdictions.py` supplies them. On a database that is already seeded --
the deployed one -- this migration is what lands them. Both paths are exercised below.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta

import psycopg
import pytest
from psycopg.rows import dict_row

from glasswell.db.migrate import discover_migrations
from glasswell.seed import seed_all
from glasswell.seed.jurisdictions import (
    JURISDICTION_RULES,
    JURISDICTIONS,
    REGISTERED_ON,
    seed_jurisdictions,
)
from tests.support.seed import seed_derivation

pytestmark = pytest.mark.integration

MIGRATION = "jurisdictions"
LATER_KNOWLEDGE = date(2026, 11, 1)
BEFORE_THE_RESTATEMENT = date(2026, 10, 15)
AFTER_THE_RESTATEMENT = date(2026, 12, 1)
CORRECTED_URL = "https://www.dmr.nd.gov/oilgas/"

_REGISTRATION = """
insert into lineage.jurisdictions (
    jurisdiction_code, effective_from, published_at, evidence_tag, evidence_commit, name,
    regulator_name, regulator_url, identity_scheme, identity_prefix, identity_pattern,
    source_ids, rationale)
values (%(code)s, %(effective_from)s, %(published_at)s, 'v0.76', %(commit)s, %(code)s,
        'regulator', %(url)s, %(scheme)s, %(prefix)s, %(pattern)s,
        array['nd_mpr_xlsx'], 'fixture')
"""


def migration_sql(name: str) -> str:
    """By name: a migration number is assigned by merge order and this one will be renumbered."""
    return next(item.sql for item in discover_migrations() if item.name == name)


def register(connection: psycopg.Connection, code: str, **overrides) -> None:
    parameters = {
        "code": code,
        "effective_from": REGISTERED_ON,
        "published_at": REGISTERED_ON,
        "commit": "a" * 40,
        "url": "https://example.invalid/",
        "scheme": "api10",
        "prefix": "44",
        "pattern": "^44[0-9]{8}$",
    }
    with connection.cursor() as cursor:
        cursor.execute(_REGISTRATION, {**parameters, **overrides})


@contextmanager
def acting_as(connection: psycopg.Connection, role: str) -> Iterator[psycopg.Cursor]:
    with connection.cursor() as cursor:
        cursor.execute(f"set local role {role}")
        try:
            yield cursor
        finally:
            connection.rollback()


def resolved(connection: psycopg.Connection, knowledge: date, valid: date) -> list[dict]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "select * from lineage.jurisdictions_as_of(%s, %s) order by jurisdiction_code",
            (knowledge, valid),
        )
        return cursor.fetchall()


@pytest.fixture
def seeded_without_the_registry_rules(db: psycopg.Connection) -> psycopg.Connection:
    """The deployed database's state: every conformance rule resident, no jurisdiction rule.

    The patch is scoped to the seeding, not to the test: what follows it calls the real seeder.
    """
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("glasswell.seed.jurisdictions.JURISDICTION_RULES", ())
        seed_all(db)
    db.commit()
    with db.cursor() as cursor:
        cursor.execute("select count(*) from lineage.jurisdiction_rules")
        assert cursor.fetchone()[0] == 0
    return db


@pytest.fixture
def populated_ledgers(seeded_without_the_registry_rules: psycopg.Connection) -> psycopg.Connection:
    db = seeded_without_the_registry_rules
    seed_jurisdictions(db)
    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.jurisdiction_well_counts (jurisdiction_code, measured_on,"
            " well_count, derivation_id) values ('ND', %s, 1, %s)",
            (REGISTERED_ON, seed_derivation(db)),
        )
    db.commit()
    return db


def test_the_registry_ships_with_its_registrations_and_the_resolver_answers_for_four(
    db: psycopg.Connection,
) -> None:
    """`glasswell-migrate` alone must yield a database that serves: the registrations are in
    the migration, not only in the seed."""
    rows = resolved(db, REGISTERED_ON, REGISTERED_ON)

    assert [row["jurisdiction_code"] for row in rows] == ["MT", "ND", "NM", "TX"]
    assert sorted(row["identity_prefix"] for row in rows) == ["25", "30", "33", "42"]
    assert {row["identity_scheme"] for row in rows} == {"api10"}
    for row in rows:
        assert row["identity_pattern"] == f"^{row['identity_prefix']}[0-9]{{8}}$"


def test_the_rule_rows_wait_for_the_conformance_registry_and_then_land(
    seeded_without_the_registry_rules: psycopg.Connection,
) -> None:
    db = seeded_without_the_registry_rules
    with db.cursor() as cursor:
        cursor.execute(migration_sql(MIGRATION))
        cursor.execute("select count(*) from lineage.jurisdiction_rules")
        assert cursor.fetchone()[0] == len(JURISDICTION_RULES)
        cursor.execute(
            "select rule_id from lineage.jurisdiction_rules"
            " where jurisdiction_code = 'MT' and decision = 'inventory_jurisdiction'"
            "   and not serving"
        )
        assert cursor.fetchone()[0] == "cr_mt_pru_inventory_jurisdiction_1"


def test_the_migration_and_the_seed_write_the_same_rule_rows(
    seeded_without_the_registry_rules: psycopg.Connection,
) -> None:
    """Two copies of a registry is one drift away from a lie; this is the guard on that."""
    db = seeded_without_the_registry_rules
    columns = "jurisdiction_code, effective_from, published_at, decision, rule_id, serving, note"
    with db.cursor() as cursor:
        cursor.execute(migration_sql(MIGRATION))
        cursor.execute(f"select {columns} from lineage.jurisdiction_rules order by 1, 4, 5")
        from_migration = cursor.fetchall()
    db.rollback()

    seed_jurisdictions(db)
    with db.cursor() as cursor:
        cursor.execute(f"select {columns} from lineage.jurisdiction_rules order by 1, 4, 5")
        from_seed = cursor.fetchall()

    assert from_migration == from_seed
    assert len(from_seed) == len(JURISDICTION_RULES)


def test_running_the_migration_twice_changes_nothing(
    seeded_without_the_registry_rules: psycopg.Connection,
) -> None:
    db = seeded_without_the_registry_rules
    with db.cursor() as cursor:
        cursor.execute(migration_sql(MIGRATION))
        cursor.execute(migration_sql(MIGRATION))
        cursor.execute("select count(*) from lineage.jurisdictions")
        assert cursor.fetchone()[0] == len(JURISDICTIONS)
        cursor.execute("select count(*) from lineage.jurisdiction_rules")
        assert cursor.fetchone()[0] == len(JURISDICTION_RULES)


def test_an_api10_registration_with_no_prefix_is_rejected(db: psycopg.Connection) -> None:
    """N-1: `false or null` is null and a CHECK rejects only on false, so without the
    coalesce this row was admitted and every prefix lookup on the serving path then missed it."""
    with pytest.raises(psycopg.errors.CheckViolation):
        register(db, "ND", prefix=None, pattern=None, effective_from=date(2027, 1, 1),
                 published_at=date(2027, 1, 1))


def test_a_uwi_registration_with_no_prefix_is_still_accepted(db: psycopg.Connection) -> None:
    """The same check must not shut Canada out: a UWI jurisdiction has no API-10 prefix."""
    with db.cursor() as cursor:
        cursor.execute("insert into lineage.jurisdiction_codes values ('CA-AB', 'province')")
    register(db, "CA-AB", scheme="uwi", prefix=None, pattern=None)

    rows = resolved(db, REGISTERED_ON, REGISTERED_ON)

    assert "CA-AB" in {row["jurisdiction_code"] for row in rows}


def test_a_prefix_and_a_pattern_are_nullable_only_together(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("insert into lineage.jurisdiction_codes values ('CA-AB', 'province')")
    with pytest.raises(psycopg.errors.CheckViolation):
        register(db, "CA-AB", scheme="uwi", prefix=None)


def test_a_restatement_is_accepted_and_resolves_at_the_later_knowledge_time(
    db: psycopg.Connection,
) -> None:
    """N-2: same effective_from, later published_at -- 'always effective that day; what we
    published about it was wrong'. A two-column key admitted only supersession, which left a
    falsified valid time as the only way to correct knowledge time."""
    register(db, "ND", published_at=LATER_KNOWLEDGE, url=CORRECTED_URL, prefix="33",
             pattern="^33[0-9]{8}$")

    founding = resolved(db, BEFORE_THE_RESTATEMENT, BEFORE_THE_RESTATEMENT)
    restated = resolved(db, AFTER_THE_RESTATEMENT, AFTER_THE_RESTATEMENT)

    assert next(r for r in founding if r["jurisdiction_code"] == "ND")["published_at"] == (
        REGISTERED_ON
    )
    later = next(r for r in restated if r["jurisdiction_code"] == "ND")
    assert later["published_at"] == LATER_KNOWLEDGE
    assert later["regulator_url"] == CORRECTED_URL


def test_two_registrations_cannot_share_a_prefix_at_one_instant(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("insert into lineage.jurisdiction_codes values ('CO', 'state')")
    with pytest.raises(psycopg.errors.UniqueViolation):
        register(db, "CO", prefix="33", pattern="^33[0-9]{8}$")


def test_a_land_grid_state_that_is_not_in_scope_is_rejected(db: psycopg.Connection) -> None:
    with db.cursor() as cursor, pytest.raises(psycopg.errors.CheckViolation):
        cursor.execute(
            "insert into lineage.jurisdictions (jurisdiction_code, effective_from,"
            " published_at, evidence_tag, evidence_commit, name, regulator_name, regulator_url,"
            " identity_scheme, identity_prefix, identity_pattern, source_ids, rationale,"
            " land_grid_state, land_grid_scope)"
            " values ('TX', date '2027-01-01', date '2027-01-01', 'v0.76', %s, 'x', 'y',"
            " 'https://z', 'api10', '44', '^44[0-9]{8}$', array['nd_mpr_xlsx'], 'r',"
            " true, false)",
            ("a" * 40,),
        )


def test_a_rule_row_needs_a_registration_at_its_own_triple(
    seeded_without_the_registry_rules: psycopg.Connection,
) -> None:
    """The composite FK is what makes the runbook's order the only order that works."""
    db = seeded_without_the_registry_rules
    with db.cursor() as cursor, pytest.raises(psycopg.errors.ForeignKeyViolation):
        cursor.execute(
            "insert into lineage.jurisdiction_rules (jurisdiction_code, effective_from,"
            " published_at, decision, rule_id)"
            " values ('ND', date '2027-01-01', date '2027-01-01', 'liquids',"
            " 'cr_nd_liquids_policy_1')"
        )


def test_a_decision_may_have_only_one_serving_rule(
    seeded_without_the_registry_rules: psycopg.Connection,
) -> None:
    db = seeded_without_the_registry_rules
    seed_jurisdictions(db)
    with db.cursor() as cursor, pytest.raises(psycopg.errors.UniqueViolation):
        cursor.execute(
            "insert into lineage.jurisdiction_rules (jurisdiction_code, effective_from,"
            " published_at, decision, rule_id)"
            " values ('MT', %s, %s, 'inventory_jurisdiction', 'cr_mt_pru_inventory_1')",
            (REGISTERED_ON, REGISTERED_ON),
        )


def test_the_jurisdiction_total_is_a_key_the_status_classes_cannot_collide_with(
    db: psycopg.Connection,
) -> None:
    """A null discriminator cannot sit in a primary key and an expression cannot either, so
    the sentinel is a stored generated column -- and it is not '' because a class id is
    [a-z_]+."""
    derivation_id = seed_derivation(db)
    with db.cursor() as cursor:
        cursor.executemany(
            "insert into lineage.jurisdiction_well_counts (jurisdiction_code, measured_on,"
            " status_canonical, well_count, derivation_id) values (%s, %s, %s, %s, %s)",
            [
                ("ND", REGISTERED_ON, None, 41000, derivation_id),
                ("ND", REGISTERED_ON, "active", 9000, derivation_id),
            ],
        )
        cursor.execute(
            "select status_canonical, status_key from lineage.jurisdiction_well_counts"
            " order by status_key"
        )
        assert cursor.fetchall() == [("active", "active"), (None, "*total*")]

        with pytest.raises(psycopg.errors.UniqueViolation):
            cursor.execute(
                "insert into lineage.jurisdiction_well_counts (jurisdiction_code, measured_on,"
                " status_canonical, well_count, derivation_id) values ('ND', %s, null, 1, %s)",
                (REGISTERED_ON, derivation_id),
            )


def test_a_count_cannot_be_negative_and_cannot_be_unattributed(db: psycopg.Connection) -> None:
    """R-3 at the DDL: no count without the refresh that produced it, and never below zero."""
    derivation_id = seed_derivation(db)
    with db.cursor() as cursor:
        with pytest.raises(psycopg.errors.CheckViolation):
            cursor.execute(
                "insert into lineage.jurisdiction_well_counts (jurisdiction_code, measured_on,"
                " well_count, derivation_id) values ('ND', %s, -1, %s)",
                (REGISTERED_ON, derivation_id),
            )
        db.rollback()
        with pytest.raises(psycopg.errors.NotNullViolation):
            cursor.execute(
                "insert into lineage.jurisdiction_well_counts (jurisdiction_code, measured_on,"
                " well_count) values ('ND', %s, 1)",
                (REGISTERED_ON,),
            )


@pytest.mark.parametrize(
    "table", ["jurisdictions", "jurisdiction_rules", "jurisdiction_well_counts"]
)
def test_every_ledger_is_append_only(
    populated_ledgers: psycopg.Connection, table: str
) -> None:
    """A row-level trigger says nothing about an empty table, so all three carry a row first."""
    db = populated_ledgers
    with db.cursor() as cursor:
        cursor.execute(f"select count(*) from lineage.{table}")
        assert cursor.fetchone()[0] > 0
        for statement in (f"update lineage.{table} set jurisdiction_code = 'ZZ'",
                          f"delete from lineage.{table}"):
            with pytest.raises(psycopg.errors.RestrictViolation):
                cursor.execute(statement)
            db.rollback()


def test_the_api_role_reads_every_object_and_the_resolver(db: psycopg.Connection) -> None:
    """044 exists because a collector grant was missed once; this is that lesson applied."""
    with acting_as(db, "glasswell_api") as cursor:
        for relation in ("jurisdiction_codes", "jurisdictions", "jurisdiction_rules",
                         "jurisdiction_well_counts"):
            cursor.execute(f"select count(*) from lineage.{relation}")
        cursor.execute(
            "select count(*) from lineage.jurisdictions_as_of(%s, %s)",
            (REGISTERED_ON, REGISTERED_ON),
        )
        assert cursor.fetchone()[0] == len(JURISDICTIONS)


def test_only_the_pipeline_role_appends_a_measurement(db: psycopg.Connection) -> None:
    derivation_id = seed_derivation(db)
    db.commit()
    statement = (
        "insert into lineage.jurisdiction_well_counts (jurisdiction_code, measured_on,"
        " well_count, derivation_id) values ('ND', %s, 1, %s)"
    )
    with acting_as(db, "glasswell_api") as cursor:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cursor.execute(statement, (REGISTERED_ON, derivation_id))
    with acting_as(db, "glasswell_pipeline") as cursor:
        cursor.execute(statement, (REGISTERED_ON, derivation_id))


def test_a_thousand_distinct_as_of_values_leave_one_cache_entry(
    db: psycopg.Connection,
) -> None:
    """gate-v076 H-3. `load_jurisdictions` caches per clock pair in a module-level dict with no
    cap, no TTL and no eviction, and `/v1/jurisdictions?as_of=` put the caller's date straight
    into the key — so a caller walking distinct dates grew the process's memory for its
    lifetime, on a VM with a stated RAM constraint and a publicly reachable API.

    Both clocks gate `jurisdictions_as_of`, so the answer only changes at an instant in
    `published_at` or `effective_from`. Resolving to those instants before the key is built is
    exact: the registration set is identical, and the key space is the registry's own history.
    """
    from glasswell.lineage.jurisdictions import (
        _CACHE,
        clear_jurisdiction_cache,
        load_jurisdictions,
    )

    seed_jurisdictions(db)
    db.commit()
    clear_jurisdiction_cache()

    first = load_jurisdictions(db, REGISTERED_ON)
    codes = sorted(row.jurisdiction_code for row in first)
    # A thousand dates on both sides of the only publication instant this registry has.
    for offset in range(1, 1001):
        registry = load_jurisdictions(db, REGISTERED_ON + timedelta(days=offset))
        assert sorted(row.jurisdiction_code for row in registry) == codes

    assert len(_CACHE) == 1, sorted(_CACHE)
    clear_jurisdiction_cache()


def test_the_registry_still_reports_the_clock_it_was_asked_for(
    db: psycopg.Connection,
) -> None:
    """The instants bound the cache; they are not what the surface reports. `/v1/jurisdictions`
    serves `registry.knowledge_as_of` as its `as_of` and mints its cursor from it, so resolving
    the reported value would have moved the envelope and broken paging across a cut."""
    from glasswell.lineage.jurisdictions import clear_jurisdiction_cache, load_jurisdictions

    seed_jurisdictions(db)
    db.commit()
    clear_jurisdiction_cache()

    asked = REGISTERED_ON + timedelta(days=500)
    registry = load_jurisdictions(db, asked)

    assert registry.knowledge_as_of == asked
    assert registry.valid_as_of == asked
    clear_jurisdiction_cache()
