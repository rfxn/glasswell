"""The launch-posture supersession: six appended rows, and 077 left exactly as it registered.

The file is found by its `*_scheduler_observe.sql` suffix rather than by its number, because the
integrator assigns the digits at the merge train. What is asserted here is the pair of claims no
CHECK can reach: that the appended rows resolve `observe` at the host's today and at a later
deploy, and that the migration and `seed/schedules.py` write the same rows rather than two
readings of one ruling.
"""

from __future__ import annotations

import re
from datetime import date

import psycopg
import pytest

from glasswell.db.migrate import discover_migrations, migrate
from glasswell.seed import conformance_schedules as rules_module
from glasswell.seed import schedules as schedules_module
from glasswell.seed import seed_all
from glasswell.seed.conformance_schedules import SCHEDULE_RULES
from glasswell.seed.schedules import (
    CO_OBSERVE_SCHEDULES,
    OBSERVED_FROM,
    REGISTERED_ON,
    _schedule_row,
    observe_rule_id,
)

pytestmark = pytest.mark.integration

MIGRATION = "scheduler_observe"
CO_JOB_IDS = (
    "co_ecmc_gis",
    "co_ecmc_production",
    "co_wells",
    "co_production",
    "co_tiles",
    "co_counts",
)
SCHEDULE_COLUMNS = (
    "job_id, effective_from, published_at, rule_id, trigger, launch_mode, cadence_interval,"
    " cadence_monthly_on_day, cadence_note, memory_max, timeout_seconds, concurrency_group,"
    " enabled, legacy_unit, external_timer_unit, external_service_unit"
)


def migration_sql(name: str) -> str:
    return next(item.sql for item in discover_migrations() if item.name == name)


@pytest.fixture
def seeded(db: psycopg.Connection) -> psycopg.Connection:
    seed_all(db)
    db.commit()
    return db


def test_the_supersession_applies_gapless_on_the_migration_before_it(empty_db) -> None:
    """A migration the runner refuses to discover disarms nothing."""
    applied = migrate(empty_db)
    empty_db.commit()
    versions = [item.version for item in applied]
    names = {item.version: item.name for item in applied}

    assert versions == list(range(1, len(versions) + 1))
    # Its own version, not the last one: the Texas track's migration merged in behind this
    # file and took the next digit, so "last applied" stopped being a property of the
    # supersession and adjacency to the migration it was written against is what is held.
    ordinal = next(version for version, name in names.items() if name == MIGRATION)
    assert names[ordinal - 1] == "facet_status_resolution"


def test_one_evidence_pair_in_the_whole_file() -> None:
    """Counted by shape, so the guard survives its own repoint: the pair is the placeholder
    before the train and the tag plus its merge commit after, and what is being held is that
    the file states its evidence once."""
    body = migration_sql(MIGRATION)

    tags = re.findall(r"'(?:UNRELEASED|v\d+\.\d+)'", body)
    commits = re.findall(r"'[0-9a-f]{40}'", body)

    assert len(tags) == 1, f"the file states its evidence tag {len(tags)} times: {tags}"
    assert len(commits) == 1, f"the file states its evidence commit {len(commits)} times"


def test_every_colorado_row_resolves_observe_today_and_at_a_later_deploy(seeded) -> None:
    """The whole point of the two clocks: the ruling has to be what the host reads, both on the
    day it was made and on every day after it, or the hazard is only disarmed on paper."""
    with seeded.cursor() as cursor:
        for horizon in ("current_date", "current_date + 30"):
            cursor.execute(
                "select s.job_id, s.launch_mode, s.rule_id, s.effective_from"
                f"  from lineage.job_schedules_as_of({horizon}, {horizon}) s"
                " where s.job_id = any(%s) order by s.job_id",
                (list(CO_JOB_IDS),),
            )
            resolved = cursor.fetchall()

            assert [row[0] for row in resolved] == sorted(CO_JOB_IDS), horizon
            assert {row[1] for row in resolved} == {"observe"}, horizon
            assert {row[2] for row in resolved} == {
                observe_rule_id(job_id) for job_id in CO_JOB_IDS
            }, horizon
            assert {row[3] for row in resolved} == {OBSERVED_FROM}, horizon


def test_no_row_the_registry_resolves_launches(seeded) -> None:
    """The posture as one number, which is the shape verify.sh asserts on the host."""
    with seeded.cursor() as cursor:
        cursor.execute(
            "select count(*) from lineage.job_schedules_as_of(current_date, current_date)"
            " where launch_mode = 'launch'"
        )

        assert cursor.fetchone()[0] == 0


def test_the_founding_rows_are_appended_over_and_never_edited(seeded) -> None:
    """077 is applied and its rows are the record of what was decided on 2026-09-02. A
    supersession that quietly rewrote them would leave nothing to read the correction against."""
    with seeded.cursor() as cursor:
        cursor.execute(
            "select job_id, launch_mode, rule_id from lineage.job_schedules"
            " where job_id = any(%s) and effective_from = %s and published_at = %s"
            " order by job_id",
            (list(CO_JOB_IDS), REGISTERED_ON, REGISTERED_ON),
        )
        founding = cursor.fetchall()

    assert [row[0] for row in founding] == sorted(CO_JOB_IDS)
    assert {row[1] for row in founding} == {"launch"}
    assert {row[2] for row in founding} == {
        f"cr_job_cadence_{job_id}_1" for job_id in CO_JOB_IDS
    }


def test_each_successor_rule_states_the_argument_in_served_words(seeded) -> None:
    """R8: a posture recorded as a row nobody can read the reason for is a posture in code."""
    with seeded.cursor() as cursor:
        cursor.execute(
            "select rule_id, supersedes_rule_id, stage, rule_kind, effective_from,"
            "       spec->>'launch_mode', rationale"
            "  from lineage.conformance_rules where rule_id = any(%s) order by rule_id",
            ([observe_rule_id(job_id) for job_id in CO_JOB_IDS],),
        )
        rules = cursor.fetchall()

    assert len(rules) == 6
    for rule_id, supersedes, stage, kind, effective_from, launch_mode, rationale in rules:
        assert supersedes == rule_id.replace("_2", "_1")
        assert (stage, kind) == ("schedule", "code_ref")
        assert effective_from == OBSERVED_FROM
        assert launch_mode == "observe"
        for phrase in (
            "plan.py:363",
            "runner.py:306",
            "legacy pipeline timers are not retired",
            "steps 6c and 6d",
            "verify.sh does not yet assert the schedule",
            "armed observe-mode ticks",
        ):
            assert phrase in rationale, f"{rule_id} does not say {phrase!r}"


def test_the_migration_writes_exactly_the_rows_the_seed_writes(
    db: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The deployed host's own path, which is the only one where this file does any work.

    A fresh database seeds both generations and the migration is a guarded no-op; the host has
    077's rows already, so the migration is what lands the correction before `seed_all` runs at
    all. Seeding the founding rows alone reproduces that state, and the rows the migration then
    writes have to be the rows the seed would have written.
    """
    founding_only = tuple(
        row for row in schedules_module.SCHEDULES if row.get("rule_id") is None
    )
    monkeypatch.setattr(schedules_module, "SCHEDULES", founding_only)
    monkeypatch.setattr(
        rules_module,
        "SCHEDULE_RULES",
        tuple(rule for rule in SCHEDULE_RULES if rule["supersedes_rule_id"] is None),
    )
    seed_all(db)
    db.commit()
    with db.cursor() as cursor:
        cursor.execute(
            "select count(*) from lineage.job_schedules where effective_from = %s",
            (OBSERVED_FROM,),
        )
        assert cursor.fetchone()[0] == 0, "the fixture already carries the correction"

        cursor.execute(migration_sql(MIGRATION))
        cursor.execute(
            f"select {SCHEDULE_COLUMNS} from lineage.job_schedules"
            " where effective_from = %s order by job_id",
            (OBSERVED_FROM,),
        )
        written = cursor.fetchall()

    expected = sorted(
        tuple(_schedule_row(row)[column.strip()] for column in SCHEDULE_COLUMNS.split(","))
        for row in CO_OBSERVE_SCHEDULES
    )

    assert written == expected


def test_the_migration_also_lands_the_rules_the_seed_would_have(
    db: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rule and the row travel together: a schedule citing an unseeded rule is a broken
    handle, and `conformance_rules` is where the reason lives."""
    monkeypatch.setattr(
        schedules_module,
        "SCHEDULES",
        tuple(row for row in schedules_module.SCHEDULES if row.get("rule_id") is None),
    )
    monkeypatch.setattr(
        rules_module,
        "SCHEDULE_RULES",
        tuple(rule for rule in SCHEDULE_RULES if rule["supersedes_rule_id"] is None),
    )
    seed_all(db)
    db.commit()
    with db.cursor() as cursor:
        cursor.execute(migration_sql(MIGRATION))
        cursor.execute(
            "select rule_id, rule_family, supersedes_rule_id, source_id, stage,"
            "       applies_to_fields, rule_kind, spec, rule, rationale, evidence_url,"
            "       code_ref, effective_from"
            "  from lineage.conformance_rules where supersedes_rule_id = any(%s)"
            " order by rule_id",
            ([f"cr_job_cadence_{job_id}_1" for job_id in CO_JOB_IDS],),
        )
        written = cursor.fetchall()

    successors = sorted(
        (rule for rule in SCHEDULE_RULES if rule["supersedes_rule_id"] is not None),
        key=lambda rule: str(rule["rule_id"]),
    )
    expected = [
        (
            rule["rule_id"],
            str(rule["rule_id"]).rsplit("_", 1)[0],
            rule["supersedes_rule_id"],
            rule["source_id"],
            rule["stage"],
            rule["applies_to_fields"],
            rule["rule_kind"],
            rule["spec"],
            rule["rule"],
            rule["rationale"],
            rule["evidence_url"],
            rule["code_ref"],
            rule["effective_from"],
        )
        for rule in successors
    ]

    assert written == expected


def test_the_ruling_date_is_written_by_both_writers(seeded) -> None:
    """Checklist item 5: the seed is the second writer and a date that drifts between them
    resolves the wrong row."""
    body = migration_sql(MIGRATION)

    assert body.count(f"date '{OBSERVED_FROM.isoformat()}'") == 4
    assert date(2026, 9, 3) == OBSERVED_FROM
    assert OBSERVED_FROM > REGISTERED_ON
