"""Two properties of shipped migration files that are read off the SQL and never off a database.

`migrate.py` runs each file in one transaction, so what a file says about its own locking and
its own evidence is decidable from `discover_migrations()` alone. Both guards lived in the
database tier beside the behaviour they bound, and neither took a fixture.
"""

from __future__ import annotations

import re

import pytest

from glasswell.db.migrate import discover_migrations

pytestmark = pytest.mark.unit


def migration_sql(name: str) -> str:
    return next(item.sql for item in discover_migrations() if item.name == name)


def test_the_facet_status_index_rebuild_is_bounded_by_a_lock_timeout() -> None:
    """An unbounded ACCESS EXCLUSIVE on the serving spine is an outage; a refusal is a retry.

    `migrate.py` runs each file in one transaction, so `create index concurrently` is refused
    and the drop takes ACCESS EXCLUSIVE on `canonical.wells` until commit. The deployed host has
    `lock_timeout = 0` and `deploy.sh` applies migrations while the API is still serving, so
    without a bound the DROP waits for the longest in-flight reader — and every new read queues
    behind the waiting request. `set local` because the whole file is one transaction.
    """
    body = migration_sql("facet_status_resolution")
    timeout = body.index("set local lock_timeout")
    assert timeout < body.index("drop index if exists canonical."), "the bound precedes the lock"
    assert "'5s'" in body[timeout : timeout + 60]


def test_the_scheduler_observe_migration_states_one_evidence_pair() -> None:
    """Counted by shape, so the guard survives its own repoint: the pair is the placeholder
    before the train and the tag plus its merge commit after, and what is being held is that
    the file states its evidence once."""
    body = migration_sql("scheduler_observe")

    tags = re.findall(r"'(?:UNRELEASED|v\d+\.\d+)'", body)
    commits = re.findall(r"'[0-9a-f]{40}'", body)

    assert len(tags) == 1, f"the file states its evidence tag {len(tags)} times: {tags}"
    assert len(commits) == 1, f"the file states its evidence commit {len(commits)} times"
