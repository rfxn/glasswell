"""The martin proxy (C11/C12): one origin, and 204 means healthy-but-empty (B9)."""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from glasswell.api.errors import TYPE_BASE
from glasswell.api.routers.tiles import PUBLISHED_LAYERS
from glasswell.marts.tiles import TILE_LAYERS
from tests.contract.conftest import TILE_BODY


def test_a_tile_is_streamed_back_unchanged(client: TestClient) -> None:
    response = client.get("/v1/tiles/nd_laterals/8/54/89.pbf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/x-protobuf"
    assert response.content == TILE_BODY


def test_an_empty_tile_passes_204_through(client: TestClient) -> None:
    """204 is an outcome, not an error: the basin does not cover every tile."""
    response = client.get("/v1/tiles/nd_laterals/0/0/0.pbf")

    assert response.status_code == 204
    assert response.content == b""


def test_an_upstream_failure_is_reported_as_such(client: TestClient) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="no such layer")

    client.app.state.tile_client = httpx.Client(
        transport=httpx.MockTransport(refuse), base_url="http://martin.invalid"
    )

    response = client.get("/v1/tiles/nd_laterals/8/54/89.pbf")

    assert response.status_code == 502
    assert response.json()["type"] == f"{TYPE_BASE}/upstream_tile_error"


def test_a_staging_layer_is_refused_before_it_reaches_martin(client: TestClient) -> None:
    """M-1: martin auto-publishes staging, so the proxy is where "staging never serves" holds."""
    response = client.get("/v1/tiles/nd_gis_wells/8/54/89.pbf")

    assert response.status_code == 404
    assert response.json()["type"] == f"{TYPE_BASE}/not_found"
    assert response.content != TILE_BODY


def test_a_canonical_relation_is_refused_too(client: TestClient) -> None:
    """Only the mart layers are published; canonical is not a tile surface either."""
    assert client.get("/v1/tiles/well_spatial/8/54/89.pbf").status_code == 404


def test_the_allowlist_is_exactly_the_published_mart_layers() -> None:
    assert frozenset(layer.name for layer in TILE_LAYERS) == PUBLISHED_LAYERS


def test_an_unreachable_martin_is_reported_as_such(client: TestClient) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client.app.state.tile_client = httpx.Client(
        transport=httpx.MockTransport(refuse), base_url="http://martin.invalid"
    )

    response = client.get("/v1/tiles/nd_laterals/8/54/89.pbf")

    assert response.status_code == 502


def test_the_layer_name_is_validated_before_it_reaches_martin(client: TestClient) -> None:
    response = client.get("/v1/tiles/..%2fetc/8/54/89.pbf")

    assert response.status_code in {404, 422}


def test_tiles_are_behind_the_owner_key(client: TestClient) -> None:
    anonymous = TestClient(client.app)

    assert anonymous.get("/v1/tiles/nd_laterals/8/54/89.pbf").status_code == 403
