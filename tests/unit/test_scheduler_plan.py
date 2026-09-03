"""The pure halves of the due rule: the calendar, the order, and the hour the key is cut on."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from glasswell.lineage.schedules import (
    JobDependency,
    RefusalCode,
    ScheduledJob,
    ScheduleRegistry,
)
from glasswell.scheduler import plan as planner
from glasswell.scheduler.cli import _exit_code
from glasswell.scheduler.plan import (
    Evidence,
    PlanEntry,
    hour_of,
    monthly_occurrence,
    order_jobs,
    plan_tick,
)
from glasswell.seed.schedules import JOB_SOURCES, resolved_schedules

pytestmark = pytest.mark.unit

DAY = datetime(2026, 9, 2, 13, 47, 3, tzinfo=UTC)


def job(job_id: str, *, kind: str = "mart", depends: tuple[str, ...] = ()) -> ScheduledJob:
    return ScheduledJob(
        job_id=job_id,
        label=job_id.replace('_', ' ').capitalize(),
        kind=kind,
        entry_point=f"glasswell.marts.{job_id}",
        argv=(),
        anchor_source_id="nd_mpr_xlsx",
        jurisdiction=None,
        run_as="glasswell",
        rationale="fixture",
        effective_from=DAY.date(),
        published_at=DAY.date(),
        rule_id=f"cr_job_cadence_{job_id}_1",
        trigger="after_dependency",
        launch_mode="observe",
        cadence_interval=None,
        cadence_monthly_on_day=None,
        cadence_note="fixture",
        memory_max="1G",
        timeout_seconds=60,
        concurrency_group="default",
        enabled=True,
        legacy_unit=None,
        external_timer_unit=None,
        external_service_unit=None,
        dependencies=tuple(
            JobDependency(depends_on_job_id=name, trigger_on="changed", rationale="fixture")
            for name in depends
        ),
    )


def seeded_job(job_id: str) -> ScheduledJob:
    """A registry job built from the seed's own resolved row, so the posture is not the
    fixture's opinion: the seed says what `job_schedules_as_of` would resolve for this job."""
    row = resolved_schedules()[job_id]
    return ScheduledJob(
        job_id=job_id,
        label=job_id,
        kind="ingest",
        entry_point=f"glasswell.ingest.{job_id}",
        argv=(),
        anchor_source_id=min(JOB_SOURCES[job_id]),
        jurisdiction="CO",
        run_as="glasswell",
        rationale="the seed's row, read as the registry resolves it",
        effective_from=DAY.date(),
        published_at=DAY.date(),
        rule_id=str(row.get("rule_id") or f"cr_job_cadence_{job_id}_1"),
        trigger=str(row["trigger"]),
        launch_mode=str(row.get("launch_mode", "observe")),
        cadence_interval=row.get("cadence_interval"),  # type: ignore[arg-type]
        cadence_monthly_on_day=None,
        cadence_note=str(row["cadence_note"]),
        memory_max="6G",
        timeout_seconds=3600,
        concurrency_group="default",
        enabled=True,
        legacy_unit=None,
        external_timer_unit=None,
        external_service_unit=None,
        source_ids=tuple(JOB_SOURCES[job_id]),
    )


def registry_of(*jobs: ScheduledJob) -> ScheduleRegistry:
    return ScheduleRegistry(
        knowledge_as_of=DAY.date(),
        valid_as_of=DAY.date(),
        by_job={item.job_id: item for item in jobs},
        refusal_codes={
            "dependency_cycle": RefusalCode("dependency_cycle", "fault", "cycle"),
        },
    )


def test_the_plan_key_is_cut_on_the_hour_so_repeated_ticks_collapse() -> None:
    assert hour_of(DAY) == datetime(2026, 9, 2, 13, tzinfo=UTC)
    assert hour_of(DAY + timedelta(minutes=11)) == hour_of(DAY)


def test_the_monthly_rule_requests_every_calendar_month_across_a_year() -> None:
    """A 35-day interval fires 10.4 times a year; twelve months need twelve occurrences."""
    requested = set()
    moment = datetime(2026, 1, 1, tzinfo=UTC)
    while moment < datetime(2027, 1, 1, tzinfo=UTC):
        occurrence = monthly_occurrence(moment, 5)
        if occurrence <= moment:
            requested.add((occurrence.year, occurrence.month))
        moment += timedelta(hours=6)

    assert len({month for year, month in requested if year == 2026}) == 12


def test_the_monthly_occurrence_before_the_day_falls_into_the_previous_month() -> None:
    assert monthly_occurrence(datetime(2026, 3, 2, 9, tzinfo=UTC), 12) == datetime(
        2026, 2, 12, tzinfo=UTC
    )
    assert monthly_occurrence(datetime(2026, 3, 12, 0, tzinfo=UTC), 12) == datetime(
        2026, 3, 12, tzinfo=UTC
    )


def test_a_not_due_ancestor_is_pulled_in_so_the_order_is_total() -> None:
    registry = registry_of(
        job("ingest_a", kind="ingest"),
        job("mart_b", depends=("ingest_a",)),
        job("mart_c", depends=("mart_b",)),
    )

    ordered, cycled = order_jobs({"mart_c"}, registry)

    assert ordered == ("mart_c",)
    assert cycled == frozenset()


def test_dependencies_are_ordered_before_the_jobs_that_read_them() -> None:
    registry = registry_of(
        job("ingest_a", kind="ingest"),
        job("mart_b", depends=("ingest_a",)),
        job("mart_c", depends=("mart_b",)),
    )

    ordered, _cycled = order_jobs({"mart_c", "mart_b", "ingest_a"}, registry)

    assert ordered == ("ingest_a", "mart_b", "mart_c")


def test_a_cycle_names_only_its_own_members_and_leaves_the_rest_orderable() -> None:
    registry = registry_of(
        job("ingest_a", kind="ingest"),
        job("mart_b", depends=("ingest_a",)),
        job("mart_x", depends=("mart_y",)),
        job("mart_y", depends=("mart_x",)),
    )

    ordered, cycled = order_jobs({"mart_b", "mart_x", "mart_y"}, registry)

    assert ordered == ("mart_b",)
    assert cycled == frozenset({"mart_x", "mart_y"})


def test_the_scheduler_never_transitively_imports_the_api() -> None:
    """The planner asking a FastAPI router what is due is the layering M-5 exists to fix."""
    import subprocess
    import sys

    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import glasswell.scheduler.cli, sys;"
            " print(sorted(m for m in sys.modules if m.startswith('glasswell.api')))",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert probe.stdout.strip() == "[]", probe.stdout


def test_the_status_router_reads_the_moved_module_and_not_the_health_router() -> None:
    """N-19: a re-export would let the inversion survive behind an import that still works."""
    from pathlib import Path

    status = (
        Path(__file__).resolve().parents[2]
        / "src/glasswell/api/routers/status.py"
    ).read_text()

    assert "from glasswell.status.source_health import source_health_data" in status
    assert "source_health_data" not in status.split("from glasswell.api.routers.health import")[
        1
    ].split("\n")[0]


def registry_with_codes(*codes: RefusalCode) -> ScheduleRegistry:
    return ScheduleRegistry(
        knowledge_as_of=DAY.date(),
        valid_as_of=DAY.date(),
        by_job={},
        refusal_codes={code.code: code for code in codes},
    )


def refusal(code: str) -> PlanEntry:
    return PlanEntry("probe", DAY, "refused", code, "fixture")


def test_the_tick_reads_its_severity_from_the_registry_and_not_from_a_second_list() -> None:
    """M-11: which class a code carries is a decision. A code added to lineage.refusal_codes
    as informational must not page someone because a constant in the CLI never heard of it."""
    registry = registry_with_codes(
        RefusalCode("upstream_quiet", "informational", "the publisher has nothing new"),
        RefusalCode("waiting_on_backfill", "waiting", "a backfill is still running"),
        RefusalCode("mart_corrupt", "fault", "the mart cannot be rebuilt"),
    )

    assert _exit_code([refusal("upstream_quiet")], registry) == 0
    assert _exit_code([refusal("waiting_on_backfill")], registry) == 0
    assert _exit_code([refusal("mart_corrupt")], registry) == 1


def test_a_refusal_the_registry_cannot_class_is_treated_as_a_fault() -> None:
    """An unclassed code is a vocabulary the page cannot render either; failing closed is the
    only reading that does not quietly stop alerting."""
    registry = registry_with_codes(RefusalCode("known", "informational", "known"))

    assert _exit_code([refusal("never_registered")], registry) == 1


def test_a_failed_or_interrupted_run_still_exits_non_zero() -> None:
    registry = registry_with_codes(
        RefusalCode("scheduler_lost_unit", "fault", "the unit is gone"),
    )
    ran = PlanEntry("probe", DAY, "would_run")

    assert _exit_code([ran], registry) == 0
    assert _exit_code([refusal("scheduler_lost_unit")], registry) == 1


def _first_observation(job: ScheduledJob) -> Evidence:
    """Nothing has polled this job's sources and each carries an interval, which is the state
    the due rule returns `hour_of(now)` for."""
    return Evidence(
        freshness={},
        source_interval={source_id: timedelta(days=1) for source_id in job.source_ids},
        ran_at={},
        derived_at={},
        last_outcome={},
        fetched_new_at={},
    )


def test_a_due_colorado_job_stays_would_run_because_the_seed_resolves_observe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ruling of 2026-09-03, tested where it takes effect rather than where it is written.

    `plan_tick` rewrites a due `would_run` entry to `run` for any job whose resolved row says
    `launch`, and the runner then starts it, so Colorado's six jobs are only disarmed if what
    the seed resolves for them observes. Reading the posture out of the seed is what makes this
    redden on a row that re-registers `launch` rather than on an edit to this file.
    """
    job = seeded_job("co_ecmc_gis")
    monkeypatch.setattr(planner, "collect_evidence", lambda *_a, **_k: _first_observation(job))

    plan = plan_tick(None, registry=registry_of(job), now=DAY)  # type: ignore[arg-type]

    assert [(entry.job_id, entry.action) for entry in plan.entries] == [
        ("co_ecmc_gis", "would_run")
    ]


def test_the_same_row_at_launch_would_have_run_on_that_tick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The negative half, so the test above is not a tautology about an unreachable branch:
    one field is the difference between a recorded plan and an unattended ECMC pull."""
    observing = seeded_job("co_ecmc_gis")
    launching = replace(observing, launch_mode="launch")
    monkeypatch.setattr(
        planner, "collect_evidence", lambda *_a, **_k: _first_observation(launching)
    )

    plan = plan_tick(None, registry=registry_of(launching), now=DAY)  # type: ignore[arg-type]

    assert [entry.action for entry in plan.entries] == ["run"]
    assert observing.launch_mode == "observe"
