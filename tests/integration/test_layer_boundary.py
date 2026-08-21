"""Staging never serves — asserted over the whole schema, for every serving role.

The rule is a hard one (CLAUDE.md, blueprint §3.0.1, SB-01 §3.1.4) and it was held by review
alone. A migration granted the API role select on four staging tables; no router or mart read
them, so nothing failed, no test moved, and the NM track's own correct schema-wide assertion
was narrowed to `stg_nm_ocd%` specifically so that another lane's violation would not report as
theirs. A guard scoped around a live breach protects the breach.

This is jurisdiction-agnostic on purpose: it takes no list of tables and no prefix, so a
staging relation added by any future slice is covered on the day it is created.
"""

from __future__ import annotations

import psycopg
import pytest

# Roles that answer a request. `glasswell_pipeline` is deliberately absent: parsers write
# staging, which is the other half of the same rule.
SERVING_ROLES = ("glasswell_api", "martin")

_STAGING_PRIVILEGES = """
select grantee, table_name, string_agg(distinct privilege_type, ',' order by privilege_type)
  from information_schema.role_table_grants
 where table_schema = 'staging' and grantee = any(%s)
 group by grantee, table_name
 order by grantee, table_name
"""

_SCHEMA_USAGE = """
select has_schema_privilege(%s, 'staging', 'usage')
"""


@pytest.fixture
def migrated(db: psycopg.Connection) -> psycopg.Connection:
    """A migrated database is the whole fixture: this is a statement about privileges."""
    return db


def test_no_serving_role_holds_any_privilege_on_any_staging_relation(migrated) -> None:
    with migrated.cursor() as cursor:
        cursor.execute(_STAGING_PRIVILEGES, (list(SERVING_ROLES),))
        granted = cursor.fetchall()

    assert granted == [], (
        "staging never serves: "
        + "; ".join(f"{role} holds {privileges} on staging.{table}"
                    for role, table, privileges in granted)
    )


def test_the_staging_schema_is_not_even_reachable_by_the_tile_server(migrated) -> None:
    """martin discovers relations through geometry_columns, which filters on schema usage."""
    with migrated.cursor() as cursor:
        cursor.execute(_SCHEMA_USAGE, ("martin",))
        assert cursor.fetchone()[0] is False


def test_the_guard_can_fail(migrated) -> None:
    """A privilege test that never sees a privilege proves nothing. Grant one, catch it, undo."""
    with migrated.cursor() as cursor:
        cursor.execute("grant select on staging.tx_wellbore_ewa to glasswell_api")
        cursor.execute(_STAGING_PRIVILEGES, (list(SERVING_ROLES),))
        assert cursor.fetchall() == [("glasswell_api", "tx_wellbore_ewa", "SELECT")]
    migrated.rollback()

    with migrated.cursor() as cursor:
        cursor.execute(_STAGING_PRIVILEGES, (list(SERVING_ROLES),))
        assert cursor.fetchall() == []


def test_the_pipeline_role_still_writes_staging(migrated) -> None:
    """The other half of the same rule: parsers write staging, so this must not over-reach."""
    with migrated.cursor() as cursor:
        cursor.execute(
            "select count(*) from information_schema.role_table_grants"
            " where table_schema = 'staging' and grantee = 'glasswell_pipeline'"
            "   and privilege_type = 'INSERT'"
        )
        assert cursor.fetchone()[0] > 0
