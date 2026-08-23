"""Response security headers (N-6). CSP content is SB-05 §1.5; SB-06 §4.5 owns emission.

SB-06 §4.5 puts these on Caddy. No Caddy is in the shipped path — uvicorn serves the SPA
from `StaticFiles` and answers `/v1` itself — so the origin emits them, and it keeps doing
so when an edge is added: an edge that sets the same header wins, and one that does not,
does not silently remove the policy.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

CSP_HEADER = "Content-Security-Policy"
CSP_REPORT_ONLY_HEADER = "Content-Security-Policy-Report-Only"
REPORT_ONLY_ENV = "GLASSWELL_CSP_REPORT_ONLY"
DOCS_PATH = "/docs"

# Swagger UI is served from jsdelivr by FastAPI's own template, so /docs cannot hold the
# app's `script-src 'self'`. The exception is one path, two origins and a style-src
# 'unsafe-inline'; self-hosting swagger-ui-dist would remove all three and is a follow-up.
DOCS_SCRIPT_ORIGIN = "https://cdn.jsdelivr.net"
DOCS_IMAGE_ORIGIN = "https://fastapi.tiangolo.com"

# Satellite imagery is inherently external: it is keyless, but there is no self-hosted
# equivalent to point at. One named origin, never a wildcard; requests to it happen only when
# a reader selects the satellite or hybrid basemap, and dark, light and none stay provably
# zero-external (`web/src/map/map.test.ts`, `infra/basemap/README.md`). The hybrid's labels
# are read from this app's own origin, so composing them adds no origin to this list.
SATELLITE_IMAGERY_ORIGIN = "https://services.arcgisonline.com"

STATIC_SECURITY_HEADERS: Mapping[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "X-Robots-Tag": "noindex, nofollow",
}

_DIRECTIVES: tuple[tuple[str, str], ...] = (
    ("default-src", "'none'"),
    ("script-src", "'self'"),
    ("style-src", "'self'"),
    # maplibre and deck.gl write element style attributes directly; this is the narrowest
    # directive that permits it and it admits neither inline <style> nor onclick handlers.
    ("style-src-attr", "'unsafe-inline'"),
    ("img-src", f"'self' data: blob: {SATELLITE_IMAGERY_ORIGIN}"),
    ("font-src", "'self'"),
    # maplibre fetches raster tiles and paints them from a bitmap, so imagery needs both.
    ("connect-src", f"'self' {SATELLITE_IMAGERY_ORIGIN}"),
    ("worker-src", "'self' blob:"),
    ("child-src", "'none'"),
    ("frame-ancestors", "'none'"),
    ("base-uri", "'none'"),
    ("form-action", "'none'"),
    ("object-src", "'none'"),
)

_DOCS_OVERRIDES: Mapping[str, str] = {
    "script-src": f"'self' {DOCS_SCRIPT_ORIGIN}",
    "style-src": f"'self' 'unsafe-inline' {DOCS_SCRIPT_ORIGIN}",
    "img-src": f"'self' data: blob: {DOCS_IMAGE_ORIGIN}",
}


def content_security_policy(*, https: bool = False, docs: bool = False) -> str:
    """`upgrade-insecure-requests` only under TLS: it would break the plain-http LAN path."""
    overrides = _DOCS_OVERRIDES if docs else {}
    policy = "; ".join(f"{name} {overrides.get(name, value)}" for name, value in _DIRECTIVES)
    return f"{policy}; upgrade-insecure-requests" if https else policy


def directives(policy: str) -> dict[str, str]:
    """Parse a policy back into `{name: value}`; a valueless directive maps to `""`."""
    parsed: dict[str, str] = {}
    for token in policy.split(";"):
        name, _, value = token.strip().partition(" ")
        if name:
            parsed[name] = value.strip()
    return parsed


def header_for(path: str, *, https: bool) -> tuple[str, str]:
    """The CSP header name and value for one request; report-only is read per request."""
    name = CSP_REPORT_ONLY_HEADER if os.environ.get(REPORT_ONLY_ENV) == "1" else CSP_HEADER
    return name, content_security_policy(https=https, docs=path == DOCS_PATH)
