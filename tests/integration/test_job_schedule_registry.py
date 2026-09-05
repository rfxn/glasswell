"""The schedule registry's own guarantees: two clocks, append-once evidence, narrow grants.

The migration ships DDL and the role; the rows arrive from `seed_all`. What is asserted here is
what no seeder can prove -- that a restatement resolves over the row it corrects, that a closed
run is immutable, that the plan key keeps a refusal and a plan apart, and that the scheduler's
login identity can read exactly the relations its own SQL names and nothing further.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import psycopg
import pytest

from glasswell.lineage import schedules as schedule_sql
from glasswell.lineage.schedules import ScheduleRegistryError, load_schedules
from glasswell.scheduler import plan as planner_sql
from glasswell.scheduler.plan import double_run_rows
from glasswell.scheduler.units import installed_timer_owned_entry_points
from glasswell.seed import seed_all
from glasswell.status import source_health

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 2, 12, tzinfo=UTC)
JOB = "ingest_nd_gis"
SIX_TABLES = (
    "lineage.refusal_codes",
    "lineage.scheduled_jobs",
    "lineage.job_sources",
    "lineage.job_schedules",
    "lineage.job_dependencies",
    "lineage.job_runs",
)


@contextmanager
def acting_as(connection: psycopg.Connection, role: str) -> Iterator[psycopg.Cursor]:
    with connection.cursor() as cursor:
        cursor.execute(f"set local role {role}")
        try:
            yield cursor
        finally:
            connection.rollback()


@pytest.fixture
def seeded(db: psycopg.Connection) -> psycopg.Connection:
    seed_all(db)
    db.commit()
    return db


def insert_run(
    connection: psycopg.Connection,
    *,
    run: str,
    planned_at: datetime,
    outcome: str | None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    refusal_code: str | None = None,
    failure_detail: str | None = None,
    launched_by: str = "scheduler",
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into lineage.job_runs"
            " (run_id, job_id, planned_at, started_at, completed_at, launched_by, outcome,"
            "  refusal_code, failure_detail)"
            " values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                run,
                JOB,
                planned_at,
                started_at,
                completed_at,
                launched_by,
                outcome,
                refusal_code,
                failure_detail,
            ),
        )


def test_the_resolver_returns_every_seeded_job_with_its_edges(seeded) -> None:
    registry = load_schedules(seeded)

    with seeded.cursor() as cursor:
        cursor.execute("select count(*) from lineage.scheduled_jobs")
        jobs = cursor.fetchone()[0]

    assert len(registry) == jobs
    assert registry.get(JOB) is not None
    assert registry.get(JOB).source_ids  # type: ignore[union-attr]
    assert any(job.dependencies for job in registry)
    assert registry.severity_of("deferred") == "waiting"
    assert registry.severity_of("scheduler_lost_unit") == "fault"


def test_a_restatement_at_one_effective_from_resolves_at_the_later_knowledge_time(
    seeded,
) -> None:
    later = date(2026, 9, 9)
    with seeded.cursor() as cursor:
        cursor.execute(
            "insert into lineage.job_schedules"
            " (job_id, effective_from, published_at, rule_id, trigger, cadence_interval,"
            "  cadence_note, memory_max, timeout_seconds)"
            " select job_id, effective_from, %s, rule_id, trigger, interval '7 days',"
            "        'Restated to 7 days', memory_max, timeout_seconds"
            "   from lineage.job_schedules where job_id = %s",
            (later, JOB),
        )
    seeded.commit()

    before = load_schedules(seeded, date(2026, 9, 2))
    after = load_schedules(seeded, later)

    assert before.by_job[JOB].cadence_interval == timedelta(days=35)
    assert after.by_job[JOB].cadence_interval == timedelta(days=7)
    assert after.by_job[JOB].published_at == later


def test_a_schedule_row_is_appended_and_never_edited(seeded) -> None:
    with pytest.raises(psycopg.errors.RestrictViolation, match="append_only_violation"):
        seeded.execute(
            "update lineage.job_schedules set enabled = false where job_id = %s", (JOB,)
        )
    seeded.rollback()
    with pytest.raises(psycopg.errors.RestrictViolation, match="append_only_violation"):
        seeded.execute("delete from lineage.job_schedules where job_id = %s", (JOB,))


def test_a_closed_run_refuses_an_update_and_an_open_one_accepts_exactly_one(seeded) -> None:
    open_run = "jrn_00000000000000000000000001"
    insert_run(seeded, run=open_run, planned_at=NOW, outcome=None, started_at=NOW)
    seeded.commit()

    with seeded.cursor() as cursor:
        cursor.execute(
            "update lineage.job_runs set outcome = 'ran', completed_at = %s where run_id = %s",
            (NOW + timedelta(minutes=4), open_run),
        )
    seeded.commit()

    with pytest.raises(psycopg.errors.RaiseException, match="is immutable"):
        seeded.execute(
            "update lineage.job_runs set exit_status = 1 where run_id = %s", (open_run,)
        )
    seeded.rollback()
    with pytest.raises(psycopg.errors.RestrictViolation, match="append_only_violation"):
        seeded.execute("delete from lineage.job_runs where run_id = %s", (open_run,))


def test_an_interrupted_run_carries_a_refusal_code_and_is_accepted(seeded) -> None:
    insert_run(
        seeded,
        run="jrn_0000000000000000000000000I",
        planned_at=NOW,
        outcome="interrupted",
        started_at=NOW,
        completed_at=NOW + timedelta(minutes=1),
        refusal_code="scheduler_lost_unit",
    )
    seeded.commit()

    with seeded.cursor() as cursor:
        cursor.execute(
            "select outcome, refusal_code from lineage.job_runs where outcome = 'interrupted'"
        )
        assert cursor.fetchall() == [("interrupted", "scheduler_lost_unit")]


def test_a_plan_and_a_refusal_coexist_at_one_instant_and_a_second_of_either_collapses(
    seeded,
) -> None:
    insert_run(
        seeded,
        run="jrn_0000000000000000000000000W",
        planned_at=NOW,
        outcome="would_run",
        completed_at=NOW,
    )
    insert_run(
        seeded,
        run="jrn_0000000000000000000000000R",
        planned_at=NOW,
        outcome="refused",
        completed_at=NOW,
        refusal_code="dependency_never_ran",
    )
    seeded.commit()

    with pytest.raises(psycopg.errors.UniqueViolation):
        insert_run(
            seeded,
            run="jrn_0000000000000000000000000X",
            planned_at=NOW,
            outcome="would_run",
            completed_at=NOW,
        )
    seeded.rollback()
    with pytest.raises(psycopg.errors.UniqueViolation):
        insert_run(
            seeded,
            run="jrn_0000000000000000000000000Y",
            planned_at=NOW,
            outcome="refused",
            completed_at=NOW,
            refusal_code="dependency_failed",
        )
    seeded.rollback()

    with seeded.cursor() as cursor:
        cursor.execute(
            "select outcome from lineage.job_runs where planned_at = %s order by outcome",
            (NOW,),
        )
        assert [row[0] for row in cursor.fetchall()] == ["refused", "would_run"]


def test_an_empty_registry_is_a_refusal_and_not_an_empty_map(db) -> None:
    with pytest.raises(ScheduleRegistryError, match="nothing has been published"):
        load_schedules(db)


def test_no_role_named_root_is_created(db) -> None:
    with db.cursor() as cursor:
        cursor.execute("select 1 from pg_roles where rolname = 'root'")
        assert cursor.fetchone() is None


def test_the_scheduler_role_can_log_in_and_holds_no_pipeline_membership(db) -> None:
    with db.cursor() as cursor:
        cursor.execute(
            "select rolcanlogin, rolsuper from pg_roles where rolname = 'glasswell_scheduler'"
        )
        row = cursor.fetchone()
        assert row == (True, False)
        cursor.execute(
            "select pg_has_role('glasswell_scheduler', 'glasswell_pipeline', 'MEMBER')"
        )
        assert cursor.fetchone()[0] is False


def planner_relations() -> set[str]:
    """The relations the planner's own SQL names, extracted rather than kept beside it.

    Derived from the modules the tick actually runs, so a query one of them grows later brings
    its own grant with it instead of waiting for someone to remember a list.
    """
    sql = "\n".join(
        [
            schedule_sql._RESOLVED,
            schedule_sql._REFUSAL_CODES,
            schedule_sql._LATEST_PUBLISHED,
            planner_sql._LAST_RAN,
            planner_sql._LAST_OUTCOME,
            planner_sql._NEW_FETCHES,
            planner_sql._SOURCE_INTERVALS,
            source_health._SOURCES,
        ]
    )
    return set(re.findall(r"\blineage\.[a-z_]+\b", sql)) - {
        "lineage.job_schedules_as_of"
    }


def test_the_scheduler_grants_are_derived_from_the_queries_the_planner_runs(db) -> None:
    relations = planner_relations()

    assert len(relations) >= 8, f"the extraction found too little to be a real check: {relations}"
    with db.cursor() as cursor:
        for relation in sorted(relations):
            cursor.execute(
                "select has_table_privilege('glasswell_scheduler', %s, 'SELECT')", (relation,)
            )
            assert cursor.fetchone()[0], f"glasswell_scheduler cannot read {relation}"


def test_the_scheduler_reads_refusals_through_a_view_and_not_the_account_trail(db) -> None:
    """H-14. Growing the source-health query grew what the scheduler must read, and 083's first
    shape granted it all of lineage.audit_events -- the same table that carries `username`,
    `client_ip`, `role` and session-revocation counts (api/routers/session.py, api/accounts.py).
    The query asks for one column of one event type, so that is what the grant is on."""
    with db.cursor() as cursor:
        cursor.execute(
            "select has_table_privilege('glasswell_scheduler', 'lineage.audit_events', 'SELECT')"
        )
        assert cursor.fetchone()[0] is False, "the scheduler can read the account and session trail"

    assert "lineage.staging_load_failures" in planner_relations()

    with acting_as(db, "glasswell_scheduler") as cursor:
        cursor.execute("select count(*) from lineage.staging_load_failures")
        assert cursor.fetchone()[0] >= 0
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cursor.execute("select payload from lineage.audit_events")


def test_the_scheduler_may_write_the_ledger_and_nothing_else(db) -> None:
    with db.cursor() as cursor:
        cursor.execute(
            "select has_table_privilege('glasswell_scheduler', 'lineage.job_runs', 'INSERT'),"
            "       has_table_privilege('glasswell_scheduler', 'lineage.job_runs', 'UPDATE'),"
            "       has_table_privilege('glasswell_scheduler', 'lineage.job_schedules',"
            "                           'INSERT'),"
            "       has_schema_privilege('glasswell_scheduler', 'canonical', 'USAGE'),"
            "       has_schema_privilege('glasswell_scheduler', 'staging', 'USAGE'),"
            "       has_schema_privilege('glasswell_scheduler', 'marts', 'USAGE')"
        )
        assert cursor.fetchone() == (True, True, False, False, False, False)


def test_the_api_role_reads_all_six_registry_objects(seeded) -> None:
    with acting_as(seeded, "glasswell_api") as cursor:
        for relation in SIX_TABLES:
            cursor.execute(f"select count(*) from {relation}")
            assert cursor.fetchone()[0] >= 0
        cursor.execute(
            "select count(*) from lineage.job_schedules_as_of(current_date, current_date)"
        )
        assert cursor.fetchone()[0] > 0


def test_a_maintenance_row_may_name_a_script_and_hold_no_uid_but_a_data_job_may_not(
    seeded,
) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        seeded.execute(
            "insert into lineage.scheduled_jobs"
            " (job_id, label, kind, entry_point, anchor_source_id, run_as, rationale)"
            " values ('ingest_probe', 'Probe', 'ingest', '/usr/local/sbin/probe.sh',"
            "         'nd_mpr_xlsx', 'glasswell', 'a data job may not name a script')"
        )
    seeded.rollback()
    with pytest.raises(psycopg.errors.CheckViolation):
        seeded.execute(
            "insert into lineage.scheduled_jobs"
            " (job_id, label, kind, entry_point, anchor_source_id, rationale)"
            " values ('ingest_probe', 'Probe', 'ingest', 'glasswell.ingest.probe',"
            "         'nd_mpr_xlsx', 'a data job must say which uid it drops to')"
        )
    seeded.rollback()
    seeded.execute(
        "insert into lineage.scheduled_jobs (job_id, label, kind, entry_point, rationale)"
        " values ('platform_probe', 'Probe', 'maintenance', '/usr/local/sbin/probe.sh',"
        "         'its own unit decides the uid')"
    )


def test_the_double_run_guard_is_red_against_a_planted_launch_row(seeded) -> None:
    """N-25's red fixture: a guard that has never been shown red is one nobody has proven.

    The planted row names the neighbour index, which the shipped ingest unit drives through a
    console script rather than a module path -- the one line a `-m <module>` parse misses, and
    the heaviest concurrent-run hazard on the box.
    """
    root = Path(__file__).resolve().parents[2]
    timer_owned = installed_timer_owned_entry_points(
        root / "infra" / "systemd", root / "pyproject.toml"
    )
    assert "glasswell.marts.neighbors" in timer_owned

    assert double_run_rows(seeded, timer_owned) == ()

    # A second job over the same entry point rather than a restatement of the first: the
    # two clocks make "a row that resolves today" a supersession of a row published today,
    # and the guard is about the entry point, not about which row names it.
    with seeded.cursor() as cursor:
        cursor.execute(
            "insert into lineage.scheduled_jobs"
            " (job_id, label, kind, entry_point, anchor_source_id, run_as, rationale)"
            " values ('marts_neighbors_probe', 'Planted neighbour index', 'mart',"
            "         'glasswell.marts.neighbors', 'fracfocus_csv', 'glasswell',"
            "         'a planted row the guard must refuse')"
        )
        cursor.execute(
            "insert into lineage.job_schedules"
            " (job_id, effective_from, published_at, rule_id, trigger, launch_mode,"
            "  cadence_interval, cadence_note, memory_max, timeout_seconds)"
            " values ('marts_neighbors_probe', current_date, current_date,"
            "         'cr_job_cadence_marts_neighbors_1', 'cadence', 'launch',"
            "         interval '35 days', 'a planted launch row', '6G', 3600)"
        )
    seeded.commit()

    assert double_run_rows(seeded, timer_owned) == ("marts_neighbors_probe",)


def test_a_launch_row_for_a_job_no_timer_drives_is_admitted(seeded) -> None:
    """The re-ruled invariant: a jurisdiction with no legacy timer is not blocked by it."""
    root = Path(__file__).resolve().parents[2]
    timer_owned = installed_timer_owned_entry_points(
        root / "infra" / "systemd", root / "pyproject.toml"
    )
    assert "glasswell.marts.tx_wells" not in timer_owned

    with seeded.cursor() as cursor:
        cursor.execute(
            "insert into lineage.scheduled_jobs"
            " (job_id, label, kind, entry_point, anchor_source_id, run_as, rationale)"
            " values ('marts_tx_wells_probe', 'Planted Texas mart', 'mart',"
            "         'glasswell.marts.tx_wells', 'tx_gis_wells_county', 'glasswell',"
            "         'a state with no legacy timer may launch from the start')"
        )
        cursor.execute(
            "insert into lineage.job_schedules"
            " (job_id, effective_from, published_at, rule_id, trigger, launch_mode,"
            "  cadence_interval, cadence_note, memory_max, timeout_seconds)"
            " values ('marts_tx_wells_probe', current_date, current_date,"
            "         'cr_job_cadence_marts_tx_wells_1', 'cadence', 'launch',"
            "         interval '35 days', 'a state with no legacy timer may launch',"
            "         '6G', 3600)"
        )
    seeded.commit()

    assert double_run_rows(seeded, timer_owned) == ()
