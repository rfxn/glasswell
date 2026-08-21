"""Staging never serves — asserted over the whole schema, for every serving role.

The rule is a hard one (CLAUDE.md, blueprint §3.0.1, SB-01 §3.1.4) and it was held by review
alone. A migration granted the API role select on four staging tables; no router or mart read
them, so nothing failed, no test moved, and the NM track's own correct schema-wide assertion
was narrowed to `stg_nm_ocd%` specifically so that another lane's violation would not report as
theirs. A guard scoped around a live breach protects the breach.

This is jurisdiction-agnostic on purpose: it takes no list of tables and no prefix, so a
staging relation added by any future slice is covered on the day it is created. It also takes
no list of roles. `information_schema` and a hardcoded role tuple between them let five grant
shapes through — a materialised view, a column-level grant, a grant to PUBLIC, role membership,
and a serving role nobody had added to the tuple — each of which confers real staging read
access (gate-tx-qa re-gate, D5). `has_table_privilege` over `pg_class` answers the question the
rule actually asks: can a role that answers requests read a staging relation, by any route.

What it cannot reach is a superuser, which holds every privilege by definition and is excluded
below. The harness connects as one, so this file proves the grant graph and not the deployed
connection role; on a host where that role is not a superuser it is inside the derived set and
subject to every assertion here.
"""

from __future__ import annotations

import psycopg
import pytest

_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
# Column ACLs are invisible to has_table_privilege; these four are the ones a column can carry.
_COLUMN_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "REFERENCES")
_RELATION_KINDS = ("r", "p", "v", "m", "f")

# A role that can read the published surface serves; a role holding a write grant on staging in
# its own right is a parser, which is the other half of the same rule. Membership is deliberately
# not unwound here: inheriting the pipeline's grants must not exempt a role from the guard.
_SERVING_ROLES = """
select distinct grantee.rolname
  from pg_class published
  join pg_namespace space on space.oid = published.relnamespace
 cross join pg_roles grantee
 where space.nspname = 'marts'
   and published.relkind = any(%(kinds)s)
   and has_table_privilege(grantee.oid, published.oid, 'SELECT')
   and not grantee.rolsuper
   and grantee.rolname not like 'pg\\_%%'
   and not exists (
       select 1
         from pg_class staged
         join pg_namespace staging_space on staging_space.oid = staged.relnamespace
        where staging_space.nspname = 'staging'
          and (staged.relowner = grantee.oid
               or exists (
                   select 1
                     from aclexplode(
                         coalesce(staged.relacl, acldefault('r', staged.relowner))) as acl
                    where acl.grantee = grantee.oid
                      and acl.privilege_type = any(%(writes)s))))
 order by 1
"""

_STAGING_PRIVILEGES = """
with serving as (select unnest(%(roles)s::text[]) as rolname),
     staged as (
         select relation.oid, relation.relname, relation.relkind
           from pg_class relation
           join pg_namespace space on space.oid = relation.relnamespace
          where space.nspname = 'staging' and relation.relkind = any(%(kinds)s)
     ),
     privilege as (select unnest(%(privileges)s::text[]) as name)
select serving.rolname, staged.relname, staged.relkind,
       string_agg(distinct privilege.name, ',' order by privilege.name)
  from serving cross join staged cross join privilege
 where has_table_privilege(serving.rolname, staged.oid, privilege.name)
    or (privilege.name = any(%(column_privileges)s)
        and has_any_column_privilege(serving.rolname, staged.oid, privilege.name))
 group by serving.rolname, staged.relname, staged.relkind
 order by serving.rolname, staged.relname
"""

_SCHEMA_USAGE = """
select has_schema_privilege(%s, 'staging', 'usage')
"""


def serving_roles(connection: psycopg.Connection) -> list[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            _SERVING_ROLES,
            {"kinds": list(_RELATION_KINDS), "writes": ["INSERT", "UPDATE", "DELETE", "TRUNCATE"]},
        )
        return [name for (name,) in cursor.fetchall()]


def staging_privileges(connection: psycopg.Connection) -> list[tuple]:
    with connection.cursor() as cursor:
        cursor.execute(
            _STAGING_PRIVILEGES,
            {
                "roles": serving_roles(connection),
                "kinds": list(_RELATION_KINDS),
                "privileges": list(_PRIVILEGES),
                "column_privileges": list(_COLUMN_PRIVILEGES),
            },
        )
        return cursor.fetchall()


@pytest.fixture
def migrated(db: psycopg.Connection) -> psycopg.Connection:
    """A migrated database is the whole fixture: this is a statement about privileges."""
    return db


def test_no_serving_role_holds_any_privilege_on_any_staging_relation(migrated) -> None:
    granted = staging_privileges(migrated)

    assert granted == [], (
        "staging never serves: "
        + "; ".join(f"{role} holds {privileges} on staging.{relation} ({kind})"
                    for role, relation, kind, privileges in granted)
    )


def test_the_serving_roles_are_read_off_the_database_rather_than_listed(migrated) -> None:
    """A guard that names its own subjects cannot see a role added after it was written."""
    derived = serving_roles(migrated)

    assert "glasswell_api" in derived
    assert "martin" in derived
    assert "glasswell_pipeline" not in derived, "parsers write staging; that is the other half"


def test_the_staging_schema_is_not_even_reachable_by_the_tile_server(migrated) -> None:
    """martin discovers relations through geometry_columns, which filters on schema usage."""
    with migrated.cursor() as cursor:
        cursor.execute(_SCHEMA_USAGE, ("martin",))
        assert cursor.fetchone()[0] is False


def test_the_pipeline_role_still_writes_staging(migrated) -> None:
    """The other half of the same rule: parsers write staging, so this must not over-reach."""
    with migrated.cursor() as cursor:
        cursor.execute(
            "select count(*) from information_schema.role_table_grants"
            " where table_schema = 'staging' and grantee = 'glasswell_pipeline'"
            "   and privilege_type = 'INSERT'"
        )
        assert cursor.fetchone()[0] > 0


@pytest.mark.parametrize(
    ("name", "mutation", "expected"),
    [
        (
            "a table grant",
            ["grant select on staging.tx_wellbore_ewa to glasswell_api"],
            ("glasswell_api", "tx_wellbore_ewa", "r", "SELECT"),
        ),
        (
            "a materialised view",
            [
                "create materialized view staging.tx_wellbore_peek as"
                " select fields from staging.tx_wellbore_ewa with no data",
                "grant select on staging.tx_wellbore_peek to glasswell_api",
            ],
            ("glasswell_api", "tx_wellbore_peek", "m", "SELECT"),
        ),
        (
            "a column-level grant",
            ["grant select (fields) on staging.tx_wellbore_ewa to glasswell_api"],
            ("glasswell_api", "tx_wellbore_ewa", "r", "SELECT"),
        ),
        (
            "a grant to PUBLIC",
            ["grant select on staging.tx_wellbore_ewa to public"],
            ("glasswell_api", "tx_wellbore_ewa", "r", "SELECT"),
        ),
        (
            "role membership",
            ["grant glasswell_pipeline to glasswell_api"],
            ("glasswell_api", "tx_wellbore_ewa", "r", "DELETE,INSERT,SELECT"),
        ),
        (
            "a serving role the tuple never named",
            [
                "create role glasswell_reader nologin",
                "grant usage on schema marts to glasswell_reader",
                "grant select on all tables in schema marts to glasswell_reader",
                "grant select on staging.tx_wellbore_ewa to glasswell_reader",
            ],
            ("glasswell_reader", "tx_wellbore_ewa", "r", "SELECT"),
        ),
    ],
)
def test_the_guard_catches(migrated, name, mutation, expected) -> None:
    """Each of these confers real staging read access, and each left the suite green before."""
    with migrated.cursor() as cursor:
        for statement in mutation:
            cursor.execute(statement)
    assert expected in staging_privileges(migrated), name
    migrated.rollback()

    assert staging_privileges(migrated) == [], f"{name}: the rollback left the breach standing"
