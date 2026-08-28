"""Liveness and freshness. `/healthz` is the probe; `/v1/health` is the answer to "is it
serving current data" (bp:544)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from glasswell.api.deps import Connection, rows
from glasswell.api.errors import problem_responses
from glasswell.api.examples import GLOSSARY_KEY, dataset, not_a_figure, request_example
from glasswell.api.responses import PENDING, EnvelopeModel, enveloped, iso
from glasswell.status.models import SourceOutcome, SourceState, source_freshness

liveness = APIRouter(tags=["service"])
router = APIRouter(tags=["service"])

# Anything not on this list degrades the service, so a state added later fails closed.
SERVING_STATES = ("current", PENDING)

_SOURCES = """
select s.source_id,
       s.name,
       artifact.fetch_vintage as retrieval_vintage,
       coalesce(artifact_count.manifest_count, 0) as manifest_count,
       artifact.manifest_id as last_manifest_id,
       artifact.fetched_at as last_manifest_fetched_at,
       (select max(v.vintage_date) from lineage.vintages v
         where v.source_id = s.source_id) as declared_vintage,
       p.cadence,
       p.expected_poll_interval,
       p.attempt_timeout,
       a.attempted_at as last_attempt_at,
       a.completed_at as last_attempt_completed_at,
       a.outcome as last_recorded_outcome,
       a.failure_code as last_failure_code,
       a.failure_detail as last_failure_detail,
       coalesce(k.failed_keys, 0) as unresolved_failed_keys,
       coalesce(k.open_keys, 0) as unresolved_open_keys,
       k.oldest_open_attempt_at,
       k.blocking_failure_code,
       k.blocking_failure_detail
  from lineage.sources s
  left join lineage.source_poll_policies p on p.source_id = s.source_id
  left join lateral (
       select observed.manifest_id, observed.fetched_at, observed.fetch_vintage
         from (
              select m.manifest_id, m.fetched_at, m.fetch_vintage,
                     m.fetched_at as observed_at, 0 as observation_rank
                from lineage.manifests m
               where m.source_id = s.source_id
              union all
              select m.manifest_id, m.fetched_at, m.fetch_vintage,
                     f.completed_at as observed_at, 1 as observation_rank
                from lineage.fetch_attempts f
                join lineage.manifests m on m.manifest_id = f.manifest_id
               where f.source_id = s.source_id
                 and f.outcome in ('new', 'unchanged')
         ) observed
        order by observed.observed_at desc, observed.observation_rank desc,
                 observed.manifest_id desc
        limit 1
  ) artifact on true
  left join lateral (
       select count(distinct m.manifest_id) as manifest_count
         from lineage.manifests m
        where m.source_id = s.source_id
           or exists (
              select 1 from lineage.fetch_attempts f
               where f.source_id = s.source_id
                 and f.manifest_id = m.manifest_id
                 and f.outcome in ('new', 'unchanged')
           )
  ) artifact_count on true
  left join lateral (
       select f.attempted_at, f.completed_at, f.outcome, f.failure_code, f.failure_detail
         from lineage.fetch_attempts f
        where f.source_id = s.source_id
        order by f.attempted_at desc, f.attempt_id desc
        limit 1
  ) a on true
  left join lateral (
       select count(*) filter (where latest.outcome = 'failed') as failed_keys,
              count(*) filter (where latest.outcome is null) as open_keys,
              min(latest.attempted_at) filter (where latest.outcome is null)
                  as oldest_open_attempt_at,
              (array_agg(latest.failure_code order by latest.attempted_at desc,
                         latest.attempt_id desc)
                  filter (where latest.outcome = 'failed'))[1] as blocking_failure_code,
              (array_agg(latest.failure_detail order by latest.attempted_at desc,
                         latest.attempt_id desc)
                  filter (where latest.outcome = 'failed'))[1] as blocking_failure_detail
         from (
              select distinct on (f.source_key)
                     f.source_key, f.attempt_id, f.attempted_at, f.outcome,
                     f.failure_code, f.failure_detail
                from lineage.fetch_attempts f
               where f.source_id = s.source_id
               order by f.source_key, f.attempted_at desc, f.attempt_id desc
         ) latest
  ) k on true
 where (%(source_ids)s::text[] is null or s.source_id = any(%(source_ids)s))
 order by s.source_id
"""


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


def source_health_data(
    connection: Connection,
    *,
    observed_at: datetime,
    source_ids: Sequence[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The shared durable poll and registered-artifact freshness view."""
    served: list[dict[str, Any]] = []
    freshness: dict[str, Any] = {}
    for row in rows(
        connection,
        _SOURCES,
        {"source_ids": list(source_ids) if source_ids is not None else None},
    ):
        assessed = source_freshness(
            observed_at=observed_at,
            artifact_at=row["last_manifest_fetched_at"],
            attempted_at=row["last_attempt_at"],
            completed_at=row["last_attempt_completed_at"],
            recorded_outcome=row["last_recorded_outcome"],
            expected_interval=row["expected_poll_interval"],
            attempt_timeout=row["attempt_timeout"],
            cadence=row["cadence"],
            failure_code=row["last_failure_code"],
            failure_detail=row["last_failure_detail"],
            unresolved_failed_keys=row["unresolved_failed_keys"],
            unresolved_open_keys=row["unresolved_open_keys"],
            oldest_open_attempt_at=row["oldest_open_attempt_at"],
            blocking_failure_code=row["blocking_failure_code"],
            blocking_failure_detail=row["blocking_failure_detail"],
        )
        source = {
            "source_id": row["source_id"],
            "name": row["name"],
            "state": assessed.state,
            "retrieval_vintage": iso(row["retrieval_vintage"]),
            "declared_vintage": iso(row["declared_vintage"]),
            "last_manifest_id": row["last_manifest_id"],
            "manifest_count": row["manifest_count"],
            "last_attempt_at": iso(row["last_attempt_at"]),
            "last_outcome": assessed.last_outcome,
            "next_expected_poll": iso(assessed.next_expected_poll),
            "cadence": row["cadence"],
            "freshness_reason": assessed.reason,
        }
        served.append(source)
        freshness[row["source_id"]] = {
            "retrieval_vintage": iso(row["retrieval_vintage"]),
            "declared_vintage": iso(row["declared_vintage"]),
            "state": assessed.state,
            "last_attempt_at": iso(row["last_attempt_at"]),
            "last_outcome": assessed.last_outcome,
            "next_expected_poll": iso(assessed.next_expected_poll),
            "cadence": row["cadence"],
            "reason": assessed.reason,
        }
    return served, freshness
