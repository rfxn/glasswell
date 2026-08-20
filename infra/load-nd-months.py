"""Load a range of ND monthly production reports as ONE knowledge-time vintage.

`glasswell.ingest.nd_mpr` has no `--months` range flag, and `lineage.vintages` is unique on
(source_id, vintage_date): six separate CLI runs fetched on the same day upsert the same row
and leave it reporting only the last month. This driver runs the months sequentially and then
re-opens the vintage with the union — six production months under one knowledge-time vintage,
which is also the correct bitemporal reading (PLAN.md P7.5 M16).

    /opt/glasswell/venv/bin/python infra/load-nd-months.py 2025-10 2026-03
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date

import psycopg

from glasswell.ingest.base import open_ingest_run
from glasswell.ingest.nd_mpr import SOURCE_ID, ingest_month
from glasswell.lineage.vintages import open_vintage

DEFAULT_DSN = "postgresql:///glasswell?host=/var/run/postgresql"
POLITE_SECONDS = 15


def months_between(first: str, last: str) -> list[tuple[int, int]]:
    start, end = date.fromisoformat(f"{first}-01"), date.fromisoformat(f"{last}-01")
    if end < start:
        raise SystemExit(f"{last} is before {first}")
    months, cursor = [], start
    while cursor <= end:
        months.append((cursor.year, cursor.month))
        cursor = date(cursor.year + cursor.month // 12, cursor.month % 12 + 1, 1)
    return months


def _vintage_months(connection: psycopg.Connection, vintage_date: date) -> list[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            "select months_touched from lineage.vintages"
            " where source_id = %s and vintage_date = %s",
            (SOURCE_ID, vintage_date),
        )
        row = cursor.fetchone()
    return list(row[0]) if row else []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first", help="first production month, YYYY-MM")
    parser.add_argument("last", help="last production month, YYYY-MM")
    parser.add_argument("--dsn", default=os.environ.get("GLASSWELL_DSN", DEFAULT_DSN))
    parser.add_argument("--polite-seconds", type=int, default=POLITE_SECONDS)
    arguments = parser.parse_args(argv)

    months = months_between(arguments.first, arguments.last)
    manifest_ids: list[str] = []
    touched: set[str] = set()
    restatements: dict[str, int] = {}
    examined = appended = 0
    vintage_date: date | None = None
    promotion_derivation_id: str | None = None
    opened_at = None

    with psycopg.connect(arguments.dsn) as connection:
        for index, (year, month) in enumerate(months):
            if index:
                time.sleep(arguments.polite_seconds)
            with open_ingest_run(connection, source_id=SOURCE_ID) as run:
                report = ingest_month(run, year=year, month=month)
                vintage_date, opened_at = run.as_of, run.session.clock.now()
            connection.commit()

            manifest_ids.append(report.manifest_id)
            promotion_derivation_id = report.promote_derivation_id
            examined += report.rows_examined
            appended += report.rows_appended
            for key, count in report.restatement_summary.items():
                restatements[key] = restatements.get(key, 0) + count
            touched.update(_vintage_months(connection, vintage_date))
            print(
                json.dumps(
                    {
                        "month": f"{year:04d}-{month:02d}",
                        "manifest_id": report.manifest_id,
                        "staged_rows": report.staged_rows,
                        "rows_examined": report.rows_examined,
                        "rows_appended": report.rows_appended,
                        "quarantined": report.quarantined,
                        "unchanged": report.unchanged,
                    }
                ),
                flush=True,
            )

        if vintage_date is None or opened_at is None:
            return 1
        open_vintage(
            connection,
            source_id=SOURCE_ID,
            vintage_date=vintage_date,
            manifest_ids=manifest_ids,
            opened_at=opened_at,
            promotion_derivation_id=promotion_derivation_id,
            rows_examined=examined,
            rows_appended=appended,
            months_touched=sorted(touched),
            restatement_summary=restatements,
        )
        connection.commit()

    print(
        json.dumps(
            {
                "vintage_date": vintage_date.isoformat(),
                "manifest_ids": len(manifest_ids),
                "months_touched": sorted(touched),
                "rows_examined": examined,
                "rows_appended": appended,
                "restatement_summary": restatements,
            }
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
