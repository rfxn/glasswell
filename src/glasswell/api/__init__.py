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
from starlette.responses import Response
from starlette.staticfiles import StaticFiles

from glasswell.api.access_log import install_access_log_redaction
from glasswell.api.deps import WEB_ROOT_ENV, require_key
from glasswell.api.errors import install_handlers, problem_response
from glasswell.api.examples import KEY_HEADER
from glasswell.api.routers import (
    conformance,
    glossary,
    health,
    index,
    lineage,
    production,
    quarantine,
    tiles,
    wells,
)
from glasswell.lineage.ids import new_ulid

API_TITLE = "glasswell"
API_VERSION = "0.1.0"
REQUEST_ID_HEADER = "X-Request-Id"
KEY_QUERY_PARAM = "key"

DESCRIPTION = """
Glass-box upstream analytics on public data. Every number this API serves carries a
derivation handle in band, and `GET /v1/explain` walks that handle back to the
checksummed government file it came from.

Conventions that hold everywhere: responses are `data` / `meta` / `links`; collections
are cursor-paginated with no offset parameter; failures are RFC 9457 problem documents
whose `type` resolves at `/v1/errors/{code}`; and `as_of` selects knowledge time, with
the resolved vintage reported back in `meta.as_of`.

This deployment is the North Dakota slice: wells, geometry, monthly production, the
lineage spine, the conformance registry, quarantine and the glossary. Forecasts,
economics and other basins are not served.
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
    async def _request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = new_ulid(datetime.now(UTC))
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request.state.request_id
        return response

    app.include_router(health.liveness)
    for router in (
        index.router,
        health.router,
        wells.router,
        production.router,
        tiles.router,
        lineage.router,
        conformance.router,
        quarantine.router,
        glossary.router,
    ):
        app.include_router(router, prefix="/v1", dependencies=[Depends(require_key)])

    web_root = os.environ.get(WEB_ROOT_ENV)
    if web_root and Path(web_root).is_dir():
        # Mounted last: /v1 and /healthz are already routed, so the SPA only sees the rest.
        app.mount("/", StaticFiles(directory=web_root, html=True), name="web")
    return app


app = create_app()

__all__ = ["app", "create_app"]
