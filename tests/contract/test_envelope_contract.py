"""SB-04 §2.2: one envelope, everywhere, with no second representation of lineage."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from glasswell.api.examples import EXAMPLE_API10
from glasswell.lineage.envelope import ENVELOPE_META_KEYS

COLLECTIONS = ("/v1/wells", "/v1/manifests", "/v1/glossary")
ENVELOPED = (
    "/v1",
    "/v1/health",
    "/v1/wells",
    f"/v1/wells/{EXAMPLE_API10}",
    f"/v1/wells/{EXAMPLE_API10}/production",
    "/v1/glossary",
)


@pytest.mark.parametrize("path", ENVELOPED)
def test_every_enveloped_response_is_data_meta_links(client: TestClient, path: str) -> None:
    response = client.get(path)

    assert response.status_code == 200
    assert set(response.json()) == {"data", "meta", "links"}


@pytest.mark.parametrize("path", ENVELOPED)
def test_meta_carries_the_declared_keys(client: TestClient, path: str) -> None:
    meta = client.get(path).json()["meta"]

    assert set(meta) == set(ENVELOPE_META_KEYS)
    assert meta["request_id"]
    assert set(meta["as_of"]) == {"requested", "resolved"}


@pytest.mark.parametrize("path", ENVELOPED)
def test_no_second_lineage_representation(client: TestClient, path: str) -> None:
    """SB-04 §10 E-01 removed meta.derivations and meta.units; B11 reversed C4."""
    meta = client.get(path).json()["meta"]

    assert "derivations" not in meta
    assert "units" not in meta


@pytest.mark.parametrize("path", COLLECTIONS)
def test_collections_carry_a_cursor_key_that_is_null_at_the_end(
    client: TestClient, path: str
) -> None:
    body = client.get(path, params={"limit": 200}).json()

    assert isinstance(body["data"], list)
    assert body["meta"]["next_cursor"] is None
    assert body["links"]["next"] is None


def test_a_short_page_advertises_the_next_cursor(client: TestClient) -> None:
    body = client.get("/v1/wells", params={"limit": 2}).json()

    assert len(body["data"]) == 2
    assert body["meta"]["next_cursor"]
    assert body["links"]["next"].startswith("/v1/wells?")


def test_links_explain_is_prebuilt_where_the_response_carries_handles(
    client: TestClient,
) -> None:
    body = client.get(f"/v1/wells/{EXAMPLE_API10}/production").json()

    assert body["links"]["explain"].startswith("/v1/explain?h=")
    assert "depth=full" in body["links"]["explain"]


def test_request_id_is_echoed_in_the_response_header(client: TestClient) -> None:
    response = client.get("/v1/health")

    assert response.headers["x-request-id"] == response.json()["meta"]["request_id"]


def test_healthz_is_outside_the_envelope_and_outside_auth(client: TestClient) -> None:
    unauthenticated = TestClient(client.app)

    response = unauthenticated.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
