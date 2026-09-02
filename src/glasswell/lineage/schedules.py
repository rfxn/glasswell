"""The job registry as the scheduler and the serving path read it: rows, at two clocks.

`lineage.job_schedules_as_of(knowledge_as_of, valid_as_of)` decides which schedule answers;
this module turns its rows into the job set every consumer needs, with each job's sources,
dependencies and refusal vocabulary attached, and refuses rather than defaulting when the
registry cannot answer at all.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta

import psycopg
from psycopg.rows import dict_row

from glasswell.lineage.clock import utc_today
from glasswell.lineage.errors import LineageError


class ScheduleRegistryError(LineageError):
    """R8: the schedule is rows, so an unloaded registry is a refusal, never a default."""


@dataclass(frozen=True, slots=True)
class RefusalCode:
    code: str
    severity_class: str
    sentence: str


@dataclass(frozen=True, slots=True)
class JobDependency:
    depends_on_job_id: str
    trigger_on: str
    rationale: str


@dataclass(frozen=True, slots=True)
class ScheduledJob:
    job_id: str
    label: str
    kind: str
    entry_point: str
    argv: tuple[str, ...]
    anchor_source_id: str | None
    jurisdiction: str | None
    run_as: str | None
    rationale: str
    effective_from: date
    published_at: date
    rule_id: str | None
    trigger: str
    launch_mode: str
    cadence_interval: timedelta | None
    cadence_monthly_on_day: int | None
    cadence_note: str
    memory_max: str | None
    timeout_seconds: int | None
    concurrency_group: str
    enabled: bool
    legacy_unit: str | None
    external_timer_unit: str | None
    external_service_unit: str | None
    source_ids: tuple[str, ...] = field(default=())
    dependencies: tuple[JobDependency, ...] = field(default=())

    @property
    def is_external(self) -> bool:
        return self.trigger == "external_timer"


@dataclass(frozen=True, slots=True)
class ScheduleRegistry:
    knowledge_as_of: date
    valid_as_of: date
    by_job: Mapping[str, ScheduledJob]
    refusal_codes: Mapping[str, RefusalCode]

    def __iter__(self) -> Iterator[ScheduledJob]:
        return iter(sorted(self.by_job.values(), key=lambda job: job.job_id))

    def __len__(self) -> int:
        return len(self.by_job)

    def get(self, job_id: str) -> ScheduledJob | None:
        return self.by_job.get(job_id)

    def severity_of(self, refusal_code: str | None) -> str | None:
        code = self.refusal_codes.get(refusal_code or "")
        return code.severity_class if code is not None else None

    def resolvable(self) -> tuple[ScheduledJob, ...]:
        """What a tick considers: enabled rows the scheduler itself could drive."""
        return tuple(job for job in self if job.enabled and not job.is_external)


_RESOLVED = """
select s.*, j.label, j.kind, j.entry_point, j.argv, j.anchor_source_id, j.jurisdiction,
       j.run_as,
       j.rationale,
       coalesce(src.source_ids, array[]::text[]) as source_ids,
       coalesce(dep.dependencies, '[]'::jsonb) as dependencies
  from lineage.job_schedules_as_of(%(knowledge_as_of)s, %(valid_as_of)s) s
  join lineage.scheduled_jobs j on j.job_id = s.job_id
  left join lateral (
      select array_agg(v.source_id order by v.source_id) as source_ids
        from lineage.job_sources v
       where v.job_id = j.job_id) src on true
  left join lateral (
      select jsonb_agg(jsonb_build_object(
                 'depends_on_job_id', d.depends_on_job_id,
                 'trigger_on', d.trigger_on,
                 'rationale', d.rationale)
             order by d.depends_on_job_id) as dependencies
        from lineage.job_dependencies d
       where d.job_id = j.job_id) dep on true
 order by s.job_id
"""

_REFUSAL_CODES = "select code, severity_class, sentence from lineage.refusal_codes order by code"

_LATEST_PUBLISHED = "select max(published_at) from lineage.job_schedules"

_JOB_FIELDS = tuple(
    name
    for name in ScheduledJob.__dataclass_fields__
    if name not in ("argv", "source_ids", "dependencies")
)

def job_from_row(row: Mapping[str, object]) -> ScheduledJob:
    return ScheduledJob(
        **{name: row[name] for name in _JOB_FIELDS},  # type: ignore[arg-type]
        argv=tuple(row["argv"] or ()),  # type: ignore[arg-type]
        source_ids=tuple(row["source_ids"] or ()),  # type: ignore[arg-type]
        dependencies=tuple(
            JobDependency(
                depends_on_job_id=edge["depends_on_job_id"],
                trigger_on=edge["trigger_on"],
                rationale=edge["rationale"],
            )
            for edge in row["dependencies"]  # type: ignore[union-attr]
        ),
    )


def load_schedules(
    connection: psycopg.Connection, as_of: date | None = None
) -> ScheduleRegistry:
    """The schedules serving at `as_of`, or at the latest published vintage and today."""
    with connection.cursor() as cursor:
        cursor.execute(_LATEST_PUBLISHED)
        latest = cursor.fetchone()[0]
    knowledge_as_of = as_of or latest
    valid_as_of = as_of or utc_today()
    if knowledge_as_of is None:
        raise ScheduleRegistryError(
            "the job registry holds no schedule: nothing has been published"
        )

    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            _RESOLVED, {"knowledge_as_of": knowledge_as_of, "valid_as_of": valid_as_of}
        )
        resolved = [job_from_row(row) for row in cursor.fetchall()]
        cursor.execute(_REFUSAL_CODES)
        codes = [RefusalCode(**row) for row in cursor.fetchall()]  # type: ignore[arg-type]

    if not resolved:
        raise ScheduleRegistryError(
            f"no job schedule resolves at knowledge {knowledge_as_of.isoformat()} /"
            f" valid {valid_as_of.isoformat()}"
        )
    if not codes:
        raise ScheduleRegistryError(
            "the refusal vocabulary is empty, so a refusal could not name its severity"
        )
    return ScheduleRegistry(
        knowledge_as_of=knowledge_as_of,
        valid_as_of=valid_as_of,
        by_job={job.job_id: job for job in resolved},
        refusal_codes={code.code: code for code in codes},
    )
