"""The standing gates on the job registry: a registered source is a scheduled source.

Five assertions no CHECK in the migration can reach. Gates 1, 2, 4 and 5 are `select`
statements over the seeded rows and live here from P1; gate 3 calls the planner and lands with
it, in the phase that builds the due rule.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import psycopg
import pytest

from glasswell.lineage.schedules import load_schedules
from glasswell.scheduler.plan import collect_evidence, due_for
from glasswell.seed.conformance_schedules import SCHEDULE_RULES
from glasswell.seed.schedules import (
    DEPENDENCIES,
    JOB_SOURCES,
    JOBS,
    REFUSAL_CODES,
    SCHEDULES,
    UNJOBBED_SOURCES,
    anchors,
    cadence_rule_id,
)

pytestmark = pytest.mark.contract

RULE_ID_PATTERN = re.compile(r"^cr_job_cadence_[a-z0-9_]+_[0-9]+$")


def test_gate_1_every_registered_source_has_a_job_and_every_job_names_a_real_source(
    db: psycopg.Connection,
) -> None:
    """Two-sided, so a source with no job and a job naming no source both redden.

    `proj_grid_nad27` is a NOAA datum grid that moves when the dependency pin moves and has no
    fetch job; `tx_pdq_dsv` carries a poll policy and, on the deployed host, no source row at
    all. Both are named rather than left to a membership check.
    """
    with db.cursor() as cursor:
        cursor.execute("select source_id from lineage.sources")
        registered = {row[0] for row in cursor.fetchall()}
        cursor.execute("select distinct source_id from lineage.job_sources")
        jobbed = {row[0] for row in cursor.fetchall()}

    assert jobbed == registered - UNJOBBED_SOURCES
    assert UNJOBBED_SOURCES & registered, "an exemption nothing registers cannot fail"


def test_gate_2_every_jurisdiction_mart_waits_on_an_ingest_of_its_own_jurisdiction(
    db: psycopg.Connection,
) -> None:
    with db.cursor() as cursor:
        cursor.execute(
            "select j.job_id, j.jurisdiction"
            "  from lineage.scheduled_jobs j"
            " where j.kind = 'mart' and j.jurisdiction is not null"
        )
        marts = cursor.fetchall()
        cursor.execute(
            "select d.job_id, count(*)"
            "  from lineage.job_dependencies d"
            "  join lineage.scheduled_jobs parent on parent.job_id = d.depends_on_job_id"
            "  join lineage.scheduled_jobs child on child.job_id = d.job_id"
            " where parent.kind = 'ingest' and parent.jurisdiction = child.jurisdiction"
            " group by d.job_id"
        )
        covered = dict(cursor.fetchall())

    assert marts, "no jurisdiction-scoped mart is registered; this gate cannot fail"
    uncovered = [job_id for job_id, _code in marts if not covered.get(job_id)]
    assert uncovered == [], (
        f"{uncovered} read a jurisdiction-scoped input and wait on no ingest of that"
        " jurisdiction, so nothing would ever make them due"
    )


def test_gate_4_every_cadence_rule_is_published_and_the_null_set_is_exactly_the_platform_rows(
    db: psycopg.Connection,
) -> None:
    with db.cursor() as cursor:
        cursor.execute(
            "select s.job_id, s.rule_id, s.trigger,"
            "       r.rule_id is not null as rule_exists,"
            "       p.rule_id is not null as published"
            "  from lineage.job_schedules s"
            "  left join lineage.conformance_rules r on r.rule_id = s.rule_id"
            "  left join lineage.conformance_rule_publications p on p.rule_id = s.rule_id"
            " order by s.job_id"
        )
        rows = cursor.fetchall()

    assert rows, "the registry seeded no schedule; this gate cannot fail"
    for job_id, rule_id, trigger, rule_exists, published in rows:
        if trigger == "external_timer":
            assert rule_id is None, (
                f"{job_id} records a cadence its own unit's OnCalendar already holds"
            )
            continue
        assert rule_id is not None, job_id
        assert RULE_ID_PATTERN.match(rule_id), rule_id
        assert rule_exists, f"{job_id} points at an unseeded rule {rule_id}"
        assert published, f"{rule_id} has no first-publication evidence"


def test_gate_4_the_seeded_rules_are_exactly_the_rules_the_schedules_name() -> None:
    named = {
        cadence_rule_id(str(row["job_id"]))
        for row in SCHEDULES
        if row["trigger"] != "external_timer"
    }

    assert {str(rule["rule_id"]) for rule in SCHEDULE_RULES} == named


def test_gate_5_the_seed_tuple_is_what_the_registry_resolves(db: psycopg.Connection) -> None:
    """The two writers, held to one truth: the module's rows and the resolver's rows agree."""
    registry = load_schedules(db)
    anchor = anchors()

    assert set(registry.by_job) == {str(job["job_id"]) for job in JOBS}
    assert set(registry.refusal_codes) == {code for code, _class, _sentence in REFUSAL_CODES}

    by_schedule = {str(row["job_id"]): row for row in SCHEDULES}
    for job in registry:
        declared = next(row for row in JOBS if row["job_id"] == job.job_id)
        schedule = by_schedule[job.job_id]
        assert job.label == declared["label"]
        assert job.kind == declared["kind"]
        assert job.entry_point == declared["entry_point"]
        assert list(job.argv) == list(declared["argv"])  # type: ignore[arg-type]
        assert job.jurisdiction == declared["jurisdiction"]
        assert job.run_as == declared["run_as"]
        assert job.anchor_source_id == anchor.get(job.job_id)
        assert job.trigger == schedule["trigger"]
        assert job.cadence_note == schedule["cadence_note"]
        assert job.cadence_interval == schedule.get("cadence_interval")
        assert job.cadence_monthly_on_day == schedule.get("cadence_monthly_on_day")
        assert job.memory_max == schedule.get("memory_max")
        assert job.timeout_seconds == schedule.get("timeout_seconds")
        assert job.legacy_unit == schedule.get("legacy_unit")
        assert set(job.source_ids) == set(JOB_SOURCES.get(job.job_id, ()))
        assert {edge.depends_on_job_id for edge in job.dependencies} == {
            depends_on for job_id, depends_on, _on, _why in DEPENDENCIES
            if job_id == job.job_id
        }


def test_gate_5_no_launching_row_shares_an_entry_point_with_an_installed_timer(
    db: psycopg.Connection,
) -> None:
    """The invariant, in the form that survived the first jurisdiction to launch.

    The hazard was never `launch` itself: it is two runners over one command. The four legacy
    jurisdictions stay armed through `glasswell-ingest.service`, so their rows observe and this
    gate says so by naming the unit rather than the posture; a jurisdiction that installs no
    unit has no second runner and may launch when its own cadence rule argues for it.
    """
    registry = load_schedules(db)

    launching = [job for job in registry if job.launch_mode != "observe"]
    assert launching, "no row launches; this gate would be vacuous"
    assert [job.job_id for job in launching if job.legacy_unit is not None] == []
    timer_driven = {
        job.entry_point for job in registry if job.trigger == "external_timer"
    }
    assert [job.job_id for job in launching if job.entry_point in timer_driven] == []
    observing = {job.job_id for job in registry if job.launch_mode == "observe"}
    assert {job.job_id for job in registry if job.legacy_unit is not None} <= observing


# Far enough forward that a 35-day interval has certainly elapsed, so a row that still cannot
# produce an instant is one the due rule can never produce one for.
FUTURE = datetime(2030, 1, 15, 9, tzinfo=UTC)


def _evidence_for(db: psycopg.Connection, registry):
    return collect_evidence(
        db,
        now=FUTURE,
        source_ids=[source for job in registry.resolvable() for source in job.source_ids],
    )


def test_gate_3_every_cadence_row_can_produce_a_planned_instant(db: psycopg.Connection) -> None:
    """M-12: an interval nothing can compute a due time from is a schedule that never fires.

    The gate calls the planner rather than re-deriving the condition, which is why it lands
    with the planner and not with the migration: testing `expected_poll_interval is not null`
    passes for a source that has an interval and has never been fetched, which is exactly the
    case that left three registered jobs permanently not due.
    """
    registry = load_schedules(db)
    evidence = _evidence_for(db, registry)

    cadence_jobs = [job for job in registry.resolvable() if job.trigger == "cadence"]
    assert len(cadence_jobs) >= 8, "too few cadence rows for this gate to be a real check"
    undueable = [
        job.job_id
        for job in cadence_jobs
        if due_for(job, registry, evidence, FUTURE) is None
    ]
    assert undueable == [], (
        f"{undueable} carry a cadence the due rule can produce no instant for, so they would"
        " never fire: give their sources an interval, or make them manual"
    )


def test_gate_3_a_source_with_no_interval_and_no_fetch_history_stays_not_due(
    db: psycopg.Connection,
) -> None:
    """The negative half, so the gate is not vacuous: this is the row that must redden."""
    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.scheduled_jobs"
            " (job_id, label, kind, entry_point, anchor_source_id, run_as, rationale)"
            " values ('ingest_null_interval_probe', 'Probe', 'ingest',"
            "         'glasswell.ingest.probe', 'nm_ocd_pool', 'glasswell',"
            "         'a probe with a null-interval source')"
        )
        cursor.execute(
            "insert into lineage.job_sources (job_id, source_id)"
            " values ('ingest_null_interval_probe', 'nm_ocd_pool')"
        )
        cursor.execute(
            "insert into lineage.job_schedules"
            " (job_id, effective_from, published_at, rule_id, trigger, cadence_interval,"
            "  cadence_note, memory_max, timeout_seconds)"
            " values ('ingest_null_interval_probe', current_date, current_date,"
            "         'cr_job_cadence_ingest_nd_gis_1', 'cadence', interval '35 days',"
            "         'a probe cadence over a source with no interval', '1G', 60)"
        )
    db.commit()
    registry = load_schedules(db)
    evidence = _evidence_for(db, registry)
    probe = registry.by_job["ingest_null_interval_probe"]

    assert due_for(probe, registry, evidence, FUTURE) is None


def test_gate_3_a_35_day_source_with_no_fetch_history_is_due_at_the_hour(
    db: psycopg.Connection,
) -> None:
    """The fixture the rule exists for: an interval, and nothing has ever polled it."""
    registry = load_schedules(db)
    evidence = _evidence_for(db, registry)
    job = registry.by_job["ingest_tx_gis"]

    with db.cursor() as cursor:
        cursor.execute(
            "select count(*) from lineage.fetch_attempts where source_id = 'tx_gis_wells_county'"
        )
        assert cursor.fetchone()[0] == 0, "the fixture needs a source nothing has polled"

    entry = due_for(job, registry, evidence, FUTURE)

    assert entry is not None
    assert entry.planned_at == FUTURE.replace(minute=0, second=0, microsecond=0)


def test_gate_5_the_seed_tuple_is_what_slash_v1_schedules_serves(client) -> None:
    """The served half: the two writers agreed in the database, and the wire agrees with both."""
    served: dict[str, dict] = {}
    url = "/v1/schedules"
    params: dict[str, object] = {"limit": 200}
    while url is not None:
        body = client.get(url, params=params).json()
        served |= {row["job_id"]: row for row in body["data"]}
        url = (body.get("links") or {}).get("next")
        params = {}

    assert set(served) == {str(job["job_id"]) for job in JOBS}
    by_schedule = {str(row["job_id"]): row for row in SCHEDULES}
    for job in JOBS:
        job_id = str(job["job_id"])
        row = served[job_id]
        schedule = by_schedule[job_id]
        assert row["label"] == job["label"]
        assert row["kind"] == job["kind"]
        assert row["entry_point"] == job["entry_point"]
        assert row["run_as"] == job["run_as"]
        assert row["trigger"] == schedule["trigger"]
        assert row["launch_mode"] == schedule.get("launch_mode", "observe")
        assert row["cadence"]["note"] == schedule["cadence_note"]
        assert row["cadence"]["monthly_on_day"] == schedule.get("cadence_monthly_on_day")
        assert row["limits"]["memory_max"] == schedule.get("memory_max")
        assert row["limits"]["timeout_seconds"] == schedule.get("timeout_seconds")
        assert set(row["source_ids"]) == set(JOB_SOURCES.get(job_id, ()))
        assert row["decision"]["rationale"] == job["rationale"]


def test_gate_5_a_platform_row_serves_its_units_where_it_serves_no_rule(client) -> None:
    """NIT-15: four rows carry a null rule_id, and an empty rule link is not an answer."""
    body = client.get("/v1/schedules/platform_backup").json()["data"]

    assert body["decision"]["rule_id"] is None
    assert body["decision"]["external_timer_unit"] == "glasswell-backup.timer"
    assert body["decision"]["external_service_unit"] == "glasswell-backup.service"
    assert body["decision"]["rationale"]
    assert {row["code"] for row in body["refusal_codes"]} >= {
        "manual_only",
        "deferred",
        "scheduler_lost_unit",
    }
    assert {row["severity_class"] for row in body["refusal_codes"]} == {
        "informational",
        "waiting",
        "fault",
    }


def test_gate_5_a_cadence_row_serves_the_rule_the_conformance_surface_resolves(client) -> None:
    served = client.get("/v1/schedules/ingest_nd_gis").json()["data"]
    rule_id = served["decision"]["rule_id"]

    assert rule_id == "cr_job_cadence_ingest_nd_gis_1"
    rule = client.get(f"/v1/conformance/{rule_id}").json()["data"]
    assert rule["stage"] == "schedule"
    assert rule["rule_kind"] == "code_ref"
    assert rule["rationale"]
    assert rule["published_vintage"]
