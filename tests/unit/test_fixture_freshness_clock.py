"""The corpus must not age into `stale` on a calendar date rather than on a code change."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tests.support.seed import FETCH_VINTAGE, FETCHED_AT

MIGRATIONS = Path(__file__).resolve().parents[2] / "src" / "glasswell" / "db" / "migrations"
CADENCE = re.compile(r"interval '(\d+) days'")


def shortest_declared_poll_interval() -> timedelta:
    days = [
        int(match)
        for path in MIGRATIONS.glob("*.sql")
        for match in CADENCE.findall(path.read_text(encoding="utf-8"))
    ]
    assert days, f"no `interval '<n> days'` cadence found under {MIGRATIONS}"
    return timedelta(days=min(days))


def test_the_seeded_artifact_is_younger_than_the_shortest_cadence():
    """`source_freshness` calls an artifact older than its cadence `stale` when no durable
    attempt proves a check. A fixed FETCHED_AT therefore reddens the health contract on a
    date with no code change — 2026-09-05, for the 35-day cadence migration 050 seeds."""
    age = datetime.now(UTC) - FETCHED_AT

    assert age < shortest_declared_poll_interval(), (
        f"the seeded artifact is {age.days} days old and the shortest declared cadence is"
        f" {shortest_declared_poll_interval().days} days — pin FETCHED_AT relative to now,"
        f" not to an absolute date"
    )
    assert age >= timedelta(0), "the seeded artifact is in the future, which reads as stale"


def test_the_pinned_vintage_is_independent_of_the_freshness_clock():
    """Served figures assert on the vintage, so it stays fixed while the clock moves. The
    clock is asserted against now rather than against the vintage: the two coincide for one
    day a year, and a ratchet against date-dependence must not itself be date-dependent."""
    assert FETCH_VINTAGE.isoformat() == "2026-08-01"
    assert datetime.now(UTC) - FETCHED_AT < timedelta(days=2)
