"""DR-21: the `marts` privileges the refresh needs, held by a migration rather than by hand.

The deployed database carried `create on schema marts` for the pipeline role because someone
typed it during P7. A privilege that exists only on one host is drift by definition — the next
database a migration builds would fail on its first `refresh_all`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
import pytest


@contextmanager
def acting_as(connection: psycopg.Connection, role: str) -> Iterator[psycopg.Cursor]:
    """Privileges are only real when the role is the one asking; the fixture owns everything."""
    with connection.cursor() as cursor:
        cursor.execute(f"set local role {role}")
        try:
            yield cursor
        finally:
            connection.rollback()


def test_the_pipeline_role_may_create_in_marts(db: psycopg.Connection):
    """`refresh_all` issues create-or-replace for the view and all three tile functions."""
    with acting_as(db, "glasswell_pipeline") as cursor:
        cursor.execute("create or replace view marts.gw_grant_probe as select 1 as probe")
        cursor.execute("create or replace function marts.gw_grant_probe_fn() returns int"
                       " language sql immutable as $$ select 1 $$")


def test_the_api_role_may_not_create_in_marts(db: psycopg.Connection):
    """The read path stays a read path: only the pipeline rebuilds a mart."""
    with acting_as(db, "glasswell_api") as cursor:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cursor.execute("create or replace view marts.gw_grant_probe as select 1 as probe")


def test_the_api_role_may_read_the_spacing_unit_view(db: psycopg.Connection):
    """Migration 009's blanket grant could not reach a view that did not exist yet."""
    with acting_as(db, "glasswell_api") as cursor:
        cursor.execute("select count(*) from marts.nd_spacing_units_tile")
        assert cursor.fetchone()[0] == 0
