"""The glass-box API: SB-04's envelope, error model and pagination over SB-07's spine.

`app = create_app()` at module scope so SB-06's unit line `uvicorn glasswell.api:app`
works unchanged.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from starlette.middleware.gzip import DEFAULT_EXCLUDED_CONTENT_TYPES
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.staticfiles import StaticFiles

from glasswell.api.access_log import install_access_log_redaction
from glasswell.api.client_ip import edge_of
from glasswell.api.csrf import CSRF_KEY_ENV
from glasswell.api.deps import (
    ALLOW_ANON_ENV,
    BASEMAP_ROOT_ENV,
    PUBLIC_ENV,
    WEB_ROOT_ENV,
    enforce_rate_limit,
    require_csrf,
    require_principal,
)
from glasswell.api.errors import install_handlers, problem_response
from glasswell.api.examples import KEY_HEADER
from glasswell.api.principal import Principal as ResolvedPrincipal
from glasswell.api.routers import (
    completions,
    conformance,
    formations,
    glossary,
    health,
    index,
    keys,
    lineage,
    neighbors,
    production,
    quarantine,
    session,
    status,
    tiles,
    users,
    wells,
)
from glasswell.api.security import (
    HSTS_HEADER,
    STATIC_SECURITY_HEADERS,
    header_for,
    hsts_for,
)
from glasswell.lineage.ids import new_ulid

API_TITLE = "glasswell"
API_VERSION = "0.1.0"
FREEZE_KEY = "x-glasswell-freeze"

# The S1 freeze, stated in the document a stranger reads rather than only in a status file.
# After this date §3.6.1 makes a removal or an incompatible tightening a /v2 event, which is
# why DR-01, DR-02 and DR-33 were done before it and cannot be done after.
FREEZE = {
    "surface": "v1",
    "status": "frozen",
    "frozen_on": "2026-08-20",
    "criterion": "S1",
    "policy": (
        "Additive change only. A path, operation, parameter, response field or enum value"
        " that is published here is published for the life of /v1; removing one, or making"
        " an optional request parameter required, is a /v2 event (blueprint §3.6.1)."
    ),
    "checked_by": "tests/contract/openapi_diff.py",
}
REQUEST_ID_HEADER = "X-Request-Id"
KEY_QUERY_PARAM = "key"
# A credential in a query string reaches the access log verbatim and the Referer of every
# outbound link. All three are refused rather than redacted.
REFUSED_QUERY_PARAMS = ("key", "password", "token")
ASSET_PREFIX = "/assets/"
BASEMAP_PREFIX = "/basemap/"
BASEMAP_MANIFEST = "/basemap/manifest.json"
IMMUTABLE_CACHE = "public, max-age=31536000, immutable"
SHELL_CACHE = "no-cache"
# The archive is immutable for the life of a vintage but its name is not, so a day is the
# lifetime a swap has to outlive rather than a year (infra/basemap/README.md § Refresh
# cadence). The manifest stays on SHELL_CACHE: it is how the client notices the swap.
BASEMAP_CACHE = "public, max-age=86400"
# Compressing a 2 MB vector tile at level 9 on every request is a map-performance
# trade-off, not a transport default; the tile path decides for itself.
TILE_CONTENT_TYPES = ("application/x-protobuf", "application/vnd.mapbox-vector-tile")

DESCRIPTION = """
Glass-box upstream analytics on public data. Every number this API serves carries a
derivation handle in band, and `GET /v1/explain` walks that handle back to the
checksummed government file it came from.

Conventions that hold everywhere: responses are `data` / `meta` / `links`; collections
are cursor-paginated with no offset parameter; failures are RFC 9457 problem documents
whose `type` resolves at `/v1/errors/{code}`; and `as_of` selects knowledge time, with
the resolved vintage reported back in `meta.as_of`.

This deployment serves North Dakota wells, geometry, monthly production, completion context,
current physical neighbours and canonical formations with current alias counts, plus Texas
wells and bore geometry with well-level production held pending allocation. Physical-neighbour
results require current lateral geometry, use strict earlier-completion cutoffs, and are not
model analogs. The lineage spine, conformance registry, quarantine and glossary are live.
Forecasts, economics, scenarios, agents and undrilled-location inventory are not served; New
Mexico promotion is not claimed. `/v1/status` adds current application-plane
checks, scheduled-job observations, registered-artifact age and explicitly grained operational
dataset inventory without treating those counts as forecast inventory or petroleum figures.
""".strip()


def create_app() -> FastAPI:
    _refuse_an_unsafe_public_configuration()
    app = FastAPI(
        title=API_TITLE,
        version=API_VERSION,
        description=DESCRIPTION,
        openapi_version="3.1.0",
        # Registered by hand below so both can carry require_principal. Finding F-2: they
        # were anonymous, and the matrix coverage test could not see it because it walks
        # `document["paths"]` and neither path is an OpenAPI paths fact.
        docs_url=None,
        openapi_url=None,
        redoc_url=None,
    )
    install_handlers(app)
    install_access_log_redaction()
    app.add_middleware(
        GZipMiddleware,
        minimum_size=1024,
        exclude_content_types=(*DEFAULT_EXCLUDED_CONTENT_TYPES, *TILE_CONTENT_TYPES),
    )

    # Registered first, so the request-id middleware wraps it and the refusal carries an id.
    @app.middleware("http")
    async def _refuse_key_in_query(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        offending = next(
            (name for name in REFUSED_QUERY_PARAMS if name in request.query_params), None
        )
        if offending is not None:
            return problem_response(
                request,
                "validation_failed",
                detail=(
                    f"a credential is not accepted in the query string: send the key in"
                    f" {KEY_HEADER}, or log in and let the session cookie carry it"
                ),
                errors=[
                    {
                        "pointer": f"/query/{offending}",
                        "code": "credential_in_query",
                        "detail": "a query string is written to the access log verbatim",
                    }
                ],
            )
        return await call_next(request)

    @app.middleware("http")
    async def _static_cache_class(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        path = request.url.path
        if path.startswith(ASSET_PREFIX):
            response.headers.setdefault("Cache-Control", IMMUTABLE_CACHE)
        elif path == BASEMAP_MANIFEST:
            response.headers.setdefault("Cache-Control", SHELL_CACHE)
        elif path.startswith(BASEMAP_PREFIX):
            response.headers.setdefault("Cache-Control", BASEMAP_CACHE)
        elif path == "/" or path.endswith(".html"):
            response.headers.setdefault("Cache-Control", SHELL_CACHE)
        return response

    @app.middleware("http")
    async def _request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = new_ulid(datetime.now(UTC))
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request.state.request_id
        return response

    # Registered last, so it is the outermost layer and no inner short-circuit — the
    # query-key refusal, a validation problem, a StaticFiles 404 — escapes unheadered.
    @app.middleware("http")
    async def _security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        # The tunnel hop is plaintext loopback. Caddy sets X-Forwarded-Proto: https via
        # header_up so uvicorn resolves the scheme correctly, and the edge marker is a
        # second, independent witness -- neither is client-settable.
        https = request.url.scheme == "https" or edge_of(request) == "tunnel"
        response.headers.update(STATIC_SECURITY_HEADERS)
        name, policy = header_for(request.url.path, https=https)
        response.headers[name] = policy
        strict_transport = hsts_for(https=https)
        if strict_transport is not None:
            response.headers[HSTS_HEADER] = strict_transport
        return response

    app.include_router(health.liveness)
    # Included without the router-set dependency: two of its five operations must answer
    # before a principal exists, and the other three carry their own gates.
    app.include_router(session.router, prefix="/v1")
    for router in (
        index.router,
        health.router,
        status.router,
        wells.router,
        neighbors.router,
        completions.router,
        production.router,
        formations.router,
        tiles.router,
        lineage.router,
        conformance.router,
        quarantine.router,
        glossary.router,
        keys.router,
        users.router,
    ):
        app.include_router(
            router,
            prefix="/v1",
            dependencies=[
                Depends(require_principal),
                Depends(require_csrf),
                Depends(enforce_rate_limit),
            ],
        )

    # Before the mounts: Starlette matches in route order, and Mount("/") shadows
    # everything after it. Registered later these answered 404 rather than 403 in any
    # deployment that sets GLASSWELL_WEB_ROOT -- which production does and the fixtures
    # did not, so the F-2 fix was real in code and vacuous on the host.
    _serve_the_document(app)

    basemap_root = os.environ.get(BASEMAP_ROOT_ENV)
    if basemap_root and Path(basemap_root).is_dir():
        # Keyless on purpose: the archive is public OSM data on this origin, and PMTiles
        # reads it with range requests, which StaticFiles answers with a 206. Mounted
        # before the SPA so `/basemap/*` never falls through to index.html.
        app.mount("/basemap", StaticFiles(directory=basemap_root), name="basemap")

    web_root = os.environ.get(WEB_ROOT_ENV)
    if web_root and Path(web_root).is_dir():
        # Mounted last: /v1 and /healthz are already routed, so the SPA only sees the rest.
        app.mount("/", StaticFiles(directory=web_root, html=True), name="web")

    _stamp_the_freeze(app)
    return app


DOCS_PATH = "/docs"
OPENAPI_PATH = "/openapi.json"


def _serve_the_document(app: FastAPI) -> None:
    """Serve `/docs` and `/openapi.json` behind the same gate as everything else.

    A tightening of a currently-open surface. `openapi_diff.py` cannot see it, because
    neither path is an entry in `document["paths"]` -- which is also why the auth matrix's
    coverage test could not catch that they were anonymous (finding F-2). The matrix now
    walks `app.routes` instead.
    """

    @app.get(OPENAPI_PATH, include_in_schema=False)
    def openapi_document(
        principal: Annotated[ResolvedPrincipal, Depends(require_principal)],
    ) -> JSONResponse:
        return JSONResponse(app.openapi())

    @app.get(DOCS_PATH, include_in_schema=False)
    def swagger_ui(
        principal: Annotated[ResolvedPrincipal, Depends(require_principal)],
    ) -> HTMLResponse:
        return get_swagger_ui_html(openapi_url=OPENAPI_PATH, title=f"{API_TITLE} — API")


def _stamp_the_freeze(app: FastAPI) -> None:
    """Carry the freeze terms in `info`, so the served document states its own change policy."""
    generate = app.openapi

    def openapi() -> dict[str, object]:
        document = generate()
        document["info"][FREEZE_KEY] = dict(FREEZE)
        return document

    app.openapi = openapi  # type: ignore[method-assign]


def _refuse_an_unsafe_public_configuration() -> None:
    """Two refusals that make a misconfigured public instance loudly broken, never quietly open.

    Restart=on-failure turns each into a unit that will not come up, which is the intended
    outcome: a public origin serving with authentication disabled is worse than a down one.
    """
    if os.environ.get(PUBLIC_ENV) == "1" and os.environ.get(ALLOW_ANON_ENV) == "1":
        raise RuntimeError(
            f"{ALLOW_ANON_ENV}=1 with {PUBLIC_ENV}=1: refusing to serve the internet with"
            " authentication disabled"
        )
    if os.environ.get(PUBLIC_ENV) == "1" and not os.environ.get(CSRF_KEY_ENV):
        raise RuntimeError(f"{CSRF_KEY_ENV} is unset: CSRF cannot be enforced")


app = create_app()

__all__ = ["app", "create_app"]
