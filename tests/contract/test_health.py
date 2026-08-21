"""`/healthz`, the service index, and `/v1/health` — the stranger's entry point (S1)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from glasswell.api.examples import EXAMPLE_MANIFEST_ID

# Four ND, nine NM and three TX sources from seed_all, plus the three the shared test
# template carries — nd_mpr_xlsx and nm_ocd_wcproduction are in both, so only tx_pdq_dsv
# adds to the total.
SOURCE_COUNT = 17


def test_healthz_is_cheap_and_unenveloped(client: TestClient) -> None:
    """SB-06 §1.3's liveness probe; it must not touch the database."""
    response = client.get("/healthz")

    assert response.json() == {"ok": True}
    assert "meta" not in response.json()


def test_the_index_names_the_version_and_the_resources(client: TestClient) -> None:
    body = client.get("/v1").json()

    assert body["data"]["api_version"] == "v1"
    assert body["links"]["wells"] == "/v1/wells"
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
    assert freshness["nd_gis_spacing_units"]["state"] == "never_fetched"


def test_health_states_whether_it_is_degraded(client: TestClient) -> None:
    data = client.get("/v1/health").json()["data"]

    assert data["state"] in {"ok", "degraded"}
    assert data["stores"]["postgres"] == "ok"
    assert data["sources"][0]["last_manifest_id"] in {EXAMPLE_MANIFEST_ID, None}


def test_health_is_degraded_when_a_source_has_never_been_fetched(client: TestClient) -> None:
    data = client.get("/v1/health").json()["data"]

    assert data["state"] == "degraded"
    assert "nd_gis_spacing_units" in data["degraded_sources"]
