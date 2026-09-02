"""`glasswell-scheduler`: one tick, or one job by hand.

No `--dsn`. The control connection comes from the environment the unit sets, which is a
password-free socket DSN naming the `glasswell_scheduler` role: a DSN on argv is visible in
`/proc` and lands in shell history.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from datetime import UTC, datetime

from glasswell.lineage.schedules import ScheduleRegistryError, load_schedules
from glasswell.scheduler.plan import PlanEntry, hour_of, plan_tick
from glasswell.scheduler.runner import (
    Runner,
    SystemctlControl,
    SystemdControl,
    append_plan_row,
    control_connection,
    reconcile,
    take_session_lock,
)

DSN_ENV = "GLASSWELL_DSN"
FALLBACK_DSN_ENV = "DATABASE_URL"
# informational refusals: no worse than partial, so they never redden the deploy gate
INFORMATIONAL = frozenset({"manual_only", "disabled", "externally_timed", "requires_superuser"})
WAITING = frozenset({"run_in_flight", "dependency_never_ran", "deferred"})


def resolved_dsn() -> str:
    dsn = os.environ.get(DSN_ENV) or os.environ.get(FALLBACK_DSN_ENV)
    if not dsn:
        raise SystemExit(f"no database DSN: set {DSN_ENV} or {FALLBACK_DSN_ENV}")
    return dsn


def _report(entries: Sequence[PlanEntry]) -> str:
    return json.dumps(
        [
            {
                "job_id": entry.job_id,
                "planned_at": entry.planned_at.isoformat(),
                "action": entry.action,
                "refusal_code": entry.refusal_code,
                "reason": entry.reason,
            }
            for entry in entries
        ],
        indent=2,
        sort_keys=True,
    )


def _exit_code(entries: Sequence[PlanEntry]) -> int:
    """Zero for observed, ran, or a refusal no one has to act on tonight."""
    for entry in entries:
        if entry.action == "refused" and entry.refusal_code not in INFORMATIONAL | WAITING:
            return 1
    return 0


def run_one(
    connection,
    *,
    registry,
    job_id: str,
    now: datetime,
    control: SystemdControl,
    force: bool,
    wait_for_lock: float,
    dry_run: bool,
) -> tuple[list[PlanEntry], int]:
    job = registry.get(job_id)
    if job is None:
        raise SystemExit(f"{job_id} is not a registered job")

    refusal: PlanEntry | None = None
    if job.is_external:
        # The unit is still armed and record_vintage_day is an unlocked read-then-write, so a
        # collision is a silently corrupted vintage row. --force does not bypass this one.
        refusal = PlanEntry(
            job_id, hour_of(now), "refused", "externally_timed",
            f"{job.external_timer_unit} still drives this job",
        )
    elif not job.enabled and not force:
        refusal = PlanEntry(
            job_id, hour_of(now), "refused", "disabled",
            "the resolved schedule row is disabled; pass --force to run it anyway",
        )
    elif job.trigger == "manual" and not force:
        refusal = PlanEntry(
            job_id, hour_of(now), "refused", "manual_only",
            "this job is owner-triggered and is never due; pass --force to run it",
        )
    if refusal is not None:
        if not dry_run:
            append_plan_row(connection, refusal, now=now, launched_by="manual")
        return [refusal], 1

    runner = Runner(
        connection=connection,
        control=control,
        registry=registry,
        started_at=now,
        launched_by="manual",
    )
    if dry_run:
        return [PlanEntry(job_id, hour_of(now), "run")], 0
    entry = runner.launch(
        job, planned_at=hour_of(now), now=now, wait_for_lock=wait_for_lock
    )
    if entry.action == "refused":
        return [entry], 1
    with connection.cursor() as cursor:
        cursor.execute(
            "select outcome from lineage.job_runs where job_id = %s"
            " order by planned_at desc, run_id desc limit 1",
            (job_id,),
        )
        row = cursor.fetchone()
    return [entry], 0 if row and row[0] == "ran" else 1


def main(argv: Sequence[str] | None = None, control: SystemdControl | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Resolve the job registry, compute what is due, and record what happened."
    )
    parser.add_argument("--run", default=None, metavar="JOB_ID", help="run one job by hand")
    parser.add_argument("--force", action="store_true", help="bypass the due test and enabled")
    parser.add_argument("--wait-for-lock", type=float, default=0.0, metavar="SECONDS")
    parser.add_argument("--dry-run", action="store_true", help="compute the plan, write nothing")
    arguments = parser.parse_args(argv)
    control = control or SystemctlControl()
    now = datetime.now(UTC)

    with control_connection(resolved_dsn()) as connection:
        if not take_session_lock(connection):
            # A previous tick is still working. The follower exits silently rather than
            # appending an hourly refusal about a job that is visibly running.
            return 0
        try:
            registry = load_schedules(connection)
        except ScheduleRegistryError as refusal:
            print(str(refusal))
            return 1

        if arguments.run is not None:
            entries, code = run_one(
                connection,
                registry=registry,
                job_id=arguments.run,
                now=now,
                control=control,
                force=arguments.force,
                wait_for_lock=arguments.wait_for_lock,
                dry_run=arguments.dry_run,
            )
            print(_report(entries))
            return code

        reconciliation = reconcile(connection, control, now=now)
        plan = plan_tick(
            connection, registry=registry, now=now, in_flight=reconciliation.in_flight
        )
        runner = Runner(
            connection=connection, control=control, registry=registry, started_at=now
        )
        recorded = runner.act(plan, now=now, dry_run=arguments.dry_run)
        print(_report(recorded))
        return _exit_code(recorded)


if __name__ == "__main__":
    raise SystemExit(main())
