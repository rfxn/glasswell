"""How the SPA is put on the wire: compression and cache class (SB-05 §1.3, §1.4).

The bundle shipped uncompressed with no `Cache-Control` at all, so the 319 KB gzipped
figure recorded in phase-6-status.md was never delivered and every repeat visit
revalidated 1.14 MB.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from glasswell.api import create_app
from glasswell.api.deps import WEB_ROOT_ENV

BUNDLE = "index-CKMgwuvy.js"


@pytest.fixture
def web_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / BUNDLE).write_text("const glasswell = 'x';\n" * 4000, encoding="utf-8")
    (assets / "index-X43KWXhA.css").write_text(".gw-card { color: #e6edf3 }\n" * 2000)
    (tmp_path / "index.html").write_text("<!doctype html><title>glasswell</title>")
    monkeypatch.setenv(WEB_ROOT_ENV, str(tmp_path))
    return tmp_path


@pytest.fixture
def web_client(web_root: Path) -> Iterator[TestClient]:
    with TestClient(create_app()) as client:
        yield client


def test_the_bundle_is_compressed_on_the_wire(web_client: TestClient, web_root: Path) -> None:
    source = (web_root / "assets" / BUNDLE).read_text(encoding="utf-8")

    response = web_client.get(f"/assets/{BUNDLE}", headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200
    assert response.headers["content-encoding"] == "gzip"
    # Decoded round trip: the frame is complete, not a truncated stream.
    assert response.text == source


def test_a_client_that_cannot_decompress_still_gets_the_bundle(web_client: TestClient) -> None:
    response = web_client.get(f"/assets/{BUNDLE}", headers={"Accept-Encoding": "identity"})

    assert response.status_code == 200
    assert "content-encoding" not in response.headers


def test_hashed_assets_are_immutable_for_a_year(web_client: TestClient) -> None:
    """The filename carries the content hash, so a revalidation can never be necessary."""
    response = web_client.get(f"/assets/{BUNDLE}")

    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_the_shell_is_never_cached_without_revalidation(web_client: TestClient) -> None:
    """index.html names the hashed assets; a stale one pins the reader to an old build."""
    for path in ("/", "/index.html"):
        response = web_client.get(path)

        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-cache"


def test_the_api_keeps_its_own_cache_semantics(web_client: TestClient) -> None:
    """Only the static mount gets a cache class; a data response must not be frozen."""
    response = web_client.get("/healthz")

    assert response.status_code == 200
    assert "cache-control" not in response.headers


def test_a_tiny_response_is_not_worth_a_gzip_frame(web_client: TestClient) -> None:
    response = web_client.get("/healthz", headers={"Accept-Encoding": "gzip"})

    assert "content-encoding" not in response.headers


def test_vector_tiles_are_left_to_the_tile_path(web_client: TestClient) -> None:
    """Level-9 gzip per tile request is a map-performance decision, not a transport one."""
    app = create_app()
    gzip_layer = next(
        middleware for middleware in app.user_middleware if "GZip" in str(middleware.cls)
    )

    excluded = gzip_layer.kwargs["exclude_content_types"]
    assert "application/x-protobuf" in excluded
    assert "application/vnd.mapbox-vector-tile" in excluded
