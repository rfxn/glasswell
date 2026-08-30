"""Finding F-1's regression test: a bare X-Forwarded-For is never a client address.

uvicorn runs with `--forwarded-allow-ips '*'`, under which ProxyHeadersMiddleware returns the
leftmost X-Forwarded-For entry -- which the client sets. If the per-IP login throttle ever
read `request.client.host`, an attacker would evade it by sending one header.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from starlette.requests import Request

from glasswell.api import client_ip as module
from glasswell.api.client_ip import (
    CLIENT_IP_HEADER,
    EDGE_HEADER,
    UNKNOWN,
    edge_of,
    looks_like_cloudflare,
    normalise_address,
    resolve_client_ip,
)

pytestmark = pytest.mark.unit


def request_with(**headers: str) -> Request:
    raw = [(name.lower().encode(), value.encode()) for name, value in headers.items()]
    return Request({"type": "http", "headers": raw, "method": "GET", "path": "/"})


def test_a_bare_x_forwarded_for_is_never_trusted() -> None:
    """The F-1 regression. No edge marker, so the value is not a client address."""
    request = request_with(**{"X-Forwarded-For": "1.2.3.4"})

    assert resolve_client_ip(request) == UNKNOWN


def test_a_client_supplied_client_ip_without_an_edge_marker_is_ignored() -> None:
    request = request_with(**{CLIENT_IP_HEADER: "1.2.3.4"})

    assert resolve_client_ip(request) == UNKNOWN


def test_a_tunnel_marked_request_reads_the_edge_header() -> None:
    request = request_with(**{EDGE_HEADER: "tunnel", CLIENT_IP_HEADER: "203.0.113.7"})

    assert resolve_client_ip(request) == "203.0.113.7"


def test_a_lan_marked_request_reads_the_edge_header() -> None:
    request = request_with(**{EDGE_HEADER: "lan", CLIENT_IP_HEADER: "192.168.2.50"})

    assert resolve_client_ip(request) == "192.168.2.50"


def test_an_unmarked_request_resolves_to_unknown() -> None:
    assert resolve_client_ip(request_with()) == UNKNOWN


def test_an_unrecognised_edge_marker_resolves_to_unknown() -> None:
    """A marker this app does not set is not a marker it trusts."""
    request = request_with(**{EDGE_HEADER: "somewhere-else", CLIENT_IP_HEADER: "203.0.113.7"})

    assert edge_of(request) is None
    assert resolve_client_ip(request) == UNKNOWN


def test_an_ipv6_value_round_trips() -> None:
    request = request_with(**{EDGE_HEADER: "tunnel", CLIENT_IP_HEADER: "2606:4700:4700::1111"})

    assert resolve_client_ip(request) == "2606:4700:4700::1111"


def test_a_bracketed_ipv6_value_is_unwrapped() -> None:
    assert normalise_address("[2606:4700::1]") == "2606:4700::1"


@pytest.mark.parametrize(
    "value",
    ["", "   ", "not-an-ip", "1.2.3.4, 5.6.7.8", "999.1.1.1", "<script>", "1.2.3.4:8080"],
)
def test_a_malformed_value_resolves_to_unknown(value: str) -> None:
    """Caddy sets exactly one value; anything else is not something to key a bucket on."""
    request = request_with(**{EDGE_HEADER: "tunnel", CLIENT_IP_HEADER: value})

    assert resolve_client_ip(request) == UNKNOWN


def reads_request_client(source: str) -> bool:
    """True when the code actually evaluates `<something>.client`, ignoring prose.

    Parsed rather than grepped: this module's own docstring explains at length why
    `request.client` is untrustworthy, and a substring search would flag that explanation.
    """
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Attribute) and node.attr == "client":
            target = node.value
            if isinstance(target, ast.Name) and target.id in ("request", "scope"):
                return True
    return False


def test_the_module_never_reads_request_client() -> None:
    """Structural, because not reading that field is the whole point of the module existing."""
    assert reads_request_client(inspect.getsource(module)) is False


def test_no_module_under_api_reads_request_client_for_an_address() -> None:
    """The class, not the instance: any future caller reaching for request.client fails here."""
    root = Path(module.__file__).resolve().parent
    offenders = [
        path.name
        for path in sorted(root.rglob("*.py"))
        if reads_request_client(path.read_text(encoding="utf-8"))
    ]

    assert offenders == []


def test_a_cloudflare_range_value_on_a_tunnel_request_is_flagged_as_misconfiguration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ranges = tmp_path / "cloudflare-ips.txt"
    ranges.write_text("# source: https://api.cloudflare.com/client/v4/ips\n173.245.48.0/20\n")
    monkeypatch.setenv(module.CF_RANGES_PATH_ENV, str(ranges))
    module._networks.cache_clear()

    assert looks_like_cloudflare("173.245.48.9") is True
    assert looks_like_cloudflare("203.0.113.7") is False


def test_a_missing_range_list_never_fails_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The detector degrades; the resolver's trust does not depend on the list at all."""
    monkeypatch.setenv(module.CF_RANGES_PATH_ENV, str(tmp_path / "absent.txt"))
    module._networks.cache_clear()

    assert looks_like_cloudflare("173.245.48.9") is False
    request = request_with(**{EDGE_HEADER: "tunnel", CLIENT_IP_HEADER: "203.0.113.7"})
    assert resolve_client_ip(request) == "203.0.113.7"


def test_the_shipped_range_list_parses_and_is_not_truncated() -> None:
    shipped = Path(__file__).resolve().parents[2] / "infra" / "cloudflare" / "ip-ranges.txt"
    cidrs = [
        line.split("#", 1)[0].strip()
        for line in shipped.read_text(encoding="utf-8").splitlines()
        if line.split("#", 1)[0].strip()
    ]

    assert len(cidrs) >= 10
    for entry in cidrs:
        assert "/" in entry, f"{entry} is not a CIDR"
