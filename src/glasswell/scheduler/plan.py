"""What is due, in what order, and why anything that is not runs anyway.

Not due is silent; due but blocked appends a refusal naming a code, so the ledger says why a
job did not run rather than saying nothing. The due rule itself is not reimplemented here: an
interval job asks the same resolver `/v1/health` asks, so one rule decides freshness for the
page and for the plan.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import psycopg
from psycopg.rows import dict_row

from glasswell.lineage.schedules import ScheduledJob, ScheduleRegistry
from glasswell.status.source_health import source_health_data

Action = Literal["would_run", "run", "refused"]

_LAST_RAN = """
select job_id,
       max(completed_at) as ran_at,
       max(completed_at) filter (where derivation_id is not null) as derived_at
  from lineage.job_runs
 where outcome = 'ran'
 group by job_id
"""

_LAST_OUTCOME = """
select distinct on (job_id) job_id, outcome, completed_at
  from lineage.job_runs
 where outcome in ('ran', 'failed', 'interrupted')
 order by job_id, planned_at desc, run_id desc
"""

_NEW_FETCHES = """
select source_id, max(completed_at) as changed_at
  from lineage.fetch_attempts
 where outcome = 'new'
 group by source_id
"""

# The interval belongs to the source, not to the job: the first-observation rule turns on
# whether the SOURCE carries one, so a cadence row over sources that carry none stays not due
# and the parity gate reddens rather than the job silently never firing.
_SOURCE_INTERVALS = """
select source_id, expected_poll_interval from lineage.source_poll_policies
"""


@dataclass(frozen=True, slots=True)
class PlanEntry:
    job_id: str
    planned_at: datetime
    action: Action
    refusal_code: str | None = None
    reason: str = ""


@dataclass(frozen=True, slots=True)
class TickPlan:
    observed_at: datetime
    entries: tuple[PlanEntry, ...]

    def __iter__(self):
        return iter(self.entries)

    @property
    def refusals(self) -> tuple[PlanEntry, ...]:
        return tuple(entry for entry in self.entries if entry.action == "refused")


@dataclass(frozen=True, slots=True)
class Evidence:
    freshness: Mapping[str, Mapping[str, object]]
    source_interval: Mapping[str, timedelta | None]
    ran_at: Mapping[str, datetime]
    derived_at: Mapping[str, datetime]
    last_outcome: Mapping[str, str]
    fetched_new_at: Mapping[str, datetime]


def hour_of(now: datetime) -> datetime:
    """Truncation is what makes the plan key stable, so repeated ticks collapse to one row."""
    return now.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def _parse(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def collect_evidence(
    connection: psycopg.Connection, *, now: datetime, source_ids: Sequence[str]
) -> Evidence:
    _served, freshness = source_health_data(
        connection, observed_at=now, source_ids=sorted(set(source_ids)) or None
    )
    ran_at: dict[str, datetime] = {}
    derived_at: dict[str, datetime] = {}
    last_outcome: dict[str, str] = {}
    fetched_new_at: dict[str, datetime] = {}
    intervals: dict[str, timedelta | None] = {}
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(_LAST_RAN)
        for row in cursor.fetchall():
            if row["ran_at"] is not None:
                ran_at[row["job_id"]] = row["ran_at"]
            if row["derived_at"] is not None:
                derived_at[row["job_id"]] = row["derived_at"]
        cursor.execute(_LAST_OUTCOME)
        for row in cursor.fetchall():
            last_outcome[row["job_id"]] = row["outcome"]
        cursor.execute(_NEW_FETCHES)
        for row in cursor.fetchall():
            if row["changed_at"] is not None:
                fetched_new_at[row["source_id"]] = row["changed_at"]
        cursor.execute(_SOURCE_INTERVALS)
        for row in cursor.fetchall():
            intervals[row["source_id"]] = row["expected_poll_interval"]
    return Evidence(
        freshness=freshness,
        source_interval=intervals,
        ran_at=ran_at,
        derived_at=derived_at,
        last_outcome=last_outcome,
        fetched_new_at=fetched_new_at,
    )


def monthly_occurrence(now: datetime, day: int) -> datetime:
    """The most recent occurrence of a calendar day at or before `now`, at midnight UTC."""
    moment = now.astimezone(UTC)
    if moment.day >= day:
        return moment.replace(day=day, hour=0, minute=0, second=0, microsecond=0)
    previous = moment.replace(day=1) - timedelta(days=1)
    return previous.replace(day=day, hour=0, minute=0, second=0, microsecond=0)


def _interval_due(job: ScheduledJob, evidence: Evidence, now: datetime) -> datetime | None:
    if not job.source_ids:
        # A mart with a clock of its own: due against its own last run, not a source's poll.
        last = evidence.ran_at.get(job.job_id)
        if last is None:
            return hour_of(now)
        due_at = last + (job.cadence_interval or timedelta(0))
        return due_at if now >= due_at else None

    expected = [
        _parse(evidence.freshness.get(source_id, {}).get("next_expected_poll"))
        for source_id in job.source_ids
    ]
    attempted = [
        evidence.freshness.get(source_id, {}).get("last_attempt_at")
        for source_id in job.source_ids
    ]
    if all(instant is None for instant in expected):
        # First observation: the resolver returns nothing for a source never polled, whatever
        # its interval, so three registered jobs would have been permanently not due.
        carries_interval = any(
            evidence.source_interval.get(source_id) is not None
            for source_id in job.source_ids
        )
        if carries_interval and all(value is None for value in attempted):
            return hour_of(now)
        return None
    earliest = min(instant for instant in expected if instant is not None)
    return earliest if now >= earliest else None


def _dependency_event(
    parent: ScheduledJob, trigger_on: str, evidence: Evidence
) -> datetime | None:
    if trigger_on == "completed":
        return evidence.ran_at.get(parent.job_id)
    if parent.kind == "ingest":
        instants = [
            evidence.fetched_new_at[source_id]
            for source_id in parent.source_ids
            if source_id in evidence.fetched_new_at
        ]
        return max(instants) if instants else None
    return evidence.derived_at.get(parent.job_id)


def due_for(
    job: ScheduledJob, registry: ScheduleRegistry, evidence: Evidence, now: datetime
) -> PlanEntry | None:
    if job.trigger == "manual":
        return None
    if job.trigger == "cadence":
        if job.cadence_monthly_on_day is not None:
            occurrence = monthly_occurrence(now, job.cadence_monthly_on_day)
            last = evidence.ran_at.get(job.job_id)
            if last is not None and last >= occurrence:
                return None
            return PlanEntry(job.job_id, occurrence, "would_run")
        due_at = _interval_due(job, evidence, now)
        return None if due_at is None else PlanEntry(job.job_id, due_at, "would_run")

    events: list[datetime] = []
    failed: list[str] = []
    never: list[str] = []
    for edge in job.dependencies:
        parent = registry.get(edge.depends_on_job_id)
        if parent is None:
            never.append(edge.depends_on_job_id)
            continue
        if evidence.last_outcome.get(parent.job_id) in ("failed", "interrupted"):
            failed.append(parent.job_id)
            continue
        instant = _dependency_event(parent, edge.trigger_on, evidence)
        if instant is None:
            never.append(parent.job_id)
        else:
            events.append(instant)
    if failed:
        return PlanEntry(
            job.job_id,
            hour_of(now),
            "refused",
            "dependency_failed",
            f"{', '.join(sorted(failed))} did not complete, and running on a failed input"
            " would publish it",
        )
    if not events:
        return PlanEntry(
            job.job_id,
            hour_of(now),
            "refused",
            "dependency_never_ran",
            f"{', '.join(sorted(never))} has recorded no run, so there is nothing to react to",
        )
    newest = max(events)
    last = evidence.ran_at.get(job.job_id)
    if last is not None and newest <= last:
        return None
    return PlanEntry(job.job_id, newest, "would_run")


def order_jobs(
    job_ids: Iterable[str], registry: ScheduleRegistry
) -> tuple[tuple[str, ...], frozenset[str]]:
    """Dependencies first, pulling in not-due ancestors so the order is total.

    Returns the ordered ids and the ids that sit in a cycle. A cycle refuses only its members:
    the rest of the tick is still orderable and still runs.
    """
    wanted = set(job_ids)
    frontier = list(wanted)
    closure = set(wanted)
    while frontier:
        job = registry.get(frontier.pop())
        if job is None:
            continue
        for edge in job.dependencies:
            if edge.depends_on_job_id not in closure:
                closure.add(edge.depends_on_job_id)
                frontier.append(edge.depends_on_job_id)

    remaining = {
        job_id: {
            edge.depends_on_job_id
            for edge in (registry.get(job_id).dependencies if registry.get(job_id) else ())
            if edge.depends_on_job_id in closure
        }
        for job_id in closure
    }
    ordered: list[str] = []
    while True:
        ready = sorted(job_id for job_id, edges in remaining.items() if not edges)
        if not ready:
            break
        for job_id in ready:
            ordered.append(job_id)
            del remaining[job_id]
        for edges in remaining.values():
            edges.difference_update(ready)
    return tuple(job_id for job_id in ordered if job_id in wanted), frozenset(remaining)


def plan_tick(
    connection: psycopg.Connection,
    *,
    registry: ScheduleRegistry,
    now: datetime,
    in_flight: frozenset[str] = frozenset(),
) -> TickPlan:
    """The whole due computation for one tick, in the order the runner should act in."""
    resolvable = registry.resolvable()
    evidence = collect_evidence(
        connection,
        now=now,
        source_ids=[source for job in resolvable for source in job.source_ids],
    )

    proposed: dict[str, PlanEntry] = {}
    for job in resolvable:
        if job.job_id in in_flight:
            proposed[job.job_id] = PlanEntry(
                job.job_id,
                hour_of(now),
                "refused",
                "run_in_flight",
                "a run of this job is still active, so this tick did not start a second one",
            )
            continue
        entry = due_for(job, registry, evidence, now)
        if entry is not None:
            proposed[job.job_id] = entry

    ordered, cycled = order_jobs(proposed, registry)
    entries: list[PlanEntry] = []
    for job_id in ordered:
        entry = proposed[job_id]
        if job_id in cycled:
            entries.append(
                PlanEntry(
                    job_id,
                    hour_of(now),
                    "refused",
                    "dependency_cycle",
                    "this job sits in a dependency cycle, so no order over it exists to run",
                )
            )
            continue
        job = registry.by_job[job_id]
        if entry.action == "would_run" and job.launch_mode == "launch":
            entry = PlanEntry(job_id, entry.planned_at, "run")
        entries.append(entry)
    # A cycle member is never orderable, so it never reaches the loop above; it is still a fact
    # the ledger has to carry, and only its own members are refused.
    for job_id in sorted(cycled & set(proposed)):
        if all(entry.job_id != job_id for entry in entries):
            entries.append(
                PlanEntry(
                    job_id,
                    hour_of(now),
                    "refused",
                    "dependency_cycle",
                    "this job sits in a dependency cycle, so no order over it exists to run",
                )
            )
    return TickPlan(observed_at=now, entries=tuple(entries))
