"""RFC 9457 problem+json, the frozen error registry, and the handlers that emit them.

`type` URIs are absolute and every one resolves at `GET /v1/errors/{code}` (SB-04 §4.1),
so a stranger holding only a response body can look the failure up.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from glasswell.lineage.errors import InvalidHandle, InvalidSelector, LineageUnresolved

TYPE_BASE = "https://glasswell.rpx.sh/v1/errors"
PROBLEM_MEDIA_TYPE = "application/problem+json"


@dataclass(frozen=True, slots=True)
class ErrorSpec:
    status: int
    title: str
    description: str
    emitted: bool = True


ERROR_REGISTRY: Mapping[str, ErrorSpec] = {
    "unauthenticated": ErrorSpec(
        403,
        "Not authenticated",
        "No credential was accepted. The body carries no detail on purpose: a caller"
        " must not be able to use the error as an oracle for why a key failed.",
    ),
    "forbidden": ErrorSpec(
        403, "Forbidden", "Authenticated, but out of scope for this operation."
    ),
    "key_required": ErrorSpec(
        403,
        "API key required",
        "The request carried no owner key. Send it in the X-Glasswell-Key header.",
    ),
    "key_revoked": ErrorSpec(
        403, "API key revoked", "The key matched a revoked or expired record.", emitted=False
    ),
    "jwks_unavailable": ErrorSpec(
        503,
        "Identity keys unavailable",
        "No usable Access signing keys and the stale-serve window has elapsed.",
        emitted=False,
    ),
    "not_found": ErrorSpec(
        404,
        "Not found",
        "The resource does not exist, or exists but is not visible to this principal."
        " Both answer the same way so probing reveals nothing.",
    ),
    "validation_failed": ErrorSpec(
        422,
        "Request validation failed",
        "A parameter failed validation, including declared caps. `errors[]` names each"
        " offending pointer. Caps are refused, never silently clamped.",
    ),
    "cursor_malformed": ErrorSpec(
        422, "Cursor malformed", "The cursor did not decode to the four declared fields."
    ),
    "cursor_query_mismatch": ErrorSpec(
        422,
        "Cursor does not match this query",
        "The cursor was minted against a different filter set. Continuing would return a"
        " page from a different result set (SB-04 §2.3).",
    ),
    "as_of_out_of_range": ErrorSpec(
        422,
        "as_of precedes the captured history",
        "`as_of` is earlier than the earliest captured vintage for every contributing"
        " source. An empty result would be indistinguishable from nothing happening.",
    ),
    "selector_ambiguous": ErrorSpec(
        422, "Handle selector is ambiguous", "The selector does not address exactly one figure."
    ),
    "lineage_unresolved": ErrorSpec(
        404,
        "Lineage could not be resolved",
        "SB-07 §9.5. The body names the handle, the last resolvable node, and the stop"
        " reason (`selector_ambiguous`, `depth_exceeded`, `derivation_swept`,"
        " `unknown_id`). An auditor never gets a bare 404.",
    ),
    "explain_on_dry_run": ErrorSpec(
        422, "explain cannot be combined with dry_run", "There is no artifact to explain.",
        emitted=False,
    ),
    "result_cap_exceeded": ErrorSpec(
        422,
        "Result cap exceeded",
        "The filter set selects more rows than the endpoint's declared cap.",
        emitted=False,
    ),
    "unregistered_artifact": ErrorSpec(
        409,
        "Artifact is not registered",
        "Serving the number would mean serving it from an unregistered artifact.",
        emitted=False,
    ),
    "model_not_promoted": ErrorSpec(
        409, "Model is not promoted", "The model registry refused a non-promoted model.",
        emitted=False,
    ),
    "idempotency_conflict": ErrorSpec(
        409, "Idempotency key conflict", "The same key was reused with a different body.",
        emitted=False,
    ),
    "idempotency_in_progress": ErrorSpec(
        409, "Idempotent request in progress", "The original request is still running.",
        emitted=False,
    ),
    "job_not_cancellable": ErrorSpec(
        409, "Job is not cancellable", "The job has already reached a terminal state.",
        emitted=False,
    ),
    "tile_token_invalid": ErrorSpec(
        403, "Tile token invalid", "Signature, expiry, audience or principal binding failed.",
        emitted=False,
    ),
    "tile_layer_not_entitled": ErrorSpec(
        403, "Tile layer not entitled", "The token is valid but does not cover this layer.",
        emitted=False,
    ),
    "rate_limited": ErrorSpec(
        429, "Rate limited", "The token bucket for this operation is exhausted.", emitted=False
    ),
    "payload_too_large": ErrorSpec(
        413, "Payload too large", "The request body exceeds the endpoint's cap.", emitted=False
    ),
    "unsupported_format": ErrorSpec(
        415, "Unsupported format", "`format` is outside the endpoint's declared set."
    ),
    "upstream_tile_error": ErrorSpec(
        502, "Tile upstream failed", "martin returned a non-2xx response to the tile proxy."
    ),
    "service_degraded": ErrorSpec(
        503, "Service degraded", "A required store is unavailable."
    ),
}


class Problem(BaseModel):
    """The wire shape of every failure (RFC 9457)."""

    model_config = ConfigDict(extra="allow")

    type: str = Field(description="Absolute URI of the error code; resolves at /v1/errors/{code}.")
    title: str = Field(description="Short, human-readable summary of the error code.")
    status: int = Field(description="HTTP status code, repeated in the body per RFC 9457.")
    detail: str | None = Field(default=None, description="What went wrong on this request.")
    instance: str = Field(description="Path of the request that failed.")
    request_id: str = Field(description="ULID joining this response to the audit trail.")
    errors: list[dict[str, Any]] | None = Field(
        default=None, description="Per-field failures, each with a JSON Pointer."
    )


class ProblemError(Exception):
    """Raised anywhere in a handler; the registered handler turns it into problem+json."""

    def __init__(
        self,
        code: str,
        *,
        detail: str | None = None,
        errors: Sequence[Mapping[str, Any]] = (),
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail
        self.errors = list(errors)
        self.extra = dict(extra or {})


def problem_response(
    request: Request,
    code: str,
    *,
    detail: str | None = None,
    errors: Sequence[Mapping[str, Any]] = (),
    extra: Mapping[str, Any] | None = None,
) -> JSONResponse:
    spec = ERROR_REGISTRY[code]
    body: dict[str, Any] = {
        "type": f"{TYPE_BASE}/{code}",
        "title": spec.title,
        "status": spec.status,
        "instance": request.url.path,
        "request_id": getattr(request.state, "request_id", ""),
    }
    if detail is not None:
        body["detail"] = detail
    if errors:
        body["errors"] = [dict(error) for error in errors]
    body |= dict(extra or {})
    return JSONResponse(body, status_code=spec.status, media_type=PROBLEM_MEDIA_TYPE)


def problem_responses(*codes: str) -> dict[int | str, dict[str, Any]]:
    """OpenAPI `responses` entries, one per problem this operation can emit."""
    declared: dict[int | str, dict[str, Any]] = {}
    for code in codes:
        spec = ERROR_REGISTRY[code]
        entry = declared.setdefault(
            spec.status,
            {"model": Problem, "description": spec.title, "content": {PROBLEM_MEDIA_TYPE: {}}},
        )
        examples = entry["content"][PROBLEM_MEDIA_TYPE].setdefault("examples", {})
        examples[code] = {
            "summary": spec.title,
            "value": {
                "type": f"{TYPE_BASE}/{code}",
                "title": spec.title,
                "status": spec.status,
                "detail": spec.description,
                "instance": "/v1",
                "request_id": "01JBQ7M0Z8K2V4N6X8R0T2Y4W6",
            },
        }
    return declared


_STATUS_CODES = {
    403: "forbidden",
    404: "not_found",
    405: "not_found",
    413: "payload_too_large",
    415: "unsupported_format",
    422: "validation_failed",
    429: "rate_limited",
    502: "upstream_tile_error",
    503: "service_degraded",
}


def _pointer(location: Sequence[Any]) -> str:
    return "/" + "/".join(str(part) for part in location)


def install_handlers(app: FastAPI) -> None:
    """Every failure leaves as problem+json, including the ones Starlette raises itself."""

    @app.exception_handler(ProblemError)
    async def _problem(request: Request, error: ProblemError) -> JSONResponse:
        return problem_response(
            request, error.code, detail=error.detail, errors=error.errors, extra=error.extra
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, error: RequestValidationError) -> JSONResponse:
        errors = [
            {"pointer": _pointer(item["loc"]), "code": item["type"], "detail": item["msg"]}
            for item in error.errors()
        ]
        return problem_response(
            request,
            "validation_failed",
            detail=errors[0]["detail"] if errors else "the request failed validation",
            errors=errors,
        )

    @app.exception_handler(LineageUnresolved)
    async def _unresolved(request: Request, error: LineageUnresolved) -> JSONResponse:
        return problem_response(
            request,
            "lineage_unresolved",
            detail=str(error),
            extra={
                "handle": error.handle,
                "last_resolved": error.last_resolved,
                "stop_reason": error.reason,
            },
        )

    @app.exception_handler(InvalidSelector)
    async def _selector(request: Request, error: InvalidSelector) -> JSONResponse:
        return problem_response(request, "selector_ambiguous", detail=str(error))

    @app.exception_handler(InvalidHandle)
    async def _handle(request: Request, error: InvalidHandle) -> JSONResponse:
        return problem_response(
            request,
            "validation_failed",
            detail=str(error),
            errors=[{"pointer": "/query/h", "code": "invalid_handle", "detail": str(error)}],
        )

    @app.exception_handler(HTTPException)
    async def _http(request: Request, error: HTTPException) -> JSONResponse:
        code = _STATUS_CODES.get(error.status_code, "service_degraded")
        return problem_response(request, code, detail=str(error.detail))
