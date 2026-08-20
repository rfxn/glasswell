"""The basemap archive is read with HTTP range requests, so the mount has to serve them.

A server that answers a ranged GET with a whole 200 turns every tile read into a download
of the entire archive. The client refuses to use the archive in that case (`map.ts`), so
this is the check that keeps the two halves of that contract honest.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from glasswell.api import BASEMAP_CACHE, SHELL_CACHE, create_app
from glasswell.api.deps import ALLOW_ANON_ENV, BASEMAP_ROOT_ENV

pytestmark = pytest.mark.unit

ARCHIVE_BYTES = bytes(range(256)) * 8


@pytest.fixture
def basemap_root(tmp_path, monkeypatch):
    (tmp_path / "basemap.pmtiles").write_bytes(ARCHIVE_BYTES)
    (tmp_path / "manifest.json").write_text(
        json.dumps({"archive": "/basemap/basemap.pmtiles", "labels": False, "vintage": "20260815"})
    )
    monkeypatch.setenv(BASEMAP_ROOT_ENV, str(tmp_path))
    monkeypatch.setenv(ALLOW_ANON_ENV, "1")
    return tmp_path


def test_a_ranged_read_of_the_archive_answers_206(basemap_root):
    with TestClient(create_app()) as client:
        response = client.get("/basemap/basemap.pmtiles", headers={"Range": "bytes=0-15"})
    assert response.status_code == 206
    assert response.content == ARCHIVE_BYTES[:16]
    assert response.headers["content-range"] == f"bytes 0-15/{len(ARCHIVE_BYTES)}"


def test_the_mount_advertises_range_support_on_a_plain_get(basemap_root):
    with TestClient(create_app()) as client:
        response = client.get("/basemap/basemap.pmtiles")
    assert response.status_code == 200
    assert response.headers["accept-ranges"] == "bytes"


def test_the_manifest_is_served_beside_the_archive(basemap_root):
    with TestClient(create_app()) as client:
        response = client.get("/basemap/manifest.json")
    assert response.status_code == 200
    assert response.json()["archive"] == "/basemap/basemap.pmtiles"


def test_the_basemap_needs_no_key(basemap_root, monkeypatch):
    # The archive is public OSM data behind the same origin; requiring the owner key would
    # put a credential on 100+ tile reads for data that is public by definition.
    monkeypatch.delenv(ALLOW_ANON_ENV, raising=False)
    with TestClient(create_app()) as client:
        assert client.get("/basemap/manifest.json").status_code == 200


def test_no_basemap_is_mounted_when_the_directory_is_not_configured(monkeypatch):
    monkeypatch.delenv(BASEMAP_ROOT_ENV, raising=False)
    monkeypatch.setenv(ALLOW_ANON_ENV, "1")
    with TestClient(create_app()) as client:
        assert client.get("/basemap/manifest.json").status_code == 404


def test_the_mount_does_not_shadow_the_api(basemap_root):
    with TestClient(create_app()) as client:
        assert client.get("/healthz").status_code == 200


def test_a_ranged_read_is_cacheable_for_the_life_of_the_vintage(basemap_root):
    """PMTiles reads the archive in hundreds of ranges; with no cache class each pan pays."""
    with TestClient(create_app()) as client:
        response = client.get("/basemap/basemap.pmtiles", headers={"Range": "bytes=0-15"})
    assert response.status_code == 206
    assert response.headers["cache-control"] == BASEMAP_CACHE


def test_the_manifest_is_never_cached_so_a_vintage_swap_is_seen(basemap_root):
    """The manifest is how the client learns the archive changed; caching it hides the swap."""
    with TestClient(create_app()) as client:
        response = client.get("/basemap/manifest.json")
    assert response.headers["cache-control"] == SHELL_CACHE


def test_the_archive_path_cannot_escape_the_basemap_directory(basemap_root, tmp_path):
    (tmp_path.parent / "secret.txt").write_text("not yours")
    with TestClient(create_app()) as client:
        response = client.get("/basemap/../secret.txt")
    assert response.status_code in {403, 404}
