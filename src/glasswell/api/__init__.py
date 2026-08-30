"""The glass-box API: SB-04's envelope, error model and pagination over SB-07's spine.

`app = create_app()` at module scope so SB-06's unit line `uvicorn glasswell.api:app`
works unchanged.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.gzip import DEFAULT_EXCLUDED_CONTENT_TYPES
from starlette.responses import Response
from starlette.staticfiles import StaticFiles

from glasswell.api.access_log import install_access_log_redaction
from glasswell.api.deps import BASEMAP_ROOT_ENV, WEB_ROOT_ENV, require_key
from glasswell.api.errors import install_handlers, problem_response
from glasswell.api.examples import KEY_HEADER
from glasswell.api.routers import (
    completions,
    conformance,
    cumulatives,
    formations,
    glossary,
    health,
    index,
    keys,
    lineage,
    neighbors,
    production,
    quarantine,
    status,
    tiles,
    wells,
)
from glasswell.api.security import STATIC_SECURITY_HEADERS, header_for
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

What this deployment serves is data-derived rather than declared here: `GET /v1/status`
reports the resident dataset inventory, each row carrying its own scope, grain, vintage
bounds and metrics. Where a regulator publishes volumes at well level they are served at
well level; where it publishes only at lease level, well-level production is held pending
allocation rather than inferred. Physical-neighbour results require current lateral
geometry, use strict earlier-completion cutoffs, and are not model analogs. The lineage
spine, conformance registry, quarantine and glossary are live. Forecasts, economics,
scenarios, agents and undrilled-location inventory are not served, and a source that is
staged without being promoted is not claimed as resident. `/v1/status` adds current
application-plane checks, scheduled-job observations, registered-artifact age and explicitly
grained operational dataset inventory without treating those counts as forecast inventory or
petroleum figures.
""".strip()


def create_app() -> FastAPI:
    app = FastAPI(
        title=API_TITLE,
        version=API_VERSION,
        description=DESCRIPTION,
        openapi_version="3.1.0",
        docs_url="/docs",
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
        if KEY_QUERY_PARAM in request.query_params:
            return problem_response(
                request,
                "validation_failed",
                detail=(
                    "the owner key is not accepted in the query string: open the app once with"
                    f" #key=<owner key>, or send the key in {KEY_HEADER}"
                ),
                errors=[
                    {
                        "pointer": f"/query/{KEY_QUERY_PARAM}",
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
        response.headers.update(STATIC_SECURITY_HEADERS)
        name, policy = header_for(request.url.path, https=request.url.scheme == "https")
        response.headers[name] = policy
        return response

    app.include_router(health.liveness)
    for router in (
        index.router,
        health.router,
        status.router,
        wells.router,
        neighbors.router,
        completions.router,
        cumulatives.router,
        production.router,
        formations.router,
        tiles.router,
        lineage.router,
        conformance.router,
        quarantine.router,
        glossary.router,
        keys.router,
    ):
        app.include_router(router, prefix="/v1", dependencies=[Depends(require_key)])

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


def _stamp_the_freeze(app: FastAPI) -> None:
    """Carry the freeze terms in `info`, so the served document states its own change policy."""
    generate = app.openapi

    def openapi() -> dict[str, object]:
        document = generate()
        document["info"][FREEZE_KEY] = dict(FREEZE)
        return document

    app.openapi = openapi  # type: ignore[method-assign]


app = create_app()

__all__ = ["app", "create_app"]
