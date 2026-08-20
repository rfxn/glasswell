"""New Mexico OCD: one polite pull of the nine in-scope tables, each under its own manifest.

The FTP publishes undated per-table zips and overwrites them nightly, so the retrieval vintage
is glasswell's own stamp and the `source_key` is the constant filename — a vintage-stamped key
would start a fresh supersession chain on every pull. The layout comes from the registry, the
host from the pin: this module holds no mapping literal beyond the address SB-01 §1.2 requires
a human to change.
"""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import psycopg

from glasswell.ingest.base import IngestRun, open_ingest_run, resolve_environment
from glasswell.lineage.audit import emit
from glasswell.lineage.conformance import ConformanceRule, load_rules
from glasswell.lineage.errors import RuleSpecError
from glasswell.lineage.fetch import fetch_raw
from glasswell.lineage.ftp import FTP, FtpTransferFailed, close_ftp, connect_ftp, ftp_url

__rule_version__ = "1"

FTP_HOST = "164.64.106.6"  # pinned; a failure halts, never guesses (SB-01 §1.2)
MEDIA_TYPE = "application/zip"
SPINE_TABLE = "wcproduction"
# The nine in-scope tables. othervolume, podvolume, podstorage, wcinjection and acreage are
# deliberately out of scope (PLAN-NM §6) and are not fetched.
TABLES: tuple[str, ...] = (
    "pool",
    "ogrid",
    "property",
    "spacingunit",
    "podwc",
    "pod",
    "wchistory",
    "wellhistory",
    SPINE_TABLE,
)
# SB-01 §1.3: sequential, spaced, one connection. The source has no published grant, so the
# pull is paced to be unmistakably a single polite client rather than a crawl.
FETCH_SPACING_SECONDS = 5.0
# The host reset the data channel on the third transfer of the first real pull, so a transfer
# failure is retried on a fresh login. A host that will not answer at all is never retried:
# SB-01 §1.2 makes that a halt, not a wait.
FETCH_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 15.0

LAYOUT_FAMILY = "ftp_layout"
VINTAGE_FAMILY = "undated_vintage"
HOST_PIN_FAMILY = "host_pin"


@dataclass(frozen=True, slots=True)
class TableFetch:
    table: str
    source_id: str
    source_key: str
    manifest_id: str
    sha256: str
    bytes: int
    unchanged: bool
    payload_path: str
    upstream_mtime: str | None
    fetch_vintage: str

    def to_dict(self) -> dict[str, object]:
        return {
            "table": self.table,
            "source_id": self.source_id,
            "source_key": self.source_key,
            "manifest_id": self.manifest_id,
            "sha256": self.sha256,
            "bytes": self.bytes,
            "unchanged": self.unchanged,
            "payload_path": self.payload_path,
            "upstream_mtime": self.upstream_mtime,
            "fetch_vintage": self.fetch_vintage,
        }


def source_id_for(table: str) -> str:
    return f"nm_ocd_{table}"


def _rule(rules: Sequence[ConformanceRule], table: str, family: str) -> ConformanceRule:
    wanted = f"cr_nm_{table}_{family}"
    for rule in rules:
        if rule.rule_family == wanted:
            return rule
    raise RuleSpecError(f"{wanted} is not seeded for nm_ocd_{table}; run seed_all first")


def fetch_table(
    run: IngestRun,
    table: str,
    *,
    connection: FTP | None = None,
    raw_root: Path | str | None = None,
) -> TableFetch:
    """Fetch one table's zip under the rules that say where it lives and what it is called."""
    source_id = source_id_for(table)
    rules = load_rules(run.connection, source_id=source_id, stage="parse", as_of=run.as_of)
    layout = _rule(rules, table, LAYOUT_FAMILY)
    vintage_rule = _rule(rules, table, VINTAGE_FAMILY)
    # code_ref has no executor (nd_mpr.py filters the same way); the pin is read and cited.
    host_pin = _rule(rules, table, HOST_PIN_FAMILY)
    if str(host_pin.spec["host"]) != FTP_HOST:
        raise RuleSpecError(
            f"{host_pin.rule_id} pins {host_pin.spec['host']!r} and the module pins {FTP_HOST!r};"
            " re-pin both in one change (SB-01 §1.2)"
        )

    source_key = str(vintage_rule.spec["source_key"])
    result = fetch_raw(
        run.connection,
        source_id,
        source_key,
        url=ftp_url(FTP_HOST, str(layout.spec["path"])),
        acquisition_method="ftp_anon",
        raw_root=raw_root if raw_root is not None else run.raw_root,
        ftp=connection,
        rules=[layout.rule_id, vintage_rule.rule_id, host_pin.rule_id],
        media_type=MEDIA_TYPE,
    )
    manifest = result.manifest
    return TableFetch(
        table=table,
        source_id=source_id,
        source_key=source_key,
        manifest_id=manifest.manifest_id,
        sha256=manifest.sha256,
        bytes=manifest.bytes,
        unchanged=result.unchanged,
        payload_path=str(result.payload_path),
        upstream_mtime=manifest.upstream_mtime.isoformat() if manifest.upstream_mtime else None,
        fetch_vintage=manifest.fetch_vintage.isoformat(),
    )


def fetch_all(
    run: IngestRun,
    *,
    tables: Sequence[str] = TABLES,
    raw_root: Path | str | None = None,
    spacing_seconds: float = FETCH_SPACING_SECONDS,
    backoff_seconds: float = RETRY_BACKOFF_SECONDS,
    sleep: object = time.sleep,
) -> list[TableFetch]:
    """One login, the tables in order, spaced, each transfer retried a bounded number of times."""
    _require_sources(run.connection, tables)
    fetched: list[TableFetch] = []
    connection = _open_session(run)
    try:
        for index, table in enumerate(tables):
            if index:
                sleep(spacing_seconds)  # type: ignore[operator]
            for attempt in range(FETCH_ATTEMPTS):
                try:
                    fetched.append(
                        fetch_table(run, table, connection=connection, raw_root=raw_root)
                    )
                    break
                except FtpTransferFailed:
                    # fetch_raw has already recorded the failure; committing keeps that row
                    # whether or not the retry succeeds.
                    run.connection.commit()
                    if attempt == FETCH_ATTEMPTS - 1:
                        raise
                    # The reset leaves the control channel mid-command, so the retry gets a
                    # fresh login rather than another RETR down a broken one.
                    close_ftp(connection)
                    sleep(backoff_seconds * (attempt + 1))  # type: ignore[operator]
                    connection = _open_session(run)
            run.connection.commit()
    finally:
        close_ftp(connection)
    return fetched


def _open_session(run: IngestRun) -> FTP:
    """The shared login happens outside fetch_raw, so its halt is recorded here instead."""
    try:
        return connect_ftp(FTP_HOST)
    except OSError as error:
        emit(
            run.connection,
            "raw.fetch_failed",
            subject_type="manifest",
            subject_id=f"nm_ocd/{FTP_HOST}",
            payload={
                "url": ftp_url(FTP_HOST, "/"),
                "reason": getattr(error, "glasswell_reason", type(error).__name__),
                "detail": str(error),
            },
            correlation_id=run.session.correlation_id,
        )
        run.connection.commit()
        raise


def _require_sources(connection: psycopg.Connection, tables: Sequence[str]) -> None:
    """Fail before the socket opens, not nine artifacts in (open_ingest_run's contract)."""
    wanted = [source_id_for(table) for table in tables]
    with connection.cursor() as cursor:
        cursor.execute(
            "select source_id from lineage.sources where source_id = any(%s)", (wanted,)
        )
        present = {row[0] for row in cursor.fetchall()}
    missing = [source for source in wanted if source not in present]
    if missing:
        raise LookupError(f"lineage.sources has no row for {missing}; seed it before fetching")


def run_fetch(
    connection: psycopg.Connection,
    *,
    tables: Sequence[str] = TABLES,
    raw_root: Path | str | None = None,
    spacing_seconds: float = FETCH_SPACING_SECONDS,
    environment: Mapping[str, str] | None = None,
    env_id: str | None = None,
    code_version: str | None = None,
) -> list[TableFetch]:
    resolved = resolve_environment(connection, env_id=env_id, code_version=code_version)
    with open_ingest_run(
        connection,
        source_id=source_id_for(SPINE_TABLE),
        raw_root=raw_root,
        environment=resolved,
    ) as run:
        return fetch_all(
            run, tables=tables, raw_root=raw_root, spacing_seconds=spacing_seconds
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch the NM OCD tables into the raw zone.")
    parser.add_argument("--dsn", required=True)
    parser.add_argument(
        "--fetch-only",
        action="store_true",
        required=True,
        help="phase 1 ships the fetch half; staging and promotion land in phase 2",
    )
    parser.add_argument(
        "--tables",
        default=",".join(TABLES),
        help="comma-separated subset, so a failed pull resumes without re-fetching the rest",
    )
    parser.add_argument("--raw-root", default=None)
    parser.add_argument("--spacing-seconds", type=float, default=FETCH_SPACING_SECONDS)
    parser.add_argument("--env-id", default=None)
    parser.add_argument("--code-version", default=None)
    arguments = parser.parse_args(argv)

    tables = [table.strip() for table in arguments.tables.split(",") if table.strip()]
    unknown = [table for table in tables if table not in TABLES]
    if unknown:
        parser.error(f"not an in-scope NM table: {unknown}")

    connection = psycopg.connect(arguments.dsn)
    try:
        try:
            fetched = run_fetch(
                connection,
                tables=tables,
                raw_root=arguments.raw_root,
                spacing_seconds=arguments.spacing_seconds,
                env_id=arguments.env_id,
                code_version=arguments.code_version,
            )
        except OSError:
            # The raw.fetch_failed row is the halt's evidence; rolling back would leave the
            # ledger claiming the pull never happened (SB-01 §1.2).
            connection.commit()
            raise
        connection.commit()
    finally:
        connection.close()
    for result in fetched:
        print(json.dumps(result.to_dict(), sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
