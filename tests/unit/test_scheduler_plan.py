"""The pure halves of the due rule: the calendar, the order, and the hour the key is cut on."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from glasswell.lineage.schedules import (
    JobDependency,
    RefusalCode,
    ScheduledJob,
    ScheduleRegistry,
)
from glasswell.scheduler.plan import hour_of, monthly_occurrence, order_jobs

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
