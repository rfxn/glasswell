"""D1's structural fix: a well that filed in two pools promotes both, and the well sums them.

The interim guard withdrew the point and said why, because `split_key_collisions` kept row one
by spreadsheet ordinal and served it as the well — 78 wells, 454 well-months, 139,644 bbl of
oil labelled `reported_zero` under `granularity: well_observed` (fp-audit D1). Under the S-E
key each pool is a first-class row and the well figure is their exact sum, carried by an
aggregation derivation over those rows and legislated by `cr_nd_pool_rollup_1`.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from glasswell.ingest import nd_mpr
from glasswell.ingest.base import open_ingest_run
from glasswell.lineage.explain import resolve_chain
from glasswell.seed import seed_all
from tests.support.mpr_workbook import filing, write_workbook

MONTH = datetime(2026, 1, 1)
PRODUCTION_MONTH = date(2026, 1, 1)
MULTI_POOL = "3305302532"
SINGLE_POOL = "3305310451"
UNPOOLED = "3305399999"

# The audit's own row: BIRDBEAR filed nothing and promoted; DUPEROW filed 3,585 bbl and was
# quarantined, so the API served 0.000 for a well that produced 3,585.
BIRDBEAR_OIL = Decimal("0.000")
DUPEROW_OIL = Decimal("3585.000")
WELL_OIL = BIRDBEAR_OIL + DUPEROW_OIL


def workbook(path: Path) -> Path:
    return write_workbook(
        path,
        [
            filing(api14=f"{MULTI_POOL}0000", month=MONTH, pool="BIRDBEAR", oil=0, water=0,
                   gas=0, days=0),
            filing(api14=f"{MULTI_POOL}0000", month=MONTH, pool="DUPEROW", oil=3585, water=901,
                   gas=1446, days=31),
            filing(api14=f"{SINGLE_POOL}0000", month=MONTH, pool="BAKKEN", oil=70965,
                   water=12635, gas=58925, days=30),
            # No pool label: an observation of the well, not a completion (cr_nd_entity_key_1).
            filing(api14=f"{UNPOOLED}0000", month=MONTH, pool=None, oil=12, water=3, gas=9,
                   days=28),
        ],
    )


def client_for(path: Path) -> httpx.Client:
    payload = path.read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=payload,
            headers={
                "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "etag": '"pool-fixture"',
                "last-modified": "Thu, 14 May 2026 13:12:00 GMT",
            },
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def ingest(db, raw_root: Path, lineage_env, path: Path) -> nd_mpr.IngestReport:
    with open_ingest_run(
        db, source_id=nd_mpr.SOURCE_ID, raw_root=raw_root, environment=lineage_env
    ) as run, client_for(path) as client:
        report = nd_mpr.ingest_month(run, year=2026, month=1, client=client)
    db.commit()
    return report


@pytest.fixture
def promoted(db, raw_root, lineage_env, tmp_path) -> nd_mpr.IngestReport:
    seed_all(db)
    db.commit()
    return ingest(db, raw_root, lineage_env, workbook(tmp_path / "2026_01.xlsx"))


def query(db, sql: str, *parameters: object) -> list[tuple]:
    with db.cursor() as cursor:
        cursor.execute(sql, parameters or None)
        return cursor.fetchall()


def scalar(db, sql: str, *parameters: object):
    return query(db, sql, *parameters)[0][0]


def test_each_pool_the_well_filed_in_gets_its_own_row(db, promoted):
    assert query(
        db,
        "select entity_key, well_completion_pool, reporting_level, volume"
        "  from canonical.production_monthly"
        " where entity_type = 'well_completion_pool' and stream = 'oil' order by entity_key",
    ) == [
        (f"{MULTI_POOL}:BIRDBEAR", "BIRDBEAR", "well_completion_pool", BIRDBEAR_OIL),
        (f"{MULTI_POOL}:DUPEROW", "DUPEROW", "well_completion_pool", DUPEROW_OIL),
    ]


def test_the_well_figure_is_the_exact_sum_of_its_pools_and_says_so(db, promoted):
    assert query(
        db,
        "select volume, aggregation, reporting_level, granularity, null_semantics"
        "  from canonical.production_monthly"
        " where entity_type = 'well' and entity_key = %s and stream = 'oil'",
        MULTI_POOL,
    ) == [(WELL_OIL, "sum_over_pools", "well_completion_pool", "well_observed", "reported")]


def test_the_wells_days_are_the_maximum_over_its_pools_never_the_sum(db, promoted):
    """31 + 0 would be 31 by luck; 31 + 30 would be 61, which no month holds."""
    assert scalar(
        db,
        "select days_produced from canonical.production_monthly"
        " where entity_type = 'well' and entity_key = %s and stream = 'oil'",
        MULTI_POOL,
    ) == 31


def test_a_single_pool_well_is_still_one_well_row_and_is_not_an_aggregate(db, promoted):
    assert query(
        db,
        "select entity_type, reporting_level, well_completion_pool, aggregation, volume"
        "  from canonical.production_monthly where entity_key = %s and stream = 'oil'",
        SINGLE_POOL,
    ) == [("well", "well", "BAKKEN", None, Decimal("70965.000"))]


def test_a_filing_with_no_pool_label_promotes_as_the_well_rather_than_inventing_a_pool(
    db, promoted
):
    assert query(
        db,
        "select entity_type, reporting_level, well_completion_pool, aggregation"
        "  from canonical.production_monthly where entity_key = %s and stream = 'oil'",
        UNPOOLED,
    ) == [("well", "well", None, None)]


def test_nothing_is_quarantined_as_a_key_collision_any_more(db, promoted):
    assert (
        scalar(
            db,
            "select count(*) from lineage.quarantine_rows where reason_code = 'key_collision'",
        )
        == 0
    )


def test_the_summed_figure_carries_its_own_derivation_over_the_pool_rows(db, promoted):
    """R6/R7: the well's number is not a serve-time sum; it is a recorded derivation."""
    aggregate = promoted.aggregate_derivation_id
    assert aggregate is not None
    assert aggregate != promoted.promote_derivation_id
    assert scalar(
        db,
        "select count(*) from canonical.production_monthly"
        " where aggregation = 'sum_over_pools' and derivation_id <> %s",
        aggregate,
    ) == 0
    assert query(
        db,
        "select ref_id from lineage.derivation_inputs"
        " where derivation_id = %s and kind = 'derivation'",
        aggregate,
    ) == [(promoted.promote_derivation_id,)]


def test_the_aggregation_cites_the_rule_that_legislated_it(db, promoted):
    assert query(
        db,
        "select rule_id, applied_rows from lineage.derivation_rules where derivation_id = %s",
        promoted.aggregate_derivation_id,
    ) == [(nd_mpr.ROLLUP_RULE, 3)]


def test_the_summed_figure_still_explains_back_to_the_workbook(db, promoted):
    chain = resolve_chain(db, promoted.aggregate_derivation_id, depth="full")
    manifests = [node for node in chain.nodes if node.type == "manifest"]

    assert len(manifests) == 1
    assert all(node.type == "manifest" for node in chain.nodes if node.id in set(chain.terminals))


def test_each_pool_is_registered_as_a_completion_entity(db, promoted):
    assert query(
        db,
        "select completion_key, api10, well_completion_pool, production_month"
        "  from canonical.well_completions_latest order by completion_key",
    ) == [
        (f"{MULTI_POOL}:BIRDBEAR", MULTI_POOL, "BIRDBEAR", PRODUCTION_MONTH),
        (f"{MULTI_POOL}:DUPEROW", MULTI_POOL, "DUPEROW", PRODUCTION_MONTH),
    ]


def test_a_single_pool_well_registers_no_completion_entity(db, promoted):
    assert (
        scalar(db, "select count(*) from canonical.well_completions where api10 = %s", SINGLE_POOL)
        == 0
    )


def test_re_promoting_the_same_bytes_appends_nothing(db, raw_root, lineage_env, tmp_path, promoted):
    before = scalar(db, "select count(*) from canonical.production_monthly")

    second = ingest(db, raw_root, lineage_env, workbook(tmp_path / "2026_01.xlsx"))

    assert second.rows_appended == 0
    assert scalar(db, "select count(*) from canonical.production_monthly") == before


def test_the_vintage_counts_the_aggregate_rows_it_appended(db, promoted):
    examined, appended = query(
        db, "select rows_examined, rows_appended from lineage.vintages"
    )[0]

    # Per stream: two well rows, two pool rows and one aggregate over them.
    assert appended == 15
    assert examined == 15


DUPLICATE_LABEL = "3305300001"


@pytest.fixture
def undecomposable(db, raw_root, lineage_env, tmp_path) -> nd_mpr.IngestReport:
    """Two filings under one pool label: the rule cannot say which of them is the well."""
    seed_all(db)
    db.commit()
    path = write_workbook(
        tmp_path / "2026_01.xlsx",
        [
            filing(api14=f"{DUPLICATE_LABEL}0000", month=MONTH, pool="BAKKEN", oil=10, days=15),
            filing(api14=f"{DUPLICATE_LABEL}0000", month=MONTH, pool="BAKKEN", oil=20, days=16),
        ],
    )
    return ingest(db, raw_root, lineage_env, path)


def test_a_group_the_rule_cannot_decompose_keeps_the_ledger_row_the_guard_reads(
    db, undecomposable
):
    assert scalar(
        db,
        "select count(*) from lineage.quarantine_rows"
        " where reason_code = 'key_collision' and state = 'open'",
    ) == 3
    assert query(
        db,
        "select entity_type, aggregation from canonical.production_monthly"
        " where entity_key = %s and stream = 'oil'",
        DUPLICATE_LABEL,
    ) == [("well", None)]
