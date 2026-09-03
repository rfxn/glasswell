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
from glasswell.seed.jurisdictions import (
    CO_REGISTERED_ON,
    COLORADO,
    COLORADO_DECISIONS,
    JURISDICTION_RULES,
)
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


def test_one_evidence_pair_in_the_whole_file() -> None:
    """M-1: the release gate asserts at most one of each repo-wide, so the registration reads
    its evidence back from the publications insert rather than restating it.

    Counted by shape, not by the placeholder's value: the pair is `UNRELEASED` plus forty zeros
    before the repoint and the tag plus its merge commit after, and the invariant this guards --
    that the file states its evidence once and reads it back everywhere else -- is the same on
    both sides of that edit. Asserting the placeholder itself made the guard true only until the
    release it was written for shipped."""
    body = migration_sql(MIGRATION)

    tags = re.findall(r"'(?:UNRELEASED|v\d+\.\d+)'", body)
    commits = re.findall(r"'[0-9a-f]{40}'", body)

    assert len(tags) == 1, f"the file states its evidence tag {len(tags)} times: {tags}"
    assert len(commits) == 1, f"the file states its evidence commit {len(commits)} times"


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
    """M-19's set equality: a rule added to the seed and forgotten in the migration reddens.

    Against the seed's one writer, `JURISDICTION_RULES`, rather than against
    `COLORADO_DECISIONS` alone: the thirteen the registration was founded with are what
    migration 077 writes and what that tuple mirrors, and a later track registering a decision
    for Colorado at the same clock appends it beside them. Both halves are asserted, so a
    founding decision dropped from either copy still reddens here.
    """
    with db.cursor() as cursor:
        cursor.execute(
            "select decision from lineage.jurisdiction_rules where jurisdiction_code = 'CO'"
        )
        resident = {row[0] for row in cursor.fetchall()}

    founding = {str(row["decision"]) for row in COLORADO_DECISIONS}
    seeded = {
        str(row["decision"])
        for row in JURISDICTION_RULES
        if str(row["jurisdiction_code"]) == "CO"
    }
    assert founding <= seeded
    assert resident == seeded


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


def test_what_a_registry_driven_resolver_owes_colorado_is_exact(db: psycopg.Connection) -> None:
    """The contract this migration deliberately does not implement.

    Colorado's arm on `canonical.status_resolution` was written here and removed: the facets
    track replaces that view with a keyed table rebuilt by its own registry-driven refresh, and
    two writers of one view means one is silently discarded. Since that track merges last, the
    arm written here would be the discarded one and every Colorado well would resolve unmapped
    with nothing on any surface saying so.

    What is owed is not a matter of opinion, so it is stated as a query: one row per codebook
    entry, at the prefix the registration resolves to, carrying the class the codebook maps.
    """
    with db.cursor() as cursor:
        cursor.execute(
            "select j.identity_prefix, m.status, m.status_canonical"
            "  from lineage.co_facility_status_map m"
            "  join lineage.jurisdictions_as_of(current_date, current_date) j"
            "    on j.jurisdiction_code = 'CO'"
            " order by m.status"
        )
        owed = cursor.fetchall()

    assert len(owed) == 13
    assert {prefix for prefix, _status, _class in owed} == {"05"}
    assert dict((status, resolved) for _prefix, status, resolved in owed) == {
        code: str(row["status_canonical"]) for code, row in CO_STATUS_MAP.items()
    }


def test_the_resolver_serves_colorado_wherever_the_resolved_table_exists(
    db: psycopg.Connection,
) -> None:
    """The cross-track half, which runs on the train and skips before it.

    A resolver that reads one regulator's codebook by name serves one jurisdiction. This is the
    assertion that catches it: wherever `lineage.status_resolution_resolved` is present, every
    row the query above owes has to be in it. It is not a substitute for that track's own
    tests; it is the row Colorado needs and the only place anything asserts it.
    """
    with db.cursor() as cursor:
        cursor.execute("select to_regclass('lineage.status_resolution_resolved')")
        if cursor.fetchone()[0] is None:
            pytest.skip(
                "the registry-driven resolver has not merged yet; on the train this asserts"
                " that its refresh covers every registered codebook and not New Mexico's alone"
            )
        cursor.execute(
            "select r.for_status_reported, r.resolved_status"
            "  from canonical.status_resolution r"
            "  join lineage.jurisdictions_as_of(current_date, current_date) j"
            "    on j.identity_prefix = r.for_state_code"
            " where j.jurisdiction_code = 'CO'"
            " order by r.for_status_reported"
        )
        served = cursor.fetchall()

    assert len(served) == 13, (
        "the resolved status table carries no Colorado rows: a refresh that names one"
        " regulator's map resolves one jurisdiction, and every Colorado well reads unmapped"
    )
    assert dict(served) == {
        code: str(row["status_canonical"]) for code, row in CO_STATUS_MAP.items()
    }, "the resolver reached Colorado but resolved a different codebook than the one registered"


def test_the_status_rule_carries_the_keys_the_registry_driven_resolver_reads(
    db: psycopg.Connection,
) -> None:
    """The three spec keys a resolver driven by rows cannot work without.

    `mapping_table` alone names where the classes live and not how to read it. The refresh
    filters on `key_col` and `value_col` too, and `->>` on an absent key is null, so a spec
    short of one is not skipped with a notice -- it never enters the loop, and the whole
    jurisdiction resolves unmapped with nothing anywhere saying so. Asserted against the map's
    own columns rather than against two strings, so a renamed column reddens here.
    """
    with db.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "select spec from lineage.conformance_rules where rule_id = %s",
            ("cr_co_wells_status_vocab_1",),
        )
        spec = cursor.fetchone()["spec"]
        cursor.execute(
            "select column_name from information_schema.columns"
            "  where table_schema = 'lineage' and table_name = %s",
            (spec["mapping_table"],),
        )
        columns = {str(row["column_name"]) for row in cursor.fetchall()}

    assert spec["resolved_at"] == "read_time"
    assert {"mapping_table", "key_col", "value_col"} <= spec.keys(), (
        "a read-time rule short of key_col or value_col is filtered out of"
        " lineage.refresh_status_resolution()'s loop before the missing-table notice can fire"
    )
    assert {spec["key_col"], spec["value_col"]} <= columns


def cumulatives_scope_statement() -> str:
    """The migration's own ND `cumulatives_scope` insert, read out of the file it ships in."""
    statements = [
        statement
        for statement in re.sub(r"--[^\n]*", "", migration_sql(MIGRATION)).split(";")
        if "cumulatives_scope" in statement
        and "cr_nd_pool_rollup_1" in statement
        and "insert into lineage.jurisdiction_rules" in statement
    ]
    assert len(statements) == 1, "the migration no longer has one ND cumulatives_scope insert"
    return statements[0]


def test_north_dakotas_cumulatives_row_follows_a_repointed_restatement_clock(
    db: psycopg.Connection,
) -> None:
    """The deployed path, where this insert is the writer rather than the seed.

    Migrations run before the seed, so on a fresh database 075's restatement lands nothing and
    seed/jurisdictions.py supplies these rows; on the deployed database, already seeded, this
    statement is what lands them. Its clock is the seam track's RESTATED_ON, one of the five
    values the integrator repoints at the train, and it used to be written here as a literal
    twice -- once selected and once in a guard. Repoint the clock and the guard matches
    nothing: North Dakota gets no cumulatives_scope row, and the migration reports success.

    So the repoint is performed. A second ND registration is appended at a later instant, the
    migration's own statement is re-run against it, and the row has to arrive at the new clock.
    """
    repointed = date(2026, 9, 6)
    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.jurisdictions"
            " select (jsonb_populate_record(null::lineage.jurisdictions,"
            "         to_jsonb(j) || jsonb_build_object('published_at', %s::text))).*"
            "   from lineage.jurisdictions j where j.jurisdiction_code = 'ND'"
            "  order by j.published_at desc, j.effective_from desc limit 1",
            (repointed,),
        )
        cursor.execute(cumulatives_scope_statement())
        cursor.execute(
            "select published_at, rule_id, serving from lineage.jurisdiction_rules"
            " where jurisdiction_code = 'ND' and decision = 'cumulatives_scope'"
            " order by published_at"
        )
        rows = cursor.fetchall()

    assert (repointed, "cr_nd_pool_rollup_1", True) in rows, (
        "the migration's cumulatives_scope insert did not follow the registration's clock, so a"
        " repointed restatement leaves North Dakota out of the cumulative mart's population"
    )


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
