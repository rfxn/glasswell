"""Proof 1 and the behaviours v0.78 turns on: registering a job changes no unit file.

The whole point of the registry is that adding a scheduled job is rows. The fixture holds
`infra/systemd/` byte-identical across the run, and no test or fixture in this file names a
migration number: the head moves at every merge train and a pinned number takes the tier down.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import pytest

from glasswell.lineage.schedules import load_schedules
from glasswell.scheduler import cli
from glasswell.scheduler.plan import hour_of, plan_tick
from glasswell.scheduler.runner import Runner, reconcile, take_job_lock, take_session_lock
from glasswell.seed import seed_all

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
SYSTEMD = ROOT / "infra" / "systemd"
NOW = datetime(2026, 9, 2, 13, 47, tzinfo=UTC)
FAKE_JOB = "mart_probe_job"


def systemd_fingerprint() -> str:
    digest = hashlib.sha256()
    for path in sorted(SYSTEMD.rglob("*")):
        if path.is_file():
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


@pytest.fixture
def unit_files_unchanged():
    before = systemd_fingerprint()
    yield
    assert systemd_fingerprint() == before, (
        "registering and running a job rewrote a unit file, which is the thing the registry"
        " exists to stop"
    )


class StubControl:
    """A transient unit that always succeeds, and remembers exactly what it was asked to run."""

    def __init__(self, values: Mapping[str, str] | None = None, status: int = 0) -> None:
        default = {"ActiveState": "inactive", "Result": "success", "ExecMainStatus": "0"}
        self.values = dict(default if values is None else values)
        self.status = status
        self.argv: list[Sequence[str]] = []
        self.reset: list[str] = []

    def show(self, unit: str) -> Mapping[str, str]:
        return dict(self.values)

    def run_transient(self, argv: Sequence[str]) -> int:
        self.argv.append(tuple(argv))
        return self.status

    def reset_failed(self, unit: str) -> None:
        self.reset.append(unit)


class Ticking:
    """An injected clock, so a stubbed launch records a real duration and not a real month."""

    def __init__(self, start: datetime, step: timedelta = timedelta(seconds=7)) -> None:
        self.moment = start
        self.step = step

    def __call__(self) -> datetime:
        self.moment += self.step
        return self.moment


def register_probe_job(
    connection: psycopg.Connection,
    *,
    trigger: str = "cadence",
    cadence_interval: str | None = "1 minute",
    enabled: bool = True,
    source_id: str | None = None,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into lineage.scheduled_jobs"
            " (job_id, kind, entry_point, argv, anchor_source_id, jurisdiction, run_as,"
            "  rationale)"
            " values (%s, 'mart', 'glasswell.marts.counts', '{}', 'nd_mpr_xlsx', null,"
            "         'glasswell', 'a probe job registered by a test, and nothing else')",
            (FAKE_JOB,),
        )
        if source_id is not None:
            cursor.execute(
                "insert into lineage.job_sources (job_id, source_id) values (%s, %s)",
                (FAKE_JOB, source_id),
            )
        cursor.execute(
            "insert into lineage.job_schedules"
            " (job_id, effective_from, published_at, rule_id, trigger, cadence_interval,"
            "  cadence_note, memory_max, timeout_seconds, enabled)"
            " values (%s, current_date, current_date, 'cr_job_cadence_marts_cumulatives_1',"
            "         %s, %s::interval, 'a one-minute probe cadence', '1G', 60, %s)",
            (FAKE_JOB, trigger, cadence_interval, enabled),
        )
    connection.commit()


@pytest.fixture
def seeded(db: psycopg.Connection) -> psycopg.Connection:
    seed_all(db)
    db.commit()
    return db


@pytest.fixture
def dsn(seeded: psycopg.Connection, monkeypatch: pytest.MonkeyPatch) -> str:
    value = seeded.info.dsn
    if "password" not in value:
        value = f"{value} password={seeded.info.password}"
    monkeypatch.setenv("GLASSWELL_DSN", value)
    return value


def runs(connection: psycopg.Connection, job_id: str) -> list[dict]:
    with connection.cursor() as cursor:
        cursor.execute(
            "select outcome, started_at, completed_at, planned_at, refusal_code, launched_by,"
            "       transient_unit"
            "  from lineage.job_runs where job_id = %s order by planned_at, run_id",
            (job_id,),
        )
        return [
            dict(
                zip(
                    ("outcome", "started_at", "completed_at", "planned_at", "refusal_code",
                     "launched_by", "transient_unit"),
                    row,
                    strict=True,
                )
            )
            for row in cursor.fetchall()
        ]


def test_registering_a_job_at_a_one_minute_cadence_runs_it_and_writes_no_unit_file(
    seeded, dsn, unit_files_unchanged
) -> None:
    """Proof 1: rows in, a run out, and `infra/systemd/` untouched on both sides."""
    register_probe_job(seeded)
    control = StubControl()

    code = cli.main(["--run", FAKE_JOB], control=control)

    assert code == 0
    recorded = runs(seeded, FAKE_JOB)
    assert len(recorded) == 1
    assert recorded[0]["outcome"] == "ran"
    assert recorded[0]["launched_by"] == "manual"
    duration = recorded[0]["completed_at"] - recorded[0]["started_at"]
    assert duration > timedelta(0)
    assert control.argv and "--property=User=glasswell" in control.argv[0]
    assert not any(token.startswith("--dsn") for token in control.argv[0])


def test_a_job_with_an_interval_and_no_fetch_attempt_is_due_on_its_first_tick(
    seeded, unit_files_unchanged
) -> None:
    """M-12: the resolver answers None for a source never polled, whatever its interval."""
    register_probe_job(seeded, source_id="tx_gis_wells_county")
    registry = load_schedules(seeded)

    plan = plan_tick(seeded, registry=registry, now=NOW)

    entry = next(item for item in plan.entries if item.job_id == FAKE_JOB)
    assert entry.action == "would_run"
    assert entry.planned_at == hour_of(NOW)


def test_observing_writes_a_would_run_row_and_launches_nothing(seeded) -> None:
    register_probe_job(seeded, source_id="tx_gis_wells_county")
    registry = load_schedules(seeded)
    control = StubControl()
    runner = Runner(connection=seeded, control=control, registry=registry, started_at=NOW)

    runner.act(plan_tick(seeded, registry=registry, now=NOW), now=NOW)
    seeded.commit()

    recorded = runs(seeded, FAKE_JOB)
    assert [row["outcome"] for row in recorded] == ["would_run"]
    assert recorded[0]["started_at"] is None
    assert control.argv == []


def test_a_second_tick_in_the_same_window_collapses_onto_the_first_row(seeded) -> None:
    register_probe_job(seeded, source_id="tx_gis_wells_county")
    registry = load_schedules(seeded)
    runner = Runner(
        connection=seeded, control=StubControl(), registry=registry, started_at=NOW
    )

    runner.act(plan_tick(seeded, registry=registry, now=NOW), now=NOW)
    later = NOW + timedelta(minutes=7)  # still inside the 13:00 window the key is cut on
    runner.act(plan_tick(seeded, registry=registry, now=later), now=later)
    seeded.commit()

    assert len(runs(seeded, FAKE_JOB)) == 1


def test_a_dry_run_writes_no_row(seeded) -> None:
    register_probe_job(seeded, source_id="tx_gis_wells_county")
    registry = load_schedules(seeded)
    runner = Runner(
        connection=seeded, control=StubControl(), registry=registry, started_at=NOW
    )

    runner.act(plan_tick(seeded, registry=registry, now=NOW), now=NOW, dry_run=True)
    seeded.commit()

    assert runs(seeded, FAKE_JOB) == []


def test_a_tick_with_less_budget_left_than_the_next_job_defers_it(seeded) -> None:
    """N-8: concurrency is 1, so a herd of due jobs is the sum of its timeouts."""
    register_probe_job(seeded, source_id="tx_gis_wells_county")
    with seeded.cursor() as cursor:
        cursor.execute(
            "insert into lineage.job_schedules"
            " (job_id, effective_from, published_at, rule_id, trigger, cadence_interval,"
            "  cadence_note, memory_max, timeout_seconds, launch_mode)"
            " values (%s, current_date, current_date + 1,"
            "         'cr_job_cadence_marts_cumulatives_1', 'cadence', interval '1 minute',"
            "         'a one-minute probe cadence', '1G', 3600, 'launch')",
            (FAKE_JOB,),
        )
    seeded.commit()
    registry = load_schedules(seeded)
    control = StubControl()
    runner = Runner(
        connection=seeded,
        control=control,
        registry=registry,
        started_at=NOW,
        budget_seconds=120,
    )

    runner.act(plan_tick(seeded, registry=registry, now=NOW), now=NOW)
    seeded.commit()

    recorded = runs(seeded, FAKE_JOB)
    assert [(row["outcome"], row["refusal_code"]) for row in recorded] == [
        ("refused", "deferred")
    ]
    assert control.argv == [], "a deferred job must not have been launched anyway"


def test_a_still_activating_unit_leaves_its_row_open_and_refuses_the_job_this_tick(
    seeded,
) -> None:
    """M-7: ActiveState is read first, always. Closing a running job starts a second copy."""
    register_probe_job(seeded, source_id="tx_gis_wells_county")
    with seeded.cursor() as cursor:
        cursor.execute(
            "insert into lineage.job_runs"
            " (run_id, job_id, planned_at, started_at, launched_by, transient_unit)"
            " values ('jrn_0000000000000000000000000A', %s, %s, %s, 'scheduler', 'gw-job-x')",
            (FAKE_JOB, NOW - timedelta(hours=2), NOW - timedelta(hours=2)),
        )
    seeded.commit()
    control = StubControl({"ActiveState": "activating", "SubState": "start"})

    reconciliation = reconcile(seeded, control, now=NOW)
    registry = load_schedules(seeded)
    plan = plan_tick(seeded, registry=registry, now=NOW, in_flight=reconciliation.in_flight)

    assert reconciliation.in_flight == frozenset({FAKE_JOB})
    assert reconciliation.closed == ()
    entry = next(item for item in plan.entries if item.job_id == FAKE_JOB)
    assert (entry.action, entry.refusal_code) == ("refused", "run_in_flight")
    assert runs(seeded, FAKE_JOB)[0]["outcome"] is None


def test_a_unit_that_no_longer_exists_closes_the_row_interrupted(seeded) -> None:
    register_probe_job(seeded)
    with seeded.cursor() as cursor:
        cursor.execute(
            "insert into lineage.job_runs"
            " (run_id, job_id, planned_at, started_at, launched_by, transient_unit)"
            " values ('jrn_0000000000000000000000000B', %s, %s, %s, 'scheduler', 'gw-job-y')",
            (FAKE_JOB, NOW - timedelta(hours=2), NOW - timedelta(hours=2)),
        )
    seeded.commit()

    reconciliation = reconcile(seeded, StubControl({}), now=NOW)

    assert reconciliation.in_flight == frozenset()
    recorded = runs(seeded, FAKE_JOB)[0]
    assert (recorded["outcome"], recorded["refusal_code"]) == (
        "interrupted",
        "scheduler_lost_unit",
    )


def test_a_forced_run_that_cannot_take_the_per_job_lock_exits_non_zero(seeded, dsn) -> None:
    """M-6b: an exit-0 skip is what would let a release believe it refreshed a mart it did not."""
    register_probe_job(seeded)
    holder = psycopg.connect(dsn)
    try:
        with holder.cursor() as cursor:
            cursor.execute(
                "select pg_advisory_lock(hashtextextended(%s, 0))",
                (f"glasswell.job.{FAKE_JOB}",),
            )
        holder.commit()

        code = cli.main(["--run", FAKE_JOB, "--force"], control=StubControl())
    finally:
        holder.close()

    assert code == 1
    recorded = runs(seeded, FAKE_JOB)
    assert [(row["outcome"], row["refusal_code"]) for row in recorded] == [
        ("refused", "run_in_flight")
    ]


def test_a_forced_run_of_an_externally_timed_job_refuses(seeded, dsn) -> None:
    """N-16: the unit is still armed and record_vintage_day is an unlocked read-then-write."""
    code = cli.main(["--run", "platform_backup", "--force"], control=StubControl())

    assert code == 1
    recorded = runs(seeded, "platform_backup")
    assert [(row["outcome"], row["refusal_code"]) for row in recorded] == [
        ("refused", "externally_timed")
    ]


def test_a_run_of_a_disabled_row_refuses_until_it_is_forced(seeded, dsn) -> None:
    register_probe_job(seeded, enabled=False)

    assert cli.main(["--run", FAKE_JOB], control=StubControl()) == 1
    assert cli.main(["--run", FAKE_JOB, "--force"], control=StubControl()) == 0

    outcomes = [(row["outcome"], row["refusal_code"]) for row in runs(seeded, FAKE_JOB)]
    assert ("refused", "disabled") in outcomes
    assert ("ran", None) in outcomes


def test_a_run_of_an_owner_triggered_job_refuses_until_it_is_forced(seeded, dsn) -> None:
    register_probe_job(seeded, trigger="manual", cadence_interval=None)

    assert cli.main(["--run", FAKE_JOB], control=StubControl()) == 1

    assert [(row["outcome"], row["refusal_code"]) for row in runs(seeded, FAKE_JOB)] == [
        ("refused", "manual_only")
    ]


def test_the_control_connection_holds_its_lock_while_reporting_idle(seeded, dsn) -> None:
    """N-7: an implicit transaction held for a whole tick pins the xmin horizon."""
    from glasswell.scheduler.runner import control_connection

    control = control_connection(os.environ["GLASSWELL_DSN"])
    try:
        assert take_session_lock(control) is True
        with control.cursor() as cursor:
            cursor.execute("select pg_backend_pid()")
            pid = cursor.fetchone()[0]
        with seeded.cursor() as cursor:
            cursor.execute("select state from pg_stat_activity where pid = %s", (pid,))
            state = cursor.fetchone()[0]
            cursor.execute(
                "select count(*) from pg_locks where locktype = 'advisory' and pid = %s", (pid,)
            )
            held = cursor.fetchone()[0]
    finally:
        control.close()

    assert state == "idle"
    assert held == 1


def test_a_second_tick_finding_the_session_lock_held_exits_zero_without_appending(
    seeded, dsn
) -> None:
    """R-9: the follower is silent; the job's open row is the evidence, not an hourly refusal."""
    from glasswell.scheduler.runner import control_connection

    holder = control_connection(os.environ["GLASSWELL_DSN"])
    try:
        assert take_session_lock(holder) is True

        code = cli.main([], control=StubControl())
    finally:
        holder.close()

    with seeded.cursor() as cursor:
        cursor.execute("select count(*) from lineage.job_runs")
        assert cursor.fetchone()[0] == 0
    assert code == 0


def test_the_per_job_lock_is_released_with_the_connection_that_took_it(seeded, dsn) -> None:
    first = psycopg.connect(dsn)
    second = psycopg.connect(dsn)
    try:
        assert take_job_lock(first, FAKE_JOB) is True
        assert take_job_lock(second, FAKE_JOB) is False
        first.close()
        assert take_job_lock(second, FAKE_JOB, wait_seconds=5) is True
    finally:
        second.close()


def test_the_planner_runs_as_the_scheduler_role_without_insufficient_privilege(seeded) -> None:
    """N-21: the grants a hand-kept list would have ratified are asserted by running the query."""
    register_probe_job(seeded, source_id="tx_gis_wells_county")
    with seeded.cursor() as cursor:
        cursor.execute("set role glasswell_scheduler")
    try:
        registry = load_schedules(seeded)
        plan = plan_tick(seeded, registry=registry, now=NOW)
    finally:
        with seeded.cursor() as cursor:
            cursor.execute("reset role")

    assert any(entry.job_id == FAKE_JOB for entry in plan.entries)
