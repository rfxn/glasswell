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
from glasswell.marts.tiles import TILE_LAYERS

router = APIRouter(tags=["tiles"])

LAYER_PATTERN = r"^[a-z][a-z0-9_]*$"
TILE_MEDIA_TYPE = "application/x-protobuf"
TILE_TIMEOUT_SECONDS = 10.0

# SB-04 §2.8's revalidate class. The URL carries no build id, so the browser has to ask —
# but asking is a forwarded `If-None-Match` that martin answers in 0.7 ms with no body,
# against the 5.6 re-fetches per distinct tile the access log showed with no class at all.
# The immutable class needs a content-addressed URL; that is the client handoff.
TILE_CACHE_CONTROL = "private, no-cache"

# What the proxy is willing to make martin spend CPU on. Measured on the z7 laterals tile
# (2,037,023 B): identity 1.8 ms, zstd 19 ms for 751,192 B, gzip 140 ms for 702,691 B,
# brotli 165 ms for 638,610 B. gzip's extra 48 KB saved is not worth 120 ms of a shared
# tile server, so a caller that cannot take zstd gets the tile uncompressed.
UPSTREAM_ENCODINGS = ("zstd",)
NO_UPSTREAM_ENCODING = "identity"

# martin runs with auto_publish on, so its catalogue is every relation with a geometry column,
# staging included. The proxy is where "staging never serves" is a control rather than a
# convention: the entitlement is this set, shared with the module that builds the layers.
PUBLISHED_LAYERS: frozenset[str] = frozenset(layer.name for layer in TILE_LAYERS)


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


def _upstream_encoding(presented: str) -> str:
    accepted = {token.partition(";")[0].strip().lower() for token in presented.split(",")}
    negotiated = [name for name in UPSTREAM_ENCODINGS if name in accepted]
    return ", ".join(negotiated) if negotiated else NO_UPSTREAM_ENCODING


def _upstream_headers(request: Request) -> dict[str, str]:
    headers = {"accept-encoding": _upstream_encoding(request.headers.get("accept-encoding", ""))}
    condition = request.headers.get("if-none-match")
    if condition:
        headers["if-none-match"] = condition
    return headers


def _cache_headers(upstream: httpx.Response) -> dict[str, str]:
    """martin's ETag is over the tile bytes and does not vary by encoding, which is what
    `Vary` is for: a 304 tells the browser to reuse its own stored representation."""
    headers = {"Cache-Control": TILE_CACHE_CONTROL, "Vary": "Accept-Encoding"}
    for name in ("etag", "content-encoding"):
        value = upstream.headers.get(name)
        if value:
            headers[name] = value
    return headers


@router.get(
    "/tiles/{layer}/{z}/{x}/{y}.pbf",
    operation_id="get_tile",
    summary="Mapbox vector tile",
    description=(
        "Streams one MVT from the tile server behind the same origin and the same key as"
        " the rest of the API. `layer` must name a published mart layer; anything else is"
        " `not_found` and never reaches the tile server. A `204` is passed through"
        " unchanged: it means the tile is empty, which is the normal answer outside the"
        " basin, not an error. A non-2xx from the tile server becomes `upstream_tile_error`."
        " Responses carry the tile server's strong `ETag` and `Cache-Control: private,"
        " no-cache`, so send `If-None-Match` and take the `304`: the tile is regenerated"
        " only when the mart is refreshed."
    ),
    response_class=Response,
    openapi_extra=request_example(path=EXAMPLE_TILE),
    responses={
        200: {"content": {TILE_MEDIA_TYPE: {}}, "description": "Vector tile"},
        204: {"description": "Empty tile: healthy, and outside the data's extent"},
        304: {"description": "The caller's copy is current; no body is sent"},
        **problem_responses("not_found", "upstream_tile_error", "validation_failed"),
    },
)
def get_tile(
    request: Request,
    layer: Annotated[str, Path(description="Tile layer id.", pattern=LAYER_PATTERN)],
    z: Annotated[int, Path(description="Zoom level.", ge=0, le=22)],
    x: Annotated[int, Path(description="Tile column.", ge=0)],
    y: Annotated[int, Path(description="Tile row.", ge=0)],
) -> Response:
    if layer not in PUBLISHED_LAYERS:
        raise ProblemError("not_found", detail=f"no published tile layer {layer}")
    try:
        # iter_raw, not .content: the body is passed on in whatever encoding martin chose,
        # so no codec runs here and the compressed form is what reaches the browser.
        with tile_client(request).stream(
            "GET", f"/{layer}/{z}/{x}/{y}", headers=_upstream_headers(request)
        ) as upstream:
            if upstream.status_code in {204, 304}:
                return Response(
                    status_code=upstream.status_code, headers=_cache_headers(upstream)
                )
            if upstream.status_code != 200:
                raise ProblemError(
                    "upstream_tile_error",
                    detail=f"tile server returned {upstream.status_code} for"
                    f" {layer}/{z}/{x}/{y}",
                )
            body = b"".join(upstream.iter_raw())
            media_type = upstream.headers.get("content-type", TILE_MEDIA_TYPE)
            headers = _cache_headers(upstream)
    except httpx.RequestError as error:
        raise ProblemError(
            "upstream_tile_error", detail=f"tile server unreachable: {error}"
        ) from None
    return Response(content=body, media_type=media_type, headers=headers)
