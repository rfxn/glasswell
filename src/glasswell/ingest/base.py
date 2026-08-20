"""The bundle every ingest phase runs under: one connection, one session, one raw zone."""

from __future__ import annotations

import hashlib
import os
import platform
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import psycopg

from glasswell.lineage.capture import LineageSession, lineage_session
from glasswell.lineage.clock import Clock
from glasswell.lineage.fetch import resolve_raw_root
from glasswell.lineage.models import DeriveEnvironment
from glasswell.lineage.store import PostgresRecorder

CODE_VERSION_ENV = "GLASSWELL_CODE_VERSION"
LOCKFILE_SHA256_ENV = "GLASSWELL_LOCKFILE_SHA256"


@dataclass(frozen=True, slots=True)
class IngestRun:
    connection: psycopg.Connection
    session: LineageSession
    as_of: date
    raw_root: Path


def _code_version() -> str:
    declared = os.environ.get(CODE_VERSION_ENV)
    if declared:
        return declared
    try:
        return f"pkg:{version('glasswell')}"
    except PackageNotFoundError:
        return "pkg:unknown"


def resolve_environment(connection: psycopg.Connection) -> DeriveEnvironment:
    """Upsert the pinned build identity derive() stamps on every node (SB-07 §4.1)."""
    python_version = platform.python_version()
    lockfile_sha256 = os.environ.get(LOCKFILE_SHA256_ENV)
    fingerprint = hashlib.sha256(f"{python_version}|{lockfile_sha256}".encode()).hexdigest()
    env_id = f"env_{fingerprint[:16]}"
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into lineage.environments (env_id, python_version, lockfile_sha256, threads)"
            " values (%s, %s, %s, 1) on conflict (env_id) do nothing",
            (env_id, python_version, lockfile_sha256),
        )
    return DeriveEnvironment(code_version=_code_version(), code_dirty=False, env_id=env_id)


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
    """Open the lineage session an ingest runs under; `as_of` is read from that session's clock."""
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
            as_of=session.clock.now().date(),
            raw_root=resolve_raw_root(raw_root),
        )
