"""The martin proxy (C11/C12): one origin, and 204 means healthy-but-empty (B9)."""

from __future__ import annotations

import gzip

import httpx
import pytest
from fastapi.testclient import TestClient

from glasswell.api.errors import TYPE_BASE
from glasswell.api.routers.tiles import TILE_CACHE_CONTROL, UPSTREAM_ENCODINGS
from tests.contract.conftest import TILE_BODY

MARTIN_ETAG = '"6CAAeWACcJ2MefYf8idX4w"'
TILE_PATH = "/v1/tiles/nd_laterals/8/54/89.pbf"


class Martin:
    """A stub with the behaviour the live server has: an ETag, and a 304 on a match."""

    def __init__(self, *, encoding: str | None = None, body: bytes = TILE_BODY) -> None:
        self.encoding = encoding
        self.body = body
        self.seen: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        if request.headers.get("if-none-match") == MARTIN_ETAG:
            return httpx.Response(304, headers={"etag": MARTIN_ETAG})
        headers = {"content-type": "application/x-protobuf", "etag": MARTIN_ETAG}
        if self.encoding:
            headers["content-encoding"] = self.encoding
        return httpx.Response(200, content=iter([self.body]), headers=headers)

    @property
    def last(self) -> httpx.Request:
        return self.seen[-1]


@pytest.fixture
def martin(client: TestClient) -> Martin:
    stub = Martin()
    client.app.state.tile_client = httpx.Client(
        transport=httpx.MockTransport(stub), base_url="http://martin.invalid"
    )
    return stub


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


def test_a_tile_is_revalidatable_rather_than_uncacheable(client: TestClient, martin: Martin):
    """5,903 tile requests over 1,050 distinct tiles in 24 h, because nothing said cache."""
    response = client.get(TILE_PATH)

    assert response.status_code == 200
    assert response.headers["cache-control"] == TILE_CACHE_CONTROL
    assert response.headers["etag"] == MARTIN_ETAG
    assert "accept-encoding" in response.headers["vary"].lower()


def test_a_conditional_request_costs_a_304_and_no_body(client: TestClient, martin: Martin):
    response = client.get(TILE_PATH, headers={"If-None-Match": MARTIN_ETAG})

    assert response.status_code == 304
    assert response.content == b""
    assert response.headers["etag"] == MARTIN_ETAG
    assert response.headers["cache-control"] == TILE_CACHE_CONTROL
    assert martin.last.headers["if-none-match"] == MARTIN_ETAG


def test_an_empty_tile_is_cacheable_too(client: TestClient) -> None:
    """Without a cache class the basin's empty margin is re-fetched on every pan."""
    response = client.get("/v1/tiles/nd_laterals/0/0/0.pbf")

    assert response.status_code == 204
    assert response.headers["cache-control"] == TILE_CACHE_CONTROL


def test_the_proxy_never_asks_martin_for_an_encoding_it_measured_as_slow(
    client: TestClient, martin: Martin
) -> None:
    """martin gzips a 2 MB tile in ~135 ms and zstds it in ~18 ms; neither is free by default."""
    client.get(TILE_PATH, headers={"Accept-Encoding": "gzip, deflate, br"})

    assert martin.last.headers["accept-encoding"] == "identity"


def test_the_proxy_asks_for_the_encoding_the_caller_and_martin_both_support(
    client: TestClient, martin: Martin
) -> None:
    client.get(TILE_PATH, headers={"Accept-Encoding": "gzip, deflate, br, zstd"})

    assert martin.last.headers["accept-encoding"] == ", ".join(UPSTREAM_ENCODINGS)


def test_a_compressed_upstream_body_reaches_the_caller_still_compressed(
    client: TestClient,
) -> None:
    """Decoding it here would spend the CPU martin already spent and ship the big form."""
    compressed = gzip.compress(TILE_BODY)
    stub = Martin(encoding="gzip", body=compressed)
    client.app.state.tile_client = httpx.Client(
        transport=httpx.MockTransport(stub), base_url="http://martin.invalid"
    )

    with client.stream("GET", TILE_PATH, headers={"Accept-Encoding": "gzip"}) as response:
        raw = b"".join(response.iter_raw())

    assert response.status_code == 200
    assert response.headers["content-encoding"] == "gzip"
    assert raw == compressed
    assert gzip.decompress(raw) == TILE_BODY
