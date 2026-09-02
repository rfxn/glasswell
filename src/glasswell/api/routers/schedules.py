"""The job registry as a served collection: what is scheduled, on whose decision, and when.

Two clocks, like `/v1/jurisdictions`: `as_of` is the knowledge cut, so a schedule published
after it is not served under it, and a restatement at the same `effective_from` supersedes only
from the day it was published. No figure is served here. A cadence, a timeout and a run's
duration are operational inventory, not petroleum quantities, and each is exempted by name in
`non_figure_allowlist.yml` rather than carrying a handle that would resolve to nothing.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query, Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from glasswell.api.deps import AsOf, Connection, Cursor, ExplainEffect, rows
from glasswell.api.errors import ProblemError, problem_responses
from glasswell.api.examples import GLOSSARY_KEY, dataset, request_example, semantics
from glasswell.api.pagination import (
    DEFAULT_LIMIT,
    decode_cursor,
    encode_cursor,
    next_link,
    page,
    query_fingerprint,
)
from glasswell.api.responses import EnvelopeModel, enveloped, inline_for, iso
from glasswell.lineage.schedules import (
    ScheduledJob,
    ScheduleRegistry,
    ScheduleRegistryError,
    load_schedules,
)

router = APIRouter(tags=["service"])

SCHEDULE_LIMIT_CAP = 200
# Each string below is the allowlist entry's reason verbatim: SB-08 A-2 serves the exempter's
# own words on the property, and the two files are held to each other by test_not_a_figure.
DURATION_REASON = (
    "Wall time between a run's start and its close, from operational run evidence; its grain"
    " and observation time are stated beside it."
)
INTERVAL_REASON = (
    "How often a job is asked to run, in seconds. A cadence is a scheduling decision recorded"
    " as a conformance rule, not a measured quantity."
)
TIMEOUT_REASON = (
    "The time ceiling a job's transient unit is given, bounded by the scheduler unit's own"
    " budget. An operational bound, not a measured quantity."
)
CALENDAR_REASON = (
    "The calendar day a monthly cadence fires on. A position in the month, not a measurement."
)
EXIT_REASON = "A process exit status. An outcome code, not a quantity."
MEMORY_REASON = (
    "Peak resident bytes a run reached, read from systemd, and absent rather than zeroed where"
    " systemd is older than 254. Operational inventory, not a petroleum figure."
)

_PUBLICATION_BOUNDS = """
select min(published_at) as earliest, max(published_at) as latest from lineage.job_schedules
"""

_RECENT_RUNS = """
select run_id, planned_at, started_at, completed_at, outcome, refusal_code, exit_status,
       memory_peak_bytes, transient_unit, launched_by
  from lineage.job_runs
 where job_id = %(job_id)s
 order by planned_at desc, run_id desc
 limit %(limit)s
"""

RUN_HISTORY = 20

ScheduleLimit = Annotated[
    int,
    Query(
        ge=1,
        le=SCHEDULE_LIMIT_CAP,
        description=f"Page size, {DEFAULT_LIMIT} by default, {SCHEDULE_LIMIT_CAP} at most.",
    ),
]


class Cadence(BaseModel):
    note: str = Field(description="The cadence in one line, as the registry states it.")
    interval_seconds: int | None = Field(
        description="The interval a cadence job fires on, or null where it fires on a day.",
        json_schema_extra={"x-glasswell-not-a-figure": INTERVAL_REASON},
    )
    monthly_on_day: int | None = Field(
        description="The calendar day a monthly cadence fires on, or null.",
        json_schema_extra={"x-glasswell-not-a-figure": CALENDAR_REASON},
    )


class Limits(BaseModel):
    memory_max: str | None = Field(description="The memory ceiling its transient unit gets.")
    timeout_seconds: int | None = Field(
        description="The time ceiling its transient unit gets, bounded by the tick's own.",
        json_schema_extra={"x-glasswell-not-a-figure": TIMEOUT_REASON},
    )


class Decision(BaseModel):
    """Why this cadence, and where the decision is recorded.

    `rule_id` is null on exactly the rows an external timer owns: their cadence lives in that
    unit's `OnCalendar=`, which is a tree artefact under review, so the row names the unit pair
    instead of minting a rule that would only restate it.
    """

    rule_id: str | None = Field(
        description="The cadence rule, resolvable at /v1/conformance/{rule_id}, or null.",
        json_schema_extra={GLOSSARY_KEY: "gt_conformance_rule"},
    )
    rationale: str = Field(description="Why this job is scheduled the way it is.")
    effective_from: str = Field(
        description="Valid time: the date this schedule takes effect from.",
        json_schema_extra={GLOSSARY_KEY: "gt_knowledge_time"},
    )
    published_at: str = Field(
        description="Knowledge time: the date glasswell published it.",
        json_schema_extra={GLOSSARY_KEY: "gt_knowledge_time"},
    )
    external_timer_unit: str | None = Field(
        description="The systemd timer that owns this job, where one does.",
        json_schema_extra={GLOSSARY_KEY: "gt_timer"},
    )
    external_service_unit: str | None = Field(
        description="The service that timer triggers, where one does.",
        json_schema_extra={GLOSSARY_KEY: "gt_timer"},
    )


class Dependency(BaseModel):
    depends_on_job_id: str = Field(description="The job this one reads.")
    trigger_on: str = Field(
        description="`changed` reacts to new input; `completed` is ordering only."
    )
    rationale: str = Field(description="Why the edge exists.")


class RunRow(BaseModel):
    run_id: str = Field(description="The run's own id.")
    planned_at: str = Field(description="The due instant this run answers, not the tick clock.")
    started_at: str | None = Field(description="When the transient unit started, if it did.")
    completed_at: str | None = Field(description="When the row was closed.")
    outcome: str | None = Field(
        description="would_run, ran, failed, interrupted or refused; null while open."
    )
    refusal_code: str | None = Field(description="Why it did not run, where it did not.")
    refusal_class: str | None = Field(
        description="informational, waiting or fault, from the registry vocabulary."
    )
    duration_seconds: int | None = Field(
        description="Wall time between start and close, where both are recorded.",
        json_schema_extra={"x-glasswell-not-a-figure": DURATION_REASON},
    )
    exit_status: int | None = Field(
        description="The process exit status, where a process ran.",
        json_schema_extra={"x-glasswell-not-a-figure": EXIT_REASON},
    )
    memory_peak_bytes: int | None = Field(
        description="Peak resident bytes, absent where systemd is older than 254.",
        json_schema_extra={"x-glasswell-not-a-figure": MEMORY_REASON},
    )
    launched_by: str = Field(description="`scheduler` or `manual`.")


class RefusalCodeRow(BaseModel):
    code: str = Field(description="The refusal code.")
    severity_class: str = Field(description="informational, waiting or fault.")
    sentence: str = Field(description="What the page says when a job carries this code.")


class ScheduleRow(BaseModel):
    job_id: str = Field(description="The registry's own id for the job.")
    label: str = Field(description="The job's name, served rather than mapped in the client.")
    kind: str = Field(description="`ingest`, `mart` or `maintenance`.")
    entry_point: str = Field(description="The one command this job runs.")
    jurisdiction: str | None = Field(
        description="The jurisdiction it serves, or null for cross-jurisdiction work.",
        json_schema_extra={GLOSSARY_KEY: "gt_jurisdiction"},
    )
    run_as: str | None = Field(
        description="The uid its transient unit drops to, or null where its own unit decides."
    )
    trigger: str = Field(
        description="`cadence`, `after_dependency`, `manual` or `external_timer`."
    )
    launch_mode: str = Field(
        description="`observe` computes the plan and records it; `launch` runs it."
    )
    enabled: bool = Field(description="Whether the resolved row is considered by a tick.")
    concurrency_group: str = Field(description="Jobs in one group serialise.")
    cadence: Cadence = Field(description="How often, and on what.")
    next_due_at: str | None = Field(
        description="When it is next due. Null for manual and after_dependency jobs."
    )
    limits: Limits = Field(description="The ceilings its transient unit is given.")
    legacy_unit: str | None = Field(
        description="The still-armed unit that drives this job while the row observes.",
        json_schema_extra={GLOSSARY_KEY: "gt_timer"},
    )
    source_ids: list[str] = Field(
        description="Every registered source this job polls.",
        json_schema_extra={GLOSSARY_KEY: "gt_source"},
    )
    dependencies: list[Dependency] = Field(description="What it waits on, and why.")
    decision: Decision = Field(description="The R8 record behind the cadence.")


class ScheduleDetail(ScheduleRow):
    last_runs: list[RunRow] = Field(description="The most recent runs, newest first.")
    refusal_codes: list[RefusalCodeRow] = Field(
        description="The refusal vocabulary and its three severity classes, as registered."
    )


def _registry(connection, as_of: date | None) -> ScheduleRegistry:
    try:
        return load_schedules(connection, as_of)
    except ScheduleRegistryError as refusal:
        raise ProblemError("service_degraded", detail=str(refusal)) from refusal


def _row(job: ScheduledJob, *, next_due: str | None) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "label": job.label,
        "kind": job.kind,
        "entry_point": job.entry_point,
        "jurisdiction": job.jurisdiction,
        "run_as": job.run_as,
        "trigger": job.trigger,
        "launch_mode": job.launch_mode,
        "enabled": job.enabled,
        "concurrency_group": job.concurrency_group,
        "cadence": {
            "note": job.cadence_note,
            "interval_seconds": (
                int(job.cadence_interval.total_seconds())
                if job.cadence_interval is not None
                else None
            ),
            "monthly_on_day": job.cadence_monthly_on_day,
        },
        "next_due_at": next_due,
        "limits": {"memory_max": job.memory_max, "timeout_seconds": job.timeout_seconds},
        "legacy_unit": job.legacy_unit,
        "source_ids": list(job.source_ids),
        "dependencies": [
            {
                "depends_on_job_id": edge.depends_on_job_id,
                "trigger_on": edge.trigger_on,
                "rationale": edge.rationale,
            }
            for edge in job.dependencies
        ],
        "decision": {
            "rule_id": job.rule_id,
            "rationale": job.rationale,
            "effective_from": iso(job.effective_from),
            "published_at": iso(job.published_at),
            "external_timer_unit": job.external_timer_unit,
            "external_service_unit": job.external_service_unit,
        },
    }


def _due_map(connection, registry: ScheduleRegistry) -> dict[str, str | None]:
    """Imported here rather than at module scope: the planner reads five lineage relations and
    the API should pay for that only when this route is asked."""
    from datetime import UTC, datetime

    from glasswell.scheduler.plan import collect_evidence, next_due_at

    now = datetime.now(UTC)
    evidence = collect_evidence(
        connection,
        now=now,
        source_ids=[source for job in registry for source in job.source_ids],
    )
    return {job.job_id: iso(next_due_at(job, evidence, now)) for job in registry}


@router.get(
    "/schedules",
    operation_id="list_schedules",
    summary="List scheduled jobs",
    description=(
        "Every registered job, what drives it, the conformance rule that decided its cadence,"
        " and when it is next due. Schedules are append-only under two clocks: `as_of` is the"
        " knowledge cut, so a schedule published after it is not served under it, and a"
        " restatement at the same effective date supersedes only from the day it was"
        " published. A row whose `launch_mode` is `observe` has its plan computed and"
        " recorded; the unit named in `legacy_unit` is what actually runs it."
    ),
    response_model=EnvelopeModel[list[ScheduleRow]],
    openapi_extra={
        **request_example(query={"kind": "ingest", "limit": 5}),
        **dataset(
            id="schedules",
            title="Scheduled jobs",
            group="service",
            collection_pointer="",
            row_id=["/job_id"],
            facets=["kind", "trigger"],
            columns={
                "default": [
                    "/job_id",
                    "/label",
                    "/kind",
                    "/trigger",
                    "/cadence",
                    "/next_due_at",
                    "/launch_mode",
                ],
                "sort": "/job_id",
            },
            intro="nb_dataset_schedules",
            order=44,
        ),
        **semantics(
            as_of={
                "glossary": "gt_knowledge_time",
                "so": (
                    "Serves the schedule published at or before the cut. A cadence corrected"
                    " later is not visible under an earlier cut, which is the whole reason"
                    " this registry carries two clocks rather than one."
                ),
            },
            kind={
                "so": "Filters to ingest, mart or maintenance jobs.",
            },
            trigger={
                "so": (
                    "Filters to what drives the job: a cadence, another job completing, an"
                    " operator, or a systemd timer this scheduler does not own."
                ),
            },
            limit={
                "so": (
                    f"Capped at {SCHEDULE_LIMIT_CAP}; the default remains {DEFAULT_LIMIT}."
                    " The registry is small, and it is a page so that it stays one when a"
                    " fifth jurisdiction registers its jobs."
                ),
            },
        ),
    },
    responses=problem_responses(
        "validation_failed",
        "cursor_malformed",
        "cursor_query_mismatch",
        "as_of_out_of_range",
        "service_degraded",
    ),
)
def list_schedules(
    request: Request,
    connection: Connection,
    explain: ExplainEffect,
    cursor: Cursor = None,
    limit: ScheduleLimit = DEFAULT_LIMIT,
    as_of: AsOf = None,
    kind: Annotated[str | None, Query(description="Filter to one job kind.")] = None,
    trigger: Annotated[
        str | None, Query(description="Filter to one trigger.")
    ] = None,
) -> JSONResponse:
    filters = {"as_of": as_of, "kind": kind, "trigger": trigger}
    fingerprint = query_fingerprint(filters)
    decoded = decode_cursor(cursor, fingerprint=fingerprint) if cursor is not None else None
    bounds = rows(connection, _PUBLICATION_BOUNDS, {})[0]
    if as_of is not None and bounds["earliest"] is not None and as_of < bounds["earliest"]:
        raise ProblemError(
            "as_of_out_of_range",
            detail=(
                f"as_of {as_of.isoformat()} precedes the earliest published schedule"
                f" {bounds['earliest'].isoformat()}, so none was published yet"
            ),
        )
    registry = _registry(connection, as_of)
    due = _due_map(connection, registry)
    resolved = [
        job
        for job in registry
        if (kind is None or job.kind == kind)
        and (trigger is None or job.trigger == trigger)
    ]
    if decoded is not None:
        resolved = [job for job in resolved if job.job_id > decoded.key]
    items, has_more = page(
        [_row(job, next_due=due.get(job.job_id)) for job in resolved[: limit + 1]], limit
    )
    next_cursor = (
        encode_cursor(
            key=items[-1]["job_id"],
            tiebreak="",
            as_of=registry.knowledge_as_of,
            fingerprint=fingerprint,
            valid_as_of=registry.valid_as_of,
        )
        if has_more and items
        else None
    )
    labels = {
        pointer: term
        for index, _ in enumerate(items)
        for pointer, term in {
            f"/{index}/cadence": "gt_cadence",
            f"/{index}/next_due_at": "gt_next_due",
            f"/{index}/launch_mode": "gt_observing",
            f"/{index}/job_id": "gt_scheduled_job",
            f"/{index}/source_ids": "gt_source",
            f"/{index}/legacy_unit": "gt_timer",
        }.items()
    }
    return enveloped(
        request,
        items,
        as_of=registry.knowledge_as_of,
        as_of_requested=iso(as_of) or "latest",
        labels=labels,
        next_cursor=next_cursor,
        links={
            "next": next_link("/v1/schedules", filters | {"limit": limit}, next_cursor)
            if next_cursor
            else None
        },
        explain=inline_for(connection, explain),
    )


@router.get(
    "/schedules/{job_id}",
    operation_id="get_schedule",
    summary="Read one scheduled job",
    description=(
        "One job's resolved schedule, the sources it polls, the jobs it waits on, the"
        " conformance rule behind its cadence, its recent runs, and the refusal vocabulary a"
        " run's code is drawn from. A refusal names why a job did not run; it is not the same"
        " fact as a failure, and the page does not collapse them."
    ),
    response_model=EnvelopeModel[ScheduleDetail],
    openapi_extra=request_example(path={"job_id": "ingest_nd_gis"}),
    responses=problem_responses("not_found", "as_of_out_of_range", "service_degraded"),
)
def get_schedule(
    request: Request,
    connection: Connection,
    explain: ExplainEffect,
    job_id: Annotated[str, Path(description="The registry id of the job to read.")],
    as_of: AsOf = None,
) -> JSONResponse:
    registry = _registry(connection, as_of)
    job = registry.get(job_id)
    if job is None:
        raise ProblemError(
            "not_found", detail=f"{job_id} resolves to no schedule at this knowledge cut"
        )
    due = _due_map(connection, registry)
    history = rows(connection, _RECENT_RUNS, {"job_id": job_id, "limit": RUN_HISTORY})
    item = _row(job, next_due=due.get(job_id))
    item["last_runs"] = [
        {
            "run_id": run["run_id"],
            "planned_at": iso(run["planned_at"]),
            "started_at": iso(run["started_at"]),
            "completed_at": iso(run["completed_at"]),
            "outcome": run["outcome"],
            "refusal_code": run["refusal_code"],
            "refusal_class": registry.severity_of(run["refusal_code"]),
            "duration_seconds": (
                int((run["completed_at"] - run["started_at"]).total_seconds())
                if run["started_at"] and run["completed_at"]
                else None
            ),
            "exit_status": run["exit_status"],
            "memory_peak_bytes": run["memory_peak_bytes"],
            "launched_by": run["launched_by"],
        }
        for run in history
    ]
    item["refusal_codes"] = [
        {
            "code": code.code,
            "severity_class": code.severity_class,
            "sentence": code.sentence,
        }
        for code in sorted(registry.refusal_codes.values(), key=lambda row: row.code)
    ]
    return enveloped(
        request,
        item,
        as_of=registry.knowledge_as_of,
        as_of_requested=iso(as_of) or "latest",
        labels={
            "/cadence": "gt_cadence",
            "/next_due_at": "gt_next_due",
            "/launch_mode": "gt_observing",
            "/job_id": "gt_scheduled_job",
            "/last_runs": "gt_refusal",
        },
        explain=inline_for(connection, explain),
    )
