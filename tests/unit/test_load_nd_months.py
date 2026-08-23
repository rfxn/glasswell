"""`infra/load-nd-months.py` is the DR-17 back-load driver: 125 workbooks, unattended, detached.

The properties pinned here are the ones a multi-hour run that nobody is watching depends on — the
range is the range, a resume skips exactly what already landed, one unreachable workbook does not
end the walk, a stop request lands on a month boundary rather than mid-transaction, and the ledger
row is left to `record_vintage_day` rather than rewritten from the driver's own memory.
"""

from __future__ import annotations

import importlib.util
import json
import signal
import sys
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SCRIPT = Path(__file__).resolve().parents[2] / "infra" / "load-nd-months.py"

FIRST_MONTH = "2015-05"
LAST_MONTH = "2025-09"
BACKLOAD_MONTHS = 125


def _load():
    spec = importlib.util.spec_from_file_location("load_nd_months", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before execution: @dataclass resolves its own module out of sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


loader = _load()


class FakeCursor:
    def __init__(self, rows: list[tuple]) -> None:
        self.rows = rows
        self.executed: list[tuple] = []

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *_: object) -> bool:
        return False

    def execute(self, statement: str, parameters: object = None) -> None:
        self.executed.append((statement, parameters))

    def fetchall(self) -> list[tuple]:
        return self.rows


class FakeConnection:
    """Answers each cursor with the next scripted row set; counts what the driver committed."""

    def __init__(self, *responses: list[tuple]) -> None:
        self.responses = list(responses)
        self.cursors: list[FakeCursor] = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self, **_: object) -> FakeCursor:
        rows = self.responses.pop(0) if self.responses else []
        cursor = FakeCursor(rows)
        self.cursors.append(cursor)
        return cursor

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


@dataclass(frozen=True)
class FakeReport:
    manifest_id: str = "man_1"
    staged_rows: int = 10
    rows_examined: int = 10
    rows_appended: int = 10
    quarantined: dict = None  # type: ignore[assignment]
    unchanged: bool = False

    def __post_init__(self) -> None:
        if self.quarantined is None:
            object.__setattr__(self, "quarantined", {})


@dataclass(frozen=True)
class FakeRun:
    as_of: date = date(2026, 8, 22)


def _patch_ingest(monkeypatch: pytest.MonkeyPatch, ingest) -> list[tuple[int, int]]:
    seen: list[tuple[int, int]] = []

    @contextmanager
    def fake_run(*_: object, **__: object):
        yield FakeRun()

    def wrapper(run, *, year: int, month: int, **_: object):
        seen.append((year, month))
        return ingest(year, month)

    monkeypatch.setattr(loader, "open_ingest_run", fake_run)
    monkeypatch.setattr(loader, "ingest_month", wrapper)
    return seen


def test_the_backload_range_is_the_xlsx_era():
    months = loader.months_between(FIRST_MONTH, LAST_MONTH)

    assert len(months) == BACKLOAD_MONTHS
    assert months[0] == (2015, 5)
    assert months[-1] == (2025, 9)


def test_a_month_names_its_workbook():
    assert loader.source_key(2015, 5) == "2015_05.xlsx"
    assert loader.source_key(2025, 9) == "2025_09.xlsx"


def test_a_resume_skips_only_the_workbooks_that_already_staged():
    months = loader.months_between("2015-05", "2015-08")

    pending = loader.pending_months(months, completed={"2015_05.xlsx", "2015_07.xlsx"})

    assert pending == [(2015, 6), (2015, 8)]


def test_nothing_is_skipped_when_nothing_has_landed():
    months = loader.months_between("2015-05", "2015-08")

    assert loader.pending_months(months, completed=set()) == months


def test_completed_source_keys_reads_the_database_not_a_state_file():
    connection = FakeConnection([("2015_05.xlsx",), ("2015_06.xlsx",)])

    completed = loader.completed_source_keys(connection)

    assert completed == {"2015_05.xlsx", "2015_06.xlsx"}
    statement, parameters = connection.cursors[0].executed[0]
    assert loader.STAGING_TABLE in statement
    assert parameters == (loader.SOURCE_ID,)


def test_a_stop_request_cuts_the_polite_pause_short():
    stop = threading.Event()
    stop.set()

    assert loader.wait_between_months(stop, 3600) is True


def test_the_polite_pause_runs_when_nothing_stops_it():
    assert loader.wait_between_months(threading.Event(), 0) is False


def test_progress_records_reach_the_log_file_and_stdout(tmp_path, capsys):
    path = tmp_path / "backload.jsonl"

    with loader.ProgressLog(path) as progress:
        progress.write({"month": "2015-05"})
        progress.write({"month": "2015-06"})

    written = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert written == [{"month": "2015-05"}, {"month": "2015-06"}]
    assert json.loads(capsys.readouterr().out.splitlines()[0]) == {"month": "2015-05"}


def test_the_log_file_is_appended_so_a_resume_keeps_the_earlier_run(tmp_path):
    path = tmp_path / "backload.jsonl"
    path.write_text('{"month": "2015-05"}\n', encoding="utf-8")

    with loader.ProgressLog(path) as progress:
        progress.write({"month": "2015-06"})

    assert len(path.read_text(encoding="utf-8").splitlines()) == 2


def test_one_unreachable_workbook_does_not_end_the_walk(monkeypatch, tmp_path, capsys):
    def ingest(year: int, month: int):
        if (year, month) == (2015, 6):
            raise RuntimeError("404 Not Found")
        return FakeReport()

    seen = _patch_ingest(monkeypatch, ingest)
    connection = FakeConnection()

    with loader.ProgressLog(None) as progress:
        summary = loader.run_backload(
            connection,
            loader.months_between("2015-05", "2015-07"),
            progress=progress,
            stop=threading.Event(),
            polite_seconds=0,
        )

    assert seen == [(2015, 5), (2015, 6), (2015, 7)]
    assert summary.failed == ["2015-06"]
    assert summary.rows_appended == 20
    assert connection.commits == 2
    assert connection.rollbacks == 1
    assert "404 Not Found" in capsys.readouterr().out


def test_a_stop_request_ends_the_walk_at_a_month_boundary(monkeypatch):
    stop = threading.Event()

    def ingest(year: int, month: int):
        stop.set()
        return FakeReport()

    seen = _patch_ingest(monkeypatch, ingest)
    connection = FakeConnection()

    with loader.ProgressLog(None) as progress:
        summary = loader.run_backload(
            connection,
            loader.months_between("2015-05", "2015-09"),
            progress=progress,
            stop=stop,
            polite_seconds=3600,
        )

    assert seen == [(2015, 5)]
    assert summary.interrupted is True
    assert connection.commits == 1


def test_a_resume_run_walks_only_what_is_missing(monkeypatch):
    seen = _patch_ingest(monkeypatch, lambda *_: FakeReport())
    connection = FakeConnection([("2015_05.xlsx",), ("2015_06.xlsx",)])

    with loader.ProgressLog(None) as progress:
        summary = loader.run_backload(
            connection,
            loader.months_between("2015-05", "2015-08"),
            progress=progress,
            stop=threading.Event(),
            polite_seconds=0,
            resume=True,
        )

    assert seen == [(2015, 7), (2015, 8)]
    assert summary.skipped == 2


def test_the_driver_writes_no_vintage_row_of_its_own():
    """`ingest_month` checkpoints the ledger per month; a driver-level union would overwrite it."""
    assert not hasattr(loader, "open_vintage")
    assert "open_vintage" not in SCRIPT.read_text(encoding="utf-8")


def test_the_stop_signals_are_the_ones_systemd_sends():
    assert set(loader.STOP_SIGNALS) == {signal.SIGINT, signal.SIGTERM}


def test_a_backwards_range_is_refused():
    with pytest.raises(SystemExit):
        loader.months_between("2025-09", "2015-05")
