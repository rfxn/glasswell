"""The Caddy trust contract, asserted against the *adapted* configuration.

`tests/unit/test_caddy_trust_headers.py` proves the directives are present. It cannot prove
what they mean, and three defects lived in exactly that blind spot: `http://127.0.0.1:8080`
as a site address adapts to `listen: [":8080"]` with a **host matcher**, not a bind — open on
every interface, matching on a header the caller supplies, and unable to match cloudflared,
which sends `Host: glasswell.rpx.sh`. A regex over the file text sees a correct-looking
string in all three cases.

So this file adapts the Caddyfile with Caddy itself and asserts the JSON. It runs in the
integration tier because it needs a container; the tier already requires docker, so it cannot
go quietly inert.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

CADDYFILE = Path(__file__).resolve().parents[2] / "infra" / "caddy" / "Caddyfile"
CADDY_IMAGE = "caddy:2"

TUNNEL_LISTEN = "127.0.0.1:8080"
LAN_LISTEN = "192.168.2.111:8000"


def strip_tls(text: str) -> str:
    """Remove the `tls` blocks so the stock image can adapt this file.

    The DNS-01 issuer needs a Cloudflare provider module the published image does not carry.
    `tls` configures certificate issuance and cannot affect a listen address, a bind, a host
    matcher or a header operation, which is everything asserted below.
    """
    out: list[str] = []
    lines = text.splitlines(True)
    index = 0
    while index < len(lines):
        if lines[index].strip().startswith("tls {"):
            depth = 0
            while index < len(lines):
                depth += lines[index].count("{") - lines[index].count("}")
                index += 1
                if depth == 0:
                    break
            continue
        out.append(lines[index])
        index += 1
    return "".join(out)


@pytest.fixture(scope="module")
def adapted(tmp_path_factory: pytest.TempPathFactory) -> dict:
    if shutil.which("docker") is None:
        pytest.fail("docker is required to adapt the Caddyfile")
    source = tmp_path_factory.mktemp("caddy") / "Caddyfile"
    source.write_text(strip_tls(CADDYFILE.read_text(encoding="utf-8")), encoding="utf-8")
    finished = subprocess.run(
        [
            "docker", "run", "--rm", "-v", f"{source}:/cf:ro",
            "--entrypoint", "caddy", CADDY_IMAGE,
            "adapt", "--config", "/cf", "--adapter", "caddyfile",
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert finished.returncode == 0, f"caddy adapt failed: {finished.stderr}"
    return json.loads(finished.stdout)


def servers(adapted: dict) -> dict:
    return adapted["apps"]["http"]["servers"]


def server_listening_on(adapted: dict, address: str) -> dict:
    found = [srv for srv in servers(adapted).values() if address in srv["listen"]]
    assert len(found) == 1, f"expected exactly one server on {address}, got {len(found)}"
    return found[0]


def header_ops(server: dict) -> list[dict]:
    ops = []
    for route in server.get("routes", []):
        for handle in route.get("handle", []):
            if handle.get("handler") == "subroute":
                for inner in handle.get("routes", []):
                    ops.extend(
                        h for h in inner.get("handle", []) if h.get("handler") == "headers"
                    )
            elif handle.get("handler") == "headers":
                ops.append(handle)
    return ops


def test_the_tunnel_listener_binds_loopback_and_not_every_interface(adapted: dict) -> None:
    """BLOCKER-1. `http://127.0.0.1:8080` would adapt to `:8080` — every interface."""
    listens = [address for srv in servers(adapted).values() for address in srv["listen"]]

    assert TUNNEL_LISTEN in listens, f"the tunnel listener is not bound to loopback: {listens}"
    assert ":8080" not in listens, "the tunnel listener is open on every interface"
    assert "0.0.0.0:8080" not in listens


def test_the_tunnel_listener_has_no_host_matcher(adapted: dict) -> None:
    """BLOCKER-2. A `host` matcher here is both a trust decision on caller-supplied input and
    a guarantee the route never matches: cloudflared sends `Host: glasswell.rpx.sh`."""
    server = server_listening_on(adapted, TUNNEL_LISTEN)

    matchers = [route["match"] for route in server.get("routes", []) if route.get("match")]
    hosts = [m for match in matchers for entry in match for m in entry.get("host", [])]

    assert hosts == [], f"the tunnel listener matches on Host: {hosts}"


def test_the_tunnel_listener_reaches_only_the_api_socket(adapted: dict) -> None:
    server = server_listening_on(adapted, TUNNEL_LISTEN)
    body = json.dumps(server)

    assert "/run/glasswell/api.sock" in body
    assert ":3000" not in body, "the tile server is reachable from the tunnel listener"


@pytest.mark.parametrize("marker", ["X-Glasswell-Edge", "X-Glasswell-Client-Ip"])
def test_the_markers_are_set_rather_than_added(adapted: dict, marker: str) -> None:
    """`add` appends beside a client-supplied copy; only `set` replaces it."""
    server = server_listening_on(adapted, TUNNEL_LISTEN)
    request_ops = [op["request"] for op in header_ops(server) if "request" in op]

    assert any(marker in op.get("set", {}) for op in request_ops), f"{marker} is not set"
    assert not any(marker in op.get("add", {}) for op in request_ops), f"{marker} is added"
    assert not any(
        marker in (op.get("delete") or []) for op in request_ops
    ), f"{marker} is deleted; Caddy deletes after setting, so it would be absent"


@pytest.mark.parametrize(
    "header", ["X-Forwarded-For", "X-Real-IP", "Forwarded", "Cf-Connecting-Ip"]
)
def test_the_client_supplied_trust_headers_are_deleted(adapted: dict, header: str) -> None:
    server = server_listening_on(adapted, TUNNEL_LISTEN)
    deleted = {
        name
        for op in header_ops(server)
        if "request" in op
        for name in (op["request"].get("delete") or [])
    }

    assert header in deleted, f"{header} survives into the origin request"


def test_the_forwarded_proto_reaches_the_origin_as_https(adapted: dict) -> None:
    """BLOCKER-3. The tunnel hop is plaintext loopback, so without this the origin infers
    `http`, and HSTS and upgrade-insecure-requests are dropped on the public path. It has to
    be `header_up` inside the proxy: `reverse_proxy` sets this header from the actual hop and
    overwrites anything an earlier `request_header` put there — measured, not assumed."""
    server = server_listening_on(adapted, TUNNEL_LISTEN)

    proxies = [
        handle
        for route in server.get("routes", [])
        for handle in route.get("handle", [])
        if handle.get("handler") == "reverse_proxy"
    ]
    assert proxies, "the tunnel listener proxies nothing"

    forced = [
        proxy.get("headers", {}).get("request", {}).get("set", {}).get("X-Forwarded-Proto")
        for proxy in proxies
    ]
    assert forced == [["https"]], (
        "X-Forwarded-Proto is not set to https on the proxy itself. A request_header above"
        f" the proxy does not survive it -- reverse_proxy overwrites the header. Got: {forced}"
    )


def test_the_lan_listener_is_bound_to_the_lan_address(adapted: dict) -> None:
    """The counter-example that keeps the tunnel assertions honest: this one is *meant* to
    carry a host matcher, and it binds an explicit address rather than every interface."""
    listens = [address for srv in servers(adapted).values() for address in srv["listen"]]

    assert LAN_LISTEN in listens
    assert ":8000" not in listens


def test_every_proxying_listener_has_its_own_log_block(adapted: dict) -> None:
    """A Caddy site inherits no logging from another site."""
    logged = [
        srv for srv in servers(adapted).values() if srv.get("logs") or "logs" in json.dumps(srv)
    ]

    assert len(logged) >= 2, "a proxying listener would be logged by the default logger"
