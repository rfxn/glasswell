"""Liveness and freshness. `/healthz` is the probe; `/v1/health` is the answer to "is it
serving current data" (bp:544)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from glasswell.api.deps import Connection, rows, today
from glasswell.api.errors import problem_responses
from glasswell.api.examples import dataset, request_example
from glasswell.api.responses import EnvelopeModel, enveloped, freshness_state, iso

liveness = APIRouter(tags=["service"])
router = APIRouter(tags=["service"])

_SOURCES = """
select s.source_id,
       s.name,
       (select max(m.fetch_vintage) from lineage.manifests m
         where m.source_id = s.source_id) as retrieval_vintage,
       (select count(*) from lineage.manifests m
         where m.source_id = s.source_id) as manifest_count,
       (select m.manifest_id from lineage.manifests m
         where m.source_id = s.source_id
         order by m.fetched_at desc, m.manifest_id desc limit 1) as last_manifest_id,
       (select max(v.vintage_date) from lineage.vintages v
         where v.source_id = s.source_id) as declared_vintage
  from lineage.sources s
 order by s.source_id
"""


class Liveness(BaseModel):
    ok: bool = Field(description="True whenever the process is serving. Touches no store.")


class SourceHealth(BaseModel):
    source_id: str = Field(description="Registry id of the upstream source.")
    name: str = Field(description="Human-readable source name.")
    state: str = Field(description="current, stale or never_fetched.")
    retrieval_vintage: str | None = Field(description="Date of the newest manifest fetched.")
    declared_vintage: str | None = Field(description="Newest vintage promoted from this source.")
    last_manifest_id: str | None = Field(description="Newest manifest registered.")
    manifest_count: int = Field(description="Manifests registered for this source.")


class Health(BaseModel):
    state: str = Field(description="ok when every source is current, otherwise degraded.")
    stores: dict[str, str] = Field(description="Reachability per backing store.")
    sources: list[SourceHealth] = Field(description="Freshness per registered source.")
    degraded_sources: list[str] = Field(description="Sources that are not current, named.")


@liveness.get(
    "/healthz",
    operation_id="get_healthz",
    summary="Liveness probe",
    description=(
        "Returns `{\"ok\": true}` with no envelope and no database access. SB-06 §1.3's"
        " probe target; it says the process is up, not that the data is fresh — use"
        " `/v1/health` for that."
    ),
    response_model=Liveness,
    openapi_extra=request_example(),
    responses=problem_responses("service_degraded"),
)
def get_healthz() -> Liveness:
    return Liveness(ok=True)


@router.get(
    "/health",
    operation_id="get_health",
    summary="Source freshness and store reachability",
    description=(
        "Per-source retrieval and declared vintages, the state of each store, and an"
        " overall `ok`/`degraded`. A source that has never been fetched is reported as"
        " `never_fetched` and degrades the service state rather than being hidden."
    ),
    response_model=EnvelopeModel[Health],
    openapi_extra={
        **request_example(),
        **dataset(
            id="sources",
            title="Sources & freshness",
            group="service",
            collection_pointer="/sources",
            row_id=["/source_id"],
            columns={
                "default": [
                    "/source_id",
                    "/name",
                    "/state",
                    "/retrieval_vintage",
                    "/declared_vintage",
                    "/manifest_count",
                ],
                "sort": "/source_id",
            },
            intro="nb_dataset_sources",
            order=50,
        ),
    },
    responses=problem_responses("service_degraded"),
)
def get_health(request: Request, connection: Connection) -> JSONResponse:
    now = today()
    served: list[dict[str, Any]] = []
    freshness: dict[str, Any] = {}
    for row in rows(connection, _SOURCES):
        state = freshness_state(row["retrieval_vintage"], today=now)
        served.append(
            {
                "source_id": row["source_id"],
                "name": row["name"],
                "state": state,
                "retrieval_vintage": iso(row["retrieval_vintage"]),
                "declared_vintage": iso(row["declared_vintage"]),
                "last_manifest_id": row["last_manifest_id"],
                "manifest_count": row["manifest_count"],
            }
        )
        freshness[row["source_id"]] = {
            "retrieval_vintage": iso(row["retrieval_vintage"]),
            "declared_vintage": iso(row["declared_vintage"]),
            "state": state,
        }
    degraded = [item["source_id"] for item in served if item["state"] != "current"]
    data = {
        "state": "degraded" if degraded else "ok",
        "stores": {"postgres": "ok"},
        "sources": served,
        "degraded_sources": degraded,
    }
    return enveloped(request, data, source_freshness=freshness)
