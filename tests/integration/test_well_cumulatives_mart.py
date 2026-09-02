"""marts.well_cumulatives and marts.well_withholding: the total, and the record under it.

The fixture is arranged so every month class the mart counts is reachable: a filed month, a
filed zero, a stored no_report, a stored withheld, a gap, a quarantined withheld month, and a
well that filed nothing at all.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import psycopg
import pytest
from psycopg.types.json import Jsonb

from glasswell.lineage.capture import lineage_session
from glasswell.lineage.store import PostgresRecorder
from glasswell.marts.cumulatives import (
    MART_STREAMS,
    NEVER_REPORTED,
    OBSERVED,
    WITHHOLDING_BY_PREFIX,
    refresh_well_cumulatives,
)
from glasswell.seed import seed_all
from tests.support.seed import seed_derivation, seed_manifest, seed_production, seed_well

FILED = "3305388001"
ZERO_FILER = "3305388002"
GAPPED = "3305388003"
STORED_CLASSES = "3305388004"
WITHHELD_LEDGER = "3305388005"
SILENT = "3305388006"
ND_WELLS = (FILED, ZERO_FILER, GAPPED, STORED_CLASSES, WITHHELD_LEDGER, SILENT)

VINTAGE = date(2026, 8, 1)
JAN, FEB, MAR = date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)

_QUARANTINE = (
    "insert into lineage.quarantine_rows (quarantine_id, row_fingerprint, source_id,"
    " staging_table, stage, reason_code, rule_id, row_payload, first_seen_at,"
    " first_seen_manifest_id, last_seen_at, last_seen_manifest_id, occurrence_count, state)"
    " values (%s, %s, %s, 'staging.nd_mpr_oil', 'conform', %s, 'cr_nd_confidential_1', %s,"
    " %s, %s, %s, %s, 1, 'open')"
)


def rows(connection: psycopg.Connection, statement: str, params=()) -> list[tuple]:
    with connection.cursor() as cursor:
        cursor.execute(statement, params)
        return cursor.fetchall()


def mart_row(connection: psycopg.Connection, api10: str, stream: str) -> tuple:
    found = rows(
        connection,
        "select cum_volume, unit, basis, months_reported, months_reported_zero,"
        " months_no_report_stored, months_withheld_stored, months_absent, span_months,"
        " first_month, last_month, coverage_outcome, snapshot_vintage"
        " from marts.well_cumulatives where api10 = %s and stream = %s",
        (api10, stream),
    )
    assert found, f"no mart row for {api10}/{stream}"
    return found[0]


@pytest.fixture
def refreshed(db: psycopg.Connection, lineage_env):
    seed_all(db)
    manifest_id = seed_manifest(db, sha256="7" * 64, source_key="cumulatives.xlsx")
    derivation_id = seed_derivation(db)
    for api10 in ND_WELLS:
        seed_well(db, api10=api10, manifest_id=manifest_id, derivation_id=derivation_id)

    def filing(api10, month, stream, volume, semantics="reported"):
        seed_production(
            db,
            api10=api10,
            production_month=month,
            report_vintage=VINTAGE,
            volume=volume,
            stream=stream,
            null_semantics=semantics,
            manifest_id=manifest_id,
            derivation_id=derivation_id,
        )

    for month, volume in ((JAN, "1000"), (FEB, "900"), (MAR, "800")):
        filing(FILED, month, "oil", Decimal(volume))
        filing(FILED, month, "gas", Decimal(volume) * 2)
        filing(FILED, month, "water", Decimal(volume) / 2)
    # A condensate month folds into the liquid row rather than becoming a fourth stream.
    filing(FILED, MAR, "condensate", Decimal("100"))

    filing(ZERO_FILER, JAN, "oil", Decimal("500"))
    filing(ZERO_FILER, FEB, "oil", Decimal("0"), semantics="reported_zero")

    filing(GAPPED, JAN, "oil", Decimal("300"))
    filing(GAPPED, MAR, "oil", Decimal("200"))

    # 009_nd_canonical_and_marts.sql:211-212 constrains the label, not the value: the volume
    # is non-zero so an admitted total would be visibly wrong rather than coincidentally right.
    filing(STORED_CLASSES, JAN, "oil", Decimal("400"))
    filing(STORED_CLASSES, FEB, "oil", Decimal("77777"), semantics="no_report")
    filing(STORED_CLASSES, MAR, "oil", Decimal("88888"), semantics="withheld")

    filing(WITHHELD_LEDGER, JAN, "oil", Decimal("600"))
    filing(WITHHELD_LEDGER, MAR, "oil", Decimal("700"))
    source_id, reason_code = WITHHOLDING_BY_PREFIX["33"][0]
    with db.cursor() as cursor:
        cursor.execute(
            _QUARANTINE,
            (
                "qr_01cumulative001",
                "fp_cumulative_0001",
                source_id,
                reason_code,
                Jsonb({"api10": WITHHELD_LEDGER, "production_month": FEB.isoformat()}),
                datetime(2026, 8, 1, 5, 0, 0, tzinfo=UTC),
                manifest_id,
                datetime(2026, 8, 1, 5, 0, 0, tzinfo=UTC),
                manifest_id,
            ),
        )
    db.commit()

    with lineage_session(recorder=PostgresRecorder(db), environment=lineage_env):
        refresh = refresh_well_cumulatives(db)
    db.commit()
    return db, refresh


def test_a_quarantined_withheld_month_is_counted_and_is_not_a_gap(refreshed):
    db, _ = refreshed
    assert rows(
        db,
        "select months_withheld, withheld_first_month, withheld_last_month"
        " from marts.well_withholding where api10 = %s",
        (WITHHELD_LEDGER,),
    ) == [(1, FEB, FEB)]
    row = mart_row(db, WITHHELD_LEDGER, "liquid")
    assert (row[3], row[4], row[5], row[6], row[7]) == (2, 0, 0, 0, 0)


def test_a_filed_zero_moves_the_count_and_not_the_total(refreshed):
    db, _ = refreshed
    cum_volume, _, _, reported, reported_zero, *_ = mart_row(db, ZERO_FILER, "liquid")

    assert (reported, reported_zero) == (1, 1)
    assert cum_volume == Decimal("500.000")


def test_a_gap_inside_the_span_is_counted_as_absent(refreshed):
    db, _ = refreshed
    row = mart_row(db, GAPPED, "liquid")

    assert (row[3], row[7], row[8]) == (2, 1, 3)


def test_a_stored_no_report_row_is_its_own_class_and_is_not_a_gap(refreshed):
    db, _ = refreshed
    cum_volume, _, _, reported, _, no_report_stored, withheld_stored, absent, *_ = mart_row(
        db, STORED_CLASSES, "liquid"
    )

    assert (reported, no_report_stored, withheld_stored, absent) == (1, 1, 1, 0)
    assert cum_volume == Decimal("400.000")


def test_every_row_reconciles_its_month_classes_to_its_span(refreshed):
    """An identity that holds only where someone remembered to check is not an identity."""
    db, _ = refreshed
    # Its own floor: an anti-join over an empty mart returns no offenders and proves nothing.
    assert rows(db, "select count(*) from marts.well_cumulatives")[0][0] == len(ND_WELLS) * len(
        MART_STREAMS
    )
    offenders = rows(
        db,
        "select c.api10, c.stream, c.span_months from marts.well_cumulatives c"
        " left join marts.well_withholding w on w.api10 = c.api10"
        " where c.span_months <> c.months_reported + c.months_reported_zero"
        "   + c.months_no_report_stored + c.months_withheld_stored + c.months_absent"
        "   + coalesce(w.months_withheld, 0)",
    )

    assert offenders == []


def test_the_mart_holds_three_streams_per_well_and_never_a_condensate_row(refreshed):
    db, _ = refreshed
    assert {row[0] for row in rows(db, "select distinct stream from marts.well_cumulatives")} == {
        *MART_STREAMS
    }
    assert rows(
        db, "select count(*) from marts.well_cumulatives where stream = 'condensate'"
    ) == [(0,)]
    liquid = mart_row(db, FILED, "liquid")
    gas = mart_row(db, FILED, "gas")
    water = mart_row(db, FILED, "water")
    assert (liquid[1], liquid[2]) == ("bbl", "oil+condensate")
    assert (gas[1], gas[2]) == ("mcf", None)
    assert (water[1], water[2]) == ("bbl", "water")
    # The condensate month rides the liquid total rather than a row of its own.
    assert liquid[0] == Decimal("2800.000")


def test_a_well_that_never_reported_carries_a_null_total_and_not_a_zero(refreshed):
    """M5: a zero here would collapse a whole-well absence into a filed zero."""
    db, _ = refreshed
    for stream in MART_STREAMS:
        row = mart_row(db, SILENT, stream)
        assert row[0] is None
        assert row[8] == 0
        assert (row[9], row[10]) == (None, None)
        assert row[11] == NEVER_REPORTED


def test_a_well_that_filed_one_stream_is_observed_with_the_others_absent(refreshed):
    db, _ = refreshed
    gas = mart_row(db, GAPPED, "gas")

    assert gas[11] == OBSERVED
    assert gas[0] is None
    assert (gas[7], gas[8]) == (3, 3)


def test_the_mart_carries_one_row_per_stream_for_every_well_in_scope(refreshed):
    db, refresh = refreshed
    wells = rows(db, "select count(*) from canonical.wells_latest where state_code = '33'")[0][0]

    assert refresh.row_counts["well_cumulatives"] == wells * len(MART_STREAMS)
    assert rows(db, "select count(*) from marts.well_cumulatives") == [
        (wells * len(MART_STREAMS),)
    ]


def test_every_row_cites_the_refresh_that_wrote_it(refreshed):
    db, refresh = refreshed
    assert rows(
        db,
        "select distinct d.operation, d.output_dataset from marts.well_cumulatives c"
        " join lineage.derivations d on d.derivation_id = c.derivation_id",
    ) == [("mart.refresh", "marts.well_cumulatives")]
    assert rows(db, "select distinct derivation_id from marts.well_cumulatives") == [
        (refresh.derivation_id,)
    ]


def test_two_refreshes_over_unchanged_canonical_are_the_same_derivation(refreshed, lineage_env):
    db, refresh = refreshed
    with lineage_session(recorder=PostgresRecorder(db), environment=lineage_env):
        again = refresh_well_cumulatives(db)
    db.commit()

    assert again.derivation_id == refresh.derivation_id
    assert again.row_counts == refresh.row_counts


def test_the_snapshot_vintage_is_the_newest_report_vintage_read(refreshed):
    db, refresh = refreshed

    assert refresh.snapshot_vintage == VINTAGE
    assert rows(db, "select distinct snapshot_vintage from marts.well_cumulatives") == [(VINTAGE,)]


def test_the_partition_names_states_rather_than_a_hardcoded_jurisdiction(refreshed):
    """M2: a jurisdiction literal inside a content-addressed identity is not widenable."""
    db, refresh = refreshed
    partition = rows(
        db,
        "select output_partition from lineage.derivations where derivation_id = %s",
        (refresh.derivation_id,),
    )[0][0]

    assert partition == {"states": "33"}
    assert rows(db, "select distinct state_code from marts.well_cumulatives") == [("33",)]
