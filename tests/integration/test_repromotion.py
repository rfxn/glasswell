"""Re-promotion under the S-E key, against a database that already promoted under the old one.

This is the deployer's situation, staged: canonical holds rows written by the `api10` key,
`key_collision` rows are open for the wells that filed in two pools, and the widened schema is
in place. The runner re-promotes from staging at a new vintage and must (a) leave every
pre-existing row exactly as it was, (b) append nothing for a well whose value did not change,
(c) give the multi-pool well its pool rows and their disclosed sum, and (d) close the ledger
rows that recorded a collision that no longer exists.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest
from psycopg.types.json import Jsonb

from glasswell.ingest import nd_mpr, repromote
from glasswell.ingest.base import open_ingest_run
from glasswell.lineage.vintages import select_production
from glasswell.seed import seed_all
from tests.support.fakes import FixedClock
from tests.support.mpr_workbook import filing, write_workbook
from tests.support.seed import seed_manifest, seed_production

MONTH = datetime(2026, 1, 1)
PRODUCTION_MONTH = date(2026, 1, 1)
OLD_VINTAGE = date(2026, 8, 1)
NEW_VINTAGE = date(2026, 8, 21)

MULTI_POOL = "3305302532"
BIRDBEAR_OIL = Decimal("0.000")
DUPEROW_OIL = Decimal("3585.000")

# The regression population: several hundred wells that filed in exactly one pool and must not
# move by a thousandth of a barrel.
UNAFFECTED_WELLS = 250
STREAMS = {"oil": ("bbl", "oil"), "gas": ("mcf", "gas"), "water": ("bbl", "wtr")}


def _api14(index: int) -> str:
    return f"3305{index:06d}0000"


def workbook_rows() -> list[dict]:
    rows = [
        filing(api14=f"{MULTI_POOL}0000", month=MONTH, pool="BIRDBEAR", oil=0, water=0, gas=0,
               days=0),
        filing(api14=f"{MULTI_POOL}0000", month=MONTH, pool="DUPEROW", oil=3585, water=901,
               gas=1446, days=31),
    ]
    rows.extend(
        filing(
            api14=_api14(index),
            month=MONTH,
            pool="BAKKEN",
            oil=1000 + index,
            water=200 + index,
            gas=5000 + index,
            days=30,
        )
        for index in range(1, UNAFFECTED_WELLS + 1)
    )
    return rows


def _legacy_hash(volume: Decimal, unit: str, days: int, semantics: str) -> str:
    return nd_mpr._value_hash(volume, unit, days, semantics)


def _seed_legacy_canonical(db: psycopg.Connection, manifest: str, derivation: str) -> None:
    """What the old key wrote: one row per (api10, month, stream), pool one by ordinal."""
    for stream, (unit, _) in STREAMS.items():
        volume = {"oil": BIRDBEAR_OIL, "gas": Decimal("0.000"), "water": Decimal("0.000")}[stream]
        seed_production(
            db,
            api10=MULTI_POOL,
            production_month=PRODUCTION_MONTH,
            report_vintage=OLD_VINTAGE,
            volume=volume,
            manifest_id=manifest,
            derivation_id=derivation,
            stream=stream,
            unit=unit,
            days_produced=0,
            null_semantics="reported_zero",
            value_hash=_legacy_hash(volume, unit, 0, "reported_zero"),
        )
    for index in range(1, UNAFFECTED_WELLS + 1):
        api10 = _api14(index)[:10]
        for stream, (unit, _) in STREAMS.items():
            volume = Decimal(
                {"oil": 1000 + index, "gas": 5000 + index, "water": 200 + index}[stream]
            ).quantize(Decimal("0.001"))
            seed_production(
                db,
                api10=api10,
                production_month=PRODUCTION_MONTH,
                report_vintage=OLD_VINTAGE,
                volume=volume,
                manifest_id=manifest,
                derivation_id=derivation,
                stream=stream,
                unit=unit,
                days_produced=30,
                value_hash=_legacy_hash(volume, unit, 30, "reported"),
            )


def _seed_open_collision(db: psycopg.Connection, manifest: str) -> None:
    with db.cursor() as cursor:
        for ordinal, stream in enumerate(("oil", "water", "gas"), start=1):
            cursor.execute(
                "insert into lineage.quarantine_rows (quarantine_id, row_fingerprint, source_id,"
                " staging_table, stage, reason_code, rule_id, row_payload, first_seen_at,"
                " first_seen_manifest_id, last_seen_at, last_seen_manifest_id)"
                " values (%s, %s, 'nd_mpr_xlsx', 'staging.nd_mpr_oil', 'conform',"
                " 'key_collision', 'cr_nd_api_identity_1', %s, now(), %s, now(), %s)",
                (
                    f"qtn_legacy_{ordinal}",
                    f"fp_legacy_{ordinal}",
                    Jsonb(
                        {
                            "api10": MULTI_POOL,
                            "pool": "DUPEROW",
                            "stream_canonical": stream,
                            "production_month": PRODUCTION_MONTH.isoformat(),
                            "volume": str(DUPEROW_OIL),
                            "unit": "bbl",
                        }
                    ),
                    manifest,
                    manifest,
                ),
            )


@pytest.fixture
def legacy(db: psycopg.Connection, tmp_path: Path, lineage_env) -> dict:
    seed_all(db)
    manifest = seed_manifest(db, sha256="7" * 64, source_key="2026_01.xlsx")
    path = write_workbook(tmp_path / "2026_01.xlsx", workbook_rows())
    frame = nd_mpr.parse_workbook(path, sheet="Oil")
    nd_mpr.load_staging(db, frame, manifest_id=manifest)
    derivation = _legacy_derivation(db, manifest, lineage_env)
    _seed_legacy_canonical(db, manifest, derivation)
    _seed_open_collision(db, manifest)
    db.commit()
    return {"manifest": manifest, "derivation": derivation}


def _legacy_derivation(db: psycopg.Connection, manifest: str, lineage_env) -> str:
    from glasswell.lineage.capture import derive, lineage_session
    from glasswell.lineage.models import InputRef, OutputSpec
    from glasswell.lineage.store import PostgresRecorder

    with lineage_session(
        recorder=PostgresRecorder(db),
        environment=lineage_env,
        clock=FixedClock(datetime(2026, 8, 1, 5, 2, 11, tzinfo=UTC)),
        correlation_id="run_legacy",
    ), derive(
        "canonical.promote",
        output=OutputSpec(
            store="postgres",
            dataset="canonical.production_monthly",
            partition={"month": "2026-01", "manifest_id": manifest},
        ),
        params={"source_key": "2026_01.xlsx", "liquids_basis": "oil+condensate"},
        inputs=[InputRef(kind="manifest", ref_id=manifest, role="primary")],
    ) as context:
        context.set_output_hash("0" * 64)
    return context.derivation_id


def run_repromotion(db: psycopg.Connection, lineage_env, *, at: date = NEW_VINTAGE):
    with open_ingest_run(
        db,
        source_id=nd_mpr.SOURCE_ID,
        environment=lineage_env,
        clock=FixedClock(datetime(at.year, at.month, at.day, 6, 0, 0, tzinfo=UTC)),
    ) as run:
        report = repromote.repromote(run)
    db.commit()
    return report


def query(db, sql: str, *parameters: object) -> list[tuple]:
    with db.cursor() as cursor:
        cursor.execute(sql, parameters or None)
        return cursor.fetchall()


def scalar(db, sql: str, *parameters: object):
    return query(db, sql, *parameters)[0][0]


def served(db, api10: str, *, as_of: date | None = None) -> dict[str, Decimal]:
    return {
        row["stream"]: row["volume"]
        for row in select_production(db, api10=api10, entity_type="well", as_of=as_of)
    }


@pytest.fixture
def repromoted(db, legacy, lineage_env):
    return run_repromotion(db, lineage_env)


def test_every_row_the_old_key_wrote_is_still_there_untouched(db, legacy, repromoted):
    """DIR-2 is append-only by construction; the gate asks for proof, not an assertion."""
    rows = query(
        db,
        "select count(*), count(distinct derivation_id) from canonical.production_monthly"
        " where report_vintage = %s",
        OLD_VINTAGE,
    )
    assert rows == [((UNAFFECTED_WELLS + 1) * 3, 1)]
    assert scalar(
        db,
        "select count(*) from canonical.production_monthly"
        " where report_vintage = %s and derivation_id <> %s",
        OLD_VINTAGE,
        legacy["derivation"],
    ) == 0


def test_a_well_whose_value_did_not_change_appends_nothing_at_all(db, repromoted):
    assert scalar(
        db,
        "select count(*) from canonical.production_monthly"
        " where report_vintage = %s and entity_type = 'well' and aggregation is null",
        NEW_VINTAGE,
    ) == 0


def test_the_unaffected_wells_serve_the_identical_value_before_and_after(db, legacy, lineage_env):
    before = {
        api: served(db, api)
        for api in (_api14(index)[:10] for index in range(1, UNAFFECTED_WELLS + 1))
    }

    run_repromotion(db, lineage_env)

    after = {
        api: served(db, api)
        for api in (_api14(index)[:10] for index in range(1, UNAFFECTED_WELLS + 1))
    }
    assert after == before
    assert len(before) == UNAFFECTED_WELLS


def test_the_multi_pool_well_gains_its_pool_rows_and_their_disclosed_sum(db, repromoted):
    assert query(
        db,
        "select entity_type, entity_key, volume, aggregation"
        "  from canonical.production_monthly"
        " where report_vintage = %s and stream = 'oil' order by entity_type, entity_key",
        NEW_VINTAGE,
    ) == [
        ("well", MULTI_POOL, BIRDBEAR_OIL + DUPEROW_OIL, "sum_over_pools"),
        ("well_completion_pool", f"{MULTI_POOL}:BIRDBEAR", BIRDBEAR_OIL, None),
        ("well_completion_pool", f"{MULTI_POOL}:DUPEROW", DUPEROW_OIL, None),
    ]


def test_the_wells_visible_figure_moves_from_zero_to_what_the_regulator_filed(db, repromoted):
    assert served(db, MULTI_POOL)["oil"] == DUPEROW_OIL


def test_the_old_vintage_still_answers_with_what_was_believed_then(db, repromoted):
    """A re-promotion adds a vintage. Asking as of the old one must not see the correction."""
    assert served(db, MULTI_POOL, as_of=OLD_VINTAGE)["oil"] == BIRDBEAR_OIL
    assert served(db, MULTI_POOL, as_of=NEW_VINTAGE)["oil"] == DUPEROW_OIL


def test_the_multi_pool_pending_ledger_rows_are_closed_not_deleted(db, repromoted):
    assert query(
        db,
        "select state, released_by_rule_id, count(*) from lineage.quarantine_rows"
        " where reason_code = 'key_collision' group by 1, 2",
    ) == [("superseded", nd_mpr.ROLLUP_RULE, 3)]
    assert repromoted.collisions_superseded == 3


def test_the_run_reports_what_it_did(db, repromoted):
    assert repromoted.report_vintage == NEW_VINTAGE
    assert repromoted.rows_appended == 9
    assert repromoted.rows_aggregated == 3
    assert repromoted.months_touched == ["2026-01-01"]


def test_running_it_a_second_time_appends_nothing(db, legacy, lineage_env, repromoted):
    before = scalar(db, "select count(*) from canonical.production_monthly")

    second = run_repromotion(db, lineage_env, at=date(2026, 8, 22))

    assert second.rows_appended == 0
    assert scalar(db, "select count(*) from canonical.production_monthly") == before


def test_the_re_promotion_opens_a_vintage_and_says_why(db, repromoted):
    payload = scalar(
        db,
        "select payload from lineage.audit_events where event_type = 'canonical.vintage_opened'"
        " order by event_id desc limit 1",
    )
    assert payload["reason"] == "s_e_entity_key_repromotion"
    assert payload["collisions_superseded"] == 3
    assert payload["rows_aggregated"] == 3


def test_the_runner_reads_staging_and_never_the_workbook(db, repromoted, tmp_path):
    """The bytes were parsed once against a verified manifest; that derivation is history."""
    assert scalar(db, "select count(*) from lineage.derivations where operation = 'stage.parse'")\
        == 0
