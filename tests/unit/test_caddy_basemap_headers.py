"""Caddy serves `/basemap/*` itself, so for those bytes the edge *is* the origin.

That means the response policy is written twice — once in `glasswell.api.security`, once in
`infra/caddy/Caddyfile`. Two copies drift. These tests are the reason the duplication is
allowed: a change to the policy that does not reach the Caddyfile fails here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from glasswell.api import BASEMAP_CACHE, SHELL_CACHE
from glasswell.api.security import STATIC_SECURITY_HEADERS, content_security_policy

pytestmark = pytest.mark.unit

CADDYFILE = Path(__file__).resolve().parents[2] / "infra" / "caddy" / "Caddyfile"
HANDLER = "handle_path /basemap/*"


def basemap_handler() -> str:
    text = CADDYFILE.read_text()
    start = text.index(HANDLER)
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise AssertionError(f"{HANDLER} never closes")


@pytest.fixture(scope="module")
def block() -> str:
    return basemap_handler()


def header_value(block: str, name: str) -> str:
    match = re.search(rf'^\s*{re.escape(name)}\s+"?(.+?)"?$', block, re.MULTILINE)
    assert match, f"{name} is not set in the /basemap handler"
    return match.group(1)


@pytest.mark.parametrize(("name", "value"), sorted(STATIC_SECURITY_HEADERS.items()))
def test_the_basemap_handler_sets_every_static_security_header(block, name, value):
    assert header_value(block, name) == value


def test_the_basemap_handler_serves_the_https_policy_the_api_would_have_served(block):
    assert header_value(block, "Content-Security-Policy") == content_security_policy(https=True)


def test_the_archive_and_the_manifest_keep_the_cache_classes_the_api_defines(block):
    assert f'header @archive Cache-Control "{BASEMAP_CACHE}"' in block
    assert f'header @manifest Cache-Control "{SHELL_CACHE}"' in block


def test_the_archive_and_the_glyph_ranges_keep_a_content_type(block):
    """Both extensions are unknown to Caddy, and the uvicorn mount typed them."""
    assert "@binary path *.pmtiles *.pbf" in block
    assert 'header @binary Content-Type application/octet-stream' in block


def test_the_manifest_matcher_and_the_archive_matcher_are_complements(block):
    """One Cache-Control per response: overlapping matchers would make the class a coin flip."""
    assert "@manifest path /manifest.json" in block
    assert "@archive not path /manifest.json" in block


def test_the_proxied_path_still_exists_so_a_revert_is_the_only_rollback_needed():
    # The upstream address is test_api_socket_contract.py's to pin; what matters here is that
    # deleting this handler hands /basemap/* straight back to the catch-all beneath it.
    text = CADDYFILE.read_text()
    assert "handle {" in text
    assert "reverse_proxy" in text[text.index("handle {") :]
    assert text.index(HANDLER) < text.index("handle {")
