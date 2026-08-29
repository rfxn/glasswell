"""The serving day is UTC everywhere, because PostgreSQL stamps publication in its own.

Migration 049 defaults `published_vintage` to the database's `current_date` and the registry
lookup filters `published_vintage <= knowledge_cut`. When the two clocks disagree by a day —
which they do for the whole evening on any host west of UTC — every row published that day is
invisible, every lookup returns nothing, and callers quarantine rows they should have resolved.
The failure is silent: an ingest run records itself as normal.
"""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime

import pytest

from glasswell.api.deps import today as api_today
from glasswell.lineage.clock import utc_today


@pytest.fixture
def west_of_utc():
    """An evening in Honolulu: local date is a day behind UTC for ten hours of every day."""
    previous = os.environ.get("TZ")
    os.environ["TZ"] = "Pacific/Honolulu"
    time.tzset()
    yield
    if previous is None:
        del os.environ["TZ"]
    else:
        os.environ["TZ"] = previous
    time.tzset()


def test_the_serving_day_does_not_move_with_the_host_timezone(west_of_utc) -> None:
    assert utc_today() == datetime.now(UTC).date()


def test_the_api_clock_is_the_same_clock(west_of_utc) -> None:
    """One definition, so a fix in one place cannot leave the other reading the host."""
    assert api_today() == utc_today()


def test_no_module_reads_the_host_local_day() -> None:
    """`date.today()` is the host's day. The registry lookups must not be able to reach it.

    Matched on the parsed call rather than the text, so the one docstring that names it as the
    thing not to do does not read as an offender.
    """
    import ast
    from pathlib import Path

    root = Path(__file__).parents[2] / "src" / "glasswell"
    offenders: list[str] = []
    files = sorted(root.rglob("*.py"))
    for path in files:
        for node in ast.walk(ast.parse(path.read_text())):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "today"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "date"
            ):
                offenders.append(f"{path.relative_to(root)}:{node.lineno}")

    # A floor, so the walk cannot pass by finding no Python to parse.
    assert len(files) > 50
    assert offenders == []
