"""The stranger's entry point (S1) and the error-type registry every `type` URI resolves to."""

from __future__ import annotations

from fastapi import APIRouter, Path, Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from glasswell.api.deps import Connection, rows
from glasswell.api.errors import ERROR_REGISTRY, TYPE_BASE, ProblemError, problem_responses
from glasswell.api.examples import EXAMPLE_ERROR_CODE, dataset, not_a_figure, request_example
from glasswell.api.responses import EnvelopeModel, enveloped, iso

router = APIRouter(tags=["service"])

API_VERSION = "v1"

RESOURCE_LINKS = {
    "health": "/v1/health",
    "wells": "/v1/wells",
    "explain": "/v1/explain?h=",
    "derivations": "/v1/derivations",
    "manifests": "/v1/manifests",
    "conformance": "/v1/conformance",
    "quarantine": "/v1/quarantine",
    "glossary": "/v1/glossary",
    "glossary_index": "/v1/glossary/index",
    "tiles": "/v1/tiles",
    "openapi": "/openapi.json",
}

_VINTAGES = """
select source_id, vintage_date, rows_examined, rows_appended, promotion_derivation_id
  from lineage.vintages
 order by source_id, vintage_date desc
"""


class PublishedVintage(BaseModel):
    source_id: str = Field(description="Source the vintage was promoted from.")
    vintage_date: str = Field(description="Knowledge-time label of the promotion.")
    rows_examined: int = Field(
        description="Rows read during the promotion.",
        json_schema_extra=not_a_figure(
            "Promotion bookkeeping from lineage.vintages, not a served observation."
        ),
    )
    rows_appended: int = Field(
        description="Rows appended; restatements append, never update.",
        json_schema_extra=not_a_figure(
            "Promotion bookkeeping from lineage.vintages, not a served observation."
        ),
    )
    promotion_derivation_id: str | None = Field(description="Derivation that did the promotion.")


class ErrorCode(BaseModel):
    code: str = Field(description="Registry code, also the last segment of the type URI.")
    status: int = Field(
        description="HTTP status this code is served with.",
        json_schema_extra=not_a_figure("An HTTP status code in the error index."),
    )
    title: str = Field(description="Short summary of the failure.")
    type: str = Field(description="Absolute, resolvable type URI.")
    emitted_by_this_slice: bool = Field(
        description="False for codes the frozen registry defines but this slice cannot emit."
    )


class ServiceIndex(BaseModel):
    api_version: str = Field(description="Served API version; the path prefix is the contract.")
    published_vintages: list[PublishedVintage] = Field(description="What has been promoted.")
    error_codes: list[ErrorCode] = Field(description="The frozen error registry (SB-04 §2.4).")
    deprecations: list[dict] = Field(description="Deprecations in force; empty in this slice.")


class ErrorType(BaseModel):
    code: str = Field(description="The registry code.")
    status: int = Field(
        description="HTTP status this code is served with.",
        json_schema_extra=not_a_figure(
            "An HTTP status code on the error-type description."
        ),
    )
    title: str = Field(description="Short summary of the failure.")
    description: str = Field(description="What causes it and what a caller should do.")
    type: str = Field(description="Absolute type URI, identical to the one in problem bodies.")
    emitted_by_this_slice: bool = Field(description="Whether this slice can emit the code.")


def _error_codes() -> list[dict]:
    return [
        {
            "code": code,
            "status": spec.status,
            "title": spec.title,
            "type": f"{TYPE_BASE}/{code}",
            "emitted_by_this_slice": spec.emitted,
        }
        for code, spec in ERROR_REGISTRY.items()
    ]


@router.get(
    "",
    operation_id="get_service_index",
    summary="Service index",
    description=(
        "Version, the vintages published per source, the complete error registry and a link"
        " to every resource family. This is the one URL a stranger needs to start from."
    ),
    response_model=EnvelopeModel[ServiceIndex],
    openapi_extra={
        **request_example(),
        # One operation, one dataset: this points at `/error_codes` and only there. The
        # vintages this response also carries are `list_vintages`'s dataset, not a second one.
        **dataset(
            id="problems",
            title="Problems",
            group="service",
            collection_pointer="/error_codes",
            row_id=["/code"],
            detail_operation="get_error_type",
            columns={
                "default": ["/code", "/status", "/title", "/type", "/emitted_by_this_slice"],
            },
            intro="nb_dataset_problems",
            order=51,
        ),
    },
    responses=problem_responses("service_degraded"),
)
def get_service_index(request: Request, connection: Connection) -> JSONResponse:
    published = [
        {
            "source_id": row["source_id"],
            "vintage_date": iso(row["vintage_date"]),
            "rows_examined": row["rows_examined"],
            "rows_appended": row["rows_appended"],
            "promotion_derivation_id": row["promotion_derivation_id"],
        }
        for row in rows(connection, _VINTAGES)
    ]
    data = {
        "api_version": API_VERSION,
        "published_vintages": published,
        "error_codes": _error_codes(),
        "deprecations": [],
    }
    return enveloped(request, data, links=RESOURCE_LINKS)


@router.get(
    "/errors/{code}",
    operation_id="get_error_type",
    summary="Describe one error code",
    description=(
        "The human-readable description behind a `type` URI. Every problem body a caller"
        " can receive names a code that resolves here."
    ),
    response_model=EnvelopeModel[ErrorType],
    openapi_extra=request_example(path={"code": EXAMPLE_ERROR_CODE}),
    responses=problem_responses("not_found"),
)
def get_error_type(
    request: Request,
    code: str = Path(description="Error registry code, e.g. lineage_unresolved."),
) -> JSONResponse:
    spec = ERROR_REGISTRY.get(code)
    if spec is None:
        raise ProblemError("not_found", detail=f"no error code {code!r} in the registry")
    data = {
        "code": code,
        "status": spec.status,
        "title": spec.title,
        "description": spec.description,
        "type": f"{TYPE_BASE}/{code}",
        "emitted_by_this_slice": spec.emitted,
    }
    return enveloped(request, data)
