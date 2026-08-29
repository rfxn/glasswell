"""Clocks are injected. SB-07 §4.2: no wall clock reaches artifact content."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


def utc_today() -> date:
    """The serving day in UTC, never the host's.

    PostgreSQL stamps `published_vintage` with its own `current_date`. A host west of UTC that
    read `date.today()` here would call every row published today unpublished for the rest of
    its evening, and a rule the registry cannot see is one the caller quarantines against.
    """
    return datetime.now(UTC).date()
