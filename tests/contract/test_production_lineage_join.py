"""D3: a served point cites the derivation that promoted *that* month, not the last id by sort.

The ND MPR publishes one workbook per month, so each month is its own promote derivation over
its own manifest. A single column-level handle can only be right for one of them.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from glasswell.api.examples import EXAMPLE_API10
from glasswell.lineage.capture import derive, lineage_session
from glasswell.lineage.ids import parse_handle
from glasswell.lineage.models import InputRef, OutputSpec
from glasswell.lineage.store import PostgresRecorder
from tests.contract.conftest import REPORT_VINTAGE, RESTATED_MONTH, _insert_production
from tests.support.fakes import FixedClock
from tests.support.seed import FIXTURE_ENV, seed_manifest, seed_well, seed_well_spatial

MULTI_MONTH_API10 = "3305310469"
MONTHS = (date(2025, 12, 1), date(2026, 1, 1), date(2026, 2, 1))
# The audit's exhibit: sorted()[-1] served the 2026-02 handle for the 2025-12 figure, and
# 2026_02.xlsx holds no 2025-12 row. Fixture shas are chosen so that ordering repeats here.
MONTH_SHA256 = {
    MONTHS[0]: "af976b7de40b3f841be34546938e4b956dc8aadd1ac71d9516742d61c0066906",
    MONTHS[1]: "de97abf0e45bb6325e7d687ae8d4bc1e82d0a22c2a5647c00e53ba623c6af973",
    MONTHS[2]: "0df7c55a85b4eaf67501bc027e7b88149e357013428f5427c47b7666c694d8f4",
}


def _promote_month(connection: psycopg.Connection, month: date, manifest_id: str) -> str:
    """One promote derivation per workbook, exactly as glasswell.ingest.nd_mpr records it."""
    with lineage_session(
        recorder=PostgresRecorder(connection),
        environment=FIXTURE_ENV,
        clock=FixedClock(),
        correlation_id="run_month_join",
    ), derive(
        "canonical.promote",
        output=OutputSpec(
            store="postgres",
            dataset="canonical.production_monthly",
            partition={"month": f"{month:%Y-%m}", "manifest_id": manifest_id},
        ),
        params={"source_key": f"{month:%Y_%m}.xlsx"},
        inputs=[
            InputRef(
                kind="manifest", ref_id=manifest_id, role="primary", as_of_vintage=REPORT_VINTAGE
            )
        ],
    ) as context:
        context.set_output_hash("c3" * 32)
        context.set_rows(1)
    return context.derivation_id


def _promote_spatial(connection: psycopg.Connection, manifest_id: str) -> str:
    """The geometry's own promotion, so the divided point's chain names the layer it read."""
    with lineage_session(
        recorder=PostgresRecorder(connection),
        environment=FIXTURE_ENV,
        clock=FixedClock(),
        correlation_id="run_month_join_spatial",
    ), derive(
        "canonical.promote",
        output=OutputSpec(
            store="postgres",
            dataset="canonical.well_spatial",
            partition={"manifest_id": manifest_id},
        ),
        params={"source_key": "horizontals.zip"},
        inputs=[
            InputRef(
                kind="manifest", ref_id=manifest_id, role="primary", as_of_vintage=REPORT_VINTAGE
            )
        ],
    ) as context:
        context.set_output_hash("c4" * 32)
        context.set_rows(1)
    return context.derivation_id


@pytest.fixture
def month_per_manifest(client: TestClient, db: psycopg.Connection) -> dict[date, str]:
    """Three months, three workbooks, three promote derivations — the production shape."""
    seed_well(db, api10=MULTI_MONTH_API10, well_name="GARFIELD FIU 2-5HSL")
    manifests: dict[date, str] = {}
    for ordinal, month in enumerate(MONTHS):
        manifest_id = seed_manifest(
            db, sha256=MONTH_SHA256[month], source_key=f"{month:%Y_%m}.xlsx"
        )
        derivation_id = _promote_month(db, month, manifest_id)
        _insert_production(
            db,
            api10=MULTI_MONTH_API10,
            production_month=month,
            stream="oil",
            volume=Decimal(1000 * (ordinal + 1)),
            manifest_id=manifest_id,
            derivation_id=derivation_id,
        )
        manifests[month] = manifest_id
    return manifests


def _series(client: TestClient) -> dict:
    return client.get(f"/v1/wells/{MULTI_MONTH_API10}/production", params={"stream": "oil"}).json()


def test_each_month_carries_the_handle_of_its_own_promotion(
    client: TestClient, month_per_manifest: dict[date, str], db: psycopg.Connection
) -> None:
    body = _series(client)
    lineage = body["data"]["_lineage"]

    handles = [lineage[f"series.oil_bbl.{index}"] for index in range(len(MONTHS))]
    assert len({parse_handle(handle).derivation_id for handle in handles}) == len(MONTHS)


def test_the_cited_manifest_is_the_workbook_that_carries_the_month(
    client: TestClient, month_per_manifest: dict[date, str]
) -> None:
    """The property the audit falsified for 83.2% of served numbers."""
    body = _series(client)
    lineage = body["data"]["_lineage"]

    for index, month in enumerate(MONTHS):
        handle = lineage[f"series.oil_bbl.{index}"]
        chain = client.get("/v1/explain", params={"h": handle, "depth": "full"}).json()
        terminals = chain["data"]["chains"][0]["terminals"]
        assert terminals == [month_per_manifest[month]], (
            f"{month:%Y-%m} explains to {terminals}, not to its own {month:%Y_%m}.xlsx"
        )


def test_the_handle_selector_names_the_month_it_addresses(
    client: TestClient, month_per_manifest: dict[date, str]
) -> None:
    lineage = _series(client)["data"]["_lineage"]

    selector = parse_handle(lineage["series.oil_bbl.0"]).selector
    assert f"pm={MONTHS[0]:%Y-%m}" in str(selector)
    assert f"api10={MULTI_MONTH_API10}" in str(selector)


def test_the_column_keeps_one_handle_when_one_derivation_produced_it(
    client: TestClient, db: psycopg.Connection
) -> None:
    """SB-07 §9.1(b)'s compact form is kept where it is true: one derivation, one entry."""
    manifest = seed_manifest(db, sha256="ab" * 32, source_key="2026_04.xlsx")
    derivation = _promote_month(db, date(2026, 4, 1), manifest)
    seed_well(db, api10="3305399999")
    for month in (date(2026, 4, 1), date(2026, 5, 1)):
        _insert_production(
            db,
            api10="3305399999",
            production_month=month,
            stream="oil",
            volume=Decimal("10"),
            manifest_id=manifest,
            derivation_id=derivation,
        )

    lineage = client.get("/v1/wells/3305399999/production").json()["data"]["_lineage"]

    assert lineage["series.oil_bbl"].startswith(derivation)
    assert "series.oil_bbl.0" not in lineage


def test_the_series_warns_that_its_points_span_derivations(
    client: TestClient, month_per_manifest: dict[date, str]
) -> None:
    warnings = _series(client)["meta"]["warnings"]

    spans = [warning for warning in warnings if warning["code"] == "series_spans_derivations"]
    assert [warning["pointer"] for warning in spans] == ["/series/oil_bbl"]


def test_the_normalised_arm_serves_the_multi_derivation_shape_and_every_point_resolves(
    client: TestClient, month_per_manifest: dict[date, str], db: psycopg.Connection
) -> None:
    """The shape 99.5 % of North Dakota has -- one promotion per month -- under the arm that
    divides it. The column's handle is the response derivation's, each point's handle names
    that derivation's own evidence, and the chain behind any of them reaches the month's own
    workbook and the geometry it was divided by."""
    geometry_manifest = seed_manifest(db, sha256="b7" * 32, source_key="horizontals.zip")
    seed_well_spatial(
        db,
        api10=MULTI_MONTH_API10,
        manifest_id=geometry_manifest,
        derivation_id=_promote_spatial(db, geometry_manifest),
    )

    response = client.get(
        f"/v1/wells/{MULTI_MONTH_API10}/production",
        params={"stream": "oil", "normalization": "per_lateral_ft"},
    )

    assert response.status_code == 200, response.text
    lineage = response.json()["data"]["_lineage"]
    assert "series.oil_bbl" in lineage
    assert "series.oil_bbl.0" not in lineage
    for month in MONTHS:
        point = f"{lineage['series.oil_bbl']}&pm={month:%Y-%m}"
        explained = client.get("/v1/explain", params={"h": point, "depth": "full"})
        assert explained.status_code == 200, explained.text
        chain = explained.json()["data"]["chains"][0]
        assert month_per_manifest[month] in chain["terminals"]
        datasets = {(node.get("output") or {}).get("dataset") for node in chain["nodes"]}
        assert {
            "api.well_production",
            "canonical.production_monthly",
            "canonical.well_spatial",
        } <= datasets


NOT_MEASURED = {"withheld", "no_report", "multi_pool_pending"}


def _drawn_points(data: dict, column: str) -> list[tuple[str, str]]:
    """Every point the chart draws a ⌾ on, with the handle it composes — `chart/series.ts`."""
    lineage = data["_lineage"]
    series = data["series"]
    drawn: list[tuple[str, str]] = []
    for index, month in enumerate(series["pm"]):
        if series[column][index] is None:
            continue
        if series[f"{column}_null_semantics"][index] in NOT_MEASURED:
            continue
        handle = lineage.get(f"series.{column}.{index}") or lineage.get(f"series.{column}")
        assert handle is not None, f"{column} {month} is drawn with no handle to compose"
        drawn.append((month, handle if "&pm=" in handle else f"{handle}&pm={month}"))
    return drawn


@pytest.mark.contract
def test_every_drawn_point_of_the_default_well_resolves(client: TestClient) -> None:
    """R8's second rule on the well every gate photographs: a figure that cannot be explained
    is not served as a figure. The exhibit is the fixture's own restatement — one month filed
    twice under one promotion, which `api10&col&pm` identifies two rows of."""
    data = client.get(f"/v1/wells/{EXAMPLE_API10}/production").json()["data"]

    checked = 0
    for column in ("oil_bbl", "gas_mcf", "water_bbl"):
        for month, handle in _drawn_points(data, column):
            answer = client.get("/v1/explain", params={"h": handle, "depth": "1"})
            assert answer.status_code == 200, f"{column} {month}: {answer.text}"
            checked += 1
    assert checked > 0


@pytest.mark.contract
def test_a_month_filed_twice_names_the_vintage_it_was_read_at(client: TestClient) -> None:
    """The selector's remaining key: `canonical.production_monthly` is keyed by report vintage
    too, so a restated month is two rows under one derivation and `pm` alone under-specifies
    it."""
    data = client.get(f"/v1/wells/{EXAMPLE_API10}/production").json()["data"]
    at = data["series"]["pm"].index(f"{RESTATED_MONTH:%Y-%m}")
    handle = data["_lineage"][f"series.oil_bbl.{at}"]

    assert f"rv={data['series']['oil_bbl_report_vintage'][at]}" in handle
    assert client.get("/v1/explain", params={"h": handle, "depth": "1"}).status_code == 200


HELD_AND_REFILED_API10 = "3305310477"
HELD_MONTH = date(2026, 2, 1)
DRAWN_MONTH = date(2026, 1, 1)
COLLISION_RULE = "cr_nd_api_identity_1"


@pytest.fixture
def held_and_refiled(client: TestClient, db: psycopg.Connection) -> str:
    """One month that is both filed twice and still colliding — the two sets are not disjoint.

    `refiled` is read from `canonical.production_monthly` and `held` from
    `lineage.quarantine_rows`; nothing joins them, so a month can be in both.
    """
    seed_well(db, api10=HELD_AND_REFILED_API10, well_name="ND STATE 9-4H")
    manifest = seed_manifest(db, sha256="e1" * 32, source_key="2026_02.xlsx")
    derivation = _promote_month(db, HELD_MONTH, manifest)
    _insert_production(
        db,
        api10=HELD_AND_REFILED_API10,
        production_month=DRAWN_MONTH,
        stream="oil",
        volume=Decimal("900"),
        manifest_id=manifest,
        derivation_id=derivation,
    )
    for vintage, volume in ((date(2026, 7, 1), Decimal("2500")), (REPORT_VINTAGE, Decimal("2750"))):
        _insert_production(
            db,
            api10=HELD_AND_REFILED_API10,
            production_month=HELD_MONTH,
            stream="oil",
            volume=volume,
            manifest_id=manifest,
            derivation_id=derivation,
            report_vintage=vintage,
        )
    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.quarantine_rows (quarantine_id, row_fingerprint, source_id,"
            " staging_table, stage, reason_code, rule_id, row_payload, first_seen_at,"
            " first_seen_manifest_id, last_seen_at, last_seen_manifest_id)"
            " values ('qtn_held_refiled', 'fp_held_refiled', 'nd_mpr_xlsx', 'staging.nd_mpr_oil',"
            " 'conform', 'key_collision', %s, %s, now(), %s, now(), %s)",
            (
                COLLISION_RULE,
                Jsonb(
                    {
                        "api10": HELD_AND_REFILED_API10,
                        "pool": "DUPEROW",
                        "stream_canonical": "oil",
                        "production_month": HELD_MONTH.isoformat(),
                        "volume": "3585.000",
                        "unit": "bbl",
                    }
                ),
                manifest,
                manifest,
            ),
        )
    db.commit()
    return HELD_AND_REFILED_API10


def _held_index(data: dict) -> int:
    return data["series"]["pm"].index(f"{HELD_MONTH:%Y-%m}")


@pytest.mark.contract
def test_a_withheld_month_that_was_also_filed_twice_is_served_no_handle(
    client: TestClient, held_and_refiled: str
) -> None:
    """R8 read backwards: papers for a number the response did not serve.

    `point_handles` guards on `held`; `point_overrides` is the same decision on the other
    arm and has to make it the same way, or `_lineage` offers a chain for a null point to
    every consumer that is not the browser.
    """
    data = client.get(f"/v1/wells/{held_and_refiled}/production", params={"stream": "oil"}).json()[
        "data"
    ]
    index = _held_index(data)

    assert data["series"]["oil_bbl"][index] is None
    assert data["series"]["oil_bbl_null_semantics"][index] == "multi_pool_pending"
    assert f"series.oil_bbl.{index}" not in data["_lineage"]


@pytest.mark.contract
def test_the_column_handle_still_stands_when_the_only_refiled_month_is_held(
    client: TestClient, held_and_refiled: str
) -> None:
    """Dropping the override must not drop the column: the drawn month still explains."""
    data = client.get(f"/v1/wells/{held_and_refiled}/production", params={"stream": "oil"}).json()[
        "data"
    ]
    handle = data["_lineage"]["series.oil_bbl"]
    at = data["series"]["pm"].index(f"{DRAWN_MONTH:%Y-%m}")

    assert data["series"]["oil_bbl"][at] is not None
    point = f"{handle}&pm={DRAWN_MONTH:%Y-%m}"
    assert client.get("/v1/explain", params={"h": point, "depth": "1"}).status_code == 200
