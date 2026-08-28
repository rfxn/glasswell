"""Independently committed source-poll evidence.

The ingest transaction owns manifests, staging, and promotion. This ledger deliberately does
not: every insert/update uses a fresh autocommit connection, and a success is finalized only
after that connection can see the referenced manifest. A killed process therefore leaves an
honest open attempt instead of a success inferred from intent.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

import psycopg

from glasswell.lineage.ids import new_ulid

FetchOutcome = Literal["new", "unchanged"]
Connector = Callable[[], psycopg.Connection]

MAX_FAILURE_DETAIL = 256
_FAILURE_CODE = re.compile(r"[^a-z0-9]+")
_URL = re.compile(r"(?i)\b(?:https?|ftp)://[^\s<>'\"]+")
_AUTH_HEADER = re.compile(
    r"(?i)['\"]?(authorization|proxy-authorization)['\"]?\s*[:=]\s*['\"]?"
    r"(?:(?:bearer|basic)\s+)?[^\s,;\]}\)>'\"]+['\"]?"
)
_LABELED_SECRET = re.compile(
    r"(?i)['\"]?(password|passwd|pwd|token|secret|api[\s_-]?key)['\"]?"
    r"\s*[:=]\s*['\"]?[^\s,;\]}\)>'\"]+['\"]?"
)
_AUTH_CREDENTIAL = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]+")
_WINDOWS_PATH = re.compile(r"(?i)\b[A-Z]:\\(?:[^\\\s]+\\)*[^\\\s,;:]*")
_UNIX_PATH = re.compile(r"(?<![\w:])/(?:[^/\s]+/)*[^/\s,;:)]*")
_IP_ADDRESS = re.compile(
    r"(?i)(?<![\w.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![\w.])"
    r"|(?<![\w:])(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}(?![\w:])"
)
_INTERNAL_HOST = re.compile(
    r"(?i)\b(?:localhost|(?:[a-z0-9-]+\.)+(?:internal|local|lan|home))\b"
)


def _now() -> datetime:
    return datetime.now(UTC)


def failure_code(error: BaseException) -> str:
    declared = getattr(error, "glasswell_reason", None)
    raw = str(declared or type(error).__name__).lower()
    normalized = _FAILURE_CODE.sub("_", raw).strip("_")[:64]
    if not normalized:
        return "fetch_failed"
    if normalized[0].isalpha():
        return normalized
    return f"fetch_{normalized}"[:64]


def sanitized_evidence_text(value: str) -> str:
    detail = value.replace("\x00", " ").replace("\r", " ").replace("\n", " ")
    detail = _URL.sub("[redacted-url]", detail)
    detail = _AUTH_HEADER.sub(lambda match: f"{match.group(1)}=[redacted]", detail)
    detail = _LABELED_SECRET.sub(lambda match: f"{match.group(1)}=[redacted]", detail)
    detail = _AUTH_CREDENTIAL.sub(lambda match: f"{match.group(1)} [redacted]", detail)
    detail = _WINDOWS_PATH.sub("[redacted-path]", detail)
    detail = _UNIX_PATH.sub("[redacted-path]", detail)
    detail = _IP_ADDRESS.sub("[redacted-host]", detail)
    detail = _INTERNAL_HOST.sub("[redacted-host]", detail)
    detail = " ".join(detail.split())[:MAX_FAILURE_DETAIL]
    return detail or "No safe failure detail was available."


def sanitized_failure_detail(error: BaseException) -> str:
    return f"{failure_code(error)}; transport detail withheld from shared status"


@dataclass(slots=True)
class FetchAttempt:
    ledger: FetchAttemptLedger | None
    attempt_id: str | None
    source_id: str
    source_key: str
    attempted_at: datetime | None = None
    pending_outcome: FetchOutcome | None = None
    manifest_id: str | None = None
    resolved: bool = False

    def succeeded(self, *, created: bool, manifest_id: str) -> None:
        if self.ledger is None or self.resolved:
            return
        if self.pending_outcome is not None:
            raise RuntimeError(f"fetch attempt {self.attempt_id} already has a candidate outcome")
        self.pending_outcome = "new" if created else "unchanged"
        self.manifest_id = manifest_id
        self.ledger._pending.append(self)

    def failed(self, error: BaseException) -> None:
        if self.ledger is None or self.resolved:
            return
        if self.ledger._finalize_if_visible(self):
            return
        self.ledger._record_failure(self, error)


class FetchAttemptLedger:
    def __init__(self, connector: Connector, *, now: Callable[[], datetime] = _now) -> None:
        self._connector = connector
        self._now = now
        self._pending: list[FetchAttempt] = []

    def begin(
        self,
        source_id: str,
        source_key: str,
        *,
        correlation_id: str | None = None,
    ) -> FetchAttempt:
        self.finalize_visible()
        attempted_at = self._now().astimezone(UTC)
        attempt_id = f"fat_{new_ulid(attempted_at)}"
        with self._connector() as connection:
            connection.autocommit = True
            connection.execute(
                "insert into lineage.fetch_attempts"
                " (attempt_id, source_id, source_key, attempted_at, correlation_id)"
                " values (%s, %s, %s, %s, %s)",
                (attempt_id, source_id, source_key, attempted_at, correlation_id),
            )
        return FetchAttempt(self, attempt_id, source_id, source_key, attempted_at)

    def finalize_visible(self) -> None:
        for attempt in tuple(self._pending):
            self._finalize_if_visible(attempt)

    def fail_unresolved(self, error: BaseException) -> None:
        self.finalize_visible()
        for attempt in tuple(self._pending):
            self._record_failure(attempt, error)

    def _finalize_if_visible(self, attempt: FetchAttempt) -> bool:
        if (
            attempt.resolved
            or attempt.pending_outcome is None
            or attempt.manifest_id is None
            or attempt.attempt_id is None
        ):
            return attempt.resolved
        completed_at = self._completed_at(attempt)
        with self._connector() as connection:
            connection.autocommit = True
            row = connection.execute(
                "update lineage.fetch_attempts a"
                "   set completed_at = %s, outcome = %s, manifest_id = %s"
                " where a.attempt_id = %s and a.outcome is null"
                "   and exists (select 1 from lineage.manifests m where m.manifest_id = %s)"
                " returning a.attempt_id",
                (
                    completed_at,
                    attempt.pending_outcome,
                    attempt.manifest_id,
                    attempt.attempt_id,
                    attempt.manifest_id,
                ),
            ).fetchone()
        if row is None:
            return False
        attempt.resolved = True
        self._remove_pending(attempt)
        return True

    def _record_failure(self, attempt: FetchAttempt, error: BaseException) -> None:
        if attempt.resolved or attempt.attempt_id is None:
            return
        completed_at = self._completed_at(attempt)
        with self._connector() as connection:
            connection.autocommit = True
            row = connection.execute(
                "update lineage.fetch_attempts"
                "   set completed_at = %s, outcome = 'failed', failure_code = %s,"
                "       failure_detail = %s"
                " where attempt_id = %s and outcome is null returning attempt_id",
                (
                    completed_at,
                    failure_code(error),
                    sanitized_failure_detail(error),
                    attempt.attempt_id,
                ),
            ).fetchone()
        if row is not None:
            attempt.resolved = True
            self._remove_pending(attempt)

    def _remove_pending(self, attempt: FetchAttempt) -> None:
        self._pending = [candidate for candidate in self._pending if candidate is not attempt]

    def _completed_at(self, attempt: FetchAttempt) -> datetime:
        observed = self._now().astimezone(UTC)
        if attempt.attempted_at is None:
            return observed
        return max(observed, attempt.attempted_at)


_CURRENT_LEDGER: ContextVar[FetchAttemptLedger | None] = ContextVar(
    "glasswell_fetch_attempt_ledger", default=None
)
_ACTIVE_ATTEMPTS: ContextVar[tuple[FetchAttempt, ...]] = ContextVar(
    "glasswell_active_fetch_attempts", default=()
)


@contextmanager
def durable_fetch_attempts(
    dsn: str,
    *,
    now: Callable[[], datetime] = _now,
) -> Iterator[FetchAttemptLedger]:
    ledger = FetchAttemptLedger(lambda: psycopg.connect(dsn), now=now)
    token = _CURRENT_LEDGER.set(ledger)
    try:
        yield ledger
    except BaseException as error:
        ledger.fail_unresolved(error)
        raise
    else:
        ledger.finalize_visible()
    finally:
        _CURRENT_LEDGER.reset(token)


@contextmanager
def source_poll(
    source_id: str,
    source_key: str,
    *,
    correlation_id: str | None = None,
) -> Iterator[FetchAttempt]:
    for active in reversed(_ACTIVE_ATTEMPTS.get()):
        if active.source_id == source_id and active.source_key == source_key:
            yield active
            return

    ledger = _CURRENT_LEDGER.get()
    attempt = (
        ledger.begin(source_id, source_key, correlation_id=correlation_id)
        if ledger is not None
        else FetchAttempt(None, None, source_id, source_key)
    )
    token = _ACTIVE_ATTEMPTS.set((*_ACTIVE_ATTEMPTS.get(), attempt))
    try:
        yield attempt
    except BaseException as error:
        attempt.failed(error)
        raise
    else:
        if ledger is not None and attempt.pending_outcome is None and not attempt.resolved:
            attempt.failed(RuntimeError("source poll returned without a fetch outcome"))
    finally:
        _ACTIVE_ATTEMPTS.reset(token)
