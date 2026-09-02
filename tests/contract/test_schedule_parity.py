"""The standing gates on the job registry: a registered source is a scheduled source.

Five assertions no CHECK in the migration can reach. Gates 1, 2, 4 and 5 are `select`
statements over the seeded rows and live here from P1; gate 3 calls the planner and lands with
it, in the phase that builds the due rule.
"""

from __future__ import annotations

import re

import psycopg
import pytest

from glasswell.lineage.schedules import load_schedules
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


def test_gate_5_every_row_this_track_seeds_observes(db: psycopg.Connection) -> None:
    """The v0.77 posture, measured rather than asserted. v0.78 inverts this."""
    registry = load_schedules(db)

    launching = [job.job_id for job in registry if job.launch_mode != "observe"]
    assert launching == []
