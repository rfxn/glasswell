"""The head map a promotion reads is scoped to the entity-months it is promoting.

The DR-17 back-load promotes 125 workbooks in one process on one knowledge day. A map keyed by
every head canonical holds — and the same-vintage map the divergence check reads back — grows
with the run rather than with the month, so both are scoped here and both are pinned to answer
exactly what an unscoped read of the whole table would have answered.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from glasswell.ingest import nd_mpr
from glasswell.lineage.errors import VintageAlreadyPromoted
from tests.support.seed import seed_derivation, seed_manifest, seed_production

VINTAGE = date(2026, 8, 20)
MONTHS = (date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1))
PROMOTED_MONTH = MONTHS[-1]
WELLS = ("3305300001", "3305300002")
STREAMS = ("oil", "gas")
RESIDENT_HEADS = len(MONTHS) * len(WELLS) * len(STREAMS)
MONTH_HEADS = len(WELLS) * len(STREAMS)
VOLUME = Decimal("304.000")


def _record(api10: str, month: date, stream: str, volume: Decimal = VOLUME) -> dict:
    return nd_mpr._record(
        entity_type="well",
        entity_key=api10,
        reporting_level="well",
        well_completion_pool=None,
        aggregation=None,
        api10=api10,
        production_month=month,
        stream=stream,
        volume=volume,
        unit="bbl" if stream == "oil" else "mcf",
        days=30,
        semantics="reported",
    )


def _records(month: date) -> list[dict]:
    return [_record(api10, month, stream) for api10 in WELLS for stream in STREAMS]


def _pool_record(api10: str, month: date, pool: str, stream: str = "oil") -> dict:
    """A pool filing, whose entity_key is not its API-10 — the case the scope qual keys on."""
    return nd_mpr._record(
        entity_type="well_completion_pool",
        entity_key=f"{api10}_{pool}",
        reporting_level="well_completion_pool",
        well_completion_pool=pool,
        aggregation=None,
        api10=api10,
        production_month=month,
        stream=stream,
        volume=VOLUME,
        unit="bbl",
        days=30,
        semantics="reported",
    )


def _land(db, records, *, report_vintage: date = VINTAGE) -> None:
    month = records[0]["production_month"]
    manifest = seed_manifest(
        db, sha256=f"{month.year:04d}{month.month:02d}".ljust(64, "a"),
        source_key=f"{month.year:04d}_{month.month:02d}.xlsx",
    )
    derivation = seed_derivation(db)
    for record in records:
        seed_production(
            db,
            api10=record["api10"],
            production_month=record["production_month"],
            report_vintage=report_vintage,
            volume=record["volume"],
            unit=record["unit"],
            days_produced=record["days_produced"],
            stream=record["stream"],
            value_hash=record["value_hash"],
            entity_type=record["entity_type"],
            entity_key=record["entity_key"],
            reporting_level=record["reporting_level"],
            well_completion_pool=record["well_completion_pool"],
            aggregation=record["aggregation"],
            manifest_id=manifest,
            derivation_id=derivation,
        )


@pytest.fixture
def resident(db) -> None:
    """Three months of heads, of which one month is the one being promoted."""
    for month in MONTHS:
        _land(db, _records(month))


def test_the_head_map_holds_only_the_month_being_promoted(db, resident):
    heads = nd_mpr._current_heads(db, _records(PROMOTED_MONTH))

    assert len(heads.by_key) == MONTH_HEADS
    assert {key[2] for key in heads.by_key} == {PROMOTED_MONTH}


def test_the_head_map_does_not_grow_as_further_months_land(db):
    """The property the back-load needs: the footprint follows the month, not the table."""
    sizes = []
    for month in (PROMOTED_MONTH, *MONTHS[:-1]):
        _land(db, _records(month))
        sizes.append(len(nd_mpr._current_heads(db, _records(PROMOTED_MONTH)).by_key))

    with db.cursor() as cursor:
        cursor.execute("select count(*) from canonical.production_monthly")
        assert cursor.fetchone()[0] == RESIDENT_HEADS
    assert sizes == [MONTH_HEADS] * len(MONTHS)


def test_a_head_outside_the_scope_refuses_rather_than_reading_as_absent(db, resident):
    """A key the read never covered must not answer None: that appends a restatement as new."""
    heads = nd_mpr._current_heads(db, _records(PROMOTED_MONTH))

    with pytest.raises(LookupError, match="outside the head scope"):
        heads.head_of(_record(WELLS[0], MONTHS[0], "oil"))


def test_the_scoped_map_answers_what_a_read_of_the_whole_table_answered(db, resident):
    """The pre-scoping behaviour, recomputed here from an unscoped read as the oracle."""
    amended = [
        _record(WELLS[0], PROMOTED_MONTH, "oil", volume=Decimal("337.000")),
        *_records(PROMOTED_MONTH)[1:],
        _record("3305300099", PROMOTED_MONTH, "oil"),
    ]
    with db.cursor() as cursor:
        cursor.execute(
            "select entity_type, entity_key, production_month, stream, value_hash,"
            "       reporting_level, aggregation"
            "  from canonical.production_monthly_latest where source_id = %s",
            (nd_mpr.SOURCE_ID,),
        )
        whole_table = {(r[0], r[1], r[2], r[3]): (r[4], r[5], r[6]) for r in cursor.fetchall()}

    expected = [
        dict(record)
        for record in amended
        if whole_table.get(nd_mpr._head_key(record)) != nd_mpr._change_key(record)
    ]
    heads = nd_mpr._current_heads(db, amended)

    assert nd_mpr._unchanged(amended, heads) == expected
    assert [record["api10"] for record in expected] == [WELLS[0], "3305300099"]
    assert [heads.holds(record) for record in expected] == [True, False]


def test_the_same_vintage_read_is_scoped_to_the_month_being_promoted(db, resident):
    """The divergence check reads canonical at one vintage — every month of a same-day walk."""
    occupied = nd_mpr._rows_at_vintage(db, _records(PROMOTED_MONTH), report_vintage=VINTAGE)

    with db.cursor() as cursor:
        cursor.execute(
            "select count(*) from canonical.production_monthly where report_vintage = %s",
            (VINTAGE,),
        )
        assert cursor.fetchone()[0] == RESIDENT_HEADS
    assert len(occupied.by_key) == MONTH_HEADS


def test_a_row_this_vintage_already_answers_is_kept_out_of_the_append(db, resident):
    records = _records(PROMOTED_MONTH)
    amended = _record(WELLS[0], PROMOTED_MONTH, "oil", volume=Decimal("337.000"))

    landable = nd_mpr.reject_same_vintage_divergence(db, records, report_vintage=VINTAGE)
    fresh = nd_mpr.reject_same_vintage_divergence(
        db, records, report_vintage=date(2026, 8, 21)
    )

    assert landable == []
    assert len(fresh) == len(records)
    with pytest.raises(VintageAlreadyPromoted):
        nd_mpr.reject_same_vintage_divergence(db, [amended], report_vintage=VINTAGE)


def test_a_pool_filing_finds_its_own_head_not_the_well_row_sharing_its_api10(db):
    """The scope is keyed by entity_key, so a pool head is in scope and the well head is not."""
    pool = _pool_record(WELLS[0], PROMOTED_MONTH, "BAKKEN")
    _land(db, [pool, _record(WELLS[0], PROMOTED_MONTH, "oil")])

    heads = nd_mpr._current_heads(db, [pool])

    assert list(heads.by_key) == [nd_mpr._head_key(pool)]
    assert heads.head_of(pool) == nd_mpr._change_key(pool)
    with pytest.raises(LookupError, match="outside the head scope"):
        heads.head_of(_record(WELLS[0], PROMOTED_MONTH, "oil"))


def test_an_empty_promotion_reads_nothing_and_still_answers(db, resident):
    heads = nd_mpr._current_heads(db, [])

    assert heads.by_key == {}
    assert nd_mpr._unchanged([], heads) == []
