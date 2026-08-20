from __future__ import annotations

from datetime import UTC, datetime, timedelta

from glasswell.lineage.models import DerivationRecord
from glasswell.lineage.store import RecordOutcome, reconcile


class FixedClock:
    """Deterministic clock; each read advances by a fixed step."""

    def __init__(self, start: datetime | None = None, step_ms: int = 0) -> None:
        self._now = start or datetime(2026, 8, 1, 5, 0, 0, tzinfo=UTC)
        self._step = timedelta(milliseconds=step_ms)

    def now(self) -> datetime:
        value = self._now
        self._now = self._now + self._step
        return value


class MemoryRecorder:
    """In-process DerivationRecorder with the same conflict semantics as Postgres."""

    def __init__(self) -> None:
        self.records: dict[str, DerivationRecord] = {}
        self.order: list[str] = []

    def record(self, record: DerivationRecord) -> RecordOutcome:
        existing = self.records.get(record.derivation_id)
        action = reconcile(
            existing_status=existing.status if existing else None,
            existing_sha256=existing.output_sha256 if existing else None,
            incoming=record,
        )
        if action == "noop":
            return RecordOutcome(derivation_id=record.derivation_id, created=False)
        self.records[record.derivation_id] = record
        if action == "insert":
            self.order.append(record.derivation_id)
        return RecordOutcome(derivation_id=record.derivation_id, created=action == "insert")
