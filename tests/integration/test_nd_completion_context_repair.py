from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from glasswell.lineage.as_of import read_feature_snapshot
from tests.support.seed import seed_derivation, seed_manifest, seed_production, seed_well

MIGRATION = (
    Path(__file__).parents[2]
    / "src/glasswell/db/migrations/042_nd_completion_context_repair.sql"
)
API10 = "3305301234"
PRODUCTION_MONTH = date(2018, 6, 1)
REPORT_VINTAGE = date(2026, 8, 20)


def test_historical_completion_repair_requires_the_same_source_manifest(db):
    manifest = seed_manifest(db, sha256="4" * 64, source_key="2018_06.xlsx")
    unrelated_manifest = seed_manifest(db, sha256="5" * 64, source_key="2018_07.xlsx")
    derivation = seed_derivation(db, partition={"source_id": "nd_mpr_xlsx"})
    seed_well(
        db,
        api10=API10,
        manifest_id=manifest,
        derivation_id=derivation,
        completion_date=date(2018, 5, 20),
    )
    seed_production(
        db,
        api10=API10,
        production_month=PRODUCTION_MONTH,
        report_vintage=REPORT_VINTAGE,
        volume=Decimal("100"),
        manifest_id=manifest,
        derivation_id=derivation,
        well_completion_pool=None,
    )
    with db.cursor() as cursor:
        cursor.executemany(
            "insert into staging.nd_mpr_oil"
            " (manifest_id, source_row_ordinal, api_wellno, report_date, pool)"
            " values (%s, %s, %s, %s, %s)",
            [
                (manifest, 1, f"{API10}0000", "2018-06-01", " BAKKEN "),
                (unrelated_manifest, 1, f"{API10}0000", "2018-07-01", "CONFIDENTIAL"),
                (manifest, 2, "33053099990000", "2018-06-01", "THREE FORKS"),
            ],
        )
        cursor.execute(MIGRATION.read_text())
        cursor.execute(MIGRATION.read_text())
        cursor.execute(
            "select completion_key, api10, well_completion_pool, pool_reported, production_month,"
            " report_vintage, source_manifest_id, derivation_id"
            " from canonical.well_completions where api10 = %s",
            (API10,),
        )
        assert cursor.fetchall() == [
            (
                f"{API10}:BAKKEN",
                API10,
                "BAKKEN",
                "BAKKEN",
                PRODUCTION_MONTH,
                REPORT_VINTAGE,
                manifest,
                derivation,
            )
        ]


def test_repaired_completion_is_visible_to_the_unchanged_fv2_formation_read(db):
    manifest = seed_manifest(db, sha256="6" * 64, source_key="2018_06.xlsx")
    derivation = seed_derivation(db, partition={"source_id": "nd_mpr_xlsx"})
    seed_well(
        db,
        api10=API10,
        manifest_id=manifest,
        derivation_id=derivation,
        completion_date=date(2018, 5, 20),
    )
    seed_production(
        db,
        api10=API10,
        production_month=PRODUCTION_MONTH,
        report_vintage=REPORT_VINTAGE,
        volume=Decimal("100"),
        manifest_id=manifest,
        derivation_id=derivation,
        well_completion_pool=None,
    )
    with db.cursor() as cursor:
        cursor.execute(
            "insert into staging.nd_mpr_oil"
            " (manifest_id, source_row_ordinal, api_wellno, report_date, pool)"
            " values (%s, 1, %s, '2018-06-01', 'BAKKEN')",
            (manifest, f"{API10}0000"),
        )
        cursor.execute(
            "insert into lineage.formation_aliases"
            " (formation_raw, formation, formation_group, confidence, effective_from, source_id,"
            " created_vintage) values ('BAKKEN', 'bakken', 'middle_bakken', 1.0, %s,"
            " 'nd_mpr_xlsx', %s)",
            (date(2015, 5, 1), date(2026, 8, 1)),
        )
        cursor.execute(MIGRATION.read_text())

    snapshot = read_feature_snapshot(
        db,
        as_of=date(2026, 8, 26),
        state_code="33",
        basin="williston",
        min_confidence=Decimal("0.800"),
        formation_source_id="nd_mpr_xlsx",
        formation_observation_policy="initial_observed",
        source_publication_lag_days=45,
    )

    assert snapshot.rows[0]["formation_pools"] == ["BAKKEN"]
    assert snapshot.rows[0]["formations"] == ["middle_bakken"]
