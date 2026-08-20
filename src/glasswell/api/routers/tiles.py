"""Vector tiles, proxied from martin so the browser sees exactly one origin (C11/C12)."""

from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastapi import APIRouter, Path, Request
from starlette.responses import Response

from glasswell.api.deps import DEFAULT_MARTIN_URL, MARTIN_URL_ENV
from glasswell.api.errors import ProblemError, problem_responses
from glasswell.api.examples import EXAMPLE_TILE, request_example

router = APIRouter(tags=["tiles"])

LAYER_PATTERN = r"^[a-z][a-z0-9_]*$"
TILE_MEDIA_TYPE = "application/x-protobuf"
TILE_TIMEOUT_SECONDS = 10.0


def tile_client(request: Request) -> httpx.Client:
    """One client per process, created on first use so no lifespan hook is required."""
    client = getattr(request.app.state, "tile_client", None)
    if client is None:
        client = httpx.Client(
            base_url=os.environ.get(MARTIN_URL_ENV, DEFAULT_MARTIN_URL),
            timeout=TILE_TIMEOUT_SECONDS,
        )
        request.app.state.tile_client = client
    return client


@router.get(
    "/tiles/{layer}/{z}/{x}/{y}.pbf",
    operation_id="get_tile",
    summary="Mapbox vector tile",
    description=(
        "Streams one MVT from the tile server behind the same origin and the same key as"
        " the rest of the API. A `204` is passed through unchanged: it means the tile is"
        " empty, which is the normal answer outside the basin, not an error. A non-2xx"
        " from the tile server becomes `upstream_tile_error`."
    ),
    response_class=Response,
    openapi_extra=request_example(path=EXAMPLE_TILE),
    responses={
        200: {"content": {TILE_MEDIA_TYPE: {}}, "description": "Vector tile"},
        204: {"description": "Empty tile: healthy, and outside the data's extent"},
        **problem_responses("upstream_tile_error", "validation_failed"),
    },
)
def get_tile(
    request: Request,
    layer: Annotated[str, Path(description="Tile layer id.", pattern=LAYER_PATTERN)],
    z: Annotated[int, Path(description="Zoom level.", ge=0, le=22)],
    x: Annotated[int, Path(description="Tile column.", ge=0)],
    y: Annotated[int, Path(description="Tile row.", ge=0)],
) -> Response:
    try:
        upstream = tile_client(request).get(f"/{layer}/{z}/{x}/{y}")
    except httpx.RequestError as error:
        raise ProblemError(
            "upstream_tile_error", detail=f"tile server unreachable: {error}"
        ) from None
    if upstream.status_code == 204:
        return Response(status_code=204)
    if upstream.status_code != 200:
        raise ProblemError(
            "upstream_tile_error",
            detail=f"tile server returned {upstream.status_code} for {layer}/{z}/{x}/{y}",
        )
    return Response(
        content=upstream.content,
        media_type=upstream.headers.get("content-type", TILE_MEDIA_TYPE),
    )
