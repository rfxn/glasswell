"""What the API says about a well that filed in two pools, now that both pools are rows.

D1's interim guard withdrew the point. The structural fix serves it — but DIR-3 and R6 mean a
summed figure has to say it is summed, name the rule that legislated the sum, resolve to a
derivation taken over the pool rows, and offer the breakdown. A naked sum would be the same
defect wearing a better number.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from glasswell.api.routers.production import ROLLUP_RULE
from glasswell.ingest import nd_mpr
from glasswell.ingest.base import open_ingest_run
from glasswell.seed import seed_all
from tests.support.mpr_workbook import filing, write_workbook
from tests.support.seed import seed_well

MONTH = datetime(2026, 1, 1)
MULTI_POOL = "3305302532"
SINGLE_POOL = "3305310451"


def client_for(path: Path) -> httpx.Client:
    payload = path.read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=payload,
            headers={
                "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "etag": '"pool-serving"',
                "last-modified": "Thu, 14 May 2026 13:12:00 GMT",
            },
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def wells(db, raw_root, lineage_env, tmp_path) -> None:
    seed_all(db)
    seed_well(db, api10=MULTI_POOL, well_name="ND STATE 6-16")
    seed_well(db, api10=SINGLE_POOL, well_name="GARFIELD FIU 2-5HSL")
    db.commit()
    path = write_workbook(
        tmp_path / "2026_01.xlsx",
        [
            filing(api14=f"{MULTI_POOL}0000", month=MONTH, pool="BIRDBEAR", oil=0, water=0,
                   gas=0, days=0),
            filing(api14=f"{MULTI_POOL}0000", month=MONTH, pool="DUPEROW", oil=3585, water=901,
                   gas=1446, days=31),
            filing(api14=f"{SINGLE_POOL}0000", month=MONTH, pool="BAKKEN", oil=70965,
                   water=12635, gas=58925, days=30),
        ],
    )
    with open_ingest_run(
        db, source_id=nd_mpr.SOURCE_ID, raw_root=raw_root, environment=lineage_env
    ) as run, client_for(path) as client:
        nd_mpr.ingest_month(run, year=2026, month=1, client=client)
    db.commit()


def series(client: TestClient, api10: str) -> dict:
    return client.get(f"/v1/wells/{api10}/production", params={"stream": "oil"}).json()


def test_the_well_serves_what_the_regulator_filed_not_the_first_pool_by_ordinal(
    wells, api_client
):
    body = series(api_client, MULTI_POOL)

    assert body["data"]["series"]["oil_bbl"] == ["3585.000"]
    assert body["data"]["series"]["oil_bbl_null_semantics"] == ["reported"]


def test_the_summed_point_says_that_it_is_a_sum(wells, api_client):
    body = series(api_client, MULTI_POOL)

    assert body["data"]["series"]["oil_bbl_aggregation"] == ["sum_over_pools"]
    assert body["data"]["reporting_level"] == "well_completion_pool"
    assert body["data"]["granularity"] == "well_observed"


def test_the_response_names_the_rule_that_legislated_the_sum(wells, api_client):
    body = series(api_client, MULTI_POOL)

    aggregated = [w for w in body["meta"]["warnings"] if w["code"] == "pools_aggregated"]
    assert aggregated, "a summed figure is served with no disclosure at all"
    assert ROLLUP_RULE in aggregated[0]["detail"]
    assert "2026-01" in aggregated[0]["detail"]
    assert aggregated[0]["pointer"] == "/series/oil_bbl"


def test_the_disclosure_links_resolve(wells, api_client):
    links = series(api_client, MULTI_POOL)["links"]

    assert links["pools"] == f"/v1/wells/{MULTI_POOL}/production/pools"
    rule = api_client.get(links["aggregation_rule"])
    assert rule.status_code == 200
    assert rule.json()["data"]["rule_id"] == ROLLUP_RULE


def test_the_served_number_explains_to_a_derivation_over_the_pool_rows(wells, api_client):
    """R6/R7: never a naked sum — the handle is an aggregation, and it resolves."""
    body = series(api_client, MULTI_POOL)
    handle = body["data"]["_lineage"]["series.oil_bbl"]

    explained = api_client.get("/v1/explain", params={"h": handle, "depth": "full"})
    assert explained.status_code == 200
    chain = explained.json()["data"]["chains"][0]
    operations = [node.get("operation") for node in chain["nodes"]]
    assert operations.count("canonical.promote") == 2
    assert any(node["type"] == "manifest" for node in chain["nodes"])


def test_the_multi_pool_point_is_no_longer_withdrawn(wells, api_client):
    body = series(api_client, MULTI_POOL)

    assert "multi_pool_pending" not in body["data"]["series"]["oil_bbl_null_semantics"]
    assert [w for w in body["meta"]["warnings"] if w["code"] == "multi_pool_pending"] == []


def test_a_single_pool_well_is_not_dressed_up_as_an_aggregate(wells, api_client):
    body = series(api_client, SINGLE_POOL)

    assert body["data"]["series"]["oil_bbl"] == ["70965.000"]
    assert body["data"]["series"]["oil_bbl_aggregation"] == [None]
    assert body["data"]["reporting_level"] == "well"
    assert "pools" not in body["links"] or body["links"]["pools"] is None


def test_the_breakdown_serves_one_series_per_pool(wells, api_client):
    body = api_client.get(f"/v1/wells/{MULTI_POOL}/production/pools").json()
    pools = body["data"]["pools"]

    assert [pool["well_completion_pool"] for pool in pools] == ["BIRDBEAR", "DUPEROW"]
    assert [pool["entity_key"] for pool in pools] == [
        f"{MULTI_POOL}:BIRDBEAR",
        f"{MULTI_POOL}:DUPEROW",
    ]
    assert pools[0]["series"]["oil_bbl"] == ["0.000"]
    assert pools[1]["series"]["oil_bbl"] == ["3585.000"]


def test_every_pool_series_carries_its_own_handle(wells, api_client):
    body = api_client.get(f"/v1/wells/{MULTI_POOL}/production/pools").json()

    lineage = body["data"]["_lineage"]
    assert "pools.0.series.oil_bbl" in lineage
    assert "pools.1.series.oil_bbl" in lineage
    assert body["data"]["reporting_level"] == "well_completion_pool"


def test_the_pool_sum_reconciles_with_the_well_figure(wells, api_client):
    pools = api_client.get(f"/v1/wells/{MULTI_POOL}/production/pools").json()["data"]["pools"]
    well = series(api_client, MULTI_POOL)["data"]["series"]["oil_bbl"][0]

    total = sum(float(pool["series"]["oil_bbl"][0]) for pool in pools)
    assert f"{total:.3f}" == well


def test_a_single_pool_well_has_no_breakdown_to_give(wells, api_client):
    body = api_client.get(f"/v1/wells/{SINGLE_POOL}/production/pools").json()

    assert body["data"]["pools"] == []


def test_the_breakdown_refuses_a_well_that_does_not_exist(wells, api_client):
    assert api_client.get("/v1/wells/3300000000/production/pools").status_code == 404


def test_pool_rollup_rule_is_the_one_the_promotion_used(wells, api_client):
    """One id, in three places: the router's pin, the promotion, and the served registry."""
    assert ROLLUP_RULE == nd_mpr.ROLLUP_RULE
    assert api_client.get(f"/v1/conformance/{ROLLUP_RULE}").status_code == 200
