"""Promotion at the grain New Mexico reports: well completion x pool, one month at a time.

The whole path runs here — the sealed zip, the streaming reader, staging, the registry's rules,
the anti-join and the ledger — against the 300-record fixture cut from the one polite pull. What
the fixture cannot carry is stated where it is asserted: it holds no duplicate S-E key and no
even county code, so those two cases are driven from synthetic documents whose shape is the
measured shape of the 48.1M-row corpus.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import polars as pl
import psycopg
import pytest

from glasswell.ingest import nm_ocd
from glasswell.ingest.base import open_ingest_run
from glasswell.lineage.conformance import load_rules
from glasswell.seed import seed_all
from tests.integration.test_nm_stage import (
    FakeFtp,
    fixture_for,
    full_record,
    stage,
    synthetic_document,
)
from tests.integration.test_nm_stage import staging_root as _staging_root
from tests.support.fakes import FixedClock

# Re-exported rather than redefined: pytest resolves a fixture by module attribute.
staging_root = _staging_root

SPINE = "wcproduction"
SPINE_SOURCE = "nm_ocd_wcproduction"
# The rules the promotion reads carry effective_from 2026-08-21, so a run clock before that
# loads none of them (load_rules filters on as_of).
DAY_ONE = datetime(2026, 8, 21, 6, 15, 0, tzinfo=UTC)
DAY_TWO = datetime(2026, 8, 22, 6, 15, 0, tzinfo=UTC)
FULL_HISTORY = date(1973, 1, 1)
# The fixture straddles DIR-12's boundary: 20 rows in 1973, 251 in 2014, 29 from 2015-01 on.
IN_WINDOW_ROWS = 29
FIXTURE_ROWS = 300
# The one well-month the fixture files under two pools (SOURCE.md), and it is pre-window.
MULTI_POOL_API10 = "3004523968"
MULTI_POOL_MONTH = date(2014, 3, 1)


@pytest.fixture
def seeded(db: psycopg.Connection) -> None:
    seed_all(db)
    db.commit()


def promote(
    db: psycopg.Connection,
    *,
    at: datetime = DAY_ONE,
    window_start: date | None = None,
    months=None,
    mod_dte_shortcut: bool = True,
) -> nm_ocd.PromotionReport:
    with open_ingest_run(db, source_id=SPINE_SOURCE, clock=FixedClock(at)) as run:
        report = nm_ocd.promote_all(
            run, window_start=window_start, months=months, mod_dte_shortcut=mod_dte_shortcut
        )
    db.commit()
    return report


def query(db: psycopg.Connection, sql: str, *parameters: object) -> list[tuple]:
    with db.cursor() as cursor:
        cursor.execute(sql, parameters or None)
        return cursor.fetchall()


def scalar(db: psycopg.Connection, sql: str, *parameters: object):
    return query(db, sql, *parameters)[0][0]


def promoted_rows(db: psycopg.Connection) -> list[tuple]:
    return query(
        db,
        "select entity_type, entity_key, production_month, stream, volume, unit, days_produced,"
        " granularity, reporting_level, well_completion_pool, api10, null_semantics,"
        " report_vintage, aggregation"
        " from canonical.production_monthly where source_id = %s"
        " order by production_month, entity_key, stream",
        SPINE_SOURCE,
    )


@pytest.fixture
def staged_day_one(db, seeded, raw_root, staging_root, tmp_path, monkeypatch):
    return stage(db, raw_root, tmp_path, monkeypatch, at=DAY_ONE)


def test_the_window_is_a_predicate_and_not_a_property_of_the_artifact(db, staged_day_one) -> None:
    """DIR-12: 2015-01 onward, applied at promotion. The other 271 staged rows are neither
    promoted nor quarantined — they were never read, and widening is the same run again."""
    report = promote(db)

    assert report.window_start == date(2015, 1, 1)
    assert report.staged_rows == IN_WINDOW_ROWS
    assert report.promoted_rows == IN_WINDOW_ROWS
    assert len(report.months) == 12
    assert scalar(db, "select count(*) from lineage.quarantine_rows where source_id = %s",
                  SPINE_SOURCE) == 0
    assert scalar(db, "select min(production_month) from canonical.production_monthly"
                      " where source_id = %s", SPINE_SOURCE) == date(2015, 1, 1)


def test_widening_the_window_is_a_re_run_and_not_a_rewrite(db, staged_day_one) -> None:
    promote(db)
    widened = promote(db, at=DAY_TWO, window_start=FULL_HISTORY)

    assert widened.staged_rows == FIXTURE_ROWS
    assert widened.promoted_rows == FIXTURE_ROWS - IN_WINDOW_ROWS
    assert widened.suppressed_unchanged == IN_WINDOW_ROWS
    assert scalar(db, "select count(*) from canonical.production_monthly where source_id = %s",
                  SPINE_SOURCE) == FIXTURE_ROWS
    assert query(
        db,
        "select vintage_date, rows_appended from lineage.vintages where source_id = %s"
        " order by vintage_date",
        SPINE_SOURCE,
    ) == [(DAY_ONE.date(), IN_WINDOW_ROWS), (DAY_TWO.date(), FIXTURE_ROWS - IN_WINDOW_ROWS)]


def test_every_promoted_row_is_the_tuple_the_composition_check_admits(db, staged_day_one) -> None:
    promote(db)

    shapes = query(
        db,
        "select entity_type, reporting_level, granularity, aggregation, count(*)"
        " from canonical.production_monthly where source_id = %s group by 1, 2, 3, 4",
        SPINE_SOURCE,
    )

    assert shapes == [("well_completion_pool", "well_completion_pool", "well_observed", None, 29)]


def test_the_entity_key_is_the_completion_in_its_pool(db, staged_day_one) -> None:
    promote(db)

    keys = {row[1] for row in promoted_rows(db)}

    assert keys == {"3000501028:8559", "3000501035:8559"}
    assert all(row[1] == f"{row[10]}:{row[9]}" for row in promoted_rows(db))


def test_an_oil_row_lands_as_oil_through_the_trim_its_rule_declares(db, staged_day_one) -> None:
    """B5, at the far end of the pipeline: staging holds 'O ' and canonical holds oil."""
    promote(db)

    january = query(
        db,
        "select stream, volume, unit, days_produced, null_semantics"
        " from canonical.production_monthly"
        " where source_id = %s and entity_key = %s and production_month = %s and stream = 'oil'",
        SPINE_SOURCE,
        "3000501028:8559",
        date(2015, 1, 1),
    )

    assert january == [("oil", Decimal("79.000"), "bbl", 31, "reported")]
    assert {row[3] for row in promoted_rows(db)} == {"oil", "water"}


def test_a_well_producing_from_two_pools_is_two_rows_and_not_a_collision(
    db, staged_day_one
) -> None:
    """The point of the widened key. ND had to quarantine this shape as key_collision because
    its key was the API-10 alone; NM's is the completion in its pool, so both filings promote
    and their sum is exact."""
    promote(db, window_start=FULL_HISTORY)

    pools = query(
        db,
        "select well_completion_pool, volume from canonical.production_monthly"
        " where source_id = %s and api10 = %s and production_month = %s and stream = 'gas'"
        " order by well_completion_pool",
        SPINE_SOURCE,
        MULTI_POOL_API10,
        MULTI_POOL_MONTH,
    )

    staged_total = sum(
        Decimal(row["prod_amt"])
        for row in pl.read_parquet(staged_day_one.parquet_uri).iter_rows(named=True)
        if row["api_st_cde"] + row["api_cnty_cde"].zfill(3) + row["api_well_idn"].zfill(5)
        == MULTI_POOL_API10
        and (int(row["prodn_yr"]), int(row["prodn_mth"])) == (2014, 3)
        and row["prd_knd_cde"].rstrip() == "G"
    )

    assert len(pools) == 2
    assert sum(volume for _, volume in pools) == staged_total
    assert scalar(
        db,
        "select count(*) from lineage.quarantine_rows where source_id = %s"
        " and reason_code = 'key_collision'",
        SPINE_SOURCE,
    ) == 0
    assert scalar(
        db,
        "select count(*) from canonical.production_monthly where source_id = %s"
        " and entity_type <> 'well_completion_pool'",
        SPINE_SOURCE,
    ) == 0


def test_the_parity_rule_is_cited_by_a_real_promotion_derivation(db, staged_day_one) -> None:
    """SB-01 §12's P7a exit criterion, asserted as the gate states it: cited by a derivation
    that promoted real rows, with a real row count."""
    promote(db)

    cited = query(
        db,
        "select r.rule_id, sum(r.applied_rows) from lineage.derivation_rules r"
        "  join lineage.derivations d using (derivation_id)"
        " where d.operation = 'canonical.promote' and r.rule_id like 'cr_nm_%%'"
        " group by 1 order by 1",
    )
    cited_rows = dict(cited)

    assert cited_rows["cr_nm_wcproduction_county_parity_1"] == IN_WINDOW_ROWS
    assert cited_rows["cr_nm_wcproduction_api10_1"] == IN_WINDOW_ROWS
    assert cited_rows["cr_nm_wcproduction_window_1"] == IN_WINDOW_ROWS
    assert cited_rows["cr_nm_wcproduction_days_1"] == IN_WINDOW_ROWS
    assert cited_rows["cr_nm_wcproduction_collision_1"] == 0


def test_a_promotion_cites_at_least_one_rule_per_derivation(db, staged_day_one) -> None:
    """SB-01 §5.2: a promotion that applied no rule is a bug, and it is one this asserts."""
    promote(db)

    uncited = query(
        db,
        "select d.derivation_id from lineage.derivations d"
        " where d.operation = 'canonical.promote'"
        "   and not exists (select 1 from lineage.derivation_rules r"
        "                    where r.derivation_id = d.derivation_id)",
    )

    assert uncited == []
    assert scalar(
        db,
        "select count(*) from lineage.derivations where operation = 'canonical.promote'",
    ) == 12


def test_every_promoted_row_carries_the_derivation_of_its_own_month(db, staged_day_one) -> None:
    """One derivation per (vintage, month) batch, so a figure resolves to the batch that
    computed it rather than to a run that touched 139 months."""
    promote(db)

    months = query(
        db,
        "select p.production_month, count(distinct p.derivation_id),"
        "       max(d.output_partition ->> 'production_month')"
        "  from canonical.production_monthly p"
        "  join lineage.derivations d on d.derivation_id = p.derivation_id"
        " where p.source_id = %s group by 1 order by 1",
        SPINE_SOURCE,
    )

    assert len(months) == 12
    assert all(count == 1 for _, count, _ in months)
    assert all(month.isoformat() == partition for month, _, partition in months)


def test_the_reconciliation_identity_holds_for_every_month(db, staged_day_one) -> None:
    """SB-01 §5.1 stage 3, with the suppression reported separately: change-only append is a
    suppression and counting it as a rejection would make the quarantine share a lie."""
    report = promote(db, window_start=FULL_HISTORY)
    quarantined = sum(report.quarantined.values())

    assert report.staged_rows == FIXTURE_ROWS
    assert report.staged_rows == report.promoted_rows + quarantined + report.suppressed_unchanged
    assert report.suppressed_unchanged == 0
    assert quarantined == 0


def test_a_month_reconciles_with_a_quarantine_and_a_suppression_at_once(
    db, seeded, raw_root, staging_root, tmp_path, monkeypatch
) -> None:
    """The identity's two correction terms, both non-zero in one month. Pinned separately at
    zero, they never constrain each other (gate-nm-fp O6)."""
    stage(db, raw_root, tmp_path, monkeypatch, at=DAY_ONE, document=collided_document())
    first = promote(db)

    second = promote(db, at=DAY_TWO)

    assert first.promoted_rows == 1
    assert second.promoted_rows == 0
    assert sum(second.quarantined.values()) == 3
    assert second.suppressed_unchanged == 1
    assert second.staged_rows == (
        second.promoted_rows + sum(second.quarantined.values()) + second.suppressed_unchanged
    )


def test_a_row_counted_as_promoted_and_suppressed_at_once_does_not_reconcile(
    db, staged_day_one, monkeypatch
) -> None:
    """O6: with `suppressed` computed as `kept - promoted` the identity cancels `promoted` and
    a mis-split is unfalsifiable by construction. Suppression is measured against the head, so
    an append that over-reports what it landed is caught."""
    landed = nm_ocd._append_promoted
    monkeypatch.setattr(
        nm_ocd, "_append_promoted", lambda *args, **keywords: landed(*args, **keywords) + 1
    )

    with pytest.raises(nm_ocd.RowCountMismatch, match="is exactly one of those"):
        promote(db)
    db.rollback()


def test_a_promotion_that_loses_a_row_before_the_append_is_refused(
    db, staged_day_one, monkeypatch
) -> None:
    """SB-01 §5.1's guard, shown firing. A row dropped between the routing and the append is
    neither promoted, quarantined nor suppressed, and the month refuses rather than recording
    a promoted count that does not reconcile."""
    routed = nm_ocd.route_collisions

    def losing(records: pl.DataFrame) -> nm_ocd.CollisionRouting:
        routing = routed(records)
        return replace(routing, kept=routing.kept.head(max(routing.kept.height - 1, 0)))

    monkeypatch.setattr(nm_ocd, "route_collisions", losing)

    with pytest.raises(nm_ocd.RowCountMismatch, match="is exactly one of those"):
        promote(db)
    db.rollback()

    assert scalar(db, "select count(*) from canonical.production_monthly where source_id = %s",
                  SPINE_SOURCE) == 0


def test_the_quarantine_share_is_measured_rather_than_required(db, staged_day_one) -> None:
    """Errata E8: a non-zero requirement rewards manufacturing rejects. The fixture's share is
    zero because the spine has no blank key component and no null volume, and that is the
    finding, not a failure."""
    report = promote(db, window_start=FULL_HISTORY)

    assert dict(report.quarantined) == {}


def test_a_day_count_longer_than_its_month_lands_null_and_keeps_its_volume(
    db, staged_day_one
) -> None:
    """The fixture carries 20 rows filing 99 days. The volume beside them is real."""
    promote(db, window_start=FULL_HISTORY)

    withheld = query(
        db,
        "select count(*), count(days_produced), min(volume)"
        " from canonical.production_monthly where source_id = %s and days_produced is null",
        SPINE_SOURCE,
    )

    assert withheld[0][0] == 20
    assert withheld[0][1] == 0
    assert scalar(
        db,
        "select count(*) from canonical.production_monthly"
        " where source_id = %s and days_produced > extract(day from"
        "       (production_month + interval '1 month' - interval '1 day'))",
        SPINE_SOURCE,
    ) == 0


def test_promoting_an_unchanged_manifest_again_appends_nothing(db, staged_day_one) -> None:
    """Arm B at the promotion layer: the same bytes on a later day compute the same rows, so
    the anti-join suppresses every one of them and the ledger records the run honestly."""
    first = promote(db)
    derivations = scalar(db, "select count(*) from lineage.derivations")

    second = promote(db, at=DAY_TWO)

    assert second.promoted_rows == 0
    assert second.suppressed_unchanged == IN_WINDOW_ROWS
    assert second.restatement_summary == {}
    assert scalar(db, "select count(*) from canonical.production_monthly where source_id = %s",
                  SPINE_SOURCE) == first.promoted_rows
    # The address is the same, so the second run reconciles to a noop rather than a new node.
    assert scalar(db, "select count(*) from lineage.derivations") == derivations
    assert scalar(
        db, "select count(*) from lineage.audit_events where event_type = %s",
        "canonical.restatement_detected",
    ) == 0


def naive_expectation(db: psycopg.Connection, *, window_start: date) -> set[tuple]:
    """The promotion rev 1 would have written: every record in Python, every head in a dict.

    This is the B1 regression's control. It is correct at 300 rows and would need ~19 GB of
    Python objects at 48.1M, which is why the shipped path is a server-side anti-join.
    """
    rules = load_rules(db, source_id=SPINE_SOURCE, as_of=date(2026, 12, 31))
    policy = nm_ocd.PromotionPolicy.from_rules(rules)
    conform = [rule for rule in rules if rule.stage == "conform"]
    validate = [rule for rule in rules if rule.stage == "validate"]
    partition = nm_ocd.partition_for(db, nm_ocd.head_manifest(db, SPINE_SOURCE).manifest_id)
    heads: dict[tuple, str] = {}
    for entity_key, month, stream, value_hash in query(
        db,
        "select entity_key, production_month, stream, value_hash from"
        " canonical.production_monthly_latest where source_id = %s",
        SPINE_SOURCE,
    ):
        heads[(entity_key, month, stream)] = value_hash

    expected: set[tuple] = set()
    frame = pl.read_parquet(Path(partition))
    for month_text in sorted(
        {f"{row['prodn_yr']}-{int(row['prodn_mth']):02d}-01" for row in frame.iter_rows(named=True)}
    ):
        month = date.fromisoformat(month_text)
        if month < window_start:
            continue
        batch = frame.filter(
            (pl.col("prodn_yr") == str(month.year))
            & (pl.col("prodn_mth").cast(pl.Int64) == month.month)
        )
        typed = nm_ocd._typed_frame(batch, policy=policy, month=month)
        from glasswell.lineage.conformance import apply_rules

        conformed = apply_rules(apply_rules(typed, validate).frame, conform)
        routing = nm_ocd.route_collisions(
            nm_ocd.promotion_records(conformed.frame, policy=policy)
        )
        for record in routing.kept.iter_rows(named=True):
            key = (record["entity_key"], record["production_month"], record["stream"])
            if heads.get(key) != record["value_hash"]:
                expected.add(key)
    return expected


def test_the_set_based_path_and_a_python_dictionary_agree(db, staged_day_one) -> None:
    """B1's regression: the optimisation is verified against the design it replaced, on a
    head that is not empty, so the anti-join is doing work when they are compared."""
    promote(db)
    expected = naive_expectation(db, window_start=FULL_HISTORY)

    promote(db, at=DAY_TWO, window_start=FULL_HISTORY)

    appended = {
        (entity_key, month, stream)
        for entity_key, month, stream in query(
            db,
            "select entity_key, production_month, stream from canonical.production_monthly"
            " where source_id = %s and report_vintage = %s",
            SPINE_SOURCE,
            DAY_TWO.date(),
        )
    }

    assert appended == expected
    assert len(appended) == FIXTURE_ROWS - IN_WINDOW_ROWS


def test_a_canonical_row_cannot_be_updated_after_it_lands(db, staged_day_one) -> None:
    promote(db)

    with pytest.raises(psycopg.errors.RestrictViolation, match="append_only_violation"), \
            db.cursor() as cursor:
        cursor.execute(
            "update canonical.production_monthly set volume = 0 where source_id = %s",
            (SPINE_SOURCE,),
        )
    db.rollback()


def spine_record(**overrides: str) -> str:
    """A record whose identity columns are New Mexico's: `full_record` fills every cell with
    `1`, which is a state code the parity rule refuses before anything else can be tested."""
    cells = {"api_st_cde": "30", "api_cnty_cde": "5", "api_well_idn": "1028",
             "pool_idn": "8559", "prodn_yr": "2015", "prodn_mth": "1", "prd_knd_cde": "O ",
             "prodn_day_num": "31", "amend_ind": "N", "prod_amt": "100",
             "mod_dte": "2015-04-07T07:37:04.160", "ogrid_cde": "111111"}
    return full_record(**{**cells, **overrides})


def collided_document() -> bytes:
    """Two filings for one completion-month under two OGRIDs — the artifact's own shape for
    25,029 in-window well-months, which the 300-record fixture happens not to carry."""
    return synthetic_document(
        [
            spine_record(prod_amt="100", ogrid_cde="111111"),
            spine_record(prod_amt="900", ogrid_cde="222222"),
            spine_record(pool_idn="9999", prod_amt="500", ogrid_cde="111111"),
            spine_record(pool_idn="9999", prod_amt="500", ogrid_cde="222222"),
        ]
    )


def test_two_filings_that_disagree_promote_nothing_and_reach_the_ledger(
    db, seeded, raw_root, staging_root, tmp_path, monkeypatch
) -> None:
    stage(db, raw_root, tmp_path, monkeypatch, at=DAY_ONE, document=collided_document())

    report = promote(db)

    assert report.staged_rows == 4
    assert report.promoted_rows == 1
    assert dict(report.quarantined) == {"key_collision": 2, "duplicate_row": 1}
    assert query(
        db,
        "select entity_key, volume from canonical.production_monthly where source_id = %s",
        SPINE_SOURCE,
    ) == [("3000501028:9999", Decimal("500.000"))]
    assert query(
        db,
        "select reason_code, rule_id, stage, count(*) from lineage.quarantine_rows"
        " where source_id = %s group by 1, 2, 3 order by 1",
        SPINE_SOURCE,
    ) == [
        ("duplicate_row", "cr_nm_wcproduction_collision_1", "join", 1),
        ("key_collision", "cr_nm_wcproduction_collision_1", "join", 2),
    ]
    assert report.staged_rows == report.promoted_rows + sum(report.quarantined.values())


def test_a_negative_volume_is_refused_before_it_can_be_a_figure(
    db, seeded, raw_root, staging_root, tmp_path, monkeypatch
) -> None:
    """Three rows in 48.1M report one, all in 1993 and all outside the window — which is why
    the rule is seeded now rather than on the day the window widens onto them."""
    document = synthetic_document(
        [
            spine_record(prod_amt="-104", prodn_mth="5"),
            spine_record(prod_amt="104", prodn_mth="5", api_well_idn="1029"),
        ]
    )
    stage(db, raw_root, tmp_path, monkeypatch, at=DAY_ONE, document=document)

    report = promote(db)

    assert report.promoted_rows == 1
    assert dict(report.quarantined) == {"impossible_volume": 1}
    assert query(
        db,
        "select reason_code, rule_id from lineage.quarantine_rows where source_id = %s",
        SPINE_SOURCE,
    ) == [("impossible_volume", "cr_nm_wcproduction_volume_range_1")]


def test_a_stream_the_map_does_not_carry_is_not_promoted(
    db, seeded, raw_root, staging_root, tmp_path, monkeypatch
) -> None:
    document = synthetic_document([spine_record(prd_knd_cde="Z ", prodn_mth="6", prod_amt="10")])
    stage(db, raw_root, tmp_path, monkeypatch, at=DAY_ONE, document=document)

    report = promote(db)

    assert report.promoted_rows == 0
    assert dict(report.quarantined) == {"stream_not_promoted": 1}


def test_the_promotion_completed_event_carries_the_window_it_ran_under(db, staged_day_one) -> None:
    promote(db)

    payload = scalar(
        db,
        "select payload from lineage.audit_events where event_type = %s",
        "canonical.promotion_completed",
    )

    assert payload["window_start"] == "2015-01-01"
    assert payload["rows_appended"] == IN_WINDOW_ROWS
    assert payload["months_touched"] == 12


def test_the_vintage_records_what_the_run_examined_and_appended(db, staged_day_one) -> None:
    report = promote(db)

    vintage = query(
        db,
        "select vintage_id, rows_examined, rows_appended, array_length(months_touched, 1),"
        "       restatement_summary, manifest_ids"
        " from lineage.vintages where source_id = %s",
        SPINE_SOURCE,
    )

    assert vintage == [
        (
            f"vin_{SPINE_SOURCE}_2026-08-21",
            IN_WINDOW_ROWS,
            IN_WINDOW_ROWS,
            12,
            {},
            [report.manifest_id],
        )
    ]


SAME_DAY_WIDENING = datetime(2026, 8, 21, 12, 15, 0, tzinfo=UTC)
SAME_DAY_RERUN = datetime(2026, 8, 21, 18, 15, 0, tzinfo=UTC)


def vintage_ledger(db: psycopg.Connection) -> list[tuple]:
    return query(
        db,
        "select vintage_id, rows_examined, rows_appended, months_touched,"
        "       restatement_summary, manifest_ids, opened_at, promotion_derivation_id"
        " from lineage.vintages where source_id = %s order by vintage_date",
        SPINE_SOURCE,
    )


def test_the_ledger_row_two_same_day_passes_produce_is_the_days_sum_exactly(
    db, staged_day_one, raw_root, staging_root, tmp_path, monkeypatch
) -> None:
    """DR-87 characterization: pins the exact ledger row so the consolidation onto
    `ingest.base.record_vintage_day` is provably byte-for-byte (gate-nm-fp D2 accumulate,
    gate-a1b §4 no-op guard, manifest dedup, month union, restatement per-month map)."""
    first = promote(db)
    widened = promote(db, at=SAME_DAY_WIDENING, window_start=FULL_HISTORY)

    day_one_row = (
        f"vin_{SPINE_SOURCE}_2026-08-21",
        first.staged_rows + widened.staged_rows,
        first.promoted_rows + widened.promoted_rows,
        sorted({*first.months, *widened.months}),
        {},
        [staged_day_one.manifest_id],
        DAY_ONE,
        None,
    )
    assert (first.staged_rows, first.promoted_rows) == (IN_WINDOW_ROWS, IN_WINDOW_ROWS)
    assert widened.promoted_rows == FIXTURE_ROWS - IN_WINDOW_ROWS
    assert vintage_ledger(db) == [day_one_row]

    rerun = promote(db, at=SAME_DAY_RERUN, window_start=FULL_HISTORY)
    assert rerun.promoted_rows == 0
    assert vintage_ledger(db) == [day_one_row], (
        "a pass that appended nothing must not overwrite the pass that did the work"
    )

    amended = (fixture_for(SPINE).parent / "nm_wcproduction_300_amended.xml").read_bytes()
    restaged = stage(db, raw_root, tmp_path, monkeypatch, at=DAY_TWO, document=amended)
    restated = promote(db, at=DAY_TWO, window_start=FULL_HISTORY)
    assert restated.restatement_summary == {"2014-03-01": 1}
    assert vintage_ledger(db) == [
        day_one_row,
        (
            f"vin_{SPINE_SOURCE}_2026-08-22",
            restated.staged_rows,
            restated.promoted_rows,
            sorted(set(restated.months)),
            {"2014-03-01": 1},
            [restaged.manifest_id],
            DAY_TWO,
            None,
        ),
    ]


def test_promoting_before_staging_says_so(db, seeded, raw_root, tmp_path, monkeypatch) -> None:
    FakeFtp.payload = b""
    with pytest.raises(LookupError, match="fetch before staging"):
        promote(db)


def test_a_month_outside_the_window_is_promotable_by_naming_it(db, staged_day_one) -> None:
    """The window is the default, not a wall: a named month promotes without widening the
    window for everything else, which is what a backfill needs."""
    report = promote(db, months=[MULTI_POOL_MONTH])

    assert report.months == [MULTI_POOL_MONTH.isoformat()]
    assert scalar(
        db,
        "select count(distinct production_month) from canonical.production_monthly"
        " where source_id = %s",
        SPINE_SOURCE,
    ) == 1


def test_the_ledger_keeps_the_source_row_that_was_refused(db, seeded, raw_root, staging_root,
                                                          tmp_path, monkeypatch) -> None:
    """A quarantine row an auditor cannot read the filing out of is a count, not a record.

    The deferred resolution needs the cell that says which operator filed which row, so what
    the payload has to carry is what the rule declares it decided on — not the derived
    canonical row, which is what it carried before gate-nm-fp O1.
    """
    stage(db, raw_root, tmp_path, monkeypatch, at=DAY_ONE, document=collided_document())
    promote(db)

    declared = set(
        scalar(
            db,
            "select spec -> 'declares_fields' from lineage.conformance_rules where rule_id = %s",
            "cr_nm_wcproduction_collision_1",
        )
    )
    payloads = query(
        db,
        "select row_payload from lineage.quarantine_rows where source_id = %s"
        " and reason_code = 'key_collision' order by row_payload ->> 'value_hash'",
        SPINE_SOURCE,
    )

    assert len(payloads) == 2
    assert declared == {"ogrid_cde", "amend_ind", "prod_amt", "prodn_day_num"}
    assert all(declared <= set(payload[0]) for payload in payloads)
    assert {payload[0]["volume"] for payload in payloads} == {"100.000", "900.000"}
    assert {payload[0]["entity_key"] for payload in payloads} == {"3000501028:8559"}
    assert {payload[0]["ogrid_cde"] for payload in payloads} == {"111111", "222222"}
    assert {payload[0]["prod_amt"] for payload in payloads} == {"100.000", "900.000"}
    assert {payload[0]["amend_ind"] for payload in payloads} == {"N"}
    assert {payload[0]["prodn_day_num"] for payload in payloads} == {"31"}


def test_the_promotion_reads_the_head_manifest_and_names_it_on_every_row(db, staged_day_one):
    report = promote(db)

    manifests = {row[0] for row in query(
        db,
        "select source_manifest_id from canonical.production_monthly where source_id = %s",
        SPINE_SOURCE,
    )}

    assert manifests == {report.manifest_id}
    assert report.manifest_id == nm_ocd.head_manifest(db, SPINE_SOURCE).manifest_id


def test_a_widened_run_stamps_the_window_it_ran_under_on_every_derivation(
    db, staged_day_one
) -> None:
    """cr_nm_wcproduction_window_1's served rationale promises a figure from a widened run is
    distinguishable from one served before it, and `params` is where that is readable. A
    derivation for 1973-07 claiming a 2015-01 window falsifies the rule row verbatim."""
    promote(db, window_start=FULL_HISTORY)

    windows = query(
        db,
        "select distinct d.params ->> 'window_start'"
        "  from canonical.production_monthly p"
        "  join lineage.derivations d on d.derivation_id = p.derivation_id"
        " where p.source_id = %s and p.production_month < %s",
        SPINE_SOURCE,
        date(2015, 1, 1),
    )

    assert windows == [(FULL_HISTORY.isoformat(),)]
