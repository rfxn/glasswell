"""The Status page's job rows, generated from the registry rather than typed out six times.

The point of the registry is that registering a job adds a row here. These read the collector
against the real schema so that a fixture row -- not a code edit -- is what makes a job appear,
and so the severity classes that decide whether a refusal reddens the deploy gate are read from
`lineage.refusal_codes` and not from a list in the collector.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from glasswell.api.routers.status import _overall_state
from glasswell.seed import seed_all
from glasswell.status.collector import _registry_jobs

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 2, 13, 47, tzinfo=UTC)
PROBE = "mart_status_probe"


def silent_runner(_command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """systemd is not on the test host, so every unit probe answers with no evidence."""
    return subprocess.CompletedProcess(_command, 1, "", "")


@pytest.fixture
def seeded(db: psycopg.Connection) -> psycopg.Connection:
    seed_all(db)
    db.commit()
    return db


def register(
    connection: psycopg.Connection,
    *,
    job_id: str = PROBE,
    label: str = "Status probe mart",
    trigger: str = "cadence",
    cadence_note: str = "Every 35 days, for as long as this test says so",
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into lineage.scheduled_jobs"
            " (job_id, label, kind, entry_point, anchor_source_id, jurisdiction, run_as,"
            "  rationale)"
            " values (%s, %s, 'mart', 'glasswell.marts.counts', 'nd_mpr_xlsx', null,"
            "         'glasswell', 'a probe registered by a test')",
            (job_id, label),
        )
        cursor.execute(
            "insert into lineage.job_schedules"
            " (job_id, effective_from, published_at, rule_id, trigger, cadence_interval,"
            "  cadence_note, memory_max, timeout_seconds)"
            " values (%s, current_date, current_date, 'cr_job_cadence_marts_cumulatives_1',"
            "         %s, interval '35 days', %s, '1G', 60)",
            (job_id, trigger, cadence_note),
        )
    connection.commit()


def close_refusal(connection: psycopg.Connection, code: str, *, job_id: str = PROBE) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into lineage.job_runs"
            " (run_id, job_id, planned_at, completed_at, launched_by, outcome, refusal_code)"
            " values ('jrn_0000000000000000000000000C', %s, %s, %s, 'scheduler', 'refused', %s)",
            (job_id, NOW, NOW, code),
        )
    connection.commit()


def job_of(jobs, job_id: str):
    return next(item for item in jobs if item.id == job_id)


def test_a_registry_row_added_in_a_fixture_yields_a_job_row_with_no_code_edit(seeded) -> None:
    before = _registry_jobs(seeded, NOW, silent_runner)
    register(seeded)
    after = _registry_jobs(seeded, NOW, silent_runner)

    assert {item.id for item in after} - {item.id for item in before} == {PROBE}
    row = job_of(after, PROBE)
    assert row.label == "Status probe mart"
    assert row.kind == "mart"
    assert row.cadence == "Every 35 days, for as long as this test says so"
    assert row.launch_mode == "observe"
    assert row.schedule is not None
    assert row.schedule.rule_id == "cr_job_cadence_marts_cumulatives_1"


def test_a_never_run_job_serves_pending_with_its_cadence_note(seeded) -> None:
    """N-10: what a registered job with no run row says, rather than nothing."""
    register(seeded, trigger="manual", cadence_note="Owner-triggered; nothing has run it")

    row = job_of(_registry_jobs(seeded, NOW, silent_runner), PROBE)

    assert row.state == "pending"
    assert row.last_outcome is None
    assert row.detail == "Owner-triggered; nothing has run it"
    assert row.next_due_at is None, "a manual job is never due and does not pretend otherwise"


@pytest.mark.parametrize("code", ["requires_superuser", "manual_only", "externally_timed"])
def test_an_informational_refusal_is_refused_and_never_degraded(seeded, code) -> None:
    """M-11: these are standing conditions, and reddening the gate on them is what rev 1 did."""
    register(seeded)
    close_refusal(seeded, code)

    row = job_of(_registry_jobs(seeded, NOW, silent_runner), PROBE)

    assert row.state == "refused"
    assert row.refusal_class == "informational"
    assert row.detail == "" or row.detail
    assert _overall_state("current", [], [row], [], []) == "partial"


@pytest.mark.parametrize("code", ["dependency_never_ran", "deferred", "run_in_flight"])
def test_a_waiting_refusal_is_pending_and_never_degraded(seeded, code) -> None:
    register(seeded)
    close_refusal(seeded, code)

    row = job_of(_registry_jobs(seeded, NOW, silent_runner), PROBE)

    assert row.state == "pending"
    assert row.refusal_class == "waiting"
    assert _overall_state("current", [], [row], [], []) == "partial"


@pytest.mark.parametrize("code", ["dependency_failed", "dependency_cycle", "entry_point_missing"])
def test_a_fault_refusal_is_degraded(seeded, code) -> None:
    register(seeded)
    close_refusal(seeded, code)

    row = job_of(_registry_jobs(seeded, NOW, silent_runner), PROBE)

    assert row.state == "degraded"
    assert row.refusal_class == "fault"
    assert _overall_state("current", [], [row], [], []) == "degraded"


def test_the_refusal_sentence_is_the_registered_one_and_not_a_string_in_the_collector(
    seeded,
) -> None:
    register(seeded)
    close_refusal(seeded, "deferred")
    with seeded.cursor() as cursor:
        cursor.execute("select sentence from lineage.refusal_codes where code = 'deferred'")
        sentence = cursor.fetchone()[0]

    row = job_of(_registry_jobs(seeded, NOW, silent_runner), PROBE)

    assert row.detail == sentence


def test_a_run_row_carries_its_duration_and_a_platform_row_carries_its_units(seeded) -> None:
    register(seeded)
    with seeded.cursor() as cursor:
        cursor.execute(
            "insert into lineage.job_runs"
            " (run_id, job_id, planned_at, started_at, completed_at, launched_by, outcome)"
            " values ('jrn_0000000000000000000000000D', %s, %s, %s, %s, 'manual', 'ran')",
            (PROBE, NOW, NOW, NOW + timedelta(seconds=94)),
        )
    seeded.commit()

    jobs = _registry_jobs(seeded, NOW, silent_runner)

    assert job_of(jobs, PROBE).duration_seconds == 94
    assert job_of(jobs, PROBE).state == "ok"
    platform = job_of(jobs, "platform_backup")
    assert platform.schedule is not None
    assert platform.schedule.rule_id is None
    assert platform.schedule.external_timer_unit == "glasswell-backup.timer"
    # The unit column reports whether a timer is armed, so it names the timer.
    assert platform.unit == "glasswell-backup.timer"


def test_an_unresolvable_registry_says_so_rather_than_serving_no_jobs(db) -> None:
    """R8: a registry that cannot answer is a refusal, and the page carries the sentence."""
    jobs = _registry_jobs(db, NOW, silent_runner)

    assert [item.id for item in jobs] == ["job_registry"]
    assert jobs[0].state == "unavailable"
    assert "nothing has been published" in jobs[0].detail


def test_a_fault_on_a_legacy_driven_row_is_shown_and_not_hidden_behind_the_unit(
    seeded,
) -> None:
    """The timer may be armed and the plan still cannot run; the row says the worse of the two."""
    close_refusal(seeded, "dependency_failed", job_id="marts_mt_wells")

    row = job_of(_registry_jobs(seeded, NOW, silent_runner), "marts_mt_wells")

    assert row.unit == "glasswell-ingest.timer", "the fixture needs a legacy-driven row"
    assert row.refusal_class == "fault"
    assert row.state == "degraded"
    assert "A job this one depends on failed" in row.detail
