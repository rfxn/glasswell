"""The two DR-17 back-load properties that only a real schema can settle.

The resume predicate is SQL over `lineage.manifests` and `staging.nd_mpr_oil`, so a unit-tier fake
proves nothing about whether it selects what it claims; and the per-month ledger checkpoint the
driver now relies on instead of writing its own union is `record_vintage_day` accumulating onto a
real row.
"""

from __future__ import annotations

import importlib.util
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path

from glasswell.ingest.base import record_vintage_day
from glasswell.ingest.nd_mpr import SOURCE_ID, IngestReport
from glasswell.lineage.vintages import open_vintage
from tests.support.seed import seed_manifest

SCRIPT = Path(__file__).resolve().parents[2] / "infra" / "load-nd-months.py"

PRIOR_ROWS = 394_278
MONTH_ROWS = 1_000


def _load():
    spec = importlib.util.spec_from_file_location("load_nd_months", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


loader = _load()


def _stage_row(connection, manifest_id: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into staging.nd_mpr_oil (manifest_id, source_row_ordinal) values (%s, 1)",
            (manifest_id,),
        )


def _report(year: int, month: int) -> IngestReport:
    return IngestReport(
        manifest_id=f"man_{year:04d}_{month:02d}",
        source_key=loader.source_key(year, month),
        report_vintage=datetime.now(UTC).date(),
        unchanged=False,
        rows_examined=MONTH_ROWS,
        rows_appended=MONTH_ROWS,
    )


def _walk(db, months, *, resume: bool = False) -> None:
    with loader.ProgressLog(None) as progress:
        loader.run_backload(
            db,
            months,
            progress=progress,
            stop=threading.Event(),
            polite_seconds=0,
            resume=resume,
        )


def test_completed_source_keys_names_the_workbooks_that_staged(db):
    staged = seed_manifest(db, sha256="a" * 64, source_key="2015_05.xlsx")
    seed_manifest(db, sha256="b" * 64, source_key="2015_06.xlsx")
    seed_manifest(db, sha256="c" * 64, source_id="nm_ocd_wcproduction", source_key="2015_05.xml")
    _stage_row(db, staged)

    assert loader.completed_source_keys(db) == {"2015_05.xlsx"}


def test_a_resume_run_skips_exactly_the_staged_workbooks(db, monkeypatch, raw_root):
    staged = seed_manifest(db, sha256="a" * 64, source_key="2015_05.xlsx")
    _stage_row(db, staged)
    db.commit()
    walked: list[tuple[int, int]] = []

    def ingest(run, *, year: int, month: int, **_: object) -> IngestReport:
        walked.append((year, month))
        return _report(year, month)

    monkeypatch.setattr(loader, "ingest_month", ingest)
    _walk(db, loader.months_between("2015-05", "2015-07"), resume=True)

    assert walked == [(2015, 6), (2015, 7)]


def test_the_walk_accumulates_the_ledger_row_and_never_rewrites_it(db, monkeypatch, raw_root):
    """Each month checkpoints onto the knowledge-day row; a driver-level union would replace it."""
    today = datetime.now(UTC).date()
    open_vintage(
        db,
        source_id=SOURCE_ID,
        vintage_date=today,
        manifest_ids=["man_prior"],
        opened_at=datetime.now(UTC),
        rows_examined=PRIOR_ROWS,
        rows_appended=PRIOR_ROWS,
        months_touched=["2025-10-01"],
    )
    db.commit()

    def ingest(run, *, year: int, month: int, **_: object) -> IngestReport:
        report = _report(year, month)
        record_vintage_day(
            db,
            source_id=SOURCE_ID,
            vintage_date=run.as_of,
            manifest_ids=[report.manifest_id],
            opened_at=datetime.now(UTC),
            rows_examined=report.rows_examined,
            rows_appended=report.rows_appended,
            months_touched=[f"{year:04d}-{month:02d}-01"],
        )
        return report

    monkeypatch.setattr(loader, "ingest_month", ingest)
    _walk(db, [(2015, 5), (2015, 6)])

    with db.cursor() as cursor:
        cursor.execute(
            "select rows_examined, rows_appended, manifest_ids, months_touched"
            "  from lineage.vintages where source_id = %s and vintage_date = %s",
            (SOURCE_ID, today),
        )
        examined, appended, manifests, months = cursor.fetchone()

    assert (examined, appended) == (PRIOR_ROWS + 2 * MONTH_ROWS, PRIOR_ROWS + 2 * MONTH_ROWS)
    assert manifests == ["man_prior", "man_2015_05", "man_2015_06"]
    assert months == ["2015-05-01", "2015-06-01", "2025-10-01"]
