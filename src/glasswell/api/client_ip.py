"""Where the client address comes from, and why it is never `request.client`.

`glasswell-api.service` runs uvicorn with `--forwarded-allow-ips '*'`. Under that setting
`ProxyHeadersMiddleware.get_trusted_client_address` short-circuits on `always_trust` and
returns the **leftmost** `X-Forwarded-For` entry, which the client supplies. The `*` is
correct for its stated purpose -- a unix peer has no address and a numeric allow-list would
stop trusting `X-Forwarded-Proto` -- but it also means `request.client.host` is
attacker-controlled. Nothing read it before the per-IP login throttle needed one.

So the address is taken from `X-Glasswell-Client-Ip`, and only when `X-Glasswell-Edge` marks
which listener the request arrived on. Caddy deletes every client-supplied copy of both
headers before setting its own; that delete is the whole security property, and
`tests/unit/test_caddy_trust_headers.py` is what holds it in place.

With Cloudflare Tunnel there is no peer address to range-check -- the connection is
outbound-initiated and arrives on loopback -- so "trust `CF-Connecting-IP` only from
Cloudflare ranges" has no socket to apply a range list to. Which listener the request
arrived on is the equivalent control. The range list is still shipped, as a misconfiguration
detector; it never grants trust, so a stale or missing list cannot fail open.
"""

from __future__ import annotations

import ipaddress
import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from starlette.requests import Request

EDGE_HEADER = "X-Glasswell-Edge"
CLIENT_IP_HEADER = "X-Glasswell-Client-Ip"
UNKNOWN = "unknown"

CF_RANGES_PATH_ENV = "GLASSWELL_CF_RANGES"
DEFAULT_CF_RANGES = "/etc/glasswell/cloudflare-ips.txt"

Edge = Literal["tunnel", "lan"]
EDGES: tuple[Edge, ...] = ("tunnel", "lan")


def edge_of(request: Request) -> Edge | None:
    """Which listener the request arrived on, or None when the marker is absent or unknown."""
    marker = request.headers.get(EDGE_HEADER, "").strip().lower()
    return marker if marker in EDGES else None  # type: ignore[return-value]


def normalise_address(value: str | None) -> str:
    """A single valid IP literal, or UNKNOWN. A comma-separated list is not one value."""
    if not value:
        return UNKNOWN
    candidate = value.strip()
    if candidate.startswith("[") and "]" in candidate:
        candidate = candidate[1 : candidate.index("]")]
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return UNKNOWN


def resolve_client_ip(request: Request) -> str:
    """Never reads `request.client`: under `--forwarded-allow-ips '*'` that field is spoofable.

    No edge marker means UNKNOWN, which shares one rate-limit bucket. Never unlimited.
    """
    if edge_of(request) is None:
        return UNKNOWN
    return normalise_address(request.headers.get(CLIENT_IP_HEADER))


@lru_cache(maxsize=1)
def _networks(path: str) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return ()
    parsed = []
    for line in text.splitlines():
        entry = line.split("#", 1)[0].strip()
        if not entry:
            continue
        try:
            parsed.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            continue
    return tuple(parsed)


def cloudflare_ranges_path() -> str:
    return os.environ.get(CF_RANGES_PATH_ENV) or DEFAULT_CF_RANGES


def looks_like_cloudflare(address: str) -> bool:
    """A misconfiguration detector, never a trust decision.

    A tunnel-marked request whose client address falls inside a Cloudflare range means the
    edge's own address reached the field instead of the visitor's. That is logged as degraded.
    An absent or unreadable list answers False, so nothing here can fail open.
    """
    if not address or address == UNKNOWN:
        return False
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(parsed in network for network in _networks(cloudflare_ranges_path()))
