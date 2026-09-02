"""Colorado's registration migration: the rows a fifth jurisdiction arrives as.

The file is found by its `*_colorado.sql` suffix, never by its number: the integrator assigns
the digits at the merge train and a test that pinned one would redden on the renumber.

Every assertion here is about what the migration writes rather than about what a Colorado
module does, which is the claim the track exists to make: the state lands as rows.
"""

from __future__ import annotations

import re
from datetime import date

import psycopg
import pytest
from psycopg.rows import dict_row

from glasswell.db.migrate import discover_migrations
from glasswell.seed import seed_all
from glasswell.seed.conformance_co import CO_RULE_IDS, CO_STATUS_MAP, DOCUMENTED_UNMAPPED_CLASS
from glasswell.seed.jurisdictions import CO_REGISTERED_ON, COLORADO, COLORADO_DECISIONS
from glasswell.seed.schedules import CO_JOBS, DEPENDENCIES, JOB_SOURCES, JOBS, SCHEDULES

pytestmark = pytest.mark.integration

MIGRATION = "colorado"
PLACEHOLDER_TAG = "UNRELEASED"
PLACEHOLDER_COMMIT = "0" * 40
TWO_DIGIT_LITERAL = re.compile(r"""['"](\d{2})['"]""")


@pytest.fixture(autouse=True)
def seeded(db: psycopg.Connection) -> None:
    """Migrations run before the seed, so the registry's rule rows arrive with seed_all."""
    seed_all(db)
    db.commit()


def migration_sql(name: str) -> str:
    return next(item.sql for item in discover_migrations() if item.name == name)


def test_one_placeholder_evidence_pair_in_the_whole_file() -> None:
    """M-1: the release gate asserts at most one of each repo-wide, so the registration reads
    its evidence back from the publications insert rather than restating it."""
    body = migration_sql(MIGRATION)

    assert body.count(f"'{PLACEHOLDER_TAG}'") == 1
    assert body.count(PLACEHOLDER_COMMIT) == 1


def test_no_two_digit_prefix_literal_reaches_the_migration() -> None:
    """N-9: the prefix is read from lineage.jurisdictions_as_of, never written down here."""
    body = re.sub(r"--[^\n]*", "", migration_sql(MIGRATION))
    offenders = [
        line
        for line in body.splitlines()
        if ("api10" in line or "left(" in line) and TWO_DIGIT_LITERAL.search(line)
    ]

    assert offenders == []
    # Declared once, in the registration that founds it, and read from the registry everywhere
    # else. A prefix nowhere in the file would mean the registration did not declare one.
    prefix = str(COLORADO["identity_prefix"])
    assert body.count(f"'{prefix}'") == 1


def test_the_registration_resolves_with_its_identity_derived(db: psycopg.Connection) -> None:
    with db.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "select * from lineage.jurisdictions_as_of(current_date, current_date)"
            " where jurisdiction_code = 'CO'"
        )
        row = cursor.fetchone()

    assert row is not None
    assert row["identity_scheme"] == "api10"
    assert row["identity_is_unique"] is True
    assert row["identity_pattern"] == "^" + row["identity_prefix"] + "[0-9]{8}$"
    assert row["liquids_basis"] == "oil+condensate"
    assert row["wells_tile_layer_id"] == "co_wells"
    assert row["wells_draw_order"] == 45
    assert row["explorer_default"] is False
    assert row["neighbors_available"] is False
    assert row["land_grid_state"] is False
    assert row["land_grid_scope"] is False
    assert row["effective_from"] == CO_REGISTERED_ON
    assert row["legend_note"] is not None
    assert "{count}" in row["wells_subtitle_template"]


def test_the_registered_decisions_are_exactly_the_ones_the_registration_declares(
    db: psycopg.Connection,
) -> None:
    """M-19's set equality: a rule added to the seed and forgotten in the migration reddens."""
    with db.cursor() as cursor:
        cursor.execute(
            "select decision from lineage.jurisdiction_rules where jurisdiction_code = 'CO'"
        )
        resident = {row[0] for row in cursor.fetchall()}

    assert resident == {str(row["decision"]) for row in COLORADO_DECISIONS}


def test_every_colorado_rule_carries_its_publication_evidence(db: psycopg.Connection) -> None:
    """049's trigger refuses an unpublished rule, so this is what makes the seed insertable."""
    with db.cursor() as cursor:
        cursor.execute(
            "select rule_id from lineage.conformance_rule_publications"
            " where rule_id = any(%s)",
            (list(CO_RULE_IDS),),
        )
        published = {row[0] for row in cursor.fetchall()}

    assert published == set(CO_RULE_IDS)


def test_the_status_map_is_seeded_verbatim_and_its_two_integers_are_computed(
    db: psycopg.Connection,
) -> None:
    """M-13: eleven classed and two documented without an equivalent, from the map itself."""
    with db.cursor() as cursor:
        cursor.execute(
            "select status, decode, status_canonical from lineage.co_facility_status_map"
        )
        resident = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}

    assert resident == {
        code: (row["decode"], row["status_canonical"]) for code, row in CO_STATUS_MAP.items()
    }
    classed = [code for code, row in resident.items() if row[1] != DOCUMENTED_UNMAPPED_CLASS]
    documented = [code for code, row in resident.items() if row[1] == DOCUMENTED_UNMAPPED_CLASS]
    assert len(classed) == 11
    assert len(documented) == 2
    assert len(resident) == 13


def test_the_resolver_answers_for_colorado_at_the_registered_prefix(
    db: psycopg.Connection,
) -> None:
    """The Colorado arm on canonical.status_resolution, labelled from the registration."""
    with db.cursor() as cursor:
        cursor.execute(
            "select r.for_state_code, count(*)"
            "  from canonical.status_resolution r"
            "  join lineage.jurisdictions_as_of(current_date, current_date) j"
            "    on j.identity_prefix = r.for_state_code"
            " where j.jurisdiction_code = 'CO'"
            " group by r.for_state_code"
        )
        rows = cursor.fetchall()

    assert len(rows) == 1
    assert rows[0][1] == 13


def test_the_new_mexico_arm_still_answers_beside_it(db: psycopg.Connection) -> None:
    """The view is replaced, not edited: a second arm must not delete the first."""
    with db.cursor() as cursor:
        cursor.execute(
            "select count(*) from canonical.status_resolution r"
            "  join lineage.jurisdictions_as_of(current_date, current_date) j"
            "    on j.identity_prefix = r.for_state_code"
            " where j.jurisdiction_code = 'NM'"
        )
        assert cursor.fetchone()[0] == 14


def test_the_mart_table_and_its_view_are_installed_with_their_grants(
    db: psycopg.Connection,
) -> None:
    with db.cursor() as cursor:
        cursor.execute("select to_regclass('marts.co_wells_tile')")
        assert cursor.fetchone()[0] is not None
        cursor.execute("select to_regclass('marts.tile_co_wells')")
        assert cursor.fetchone()[0] is not None
        cursor.execute(
            "select has_table_privilege('martin', 'marts.tile_co_wells', 'select'),"
            "       has_table_privilege('glasswell_api', 'marts.co_wells_tile', 'select'),"
            "       has_table_privilege('glasswell_pipeline', 'marts.co_wells_tile', 'insert')"
        )
        assert list(cursor.fetchone()) == [True, True, True]


def test_all_four_schedule_tables_carry_colorado(db: psycopg.Connection) -> None:
    """N-32: the rows are written by both writers, so a deploy that seeds nothing schedules."""
    job_ids = [str(job["job_id"]) for job in CO_JOBS]
    with db.cursor() as cursor:
        cursor.execute(
            "select job_id, kind, entry_point, anchor_source_id, run_as"
            "  from lineage.scheduled_jobs where job_id = any(%s) order by job_id",
            (job_ids,),
        )
        jobs = cursor.fetchall()
        cursor.execute(
            "select count(*) from lineage.job_sources where job_id = any(%s)", (job_ids,)
        )
        sources = cursor.fetchone()[0]
        cursor.execute(
            "select job_id, rule_id, trigger, launch_mode from lineage.job_schedules"
            " where job_id = any(%s)",
            (job_ids,),
        )
        schedules = cursor.fetchall()
        cursor.execute(
            "select count(*) from lineage.job_dependencies"
            " where job_id = any(%s) and btrim(rationale) <> ''",
            (job_ids,),
        )
        edges = cursor.fetchone()[0]

    assert len(jobs) == 6
    assert sources == sum(len(JOB_SOURCES[job_id]) for job_id in job_ids if job_id in JOB_SOURCES)
    assert len(schedules) == 6
    assert all(rule_id is not None for _job, rule_id, _trigger, _mode in schedules)
    assert {mode for *_rest, mode in schedules} == {"launch"}
    assert edges == len([edge for edge in DEPENDENCIES if edge[0] in set(job_ids)])
    assert edges == 5


def test_no_colorado_job_is_driven_by_an_installed_timer(db: psycopg.Connection) -> None:
    """NIT-12: launch is admissible only where no external timer drives the same entry point."""
    timed = {str(row["job_id"]) for row in SCHEDULES if row["trigger"] == "external_timer"}
    colorado = {str(job["entry_point"]) for job in CO_JOBS}
    timer_driven = {
        str(job["entry_point"]) for job in JOBS if str(job["job_id"]) in timed
    }

    assert timed, "no external timer is registered; this check would be vacuous"
    assert colorado & timer_driven == set()
    with db.cursor() as cursor:
        cursor.execute(
            "select count(*) from lineage.job_schedules s"
            "  join lineage.scheduled_jobs j on j.job_id = s.job_id"
            " where s.launch_mode = 'launch' and s.legacy_unit is not null"
        )
        assert cursor.fetchone()[0] == 0


def test_seeding_a_seeded_database_twice_changes_nothing(db: psycopg.Connection) -> None:
    def census() -> tuple[int, ...]:
        with db.cursor() as cursor:
            counts = []
            for relation in (
                "lineage.jurisdictions",
                "lineage.jurisdiction_rules",
                "lineage.conformance_rules",
                "lineage.co_facility_status_map",
                "lineage.scheduled_jobs",
                "lineage.job_schedules",
                "lineage.job_sources",
                "lineage.job_dependencies",
                "lineage.sources",
            ):
                cursor.execute(f"select count(*) from {relation}")
                counts.append(int(cursor.fetchone()[0]))
        return tuple(counts)

    before = census()
    seed_all(db)
    assert census() == before


def test_the_registration_resolves_at_the_clock_the_resolver_reads() -> None:
    """The clock cannot run ahead of the deploy host: the Colorado arm on
    canonical.status_resolution resolves through jurisdictions_as_of(current_date, current_date),
    so a registration dated tomorrow resolves nowhere and Colorado draws unmapped."""
    assert isinstance(CO_REGISTERED_ON, date)
    assert date.today() >= CO_REGISTERED_ON


def test_the_migration_is_what_lands_the_rows_on_a_database_that_is_already_seeded(
    db: psycopg.Connection,
) -> None:
    """The deployed path: every table here is append-only, so the file has to be safe to
    re-apply against a database that already carries its rows rather than only against a fresh
    one. Re-executing it is the only honest way to exercise the residency guards."""
    def census() -> tuple[int, ...]:
        with db.cursor() as cursor:
            counts = []
            for relation in (
                "lineage.scheduled_jobs",
                "lineage.job_sources",
                "lineage.job_schedules",
                "lineage.job_dependencies",
                "lineage.jurisdictions",
                "lineage.jurisdiction_rules",
            ):
                cursor.execute(
                    f"select count(*) from {relation} where true"
                )
                counts.append(int(cursor.fetchone()[0]))
        return tuple(counts)

    before = census()
    with db.cursor() as cursor:
        cursor.execute(migration_sql(MIGRATION))
    assert census() == before
    with db.cursor() as cursor:
        cursor.execute(
            "select count(*) from lineage.job_schedules where launch_mode = 'launch'"
        )
        assert cursor.fetchone()[0] == 6
