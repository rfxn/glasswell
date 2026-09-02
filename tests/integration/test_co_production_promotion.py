"""The Colorado production promotion, and the dual write that makes a well's history render.

Pool rows alone leave `/v1/wells/{api10}/production` empty, because that route asks for
`entity_type='well'`. North Dakota writes both; so does this. Every assertion here is positive:
the series is non-empty, the sums are exact, and the days are a maximum rather than a sum.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from glasswell.ingest import co_production
from glasswell.ingest.base import open_ingest_run
from tests.integration.test_co_staging import seeded as _seeded
from tests.integration.test_co_staging import staged_rolling as _staged_rolling

# Bound under their own names rather than imported into the namespace: pytest resolves
# fixtures by name and an unbound import is dead to it.
seeded = _seeded
staged_rolling = _staged_rolling

pytestmark = pytest.mark.integration


@pytest.fixture
def promoted(staged_rolling, seeded, lineage_env) -> co_production.ProductionReport:
    with open_ingest_run(
        seeded, source_id=co_production.SOURCE_ID, environment=lineage_env
    ) as run:
        report = co_production.promote_production(run)
    seeded.commit()
    return report


def test_the_dual_write_lands_both_shapes(promoted, seeded) -> None:
    with seeded.cursor() as cursor:
        cursor.execute(
            "select entity_type, reporting_level, aggregation, count(*)"
            "  from canonical.production_monthly where source_id = %s"
            " group by 1, 2, 3 order by 1, 2, 3",
            (co_production.SOURCE_ID,),
        )
        shapes = cursor.fetchall()

    assert ("well", "well_completion_pool", "sum_over_pools") in {
        (row[0], row[1], row[2]) for row in shapes
    }
    assert ("well_completion_pool", "well_completion_pool", None) in {
        (row[0], row[1], row[2]) for row in shapes
    }
    assert promoted.aggregate_rows > 0
    assert promoted.pool_rows > 0


def test_the_aggregate_row_passes_the_checks_that_admit_it(promoted, seeded) -> None:
    """020's aggregation CHECK constrains four columns; a row that satisfies it is the only
    shape the table admits for a rollup, and the promotion has to build exactly that."""
    with seeded.cursor() as cursor:
        cursor.execute(
            "select count(*) from canonical.production_monthly"
            " where aggregation = 'sum_over_pools'"
            "   and (entity_type <> 'well' or reporting_level <> 'well_completion_pool'"
            "        or well_completion_pool is not null)"
        )
        assert cursor.fetchone()[0] == 0


def test_the_aggregate_volume_is_the_exact_sum_and_the_days_are_the_maximum(
    promoted, seeded
) -> None:
    with seeded.cursor() as cursor:
        cursor.execute(
            "select w.api10, w.production_month, w.stream, w.volume, w.days_produced,"
            "       sum(p.volume), max(p.days_produced), count(*)"
            "  from canonical.production_monthly w"
            "  join canonical.production_monthly p"
            "    on p.api10 = w.api10 and p.production_month = w.production_month"
            "   and p.stream = w.stream and p.entity_type = 'well_completion_pool'"
            " where w.aggregation = 'sum_over_pools'"
            " group by 1, 2, 3, 4, 5"
        )
        rows = cursor.fetchall()

    assert rows, "no aggregate row has pool rows beneath it; the dual write is not proven"
    for _api10, _month, _stream, volume, days, total, longest, members in rows:
        assert members > 1
        assert volume == total
        assert days == longest
        assert days is None or days <= 31


def test_a_one_completion_month_promotes_as_the_well_and_carries_no_aggregation(
    promoted, seeded
) -> None:
    """Relabelling an unaffected row as an aggregate would signal a restatement that did not
    happen, which is North Dakota's stated reason and Colorado's too."""
    with seeded.cursor() as cursor:
        cursor.execute(
            "select count(*) from canonical.production_monthly"
            " where entity_type = 'well' and reporting_level = 'well'"
            "   and aggregation is null and source_id = %s",
            (co_production.SOURCE_ID,),
        )
        singles = cursor.fetchone()[0]

    assert singles > 0


def test_a_wells_own_series_is_not_empty_which_is_what_the_dual_write_buys(
    promoted, seeded
) -> None:
    """The route passes entity_type='well'. Pool rows alone would render nothing at all."""
    with seeded.cursor() as cursor:
        cursor.execute(
            "select api10, count(*) from canonical.production_monthly"
            " where entity_type = 'well' and source_id = %s group by 1 order by 2 desc limit 1",
            (co_production.SOURCE_ID,),
        )
        api10, months = cursor.fetchone()

    assert months > 1
    assert api10.startswith("05")


def test_every_completion_is_recorded_with_the_code_ecmc_filed(promoted, seeded) -> None:
    with seeded.cursor() as cursor:
        cursor.execute(
            "select count(*), count(pool_reported) from canonical.well_completions"
            " where source_id = %s",
            (co_production.SOURCE_ID,),
        )
        rows, reported = cursor.fetchone()

    assert rows == promoted.completions
    assert reported == rows


def test_the_null_semantics_distinguish_an_absent_month_from_a_filed_zero(
    promoted, seeded
) -> None:
    with seeded.cursor() as cursor:
        cursor.execute(
            "select null_semantics, count(*) from canonical.production_monthly"
            " where source_id = %s group by 1",
            (co_production.SOURCE_ID,),
        )
        semantics = dict(cursor.fetchall())

    assert set(semantics) <= {"reported", "reported_zero", "no_report", "withheld"}
    assert semantics.get("no_report", 0) > 0
    assert semantics.get("reported", 0) > 0


def test_a_second_run_appends_nothing(promoted, seeded, lineage_env) -> None:
    with seeded.cursor() as cursor:
        cursor.execute("select count(*) from canonical.production_monthly")
        before = cursor.fetchone()[0]

    with open_ingest_run(
        seeded, source_id=co_production.SOURCE_ID, environment=lineage_env
    ) as run:
        co_production.promote_production(run)
    seeded.commit()

    with seeded.cursor() as cursor:
        cursor.execute("select count(*) from canonical.production_monthly")
        assert cursor.fetchone()[0] == before


def test_the_sum_is_over_the_filings_that_reported_and_not_over_their_absences() -> None:
    """The unit half of the rollup, where the fixture cannot reach: a month in which every
    completion filed nothing is `no_report` on the well row, not a zero."""
    filings = [
        {"volume": Decimal("10.5"), "days": 30},
        {"volume": Decimal("4.5"), "days": 28},
    ]
    total, days = co_production.sum_over_pools(filings)
    assert total == Decimal("15.0")
    assert days == 30

    absent = [{"volume": None, "days": None}, {"volume": None, "days": None}]
    assert co_production.sum_over_pools(absent) == (None, None)

    mixed = [{"volume": None, "days": 5}, {"volume": Decimal("3"), "days": 31}]
    assert co_production.sum_over_pools(mixed) == (Decimal("3"), 31)


def _plant(connection, manifest_id: str, ordinal: int, **columns: str | None) -> None:
    """One staged row, at an ordinal past the fixture's own, with the defaults of a good row."""
    row = {
        "manifest_id": manifest_id,
        "source_row_ordinal": ordinal,
        "apicountycode": "123",
        "apisequencenumber": "45678",
        "apisidetrack": "00",
        "formationcode": "CODELL",
        "facilityid": "999999",
        "reportyear": "2026",
        "reportmonth": "4",
        "daysproduced": "30",
        "oilproduced": "10",
        "gasproduced": "20",
        "waterproduced": "30",
        **columns,
    }
    names = ", ".join(row)
    placeholders = ", ".join(f"%({name})s" for name in row)
    with connection.cursor() as cursor:
        cursor.execute(
            f"insert into staging.co_ecmc_production ({names}) values ({placeholders})", row
        )


@pytest.fixture
def promoted_with_rejects(staged_rolling, seeded, lineage_env) -> co_production.ProductionReport:
    """Two rows the promotion cannot place: one with no readable API-10, one with no month."""
    ordinal = staged_rolling.rows_staged + 1
    _plant(seeded, staged_rolling.manifest_id, ordinal, apicountycode="")
    _plant(seeded, staged_rolling.manifest_id, ordinal + 1, reportmonth="13")
    seeded.commit()
    with open_ingest_run(
        seeded, source_id=co_production.SOURCE_ID, environment=lineage_env
    ) as run:
        report = co_production.promote_production(run)
    seeded.commit()
    return report


def test_a_row_that_cannot_be_keyed_or_dated_is_quarantined_and_never_dropped(
    promoted_with_rejects, seeded
) -> None:
    """The hard rule, on the path that had no ledger entry at all.

    `cr_co_production_entity_key_1` publishes `on_missing: quarantine`, and until this test the
    promotion answered it with `continue`: a row ECMC files with a blank county code or a
    thirteenth month vanished between staging and canonical with no count, no reason and no
    query that could find it. The rolling file is clean today, which is why nothing fired; the
    archive backfill is where it would have.
    """
    assert promoted_with_rejects.quarantined == {"key_incomplete": 1, "out_of_range_date": 1}

    with seeded.cursor() as cursor:
        cursor.execute(
            "select reason_code, rule_id, state, row_payload->>'source_row_ordinal'"
            "  from lineage.quarantine_rows"
            " where source_id = %s and staging_table = %s order by reason_code",
            (co_production.SOURCE_ID, co_production.STAGING_TABLE),
        )
        rows = cursor.fetchall()

    assert [(reason, rule, state) for reason, rule, state, _ in rows] == [
        ("key_incomplete", "cr_co_production_entity_key_1", "open"),
        ("out_of_range_date", "cr_co_production_grain_1", "open"),
    ]
    assert len({ordinal for *_rest, ordinal in rows}) == 2


def test_a_quarantined_null_is_a_json_null_and_not_the_text_none(
    promoted_with_rejects, seeded
) -> None:
    """A blank the regulator filed and the four characters `None` are different facts.

    `lineage.quarantine_rows.row_payload` is the whole of what a reader of a rejected row has,
    and a staged SQL null rendered as `None` cannot be told from a column ECMC filed with that
    text. `nd_mpr.py` hands polars frames through with their nulls intact; this promotion built
    its payload with `str(value)`, which has no null.

    The key is asserted present first. `->>` on a key the payload does not carry is SQL null,
    so a test written against a column the promotion never selects passes on nothing.
    """
    with seeded.cursor() as cursor:
        cursor.execute(
            "select row_payload ? 'revised', row_payload -> 'revised', row_payload ->> 'revised'"
            "  from lineage.quarantine_rows"
            " where source_id = %s and reason_code = 'key_incomplete'",
            (co_production.SOURCE_ID,),
        )
        present, typed, text = cursor.fetchone()

    assert present, "the payload does not carry this column, so the assertion below is vacuous"
    assert text != "None", "a staged null reached the ledger as the four characters None"
    assert typed is None


def test_every_staged_row_is_either_promoted_or_quarantined(
    promoted_with_rejects, seeded
) -> None:
    """The identity that makes the count above meaningful rather than decorative."""
    report = promoted_with_rejects
    with seeded.cursor() as cursor:
        cursor.execute(
            "select count(distinct (api10, production_month))"
            "  from canonical.production_monthly where source_id = %s",
            (co_production.SOURCE_ID,),
        )
        well_months = cursor.fetchone()[0]

    assert report.rows_read == report.rows_keyed + sum(report.quarantined.values())
    assert report.rows_keyed > 0
    assert well_months > 0
