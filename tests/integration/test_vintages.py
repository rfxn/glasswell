from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from glasswell.lineage.vintages import open_vintage, select_production
from tests.support.seed import seed_derivation, seed_manifest, seed_production

API10 = "33053012340000"
MARCH = date(2024, 3, 1)
FIRST_VINTAGE = date(2026, 7, 1)
RESTATED_VINTAGE = date(2026, 8, 1)


@pytest.fixture
def two_vintages(db):
    """The same production month reported twice: 12,034 bbl, later restated to 12,510 bbl."""
    first_manifest = seed_manifest(
        db, sha256="a" * 64, fetched_at=datetime(2026, 7, 1, 5, tzinfo=UTC)
    )
    second_manifest = seed_manifest(
        db, sha256="b" * 64, fetched_at=datetime(2026, 8, 1, 5, tzinfo=UTC)
    )
    first_derivation = seed_derivation(db, params={"vintage": "2026-07-01"})
    second_derivation = seed_derivation(db, params={"vintage": "2026-08-01"})
    seed_production(
        db,
        api10=API10,
        production_month=MARCH,
        report_vintage=FIRST_VINTAGE,
        volume=Decimal("12034.000"),
        manifest_id=first_manifest,
        derivation_id=first_derivation,
    )
    seed_production(
        db,
        api10=API10,
        production_month=MARCH,
        report_vintage=RESTATED_VINTAGE,
        volume=Decimal("12510.000"),
        manifest_id=second_manifest,
        derivation_id=second_derivation,
    )
    db.commit()
    return second_manifest, second_derivation


def volumes(rows):
    return [(row["report_vintage"], row["volume"]) for row in rows]


def test_the_serving_default_is_the_latest_vintage(db, two_vintages):
    assert volumes(select_production(db, api10=API10)) == [
        (RESTATED_VINTAGE, Decimal("12510.000"))
    ]


def test_as_of_before_the_restatement_returns_the_original_figure(db, two_vintages):
    rows = select_production(db, api10=API10, as_of=date(2026, 7, 15))
    assert volumes(rows) == [(FIRST_VINTAGE, Decimal("12034.000"))]


def test_as_of_on_the_restatement_date_returns_the_restated_figure(db, two_vintages):
    rows = select_production(db, api10=API10, as_of=RESTATED_VINTAGE)
    assert volumes(rows) == [(RESTATED_VINTAGE, Decimal("12510.000"))]


def test_as_of_before_any_vintage_returns_nothing(db, two_vintages):
    assert select_production(db, api10=API10, as_of=date(2026, 1, 1)) == []


def test_the_superseded_vintage_stays_addressable_forever(db, two_vintages):
    with db.cursor() as cursor:
        cursor.execute(
            "select report_vintage, volume from canonical.production_monthly"
            " where api10 = %s order by report_vintage",
            (API10,),
        )
        assert cursor.fetchall() == [
            (FIRST_VINTAGE, Decimal("12034.000")),
            (RESTATED_VINTAGE, Decimal("12510.000")),
        ]


def test_the_latest_view_agrees_with_the_as_of_default(db, two_vintages):
    with db.cursor() as cursor:
        cursor.execute(
            "select report_vintage, volume from canonical.production_monthly_latest"
            " where api10 = %s",
            (API10,),
        )
        assert cursor.fetchall() == [(RESTATED_VINTAGE, Decimal("12510.000"))]


def test_as_of_resolves_per_well_month_not_per_query(db, two_vintages):
    """A well only reported in the first vintage keeps that vintage under a later as-of."""
    manifest, derivation = two_vintages
    seed_production(
        db,
        api10="33053099990000",
        production_month=MARCH,
        report_vintage=FIRST_VINTAGE,
        volume=Decimal("800.000"),
        manifest_id=manifest,
        derivation_id=derivation,
    )
    db.commit()

    rows = select_production(db, production_month=MARCH, as_of=RESTATED_VINTAGE)
    assert volumes(rows) == [
        (RESTATED_VINTAGE, Decimal("12510.000")),
        (FIRST_VINTAGE, Decimal("800.000")),
    ]


def test_opening_a_vintage_records_the_restatement_magnitude(db, two_vintages):
    manifest, derivation = two_vintages
    record = open_vintage(
        db,
        source_id="nd_mpr_xlsx",
        vintage_date=RESTATED_VINTAGE,
        manifest_ids=[manifest],
        opened_at=datetime(2026, 8, 1, 5, 30, tzinfo=UTC),
        promotion_derivation_id=derivation,
        rows_examined=4118203,
        rows_appended=9412,
        months_touched=["2024-03"],
        restatement_summary={"2024-03": 9412},
    )
    db.commit()

    assert record.vintage_id == "vin_nd_mpr_xlsx_2026-08-01"
    with db.cursor() as cursor:
        cursor.execute(
            "select rows_appended, months_touched, restatement_summary from lineage.vintages"
            " where vintage_id = %s",
            (record.vintage_id,),
        )
        assert cursor.fetchone() == (9412, ["2024-03"], {"2024-03": 9412})
