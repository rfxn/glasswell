"""What the harness has to know about roles before any worker migrates.

A role is cluster-global, not per-database, so the `if not exists (select 1 from pg_roles ...)`
that 001, 026 and 076 each guard their CREATE with is a check and not a lock. The harness closes
that by creating them all up front under an advisory lock. Two things have to hold for it to
work, and neither needs a database: it must know every role there is, and it must name the
outcomes a lost race actually produces.
"""

from __future__ import annotations

import re

import psycopg

from glasswell.db.migrate import discover_migrations
from tests.conftest import CLUSTER_ROLE_RACE, declared_cluster_roles


def test_the_harness_finds_every_role_a_migration_declares() -> None:
    """A migration that spelled its CREATE differently would slip past the pattern, the
    pre-create would miss that role, and the duplicate-key race would come back silently."""
    declarations = sum(
        len(re.findall(r"(?i)\bcreate\s+role\b", migration.sql))
        for migration in discover_migrations()
    )
    resolved = declared_cluster_roles()

    assert declarations > 0, "no migration creates a role; the pattern moved"
    assert len(resolved) == declarations, (
        f"{declarations} create-role statements resolved to {sorted(resolved)} — the harness's"
        " pattern does not read one of them, so it would not be pre-created"
    )
    assert all(attributes in ("", "login", "nologin") for attributes in resolved.values()), resolved


def test_the_suppressed_classes_are_the_two_a_lost_race_produces() -> None:
    """Asserted by SQLSTATE, not by class name, because the first fix caught the wrong one:
    `CREATE ROLE` on a role that already exists is 42710, but two sessions issuing it at the same
    instant put the loser on `pg_authid_rolname_index`, which is 23505 — and 23505 is not a
    subclass of 42710."""
    assert {psycopg.errors.lookup("42710"), psycopg.errors.lookup("23505")} == set(
        CLUSTER_ROLE_RACE
    )
    assert not issubclass(psycopg.errors.UniqueViolation, psycopg.errors.DuplicateObject)
