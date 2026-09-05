"""The per-well rollup mart: what it sums, what it refuses to sum, and who it builds for.

New Mexico is the only registration whose production_grain rule registers a served rollup, and
the mart has to hold that and nothing else: Montana registers a grain decision and no rollup,
North Dakota rolls up in its own promotion, and a mart that quietly covered either would serve
a sum neither jurisdiction decided.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from glasswell.lineage.capture import lineage_session
from glasswell.lineage.jurisdictions import clear_jurisdiction_cache
from glasswell.lineage.store import PostgresRecorder
from glasswell.marts import well_pool_rollup
from glasswell.marts.well_pool_rollup import (
    RollupRegistrationError,
    refresh_well_pool_rollup,
    rollup_registrations,
)
from glasswell.seed import seed_all
from tests.support.jurisdictions import restate
from tests.support.layers import schema_reads_in
from tests.support.seed import seed_derivation, seed_manifest, seed_production, seed_well

pytestmark = pytest.mark.integration

NM_API10 = "3001599101"
NM_POOLS = ("96269", "77213")
MONTH = date(2026, 5, 1)
LATER_MONTH = date(2026, 6, 1)
VINTAGE = date(2026, 8, 20)
LATER_VINTAGE = date(2026, 8, 27)
MT_API10 = "2500399101"


def rows(db: psycopg.Connection, sql: str, parameters: dict | None = None) -> list[dict]:
    with db.cursor(row_factory=dict_row) as cursor:
        cursor.execute(sql, parameters or {})
        return [dict(row) for row in cursor.fetchall()]


def scalar(db: psycopg.Connection, sql: str, parameters: dict | None = None):
    with db.cursor() as cursor:
        cursor.execute(sql, parameters or {})
        row = cursor.fetchone()
    return row[0] if row else None


def pool_filing(
    db: psycopg.Connection,
    *,
    api10: str,
    pool: str,
    month: date,
    stream: str,
    volume: str,
    manifest_id: str,
    derivation_id: str,
    days_produced: int | None = 30,
    null_semantics: str = "reported",
    report_vintage: date = VINTAGE,
    unit: str | None = None,
) -> None:
    seed_production(
        db,
        api10=api10,
        entity_type="well_completion_pool",
        entity_key=f"{api10}:{pool}",
        reporting_level="well_completion_pool",
        well_completion_pool=pool,
        production_month=month,
        report_vintage=report_vintage,
        stream=stream,
        unit=unit,
        volume=Decimal(volume),
        days_produced=days_produced,
        null_semantics=null_semantics,
        source_id="nm_ocd_wcproduction",
        manifest_id=manifest_id,
        derivation_id=derivation_id,
    )


@pytest.fixture
def filed(db: psycopg.Connection, lineage_env):
    """A New Mexico well filing in two pools, and a Montana well filing in one.

    Two pools in one month is the case the mart exists for; the second month is one pool, which
    is 87.4 per cent of the deployed rows and is where a sum that is the identity function has
    to still say it is a sum.
    """
    seed_all(db)
    clear_jurisdiction_cache()
    manifest = seed_manifest(db, sha256="c" * 64, source_id="nm_ocd_wcproduction")
    derivation = seed_derivation(db, partition={"source": "nm_ocd_wcproduction"})
    seed_well(db, api10=NM_API10, state_code="30", status_reported="A")
    seed_well(db, api10=MT_API10, state_code="25", status_reported="ACTIVE")
    filings = (
        (NM_POOLS[0], "100.500", "2000.000", 28),
        (NM_POOLS[1], "40.250", "500.000", 31),
    )
    for pool, oil, gas, days in filings:
        pool_filing(db, api10=NM_API10, pool=pool, month=MONTH, stream="oil", volume=oil,
                    days_produced=days, manifest_id=manifest, derivation_id=derivation)
        pool_filing(db, api10=NM_API10, pool=pool, month=MONTH, stream="gas", volume=gas,
                    days_produced=days, manifest_id=manifest, derivation_id=derivation)
    pool_filing(db, api10=NM_API10, pool=NM_POOLS[0], month=LATER_MONTH, stream="oil",
                volume="7.000", manifest_id=manifest, derivation_id=derivation)
    # Montana files at pool grain in this fixture too, and registers no served rollup: the mart
    # has to leave it alone on the registration rather than on the state code.
    seed_production(
        db,
        api10=MT_API10,
        entity_type="well_completion_pool",
        entity_key=f"{MT_API10}:BAKKEN",
        reporting_level="well_completion_pool",
        well_completion_pool="BAKKEN",
        production_month=MONTH,
        report_vintage=VINTAGE,
        stream="oil",
        volume=Decimal("11.000"),
        source_id="mt_bogc_well_production",
        manifest_id=manifest,
        derivation_id=derivation,
    )
    db.commit()
    return db


@pytest.fixture
def refreshed(filed: psycopg.Connection, lineage_env):
    with lineage_session(recorder=PostgresRecorder(filed), environment=lineage_env):
        reports = refresh_well_pool_rollup(filed)
    filed.commit()
    return reports


def test_the_mart_builds_for_the_registration_that_registers_a_rollup_and_no_other(
    filed: psycopg.Connection,
) -> None:
    """Registry-driven, so a sixth pool-grain state is a spec key rather than a module."""
    registrations = rollup_registrations(filed)

    assert [(item.jurisdiction_code, item.rule_id) for item in registrations] == [
        ("NM", "cr_nm_wcproduction_pool_rollup_2")
    ]


def test_a_well_that_filed_in_two_pools_is_served_their_exact_sum(
    refreshed, filed: psycopg.Connection
) -> None:
    """Volume sums exactly; days do not sum, because the filings are concurrent."""
    summed = rows(
        filed,
        "select stream, volume, unit, days_produced, pools_summed, aggregation"
        "  from marts.well_pool_rollup where api10 = %(api10)s and production_month = %(month)s"
        " order by stream",
        {"api10": NM_API10, "month": MONTH},
    )

    assert [(row["stream"], str(row["volume"])) for row in summed] == [
        ("gas", "2500.000"),
        ("liquid", "140.750"),
    ]
    assert {row["days_produced"] for row in summed} == {31}
    assert {row["pools_summed"] for row in summed} == {2}
    assert {row["aggregation"] for row in summed} == {"sum_over_pools"}
    assert {row["unit"] for row in summed} == {"mcf", "bbl"}


def test_a_month_with_one_pool_is_still_a_sum_and_says_it_summed_one(
    refreshed, filed: psycopg.Connection
) -> None:
    """87.4 per cent of the deployed rows restate a single filing, and the disclosure is what
    keeps them honest: the figure is glasswell's sum either way."""
    row = rows(
        filed,
        "select volume, pools_summed, aggregation from marts.well_pool_rollup"
        " where api10 = %(api10)s and production_month = %(month)s",
        {"api10": NM_API10, "month": LATER_MONTH},
    )

    assert [(str(item["volume"]), item["pools_summed"], item["aggregation"]) for item in row] == [
        ("7.000", 1, "sum_over_pools")
    ]


def test_montana_files_at_pool_grain_and_registers_no_rollup_so_it_gets_no_rows(
    refreshed, filed: psycopg.Connection
) -> None:
    """The negative half, drawn from a jurisdiction that registers the grain and not the sum."""
    other = "select count(*) from marts.well_pool_rollup where state_code <> '30'"
    assert scalar(filed, other) == 0
    assert [report.jurisdiction_code for report in refreshed] == ["NM"]


def test_a_restated_month_is_summed_at_its_latest_vintage_and_not_beside_it(
    filed: psycopg.Connection, lineage_env
) -> None:
    """The serving path reads the greatest report_vintage per key; a sum that read both would
    add a filing to its own correction."""
    manifest = seed_manifest(filed, sha256="d" * 64, source_id="nm_ocd_wcproduction")
    derivation = seed_derivation(filed, partition={"source": "nm_restatement"})
    pool_filing(
        filed,
        api10=NM_API10,
        pool=NM_POOLS[0],
        month=LATER_MONTH,
        stream="oil",
        volume="9.000",
        report_vintage=LATER_VINTAGE,
        manifest_id=manifest,
        derivation_id=derivation,
    )
    with lineage_session(recorder=PostgresRecorder(filed), environment=lineage_env):
        refresh_well_pool_rollup(filed)

    assert scalar(
        filed,
        "select volume from marts.well_pool_rollup where api10 = %(api10)s"
        "   and production_month = %(month)s and stream = 'liquid'",
        {"api10": NM_API10, "month": LATER_MONTH},
    ) == Decimal("9.000")


def test_a_withheld_filing_is_not_a_number_to_add_and_leaves_no_row_behind(
    filed: psycopg.Connection, lineage_env
) -> None:
    """A regulator's silence summed as the zero it is stored with would be a measured zero."""
    manifest = seed_manifest(filed, sha256="e" * 64, source_id="nm_ocd_wcproduction")
    derivation = seed_derivation(filed, partition={"source": "nm_withheld"})
    pool_filing(
        filed,
        api10=NM_API10,
        pool=NM_POOLS[0],
        month=date(2026, 7, 1),
        stream="water",
        volume="0.000",
        null_semantics="withheld",
        manifest_id=manifest,
        derivation_id=derivation,
    )
    with lineage_session(recorder=PostgresRecorder(filed), environment=lineage_env):
        reports = refresh_well_pool_rollup(filed)

    assert scalar(
        filed,
        "select count(*) from marts.well_pool_rollup where production_month = %(month)s",
        {"month": date(2026, 7, 1)},
    ) == 0
    assert reports[0].excluded_filings == 1


def test_the_refresh_cites_every_promotion_the_sum_read(
    refreshed, filed: psycopg.Connection
) -> None:
    """N-11: one handle for the whole series is coarser than one per month, so the edge set is
    what a reader follows instead."""
    report = refreshed[0]
    inputs = rows(
        filed,
        "select ref_id from lineage.derivation_inputs"
        " where derivation_id = %(id)s and kind = 'derivation'",
        {"id": report.derivation_id},
    )
    expected = rows(
        filed,
        "select distinct derivation_id from canonical.production_monthly"
        " where entity_type = 'well_completion_pool' and left(api10, 2) = '30'",
    )

    assert {row["ref_id"] for row in inputs} == {
        row["derivation_id"] for row in expected
    }
    assert scalar(
        filed,
        "select count(*) from lineage.derivation_rules where derivation_id = %(id)s"
        "   and rule_id = 'cr_nm_wcproduction_pool_rollup_2'",
        {"id": report.derivation_id},
    ) == 1


def test_every_row_carries_the_refresh_that_wrote_it(
    refreshed, filed: psycopg.Connection
) -> None:
    """No naked numbers: a served point resolves through the row's own derivation."""
    assert scalar(
        filed, "select count(*) from marts.well_pool_rollup where derivation_id is null"
    ) == 0
    assert scalar(
        filed,
        "select count(distinct derivation_id) from marts.well_pool_rollup where state_code = '30'",
    ) == 1


def test_a_second_refresh_rebuilds_rather_than_appending(
    refreshed, filed: psycopg.Connection, lineage_env
) -> None:
    """Marts are rebuilt, never appended: a second run over unchanged inputs is the same rows."""
    every = "select * from marts.well_pool_rollup order by api10, production_month, stream"
    before = rows(filed, every)
    with lineage_session(recorder=PostgresRecorder(filed), environment=lineage_env):
        refresh_well_pool_rollup(filed)
    after = rows(filed, every)

    assert before == after


def test_the_mart_reads_canonical_only(filed: psycopg.Connection) -> None:
    """Blueprint layer boundary, asserted over the module's own folded strings."""
    assert schema_reads_in(Path(well_pool_rollup.__file__), "staging") == []


PLANTED_RULE = "cr_nm_wcproduction_pool_rollup_9"


def test_a_rollup_registered_without_saying_what_canonical_holds_is_refused(
    filed: psycopg.Connection,
) -> None:
    """The spec key pair is the decision: a served rollup with no statement about canonical
    would leave a reader unable to tell a mart sum from a promoted filing.

    Planted as an append and a restatement, because that is the only way a registry that
    refuses UPDATE can arrive at it: a successor rule and a registration that cites it.
    """
    with filed.cursor() as cursor:
        cursor.execute(
            "insert into lineage.conformance_rule_publications"
            " (rule_id, published_vintage, evidence_tag, evidence_commit)"
            " values (%s, current_date, 'UNRELEASED', %s)",
            (PLANTED_RULE, "0" * 40),
        )
        cursor.execute(
            "insert into lineage.conformance_rules (rule_id, rule_family, supersedes_rule_id,"
            " source_id, stage, applies_to_fields, rule_kind, spec, rule, rationale,"
            " effective_from)"
            " values (%s, 'cr_nm_wcproduction_pool_rollup', 'cr_nm_wcproduction_pool_rollup_2',"
            " 'nm_ocd_wcproduction', 'conform', array['volume'], 'code_ref', %s,"
            " 'planted', 'planted', current_date)",
            (PLANTED_RULE, Jsonb({"state_code": "30", "served_rollup": "sum_over_pools"})),
        )
    restate(filed, "NM", rules={"production_grain": PLANTED_RULE})
    clear_jurisdiction_cache()

    with pytest.raises(RollupRegistrationError, match="rolls_up_to_the_well"):
        rollup_registrations(filed)
