"""How Caddy neutralises client-supplied trust headers, held as a test not a convention.

`resolve_client_ip` trusts `X-Glasswell-Client-Ip` whenever `X-Glasswell-Edge` is present.
That is only sound because a client cannot supply either one: Caddy deletes the headers it
does not set, and overwrites the two it does. Lose one of those lines and the app trusts a
header the internet writes.

Both listeners are checked. The LAN one matters as much as the tunnel one: a request reaching
the LAN listener with a forged `X-Glasswell-Edge: tunnel` and a forged client address would
otherwise land in the wrong bucket and dodge the tunnel-only refusals.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

CADDYFILE = Path(__file__).resolve().parents[2] / "infra" / "caddy" / "Caddyfile"

TUNNEL_BLOCK = "http://:8080"
LAN_BLOCK = "glasswell.lab.rpx.sh {"

# Headers a client could set that this deployment's trust decisions read, and that Caddy does
# not set itself. These must be deleted.
#
# X-Glasswell-Edge and X-Glasswell-Client-Ip are deliberately NOT in this tuple. Caddy applies
# a field-specific `delete` AFTER `set` within one headers handler, so `-H` followed by `H v`
# yields no header at all. For those two, `set` IS the defence: it replaces any client-supplied
# value outright. test_the_markers_are_set_and_never_deleted holds that distinction.
TRUST_HEADERS = (
    "X-Forwarded-For",
    "X-Real-IP",
    "Forwarded",
    "Cf-Connecting-Ip",
    "X-Glasswell-Origin",
)

OVERWRITTEN_MARKERS = ("X-Glasswell-Edge", "X-Glasswell-Client-Ip")


def without_comments(block: str) -> str:
    """Directives only. The blocks explain in comments what they deliberately do not do, and
    a substring search would otherwise match the explanation instead of a directive."""
    return "\n".join(
        line for line in block.splitlines() if not line.strip().startswith("#")
    )


def block_at(marker: str) -> str:
    text = CADDYFILE.read_text(encoding="utf-8")
    start = text.index(marker)
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise AssertionError(f"{marker} never closes")


@pytest.fixture(scope="module")
def tunnel() -> str:
    return block_at(TUNNEL_BLOCK)


@pytest.fixture(scope="module")
def lan() -> str:
    return block_at(LAN_BLOCK)


def deletes(block: str, header: str) -> bool:
    pattern = rf"^\s*request_header\s+-{re.escape(header)}\s*$"
    return re.search(pattern, block, re.MULTILINE) is not None


@pytest.mark.parametrize("header", TRUST_HEADERS)
def test_the_tunnel_listener_deletes_every_trust_header(tunnel: str, header: str) -> None:
    assert deletes(tunnel, header), f"the tunnel listener does not delete {header}"


@pytest.mark.parametrize("header", TRUST_HEADERS)
def test_the_lan_listener_deletes_every_trust_header(lan: str, header: str) -> None:
    assert deletes(lan, header), f"the LAN listener does not delete {header}"


def test_the_lan_listener_deletes_the_forwarded_proto_before_the_proxy(lan: str) -> None:
    """A forged `X-Forwarded-Proto: http` would drop upgrade-insecure-requests and HSTS.
    The LAN listener deletes it and lets reverse_proxy set the real scheme."""
    assert deletes(lan, "X-Forwarded-Proto")
    assert lan.index("request_header -X-Forwarded-Proto") < lan.index("reverse_proxy")


def test_the_tunnel_listener_forces_the_forwarded_proto_inside_the_proxy(tunnel: str) -> None:
    """The tunnel hop is plaintext loopback, so the real scheme is the wrong answer: TLS was
    terminated at the edge. It must be `header_up` inside reverse_proxy, because
    reverse_proxy sets this header itself and overwrites anything set above it --
    tests/integration/test_caddy_adapt.py asserts that on the adapted JSON."""
    assert "header_up X-Forwarded-Proto https" in tunnel
    assert not deletes(tunnel, "X-Forwarded-Proto"), (
        "deleting it here is dead config: reverse_proxy re-adds it from the plaintext hop"
    )


def test_each_listener_sets_its_own_edge_marker(tunnel: str, lan: str) -> None:
    assert re.search(r"^\s*request_header\s+X-Glasswell-Edge\s+tunnel\s*$", tunnel, re.MULTILINE)
    assert re.search(r"^\s*request_header\s+X-Glasswell-Edge\s+lan\s*$", lan, re.MULTILINE)


def test_the_tunnel_listener_takes_the_address_from_cf_connecting_ip(tunnel: str) -> None:
    assert "request_header X-Glasswell-Client-Ip {http.request.header.Cf-Connecting-Ip}" in tunnel


def test_the_lan_listener_takes_the_address_from_the_real_peer(lan: str) -> None:
    assert "request_header X-Glasswell-Client-Ip {http.request.remote.host}" in lan


@pytest.mark.parametrize("header", OVERWRITTEN_MARKERS)
def test_the_markers_are_set_and_never_deleted(tunnel: str, lan: str, header: str) -> None:
    """The bug this test exists to prevent.

    Caddy's headers handler applies a field-specific delete after set, so a block that both
    deletes and sets one header emits nothing for it. If that happened to X-Glasswell-Edge,
    resolve_client_ip would answer `unknown` for every request through the edge -- the whole
    internet in one rate bucket -- and the tunnel refusal of the static owner key, which keys
    on that marker, would never fire. Setting alone already replaces a client-supplied value.
    """
    for block in (tunnel, lan):
        assert not deletes(block, header), (
            f"{header} is both deleted and set; Caddy deletes after setting, so it would be"
            " absent -- rely on the set alone, which overwrites any client-supplied value"
        )
        assert re.search(
            rf"^\s*request_header\s+{re.escape(header)}\s+\S", block, re.MULTILINE
        ), f"{header} is not set by this listener"


def test_neither_listener_routes_the_edge_at_the_tile_server(tunnel: str, lan: str) -> None:
    """SB-06 §4.5 specifies `handle_path /tiles/*` on both listeners. Adopting it would bypass
    PUBLISHED_LAYERS and the session gate together, so it is deliberately not adopted."""
    for block in (tunnel, lan):
        directives = without_comments(block)
        assert "handle_path /tiles/*" not in directives
        assert ":3000" not in directives


def test_the_tunnel_listener_proxies_only_the_api_socket(tunnel: str) -> None:
    assert "reverse_proxy unix//run/glasswell/api.sock" in tunnel
    assert len(re.findall(r"^\s*reverse_proxy\s", tunnel, re.MULTILINE)) == 1
