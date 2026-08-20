"""The withdrawal guard, on the two well-months the S-E key still cannot decompose.

Well 3305302532 filed 17,247 bbl of oil over six months and the API served 0.000, labelled
`reported_zero` under `granularity: well_observed` — 78 wells, 454 well-months, 139,644 bbl
(fp-audit D1). The structural fix promotes each pool and serves their disclosed sum, and
`test_multi_pool_serving.py` holds it to that.

This file holds the remainder: a well-month whose `key_collision` rows are still open, either
because two filings share one pool label so `cr_nd_pool_rollup_1` cannot say which is the
well, or because the month has not been re-promoted yet. There the point stays withdrawn and
the response says why, because a figure that is 39% of the well is worse than no figure.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from glasswell.seed import seed_all
from tests.support.seed import (
    seed_derivation,
    seed_manifest,
    seed_production,
    seed_well,
)

MULTI_POOL_API10 = "3305302532"
COLLISION_RULE = "cr_nd_api_identity_1"
MONTH = date(2026, 1, 1)
VINTAGE = date(2026, 8, 1)
# The audit's row: BIRDBEAR filed 0 and promoted; DUPEROW filed 3,585 bbl and collided.
PROMOTED_OIL = Decimal("0.000")
COLLIDED_OIL = Decimal("3585.000")


@pytest.fixture
def multi_pool(db: psycopg.Connection) -> psycopg.Connection:
    seed_all(db)
    manifest = seed_manifest(db, sha256="9" * 64, source_key="2026_01.xlsx")
    seed_well(db, api10=MULTI_POOL_API10, well_name="ND STATE 6-16")
    derivation = seed_derivation(db, partition={"manifest_id": manifest})
    for month, volume, semantics in (
        (date(2025, 12, 1), Decimal("120.000"), "reported"),
        (MONTH, PROMOTED_OIL, "reported_zero"),
    ):
        seed_production(
            db,
            api10=MULTI_POOL_API10,
            production_month=month,
            report_vintage=VINTAGE,
            volume=volume,
            manifest_id=manifest,
            derivation_id=derivation,
            null_semantics=semantics,
        )
    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.quarantine_rows (quarantine_id, row_fingerprint, source_id,"
            " staging_table, stage, reason_code, rule_id, row_payload, first_seen_at,"
            " first_seen_manifest_id, last_seen_at, last_seen_manifest_id)"
            " values ('qtn_pool_1', 'fp_pool_1', 'nd_mpr_xlsx', 'staging.nd_mpr_oil', 'conform',"
            " 'key_collision', %s, %s, now(), %s, now(), %s)",
            (
                COLLISION_RULE,
                Jsonb(
                    {
                        "api10": MULTI_POOL_API10,
                        "pool": "DUPEROW",
                        "stream_canonical": "oil",
                        "production_month": MONTH.isoformat(),
                        "volume": str(COLLIDED_OIL),
                        "unit": "bbl",
                    }
                ),
                manifest,
                manifest,
            ),
        )
    db.commit()
    return db


def series(client: TestClient) -> dict:
    return client.get(f"/v1/wells/{MULTI_POOL_API10}/production", params={"stream": "oil"}).json()


def test_the_colliding_month_is_not_served_as_the_wells_production(multi_pool, api_client):
    body = series(api_client)
    index = body["data"]["series"]["pm"].index("2026-01")

    assert body["data"]["series"]["oil_bbl"][index] is None
    assert body["data"]["series"]["oil_bbl"][0] == "120.000"


def test_the_withdrawn_point_is_not_labelled_a_reported_zero(multi_pool, api_client):
    """`reported_zero` asserts the regulator reported a zero. It did not."""
    body = series(api_client)
    index = body["data"]["series"]["pm"].index("2026-01")

    assert body["data"]["series"]["oil_bbl_null_semantics"][index] == "multi_pool_pending"


def test_the_response_discloses_the_pool_filings_it_is_holding_back(multi_pool, api_client):
    warnings = series(api_client)["meta"]["warnings"]

    pending = [w for w in warnings if w["code"] == "multi_pool_pending"]
    assert pending, "the well serves a hole in its series with no explanation"
    detail = pending[0]["detail"]
    assert "2026-01" in detail
    assert str(COLLIDED_OIL) in detail
    assert COLLISION_RULE in detail
    assert pending[0]["pointer"] == "/series/oil_bbl"


def test_a_well_with_one_pool_is_unaffected(multi_pool, api_client):
    body = series(api_client)

    assert body["data"]["series"]["oil_bbl"][0] == "120.000"
    assert body["data"]["series"]["oil_bbl_null_semantics"][0] == "reported"
    assert body["data"]["granularity"] == "well_observed"
