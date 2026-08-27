"""`/healthz`, the service index, and `/v1/health` — the stranger's entry point (S1)."""

from __future__ import annotations

from datetime import UTC, datetime

import psycopg
from fastapi.testclient import TestClient

from glasswell.api.examples import EXAMPLE_MANIFEST_ID
from glasswell.seed.conformance_c115b import C115B_SOURCES
from glasswell.seed.conformance_land import LAND_SOURCES
from glasswell.seed.conformance_tx import TX_SOURCES
from glasswell.seed.reference import SOURCES
from tests.support.seed import seed_manifest

# The shared test template also carries tx_pdq_dsv; its other sources are seed-registry members.
SOURCE_COUNT = len(
    {
        source["source_id"]
        for registry in (SOURCES, C115B_SOURCES, LAND_SOURCES, TX_SOURCES)
        for source in registry
    }
    | {"tx_pdq_dsv"}
)


def test_healthz_is_cheap_and_unenveloped(client: TestClient) -> None:
    """SB-06 §1.3's liveness probe; it must not touch the database."""
    response = client.get("/healthz")

    assert response.json() == {"ok": True}
    assert "meta" not in response.json()


def test_the_index_names_the_version_and_the_resources(client: TestClient) -> None:
    body = client.get("/v1").json()

    assert body["data"]["api_version"] == "v1"
    assert body["links"]["wells"] == "/v1/wells"
    assert body["links"]["well_neighbors"] == "/v1/wells/{api10}/neighbors"
    assert body["links"]["explain"].startswith("/v1/explain")
    assert body["links"]["glossary"] == "/v1/glossary"


def test_the_index_publishes_the_vintages(client: TestClient) -> None:
    published = client.get("/v1").json()["data"]["published_vintages"]

    assert [item["source_id"] for item in published] == ["nd_mpr_xlsx"]
    assert published[0]["vintage_date"] == "2026-08-01"
    assert published[0]["rows_appended"] == 19


def test_the_index_carries_the_error_registry(client: TestClient) -> None:
    """Every `type` URI a client can meet is discoverable from the entry point."""
    codes = client.get("/v1").json()["data"]["error_codes"]

    assert {"code", "status", "title", "type"} <= set(codes[0])


def test_health_reports_freshness_per_source(client: TestClient) -> None:
    """Smoke check 2 asserts the key is present; the permitted degradation keeps it."""
    body = client.get("/v1/health").json()

    freshness = body["meta"]["source_freshness"]
    assert len(freshness) == SOURCE_COUNT
    assert freshness["nd_mpr_xlsx"]["retrieval_vintage"] == "2026-08-01"
    assert freshness["nd_mpr_xlsx"]["state"] == "current"
    assert freshness["nd_gis_spacing_units"]["state"] == "pending"


def test_health_states_whether_it_is_degraded(client: TestClient) -> None:
    data = client.get("/v1/health").json()["data"]

    assert data["state"] in {"ok", "degraded"}
    assert data["stores"]["postgres"] == "ok"
    assert data["sources"][0]["last_manifest_id"] in {EXAMPLE_MANIFEST_ID, None}


def test_a_source_that_has_never_been_fetched_is_pending_and_named(client: TestClient) -> None:
    """Controller ruling: registration is not a promise that a pull has happened, so a source
    with no manifest is `pending` rather than degraded — named in its own list, because the
    complaint the old behaviour answered was about hiding it, not about the word."""
    data = client.get("/v1/health").json()["data"]

    assert data["state"] == "ok"
    assert data["degraded_sources"] == []
    assert "nd_gis_spacing_units" in data["pending_sources"]
    assert all(
        source["state"] == "pending"
        for source in data["sources"]
        if source["source_id"] in data["pending_sources"]
    )


def test_the_nm_sources_are_pending_until_one_is_fetched(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """Wave 2 registers nine NM sources on every deployment and promotes them at a later one.
    Nine permanently degraded sources would make the signal useless exactly while it matters."""
    before = client.get("/v1/health").json()["data"]

    assert {source for source in before["pending_sources"] if source.startswith("nm_ocd_")}
    assert before["state"] == "ok"

    seed_manifest(
        seeded,
        sha256="a" * 64,
        source_id="nm_ocd_wcproduction",
        source_key="wcproduction.zip",
        fetched_at=datetime.now(UTC),
    )
    seeded.commit()
    after = client.get("/v1/health").json()["data"]
    states = {source["source_id"]: source["state"] for source in after["sources"]}

    assert states["nm_ocd_wcproduction"] == "current"
    assert "nm_ocd_wcproduction" not in after["pending_sources"]
    assert after["state"] == "ok"
