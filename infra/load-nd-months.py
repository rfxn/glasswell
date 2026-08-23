"""Load a range of ND monthly production reports, one committed month at a time.

`glasswell.ingest.nd_mpr` has no month-range flag, so this driver walks the range and commits each
month on its own. The ledger checkpoint is `ingest_month`'s own `record_vintage_day` (DR-78): it
accumulates onto the (source, knowledge-day) row, so an interrupted walk still reports exactly the
months that landed. The driver writes no vintage row of its own — a union written at the end would
overwrite those accumulated counters, and a walk that crosses UTC midnight spans two knowledge days
that must stay two rows.

The DR-17 back-load is 125 workbooks and runs for hours, so a month that fails is reported and the
walk continues, SIGTERM stops it at a month boundary, and `--resume` skips workbooks that already
staged. `--resume` trades away restatement detection: a month whose upstream bytes changed since it
landed is skipped unexamined, so a routine re-walk that is looking for restatements must omit it.

    load-nd-months.py 2015-05 2025-09 --resume --raw-root /data/raw
        --log-file /var/lib/glasswell/nd-backload.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, TextIO

import psycopg

from glasswell.ingest.base import open_ingest_run
from glasswell.ingest.nd_mpr import SOURCE_ID, STAGING_TABLE, ingest_month
from glasswell.lineage.fetch import RAW_ROOT_ENV, resolve_raw_root

DEFAULT_DSN = "postgresql:///glasswell?host=/var/run/postgresql"
POLITE_SECONDS = 15
STOP_SIGNALS = (signal.SIGINT, signal.SIGTERM)
INTERRUPTED_EXIT = 130


def months_between(first: str, last: str) -> list[tuple[int, int]]:
    start, end = date.fromisoformat(f"{first}-01"), date.fromisoformat(f"{last}-01")
    if end < start:
        raise SystemExit(f"{last} is before {first}")
    months, cursor = [], start
    while cursor <= end:
        months.append((cursor.year, cursor.month))
        cursor = date(cursor.year + cursor.month // 12, cursor.month % 12 + 1, 1)
    return months


def source_key(year: int, month: int) -> str:
    """The workbook name `nd_mpr.ingest_month` fetches, which is also the manifest's source_key."""
    return f"{year:04d}_{month:02d}.xlsx"


_COMPLETED_KEYS = f"""
select distinct m.source_key
  from lineage.manifests m
 where m.source_id = %s
   and exists (select 1 from {STAGING_TABLE} s where s.manifest_id = m.manifest_id)
"""


def completed_source_keys(connection: psycopg.Connection) -> set[str]:
    """The workbooks whose staged rows are committed — the same condition `ingest_month` uses to
    short-circuit a re-fetch, so skipping them skips no work it would have done."""
    with connection.cursor() as cursor:
        cursor.execute(_COMPLETED_KEYS, (SOURCE_ID,))
        return {row[0] for row in cursor.fetchall()}


def pending_months(
    months: Sequence[tuple[int, int]], *, completed: set[str]
) -> list[tuple[int, int]]:
    return [month for month in months if source_key(*month) not in completed]


def wait_between_months(stop: threading.Event, seconds: int) -> bool:
    """True when a stop request cut the pause short.

    `Event.wait` rather than `time.sleep`: PEP 475 restarts a signal-interrupted sleep, so a
    SIGTERM during a 15-second pause would otherwise be deferred for the rest of it.
    """
    return stop.wait(seconds)


def install_stop_handler(signals: Sequence[int] = STOP_SIGNALS) -> threading.Event:
    """Record the stop request; the walk reads it at the next month boundary."""
    stop = threading.Event()
    for number in signals:
        signal.signal(number, lambda *_: stop.set())
    return stop


class ProgressLog:
    """One JSON record per line on stdout and, given a path, in a file that outlives the session."""

    def __init__(self, path: Path | str | None) -> None:
        self._path = Path(path) if path is not None else None
        self._handle: TextIO | None = None

    def __enter__(self) -> ProgressLog:
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._handle = self._path.open("a", encoding="utf-8")
        return self

    def __exit__(self, *_: object) -> bool:
        if self._handle is not None:
            self._handle.close()
            self._handle = None
        return False

    def write(self, record: Mapping[str, Any]) -> None:
        line = json.dumps(record, sort_keys=True, default=str)
        print(line, flush=True)
        if self._handle is not None:
            self._handle.write(f"{line}\n")
            self._handle.flush()


_VINTAGE_LEDGER = """
select vintage_date, cardinality(manifest_ids), rows_examined, rows_appended,
       cardinality(months_touched)
  from lineage.vintages
 where source_id = %s and vintage_date = any(%s)
 order by vintage_date
"""


def vintage_ledger(
    connection: psycopg.Connection, dates: Sequence[date]
) -> list[dict[str, Any]]:
    """What the ledger says landed, read back rather than reported from the driver's counters."""
    if not dates:
        return []
    with connection.cursor() as cursor:
        cursor.execute(_VINTAGE_LEDGER, (SOURCE_ID, list(dates)))
        return [
            {
                "vintage_date": row[0],
                "manifests": row[1],
                "rows_examined": row[2],
                "rows_appended": row[3],
                "months_touched": row[4],
            }
            for row in cursor.fetchall()
        ]


@dataclass(frozen=True, slots=True)
class Summary:
    attempted: int
    skipped: int
    unchanged: int
    failed: list[str]
    interrupted: bool
    rows_examined: int
    rows_appended: int
    vintages: list[dict[str, Any]]


def run_backload(
    connection: psycopg.Connection,
    months: Sequence[tuple[int, int]],
    *,
    progress: ProgressLog,
    stop: threading.Event,
    polite_seconds: int = POLITE_SECONDS,
    resume: bool = False,
    raw_root: str | None = None,
) -> Summary:
    """Walk the months, one committed transaction each, reporting every month as it lands."""
    completed = completed_source_keys(connection) if resume else set()
    pending = pending_months(months, completed=completed)
    progress.write(
        {
            "event": "start",
            "months": len(months),
            "pending": len(pending),
            "skipped": len(months) - len(pending),
            "raw_root": str(resolve_raw_root(raw_root)),
        }
    )

    failed: list[str] = []
    vintage_dates: set[date] = set()
    examined = appended = unchanged = attempted = 0
    interrupted = False

    for index, (year, month) in enumerate(pending):
        if stop.is_set() or (index and wait_between_months(stop, polite_seconds)):
            interrupted = True
            break
        label = f"{year:04d}-{month:02d}"
        attempted += 1
        try:
            with open_ingest_run(connection, source_id=SOURCE_ID, raw_root=raw_root) as run:
                report = ingest_month(run, year=year, month=month)
                vintage = run.as_of
            connection.commit()
        # Broad on purpose: one unreachable or malformed workbook must not end a 125-month walk.
        except Exception as error:
            connection.rollback()
            failed.append(label)
            progress.write({"month": label, "error": f"{type(error).__name__}: {error}"})
            continue

        vintage_dates.add(vintage)
        examined += report.rows_examined
        appended += report.rows_appended
        unchanged += int(report.unchanged)
        progress.write(
            {
                "month": label,
                "manifest_id": report.manifest_id,
                "staged_rows": report.staged_rows,
                "rows_examined": report.rows_examined,
                "rows_appended": report.rows_appended,
                "quarantined": dict(report.quarantined),
                "unchanged": report.unchanged,
                "vintage_date": vintage,
            }
        )

    summary = Summary(
        attempted=attempted,
        skipped=len(months) - len(pending),
        unchanged=unchanged,
        failed=failed,
        interrupted=interrupted,
        rows_examined=examined,
        rows_appended=appended,
        vintages=vintage_ledger(connection, sorted(vintage_dates)),
    )
    progress.write({"event": "complete", **_summary_record(summary)})
    return summary


def _summary_record(summary: Summary) -> dict[str, Any]:
    return {
        "attempted": summary.attempted,
        "skipped": summary.skipped,
        "unchanged": summary.unchanged,
        "failed": summary.failed,
        "interrupted": summary.interrupted,
        "rows_examined": summary.rows_examined,
        "rows_appended": summary.rows_appended,
        "vintages": summary.vintages,
    }


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("first", help="first production month, YYYY-MM")
    parser.add_argument("last", help="last production month, YYYY-MM")
    parser.add_argument("--dsn", default=os.environ.get("GLASSWELL_DSN", DEFAULT_DSN))
    parser.add_argument(
        "--raw-root",
        default=os.environ.get(RAW_ROOT_ENV),
        help="where fetched workbooks land; defaults to $GLASSWELL_RAW_ROOT, then data/raw",
    )
    parser.add_argument("--polite-seconds", type=int, default=POLITE_SECONDS)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="skip months whose workbook already staged; misses upstream restatements",
    )
    parser.add_argument("--log-file", help="append every progress record here as well as stdout")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _arguments(argv)
    months = months_between(arguments.first, arguments.last)
    stop = install_stop_handler()

    with (
        ProgressLog(arguments.log_file) as progress,
        psycopg.connect(arguments.dsn) as connection,
    ):
        summary = run_backload(
            connection,
            months,
            progress=progress,
            stop=stop,
            polite_seconds=arguments.polite_seconds,
            resume=arguments.resume,
            raw_root=arguments.raw_root,
        )

    if summary.interrupted:
        return INTERRUPTED_EXIT
    return 1 if summary.failed else 0


if __name__ == "__main__":
    sys.exit(main())
