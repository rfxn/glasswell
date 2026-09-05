"""The bundle every ingest phase runs under: one connection, one session, one raw zone."""

from __future__ import annotations

import hashlib
import os
import platform
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from glasswell.lineage.capture import LineageSession, lineage_session
from glasswell.lineage.clock import Clock
from glasswell.lineage.fetch import resolve_raw_root
from glasswell.lineage.models import DeriveEnvironment, VintageRecord
from glasswell.lineage.store import PostgresRecorder
from glasswell.lineage.vintages import open_vintage

CODE_VERSION_ENV = "GLASSWELL_CODE_VERSION"
LOCKFILE_SHA256_ENV = "GLASSWELL_LOCKFILE_SHA256"


@dataclass(frozen=True, slots=True)
class IngestRun:
    connection: psycopg.Connection
    session: LineageSession
    as_of: date
    declared_raw_root: Path | str | None = None

    @property
    def raw_root(self) -> Path:
        """The raw zone, resolved where it is reached rather than where the run opens.

        A promotion reads staging and writes canonical and never touches the raw zone, so
        requiring it to declare one would refuse over a resource it does not use.
        """
        return resolve_raw_root(self.declared_raw_root)


def _code_version() -> str:
    declared = os.environ.get(CODE_VERSION_ENV)
    if declared:
        return declared
    try:
        return f"pkg:{version('glasswell')}"
    except PackageNotFoundError:
        return "pkg:unknown"


def resolve_environment(
    connection: psycopg.Connection,
    *,
    env_id: str | None = None,
    code_version: str | None = None,
) -> DeriveEnvironment:
    """Upsert the pinned build identity derive() stamps on every node (SB-07 §4.1).

    `env_id` names the row instead of fingerprinting it, and the pin is recorded on the way in,
    so a CLI override is no longer the reason a derivation lands unpinned (M-4). An env_id that
    already exists keeps what it recorded: derivations already point at it.
    """
    python_version = platform.python_version()
    lockfile_sha256 = os.environ.get(LOCKFILE_SHA256_ENV)
    fingerprint = hashlib.sha256(f"{python_version}|{lockfile_sha256}".encode()).hexdigest()
    resolved = env_id or f"env_{fingerprint[:16]}"
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into lineage.environments (env_id, python_version, lockfile_sha256, threads)"
            " values (%s, %s, %s, 1) on conflict (env_id) do nothing",
            (resolved, python_version, lockfile_sha256),
        )
    return DeriveEnvironment(
        code_version=code_version or _code_version(), code_dirty=False, env_id=resolved
    )


_VINTAGE_DAY_COUNTERS = """
select rows_examined, rows_appended, manifest_ids, months_touched, restatement_summary
  from lineage.vintages where source_id = %s and vintage_date = %s
"""


def record_vintage_day(
    connection: psycopg.Connection,
    *,
    source_id: str,
    vintage_date: date,
    manifest_ids: Sequence[str],
    opened_at: datetime,
    promotion_derivation_id: str | None = None,
    rows_examined: int = 0,
    rows_appended: int = 0,
    months_touched: Sequence[str] = (),
    restatement_summary: Mapping[str, int] | None = None,
) -> VintageRecord | None:
    """The vintage row is the ledger of the vintage-day, not the report of one run.

    `open_vintage` upserts on (source, day) while canonical accumulates across same-day runs,
    so prior counters are read back and summed (DR-78, the shape gate-nm-fp D2 closed for NM).
    Returns the written record, or None when a run that appended nothing left an existing row
    alone rather than overwriting the pass that did the work with its own zeroes (DR-85 widened
    the return from bool so callers can cite the vintage_id).
    """
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(_VINTAGE_DAY_COUNTERS, (source_id, vintage_date))
        prior = cursor.fetchone()
    if prior is not None and not rows_appended:
        return None
    restatement = dict(prior["restatement_summary"] if prior else {})
    for month, rows in (restatement_summary or {}).items():
        restatement[month] = restatement.get(month, 0) + rows
    return open_vintage(
        connection,
        source_id=source_id,
        vintage_date=vintage_date,
        manifest_ids=list(
            dict.fromkeys([*(prior["manifest_ids"] if prior else []), *manifest_ids])
        ),
        opened_at=opened_at,
        promotion_derivation_id=promotion_derivation_id,
        rows_examined=(prior["rows_examined"] if prior else 0) + rows_examined,
        rows_appended=(prior["rows_appended"] if prior else 0) + rows_appended,
        months_touched=sorted({*(prior["months_touched"] if prior else []), *months_touched}),
        restatement_summary=restatement,
    )


@contextmanager
def open_ingest_run(
    connection: psycopg.Connection,
    *,
    source_id: str,
    raw_root: Path | str | None = None,
    environment: DeriveEnvironment | None = None,
    clock: Clock | None = None,
    correlation_id: str | None = None,
) -> Iterator[IngestRun]:
    """Open the lineage session an ingest runs under; `as_of` is the session's pinned vintage."""
    with connection.cursor() as cursor:
        cursor.execute("select 1 from lineage.sources where source_id = %s", (source_id,))
        if cursor.fetchone() is None:
            raise LookupError(
                f"lineage.sources has no row for {source_id!r}; seed it before fetching"
            )
    with lineage_session(
        recorder=PostgresRecorder(connection),
        environment=environment or resolve_environment(connection),
        clock=clock,
        correlation_id=correlation_id,
    ) as session:
        yield IngestRun(
            connection=connection,
            session=session,
            as_of=session.vintage,
            declared_raw_root=raw_root,
        )
