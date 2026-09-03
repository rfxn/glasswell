"""Acting on a plan: the ledger, the locks, the reconciler and the transient unit.

Nothing here launches on a tick until the launch flip lands: every row the registry resolves
observes, and `tests/unit/test_schedule_posture.py` is what holds it. The launch path is built
and exercised through `--run`, so turning it on is a row rather than a code change. What the
tick does do is reconcile: a run whose unit vanished has to close with a reason, because a
dropped session that leaves an open row and no evidence is how an operator loses a night.
"""

from __future__ import annotations

import importlib.util
import os
import pwd
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

import psycopg

from glasswell.lineage.ids import new_ulid
from glasswell.lineage.schedules import ScheduledJob, ScheduleRegistry
from glasswell.scheduler.plan import PlanEntry, TickPlan, hour_of
from glasswell.scheduler.units import render_transient_argv, transient_unit_name

SESSION_LOCK_KEY = "glasswell.scheduler"
# Equal to the scheduler unit's own TimeoutStartSec, which is what the job ceiling is capped
# against: concurrency is 1, so a tick is the sum of its jobs and a herd could otherwise run
# past the unit's budget and be SIGTERMed mid-write.
TICK_BUDGET_SECONDS = 21600
ACTIVE_STATES = frozenset({"active", "activating", "reloading", "deactivating"})

# LoadState is here because it is the only one of these that tells a unit that finished
# from a unit that never existed: measured on systemd 255, an unknown unit answers
# Result=success, ExecMainStatus=0, ActiveState=inactive, SubState=dead.
_PROPERTIES = ("LoadState", "ActiveState", "SubState", "Result", "ExecMainStatus",
               "ExecMainExitTimestamp", "MemoryPeak")


class SystemdControl(Protocol):
    def show(self, unit: str) -> Mapping[str, str]: ...
    def run_transient(self, argv: Sequence[str]) -> int: ...
    def reset_failed(self, unit: str) -> None: ...


class SystemctlControl:
    """The real thing. `show` on an unknown unit exits 0 and answers `LoadState=not-found`
    beside a full set of default values, so the caller discriminates on that and never on an
    empty answer."""

    def show(self, unit: str) -> Mapping[str, str]:
        completed = subprocess.run(
            ["systemctl", "show", unit, "--property=" + ",".join(_PROPERTIES)],
            capture_output=True,
            text=True,
            check=False,
        )
        values: dict[str, str] = {}
        for line in completed.stdout.splitlines():
            key, _, value = line.partition("=")
            values[key] = value
        return values

    def run_transient(self, argv: Sequence[str]) -> int:
        return subprocess.run(list(argv), check=False).returncode

    def reset_failed(self, unit: str) -> None:
        subprocess.run(["systemctl", "reset-failed", unit], check=False,
                       capture_output=True)  # a unit that already went away is not an error


@dataclass(frozen=True, slots=True)
class Reconciliation:
    in_flight: frozenset[str]
    closed: tuple[str, ...]


def control_connection(dsn: str) -> psycopg.Connection:
    """Autocommit is load-bearing: an implicit transaction held for a whole tick pins the xmin
    horizon against VACUUM on a swapless host in the middle of a bulk ingest."""
    return psycopg.connect(dsn, autocommit=True)


def take_session_lock(connection: psycopg.Connection) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            "select pg_try_advisory_lock(hashtextextended(%s, 0))", (SESSION_LOCK_KEY,)
        )
        return bool(cursor.fetchone()[0])


def take_job_lock(
    connection: psycopg.Connection, job_id: str, *, wait_seconds: float = 0.0
) -> bool:
    """The select-then-insert check is not race-free under READ COMMITTED; this is."""
    key = f"glasswell.job.{job_id}"
    deadline = datetime.now(UTC) + timedelta(seconds=wait_seconds)
    while True:
        with connection.cursor() as cursor:
            cursor.execute("select pg_try_advisory_lock(hashtextextended(%s, 0))", (key,))
            if cursor.fetchone()[0]:
                return True
        if datetime.now(UTC) >= deadline:
            return False
        _sleep(0.5)


def _sleep(seconds: float) -> None:
    import time

    time.sleep(seconds)


def new_run_id(now: datetime) -> str:
    return f"jrn_{new_ulid(now)}"


def append_plan_row(
    connection: psycopg.Connection, entry: PlanEntry, *, now: datetime, launched_by: str
) -> str | None:
    """One row per job per due window per fact; a repeat inside the window is a no-op."""
    run_id = new_run_id(now)
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into lineage.job_runs"
            " (run_id, job_id, planned_at, completed_at, launched_by, outcome, refusal_code,"
            "  failure_detail)"
            " values (%s, %s, %s, %s, %s, %s, %s, null)"
            " on conflict do nothing"
            " returning run_id",
            (
                run_id,
                entry.job_id,
                entry.planned_at,
                now,
                launched_by,
                "refused" if entry.action == "refused" else "would_run",
                entry.refusal_code,
            ),
        )
        row = cursor.fetchone()
    return row[0] if row else None


def open_run(
    connection: psycopg.Connection,
    *,
    job_id: str,
    planned_at: datetime,
    started_at: datetime,
    launched_by: str,
) -> tuple[str, str]:
    """The open row and the unit name it will be reconciled through, minted together."""
    run_id = new_run_id(started_at)
    unit = transient_unit_name(job_id, run_id)
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into lineage.job_runs"
            " (run_id, job_id, planned_at, started_at, launched_by, transient_unit)"
            " values (%s, %s, %s, %s, %s, %s)",
            (run_id, job_id, planned_at, started_at, launched_by, unit),
        )
    return run_id, unit


def close_run(
    connection: psycopg.Connection,
    run_id: str,
    *,
    outcome: str,
    completed_at: datetime,
    exit_status: int | None = None,
    refusal_code: str | None = None,
    failure_detail: str | None = None,
    memory_peak_bytes: int | None = None,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "update lineage.job_runs"
            "   set outcome = %s, completed_at = %s, exit_status = %s, refusal_code = %s,"
            "       failure_detail = %s, memory_peak_bytes = %s"
            " where run_id = %s",
            (
                outcome,
                completed_at,
                exit_status,
                refusal_code,
                failure_detail,
                memory_peak_bytes,
                run_id,
            ),
        )


def _memory_peak(values: Mapping[str, str]) -> int | None:
    """MemoryPeak needs systemd 254; where it is absent the row says so rather than zeroing.

    The sentinel a supporting systemd prints for a run it did not measure is `[not set]`,
    which is not a number either, so one test covers both absences.
    """
    raw = values.get("MemoryPeak", "")
    return int(raw) if raw.isdigit() else None


def reconcile(
    connection: psycopg.Connection,
    control: SystemdControl,
    *,
    now: datetime,
) -> Reconciliation:
    """Read ActiveState first, always: closing a still-running job is how two copies start."""
    with connection.cursor() as cursor:
        cursor.execute(
            "select run_id, job_id, transient_unit from lineage.job_runs"
            " where outcome is null order by planned_at, run_id"
        )
        open_runs = cursor.fetchall()

    in_flight: set[str] = set()
    closed: list[str] = []
    for run_id, job_id, unit in open_runs:
        values = control.show(unit or transient_unit_name(job_id, run_id))
        state = values.get("ActiveState", "")
        if state in ACTIVE_STATES:
            in_flight.add(job_id)
            continue
        # A unit that never existed answers `success` and exit 0 like one that finished, so
        # closing on those would record a run nobody can account for as a successful one.
        if not values or values.get("LoadState") == "not-found":
            close_run(
                connection,
                run_id,
                outcome="interrupted",
                completed_at=now,
                refusal_code="scheduler_lost_unit",
            )
            closed.append(run_id)
            continue
        exit_status = int(values.get("ExecMainStatus") or 0)
        succeeded = values.get("Result", "") == "success" and exit_status == 0
        close_run(
            connection,
            run_id,
            outcome="ran" if succeeded else "failed",
            completed_at=now,
            exit_status=exit_status,
            failure_detail=None
            if succeeded
            else f"unit {values.get('Result', 'failed')} with status {exit_status}"[:256],
            memory_peak_bytes=_memory_peak(values),
        )
        control.reset_failed(unit or transient_unit_name(job_id, run_id))
        closed.append(run_id)
    return Reconciliation(in_flight=frozenset(in_flight), closed=tuple(closed))


def entry_point_resolves(entry_point: str) -> bool:
    try:
        return importlib.util.find_spec(entry_point) is not None
    except (ImportError, ValueError):
        return False


def _current_user() -> str:
    return pwd.getpwuid(os.geteuid()).pw_name


def uid_reachable(run_as: str | None) -> bool:
    """Dropping to another uid needs root; a hand-run scheduler can only be itself."""
    if run_as is None:
        return False
    return os.geteuid() == 0 or run_as == _current_user()


def _wall_clock() -> datetime:
    return datetime.now(UTC)


@dataclass
class Runner:
    connection: psycopg.Connection
    control: SystemdControl
    registry: ScheduleRegistry
    started_at: datetime
    budget_seconds: int = TICK_BUDGET_SECONDS
    launched_by: str = "scheduler"
    # Injected so a test can advance it: a run's completed_at has to come from the clock the
    # run was planned against, or a stubbed launch records a duration measured in months.
    clock: Callable[[], datetime] = _wall_clock

    def remaining_budget(self, now: datetime) -> float:
        spent = (now - self.started_at).total_seconds()
        return self.budget_seconds - spent

    def act(self, plan: TickPlan, *, now: datetime, dry_run: bool = False) -> list[PlanEntry]:
        """Observe or launch, in the plan's order. Returns what was actually recorded."""
        recorded: list[PlanEntry] = []
        for proposed in plan.entries:
            job = self.registry.by_job[proposed.job_id]
            entry = self._guard(job, proposed, now=now) if proposed.action == "run" else proposed
            if dry_run:
                recorded.append(entry)
                continue
            if entry.action == "run":
                recorded.append(self.launch(job, planned_at=entry.planned_at, now=now))
                continue
            append_plan_row(self.connection, entry, now=now, launched_by=self.launched_by)
            recorded.append(entry)
        return recorded

    def _guard(self, job: ScheduledJob, entry: PlanEntry, *, now: datetime) -> PlanEntry:
        if not entry_point_resolves(job.entry_point):
            return PlanEntry(
                job.job_id, entry.planned_at, "refused", "entry_point_missing",
                f"{job.entry_point} does not resolve to an importable module on this host",
            )
        if not uid_reachable(job.run_as):
            return PlanEntry(
                job.job_id, entry.planned_at, "refused", "requires_superuser",
                f"dropping to {job.run_as} needs root and this scheduler runs as"
                f" {_current_user()}",
            )
        if job.timeout_seconds is not None and self.remaining_budget(now) < job.timeout_seconds:
            return PlanEntry(
                job.job_id, hour_of(now), "refused", "deferred",
                "the tick had less budget left than this job's timeout, so it waits",
            )
        return entry

    def launch(
        self,
        job: ScheduledJob,
        *,
        planned_at: datetime,
        now: datetime,
        wait_for_lock: float = 0.0,
    ) -> PlanEntry:
        """Take the per-job lock, open a row, run the transient unit, close the row."""
        if not take_job_lock(self.connection, job.job_id, wait_seconds=wait_for_lock):
            entry = PlanEntry(
                job.job_id, hour_of(now), "refused", "run_in_flight",
                "a run of this job already holds the per-job lock",
            )
            append_plan_row(self.connection, entry, now=now, launched_by=self.launched_by)
            return entry
        run_id, unit = open_run(
            self.connection,
            job_id=job.job_id,
            planned_at=planned_at,
            started_at=now,
            launched_by=self.launched_by,
        )
        argv = render_transient_argv(
            job_id=job.job_id,
            run_id=run_id,
            entry_point=job.entry_point,
            argv=job.argv,
            run_as=job.run_as or "glasswell",
            memory_max=job.memory_max,
            timeout_seconds=job.timeout_seconds,
        )
        status = self.control.run_transient(argv)
        values = self.control.show(unit)
        finished = self.clock()
        close_run(
            self.connection,
            run_id,
            outcome="ran" if status == 0 else "failed",
            completed_at=max(finished, now),
            exit_status=status,
            failure_detail=None if status == 0 else f"transient unit exited {status}",
            memory_peak_bytes=_memory_peak(values),
        )
        self.control.reset_failed(unit)
        return PlanEntry(job.job_id, planned_at, "run")
