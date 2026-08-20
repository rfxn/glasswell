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

from glasswell.lineage.capture import derive, lineage_session
from glasswell.lineage.ids import parse_handle
from glasswell.lineage.models import InputRef, OutputSpec
from glasswell.lineage.store import PostgresRecorder
from tests.contract.conftest import REPORT_VINTAGE, _insert_production
from tests.support.fakes import FixedClock
from tests.support.seed import FIXTURE_ENV, seed_manifest, seed_well

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
