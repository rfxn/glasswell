"""Liveness and freshness. `/healthz` is the probe; `/v1/health` is the answer to "is it
serving current data" (bp:544)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from glasswell.api.deps import Connection
from glasswell.api.errors import problem_responses
from glasswell.api.examples import GLOSSARY_KEY, dataset, not_a_figure, request_example
from glasswell.api.responses import PENDING, EnvelopeModel, enveloped
from glasswell.status.models import SourceOutcome, SourceState
from glasswell.status.source_health import source_health_data

liveness = APIRouter(tags=["service"])
router = APIRouter(tags=["service"])

# Anything not on this list degrades the service, so a state added later fails closed.
SERVING_STATES = ("current", PENDING)




class Liveness(BaseModel):
    ok: bool = Field(description="True whenever the process is serving. Touches no store.")


class SourceHealth(BaseModel):
    source_id: str = Field(
        description="Registry id of the upstream source.",
        json_schema_extra={GLOSSARY_KEY: "gt_source"},
    )
    name: str = Field(description="Human-readable source name.")
    state: SourceState = Field(description="current, stale or pending.")
    # `format: date` so the explorer's grid classifies these as dates rather than as prose,
    # which is what every other date on the surface gets from its own type (C7 §8).
    retrieval_vintage: str | None = Field(
        description="Date of the newest manifest fetched.",
        json_schema_extra={"format": "date", GLOSSARY_KEY: "gt_knowledge_time"},
    )
    declared_vintage: str | None = Field(
        description="Newest vintage promoted from this source.",
        json_schema_extra={"format": "date", GLOSSARY_KEY: "gt_knowledge_time"},
    )
    last_manifest_id: str | None = Field(description="Newest manifest registered.")
    manifest_count: int = Field(
        description="Manifests registered for this source.",
        json_schema_extra=not_a_figure(
            "Count of registered manifests per source on the health page."
        ),
    )
    last_attempt_at: datetime | None = Field(
        description="When the newest independently committed source poll began."
    )
    last_outcome: SourceOutcome | None = Field(
        description="attempted, new, unchanged, failed, interrupted, or null before any poll."
    )
    next_expected_poll: datetime | None = Field(
        description="Cadence-derived next expected poll; null for event-driven or unknown cadence."
    )
    cadence: str | None = Field(
        default=None,
        max_length=80,
        description="Source-specific expected cadence from the single poll-policy registry.",
    )
    freshness_reason: str = Field(
        min_length=1,
        max_length=512,
        description=(
            "Bounded reason for the state, including sanitized failure limits where needed."
        ),
    )


class Health(BaseModel):
    state: str = Field(description="ok when no source is stale, otherwise degraded.")
    stores: dict[str, str] = Field(description="Reachability per backing store.")
    sources: list[SourceHealth] = Field(description="Freshness per registered source.")
    degraded_sources: list[str] = Field(description="Sources whose data has gone stale, named.")
    pending_sources: list[str] = Field(
        description="Registered sources that have never been fetched, named."
    )


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
        "Per-source durable poll outcomes, artifact and declared vintages, expected cadence,"
        " store state, and an overall `ok`/`degraded`. A current unchanged poll keeps an older"
        " artifact current; a failed or interrupted poll cannot be hidden by that artifact."
        " Sources with no completed evidence are explicit pending or stale states rather than"
        " inferred successes."
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
                    "/state",
                    "/last_attempt_at",
                    "/last_outcome",
                    "/next_expected_poll",
                    "/cadence",
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
    served, freshness = source_health_data(connection, observed_at=datetime.now(UTC))
    degraded = [item["source_id"] for item in served if item["state"] not in SERVING_STATES]
    pending = [item["source_id"] for item in served if item["state"] == PENDING]
    data = {
        "state": "degraded" if degraded else "ok",
        "stores": {"postgres": "ok"},
        "sources": served,
        "degraded_sources": degraded,
        "pending_sources": pending,
    }
    return enveloped(request, data, source_freshness=freshness)
