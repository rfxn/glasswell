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

import psycopg

from glasswell.lineage.schedules import (
    ScheduleRegistry,
    ScheduleRegistryError,
    load_schedules,
)
from glasswell.scheduler.plan import (
    PlanEntry,
    double_run_rows,
    hour_of,
    plan_tick,
    read_relations,
)
from glasswell.scheduler.runner import (
    Runner,
    SystemctlControl,
    SystemdControl,
    append_plan_row,
    control_connection,
    reconcile,
    take_session_lock,
)
from glasswell.scheduler.units import installed_timer_owned_entry_points

DSN_ENV = "GLASSWELL_DSN"
FALLBACK_DSN_ENV = "DATABASE_URL"

# The double-run guard answers with a status, never with prose. A gate that read the
# message could not tell "no launch row resolved" from "I never reached the database",
# and the second is what a first deploy hits: a peer-auth failure was reported as a
# double-run hazard, which is a claim about rows nothing had read.
GUARD_CLEAN = 0
GUARD_HAZARD = 1
GUARD_NO_DSN = 3
GUARD_UNREACHABLE = 4
GUARD_UNREADABLE = 5
GUARD_NO_TIMER_SET = 6


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


def _exit_code(entries: Sequence[PlanEntry], registry: ScheduleRegistry) -> int:
    """Zero for observed, ran, or a refusal no one has to act on tonight.

    The class comes from `lineage.refusal_codes`, the same row the Status page reads. A
    second list here would be a second authority over the one output that pages someone:
    add a code as informational and the page would render it correctly while the tick
    alerted. An unclassed code fails closed, because a vocabulary neither side can render
    is not a reason to stop alerting.
    """
    for entry in entries:
        if entry.action != "refused":
            continue
        if registry.severity_of(entry.refusal_code) not in ("informational", "waiting"):
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


def double_run_check() -> int:
    """The permanent guard, and every way of failing to run it, each with its own status.

    Outside the tick's session lock and outside its connection: the guard is a read that needs
    no mutual exclusion, and it has to be able to report that it never reached the database
    without that being mistaken for a clean registry.
    """
    try:
        dsn = resolved_dsn()
    except SystemExit as refusal:
        print(f"no DSN, so nothing was checked: {refusal}")
        return GUARD_NO_DSN
    try:
        connection = control_connection(dsn)
    except psycopg.OperationalError as unreachable:
        print(f"the database could not be reached, so nothing was checked: {unreachable}")
        return GUARD_UNREACHABLE
    with connection:
        try:
            load_schedules(connection)
        except ScheduleRegistryError as refusal:
            print(f"the registry could not be read, so nothing was checked: {refusal}")
            return GUARD_UNREADABLE
        timer_owned = installed_timer_owned_entry_points()
        if not timer_owned:
            print("no installed timer drives any entry point, so this guard checked nothing")
            return GUARD_NO_TIMER_SET
        offending = double_run_rows(connection, timer_owned)
        for job_id in offending:
            print(job_id)
        return GUARD_HAZARD if offending else GUARD_CLEAN


def main(argv: Sequence[str] | None = None, control: SystemdControl | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Resolve the job registry, compute what is due, and record what happened."
    )
    parser.add_argument("--run", default=None, metavar="JOB_ID", help="run one job by hand")
    parser.add_argument("--force", action="store_true", help="bypass the due test and enabled")
    parser.add_argument("--wait-for-lock", type=float, default=0.0, metavar="SECONDS")
    parser.add_argument("--dry-run", action="store_true", help="compute the plan, write nothing")
    # Two read-only introspections the deploy gate joins its assertions to, so the gate
    # derives them from the code that runs rather than keeping a second copy in shell.
    parser.add_argument(
        "--timer-owned",
        action="store_true",
        help="print the entry points an installed timer already drives, one per line",
    )
    parser.add_argument(
        "--read-relations",
        action="store_true",
        help="print the lineage relations the tick reads, one per line",
    )
    parser.add_argument(
        "--double-run-check",
        action="store_true",
        help="refuse if a launch row names an entry point an installed timer already drives",
    )
    arguments = parser.parse_args(argv)
    if arguments.timer_owned:
        for entry_point in sorted(installed_timer_owned_entry_points()):
            print(entry_point)
        return 0
    if arguments.read_relations:
        for relation in sorted(read_relations()):
            print(relation)
        return 0
    if arguments.double_run_check:
        return double_run_check()
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
        return _exit_code(recorded, registry)


if __name__ == "__main__":
    raise SystemExit(main())
