from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from glasswell.ingest import nd_mpr
from glasswell.ingest.base import open_ingest_run
from glasswell.lineage.vintages import select_production
from glasswell.seed import seed_all
from tests.integration.test_nd_mpr_promote import CLEAN_ROWS, client_for
from tests.support.fakes import FixedClock

FIXTURES = Path(__file__).parents[1] / "fixtures" / "nd_mpr"
TRUNCATED = FIXTURES / "2026_03_truncated.xlsx"
RESTATED = FIXTURES / "2026_03_restated.xlsx"

RESTATED_API10 = "3310504037"
PRODUCTION_MONTH = date(2026, 3, 1)
ORIGINAL_OIL = Decimal("304.000")
AMENDED_OIL = Decimal("337.000")

FIRST_VINTAGE = date(2026, 8, 18)
SECOND_VINTAGE = date(2026, 8, 19)


def ingest_at(db, raw_root, lineage_env, fixture: Path, day: date) -> nd_mpr.IngestReport:
    clock = FixedClock(start=datetime(day.year, day.month, day.day, 9, 0, tzinfo=UTC))
    with open_ingest_run(
        db,
        source_id=nd_mpr.SOURCE_ID,
        raw_root=raw_root,
        environment=lineage_env,
        clock=clock,
    ) as run, client_for(fixture) as client:
        report = nd_mpr.ingest_month(run, year=2026, month=3, client=client)
    db.commit()
    return report


def oil_rows(db) -> list[tuple]:
    with db.cursor() as cursor:
        cursor.execute(
            "select report_vintage, volume, value_hash from canonical.production_monthly"
            " where api10 = %s and stream = %s and production_month = %s order by report_vintage",
            (RESTATED_API10, "oil", PRODUCTION_MONTH),
        )
        return cursor.fetchall()


@pytest.fixture
def restated(db, raw_root, lineage_env) -> tuple[nd_mpr.IngestReport, nd_mpr.IngestReport]:
    seed_all(db)
    db.commit()
    first = ingest_at(db, raw_root, lineage_env, TRUNCATED, FIRST_VINTAGE)
    second = ingest_at(db, raw_root, lineage_env, RESTATED, SECOND_VINTAGE)
    return first, second


def test_the_amended_month_appends_a_row_and_leaves_the_prior_one_untouched(db, restated):
    first, second = restated
    rows = oil_rows(db)

    assert [(row[0], row[1]) for row in rows] == [
        (FIRST_VINTAGE, ORIGINAL_OIL),
        (SECOND_VINTAGE, AMENDED_OIL),
    ]
    assert rows[0][2] != rows[1][2]
    assert first.report_vintage == FIRST_VINTAGE
    assert second.report_vintage == SECOND_VINTAGE


def test_only_the_changed_row_appends(db, restated):
    _, second = restated

    assert second.rows_appended == 1
    assert second.restatement_summary == {"2026-03-01": 1}
    with db.cursor() as cursor:
        cursor.execute("select count(*) from canonical.production_monthly")
        assert cursor.fetchone()[0] == CLEAN_ROWS * 3 + 1


def test_the_latest_view_serves_the_amended_value(db, restated):
    with db.cursor() as cursor:
        cursor.execute(
            "select volume, report_vintage from canonical.production_monthly_latest"
            " where api10 = %s and stream = %s",
            (RESTATED_API10, "oil"),
        )
        assert cursor.fetchone() == (AMENDED_OIL, SECOND_VINTAGE)


def test_an_as_of_read_returns_the_value_as_it_stood_at_that_vintage(db, restated):
    """DIR-2 and S14 in one assertion: yesterday's answer is still retrievable today."""
    as_first = select_production(
        db, as_of=FIRST_VINTAGE, api10=RESTATED_API10, stream="oil", source_id=nd_mpr.SOURCE_ID
    )
    as_latest = select_production(
        db, api10=RESTATED_API10, stream="oil", source_id=nd_mpr.SOURCE_ID
    )

    assert [row["volume"] for row in as_first] == [ORIGINAL_OIL]
    assert [row["report_vintage"] for row in as_first] == [FIRST_VINTAGE]
    assert [row["volume"] for row in as_latest] == [AMENDED_OIL]


def test_the_restatement_is_a_new_manifest_that_supersedes_the_first(db, restated):
    with db.cursor() as cursor:
        cursor.execute(
            "select manifest_id, supersedes_manifest_id from lineage.manifests"
            " order by fetched_at"
        )
        manifests = cursor.fetchall()

    assert len(manifests) == 2
    assert manifests[1][1] == manifests[0][0]


def test_the_restatement_is_announced_on_the_audit_stream(db, restated):
    with db.cursor() as cursor:
        cursor.execute(
            "select payload from lineage.audit_events where event_type = %s",
            ("canonical.restatement_detected",),
        )
        events = cursor.fetchall()

    assert len(events) == 1
    assert events[0][0]["restatement_summary"] == {"2026-03-01": 1}


def test_the_second_vintage_row_records_only_the_appended_row(db, restated):
    with db.cursor() as cursor:
        cursor.execute(
            "select vintage_date, rows_appended, restatement_summary from lineage.vintages"
            " order by vintage_date"
        )
        vintages = cursor.fetchall()

    assert [row[0] for row in vintages] == [FIRST_VINTAGE, SECOND_VINTAGE]
    assert [row[1] for row in vintages] == [CLEAN_ROWS * 3, 1]
    assert vintages[1][2] == {"2026-03-01": 1}
