"""Re-promotion under the S-E key, against a database that already promoted under the old one.

This is the deployer's situation, staged: canonical holds rows written by the `api10` key,
`key_collision` rows are open for the wells that filed in two pools, and the widened schema is
in place. The runner re-promotes from staging at a new vintage and must (a) leave every
pre-existing row exactly as it was, (b) append nothing for a well whose value did not change,
(c) give the multi-pool well its pool rows and their disclosed sum, and (d) close the ledger
rows that recorded a collision that no longer exists.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest
from psycopg.types.json import Jsonb

from glasswell.ingest import nd_mpr, repromote
from glasswell.ingest.base import open_ingest_run
from glasswell.lineage.errors import VintageAlreadyPromoted
from glasswell.lineage.vintages import select_production
from glasswell.seed import seed_all
from glasswell.seed.conformance_nd import SUPERSESSION_FROM
from tests.support.fakes import FixedClock
from tests.support.mpr_workbook import filing, write_workbook
from tests.support.seed import seed_manifest, seed_production, seed_well

MONTH = datetime(2026, 1, 1)
PRODUCTION_MONTH = date(2026, 1, 1)
# VM 111 modelled exactly: the fleet's last promotion sits on the day cr_nd_pool_rollup_1
# became effective, which is the case that produced gate-a1b Defect A. Read from the seed
# rather than written down, so moving the rule moves the fixture with it.
OLD_VINTAGE = SUPERSESSION_FROM

MULTI_POOL = "3305302532"
BIRDBEAR_OIL = Decimal("0.000")
DUPEROW_OIL = Decimal("3585.000")

# gate-a1b Defect B: a well whose sibling pool contributes nothing, so the sum hashes
# identically to the row already there. Its value never moves; its disclosure has to appear
# anyway, or a cross-pool sum is served as a single-pool observation.
DISCLOSURE_ONLY = "3305300777"
DISCLOSURE_OIL = Decimal("500.000")

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
        filing(api14=f"{DISCLOSURE_ONLY}0000", month=MONTH, pool="BAKKEN", oil=500, water=100,
               gas=2000, days=30),
        filing(api14=f"{DISCLOSURE_ONLY}0000", month=MONTH, pool="LODGEPOLE", oil=0, water=0,
               gas=0, days=0),
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
    for stream, (unit, _) in STREAMS.items():
        volume = Decimal({"oil": 500, "gas": 2000, "water": 100}[stream]).quantize(
            Decimal("0.001")
        )
        seed_production(
            db,
            api10=DISCLOSURE_ONLY,
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


def _seed_open_collision(
    db: psycopg.Connection, manifest: str, *, api10: str = MULTI_POOL, pool: str = "DUPEROW"
) -> None:
    with db.cursor() as cursor:
        for ordinal, stream in enumerate(("oil", "water", "gas"), start=1):
            cursor.execute(
                "insert into lineage.quarantine_rows (quarantine_id, row_fingerprint, source_id,"
                " staging_table, stage, reason_code, rule_id, row_payload, first_seen_at,"
                " first_seen_manifest_id, last_seen_at, last_seen_manifest_id)"
                " values (%s, %s, 'nd_mpr_xlsx', 'staging.nd_mpr_oil', 'conform',"
                " 'key_collision', 'cr_nd_api_identity_1', %s, now(), %s, now(), %s)",
                (
                    f"qtn_legacy_{api10}_{ordinal}",
                    f"fp_legacy_{api10}_{ordinal}",
                    Jsonb(
                        {
                            "api10": api10,
                            "pool": pool,
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
    for api10 in (MULTI_POOL, DISCLOSURE_ONLY):
        seed_well(db, api10=api10)
    manifest = seed_manifest(db, sha256="7" * 64, source_key="2026_01.xlsx")
    path = write_workbook(tmp_path / "2026_01.xlsx", workbook_rows())
    frame = nd_mpr.parse_workbook(path, sheet="Oil")
    nd_mpr.load_staging(db, frame, manifest_id=manifest)
    derivation = _legacy_derivation(db, manifest, lineage_env)
    _seed_legacy_canonical(db, manifest, derivation)
    _seed_open_collision(db, manifest)
    _seed_open_collision(db, manifest, api10=DISCLOSURE_ONLY, pool='LODGEPOLE')
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


def newest_vintage(db: psycopg.Connection) -> date:
    """Whatever the database actually believes, so no test asserts against a hardcoded day."""
    with db.cursor() as cursor:
        cursor.execute("select max(report_vintage) from canonical.production_monthly")
        return cursor.fetchone()[0]


def run_repromotion(db: psycopg.Connection, lineage_env, *, at: date | None = None):
    day = at or (newest_vintage(db) + timedelta(days=1))
    with open_ingest_run(
        db,
        source_id=nd_mpr.SOURCE_ID,
        environment=lineage_env,
        clock=FixedClock(datetime(day.year, day.month, day.day, 6, 0, 0, tzinfo=UTC)),
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
    """The intended case: a knowledge day later than anything already recorded."""
    return run_repromotion(db, lineage_env)


def multi_pool_groups(db) -> int:
    """G, from the ledger: one per (well, month, stream) that filed in more than one pool."""
    return scalar(
        db,
        "select count(*) from (select distinct row_payload->>'api10',"
        "       (row_payload->>'production_month')::date, row_payload->>'stream_canonical'"
        "  from lineage.quarantine_rows where reason_code = 'key_collision') g",
    )


def test_every_row_the_old_key_wrote_is_still_there_untouched(db, legacy, repromoted):
    """DIR-2 is append-only by construction; the gate asks for proof, not an assertion."""
    rows = query(
        db,
        "select count(*), count(distinct derivation_id) from canonical.production_monthly"
        " where report_vintage = %s",
        OLD_VINTAGE,
    )
    assert rows == [((UNAFFECTED_WELLS + 2) * 3, 1)]
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
        repromoted.report_vintage,
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
        " where report_vintage = %s and stream = 'oil' and api10 = %s"
        " order by entity_type, entity_key",
        repromoted.report_vintage,
        MULTI_POOL,
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
    assert served(db, MULTI_POOL, as_of=repromoted.report_vintage)["oil"] == DUPEROW_OIL


def test_the_multi_pool_pending_ledger_rows_are_closed_not_deleted(db, repromoted):
    assert query(
        db,
        "select state, released_by_rule_id, count(*) from lineage.quarantine_rows"
        " where reason_code = 'key_collision' group by 1, 2",
    ) == [("superseded", nd_mpr.ROLLUP_RULE, 6)]
    assert repromoted.collisions_superseded == 6


def test_the_run_reports_what_it_did(db, legacy, repromoted):
    groups = multi_pool_groups(db)

    assert repromoted.report_vintage == OLD_VINTAGE + timedelta(days=1)
    assert repromoted.rows_aggregated == groups
    assert repromoted.months_touched == ["2026-01-01"]


def test_the_report_counts_only_rows_that_actually_landed(db, repromoted):
    """It said 3,625 where 2,763 landed, because the aggregates were swallowed on insert."""
    landed = scalar(
        db,
        "select count(*) from canonical.production_monthly where report_vintage = %s",
        repromoted.report_vintage,
    )

    assert repromoted.rows_appended == landed


def test_every_multi_pool_group_lands_an_aggregate_even_when_its_value_did_not_move(
    db, legacy, repromoted
):
    """gate-a1b Defect B: 500 of 1,362 aggregates were dropped as `unchanged` and their
    wells went on being served a cross-pool sum labelled as a single-pool observation."""
    groups = multi_pool_groups(db)
    aggregates = scalar(
        db,
        "select count(*) from canonical.production_monthly"
        " where aggregation = 'sum_over_pools' and report_vintage = %s",
        repromoted.report_vintage,
    )

    assert aggregates == groups
    assert query(
        db,
        "select volume, aggregation, reporting_level from canonical.production_monthly"
        " where entity_key = %s and stream = 'oil' and report_vintage = %s",
        DISCLOSURE_ONLY,
        repromoted.report_vintage,
    ) == [(DISCLOSURE_OIL, "sum_over_pools", "well_completion_pool")]


def test_the_unmoved_wells_value_is_still_exactly_what_it_was(db, repromoted):
    """The disclosure is added by appending a vintage, not by changing a number."""
    assert served(db, DISCLOSURE_ONLY)["oil"] == DISCLOSURE_OIL


def test_running_it_again_the_next_day_appends_nothing(db, legacy, lineage_env, repromoted):
    before = scalar(db, "select count(*) from canonical.production_monthly")

    second = run_repromotion(db, lineage_env, at=newest_vintage(db) + timedelta(days=1))

    assert second.rows_appended == 0
    assert scalar(db, "select count(*) from canonical.production_monthly") == before


def test_running_it_twice_on_the_same_day_is_a_no_op_rather_than_a_second_promotion(
    db, legacy, lineage_env, repromoted
):
    """Idempotence has to survive the same-vintage guard: a repeat run computes what is
    already recorded, so it lands nothing and raises nothing."""
    before = scalar(db, "select count(*) from canonical.production_monthly")

    second = run_repromotion(db, lineage_env, at=repromoted.report_vintage)

    assert (second.rows_appended, second.rows_aggregated) == (0, 0)
    assert scalar(db, "select count(*) from canonical.production_monthly") == before


def test_a_no_op_re_run_does_not_erase_the_record_of_what_the_first_pass_did(
    db, legacy, lineage_env, repromoted
):
    run_repromotion(db, lineage_env, at=repromoted.report_vintage)

    assert scalar(
        db,
        "select rows_appended from lineage.vintages where vintage_date = %s",
        repromoted.report_vintage,
    ) == repromoted.rows_appended


def test_re_promoting_at_a_vintage_that_already_answers_is_refused(db, legacy, lineage_env):
    """gate-a1b Defect A. `report_vintage` is the wall-clock day, so deploying on the day the
    fleet was last promoted put the aggregates on a collision course with the rows they
    correct. They were swallowed by `on conflict do nothing` while every collision row closed
    anyway: the wrong figure came back with its only disclosure deleted."""
    occupied = newest_vintage(db)
    before = scalar(db, "select count(*) from canonical.production_monthly")

    with pytest.raises(VintageAlreadyPromoted, match="already holds"):
        run_repromotion(db, lineage_env, at=occupied)
    db.rollback()

    assert scalar(db, "select count(*) from canonical.production_monthly") == before


def test_a_refused_run_leaves_the_ledger_exactly_as_it_found_it(db, legacy, lineage_env):
    """The failure mode was not the refusal; it was closing 1,401 rows and writing none."""
    before = query(
        db,
        "select state, count(*) from lineage.quarantine_rows"
        " where reason_code = 'key_collision' group by 1 order by 1",
    )

    with pytest.raises(VintageAlreadyPromoted):
        run_repromotion(db, lineage_env, at=newest_vintage(db))
    db.rollback()

    assert query(
        db,
        "select state, count(*) from lineage.quarantine_rows"
        " where reason_code = 'key_collision' group by 1 order by 1",
    ) == before
    assert before[0][0] == "open"


def test_the_refusal_names_the_vintage_and_says_what_to_do(db, legacy, lineage_env):
    occupied = newest_vintage(db)

    with pytest.raises(VintageAlreadyPromoted) as refused:
        run_repromotion(db, lineage_env, at=occupied)
    db.rollback()

    message = str(refused.value)
    assert str(occupied) in message
    assert "later one" in message


def test_the_re_promotion_opens_a_vintage_and_says_why(db, legacy, repromoted):
    payload = scalar(
        db,
        "select payload from lineage.audit_events where event_type = 'canonical.vintage_opened'"
        " order by event_id desc limit 1",
    )
    assert payload["reason"] == "s_e_entity_key_repromotion"
    assert payload["collisions_superseded"] == repromoted.collisions_superseded
    assert payload["rows_aggregated"] == multi_pool_groups(db)


def test_the_runner_reads_staging_and_never_the_workbook(db, repromoted, tmp_path):
    """The bytes were parsed once against a verified manifest; that derivation is history."""
    assert scalar(db, "select count(*) from lineage.derivations where operation = 'stage.parse'")\
        == 0


def api_series(client, api10: str, *, as_of: date | None = None) -> dict:
    params: dict[str, object] = {"stream": "oil"}
    if as_of is not None:
        params["as_of"] = as_of.isoformat()
    return client.get(f"/v1/wells/{api10}/production", params=params).json()


def test_a_well_whose_number_did_not_move_still_says_the_number_is_a_sum(
    db, legacy, repromoted, api_client
):
    """gate-a1b Defect B on the wire: 20 wells had no month disclosed as a sum, and no
    `links.pools` to follow, while `/pools` held two pools the reader could not find."""
    body = api_series(api_client, DISCLOSURE_ONLY)

    assert body["data"]["series"]["oil_bbl"] == [str(DISCLOSURE_OIL)]
    assert body["data"]["series"]["oil_bbl_aggregation"] == ["sum_over_pools"]
    assert body["data"]["reporting_level"] == "well_completion_pool"
    assert body["links"]["pools"] == f"/v1/wells/{DISCLOSURE_ONLY}/production/pools"
    assert [w["code"] for w in body["meta"]["warnings"] if w["code"] == "pools_aggregated"]


def test_the_breakdown_a_reader_can_now_reach_sums_to_the_well(db, legacy, repromoted, api_client):
    pools = api_client.get(
        f"/v1/wells/{DISCLOSURE_ONLY}/production/pools"
    ).json()["data"]["pools"]

    assert [pool["well_completion_pool"] for pool in pools] == ["BAKKEN", "LODGEPOLE"]
    assert sum(Decimal(pool["series"]["oil_bbl"][0]) for pool in pools) == DISCLOSURE_OIL


def test_an_as_of_read_from_before_the_release_still_discloses_the_withholding(
    db, legacy, repromoted, api_client
):
    """gate-a1b Defect C. The ledger was not bitemporal, so a replay of the day before the
    re-promotion answered `0.000 / reported_zero / no warning` where the system on that date
    answered `null / multi_pool_pending / here is the 17,247 bbl`. It manufactured a
    regulator zero that was never filed."""
    before = api_series(api_client, MULTI_POOL, as_of=repromoted.report_vintage - timedelta(days=1))

    assert before["data"]["series"]["oil_bbl"] == [None]
    assert before["data"]["series"]["oil_bbl_null_semantics"] == ["multi_pool_pending"]
    pending = [w for w in before["meta"]["warnings"] if w["code"] == "multi_pool_pending"]
    assert pending, "the replay serves a number the ledger says nobody had"
    assert str(DUPEROW_OIL) in pending[0]["detail"]


def test_an_as_of_read_on_the_release_vintage_sees_the_correction(
    db, legacy, repromoted, api_client
):
    on_release = api_series(api_client, MULTI_POOL, as_of=repromoted.report_vintage)

    assert on_release["data"]["series"]["oil_bbl"] == [str(DUPEROW_OIL)]
    assert on_release["data"]["series"]["oil_bbl_null_semantics"] == ["reported"]
    assert [w for w in on_release["meta"]["warnings"] if w["code"] == "multi_pool_pending"] == []


def test_the_latest_read_is_unaffected_by_the_as_of_predicate(db, legacy, repromoted, api_client):
    latest = api_series(api_client, MULTI_POOL)

    assert latest["data"]["series"]["oil_bbl"] == [str(DUPEROW_OIL)]
    assert latest["data"]["series"]["oil_bbl_aggregation"] == ["sum_over_pools"]


def test_the_release_records_the_vintage_it_happened_at(db, repromoted):
    assert query(
        db,
        "select distinct released_at_vintage from lineage.quarantine_rows"
        " where reason_code = 'key_collision' and state = 'superseded'",
    ) == [(repromoted.report_vintage,)]
