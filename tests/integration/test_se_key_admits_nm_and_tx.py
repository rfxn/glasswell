"""D1 (NM) and D2 (TX) unblocked structurally: the widened key admits both without a migration.

`reconciliation.md:902` gates the S-E key on **P7a**, not P7b: NM reports at
well-completion x pool, so landing it on migration 008's `api10` key would re-key an entire
second state's spine. This is a schema admission test, not an ingest — it proves the shape the
Wave-2 tracks will write into, so neither discovers a blocking migration mid-phase.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import psycopg
import pytest

from tests.support.seed import seed_derivation, seed_manifest, seed_production

MONTH = date(2026, 1, 1)
VINTAGE = date(2026, 8, 1)

# NM API numbers are state 30; TX leases key on (OIL_GAS_CODE, DISTRICT_NO, LEASE_NO) because
# LEASE_NO is unique within district only (SB-01 §4.1, DIR-9).
NM_WELL = "3002512345"
NM_POOL = "WC-025 G-09 S262310"
TX_LEASE_KEY = "O:08:012345"


@pytest.fixture
def lineage_refs(db: psycopg.Connection) -> tuple[str, str]:
    manifest = seed_manifest(db, sha256="1" * 64, source_id="nd_mpr_xlsx")
    return manifest, seed_derivation(db)


def rows(connection: psycopg.Connection, sql: str, *parameters: object) -> list[tuple]:
    with connection.cursor() as cursor:
        cursor.execute(sql, parameters or None)
        return cursor.fetchall()


def test_a_new_mexico_well_row_needs_no_further_migration(db, lineage_refs):
    manifest, derivation = lineage_refs
    seed_production(
        db,
        api10=NM_WELL,
        production_month=MONTH,
        report_vintage=VINTAGE,
        volume=Decimal("4210.000"),
        manifest_id=manifest,
        derivation_id=derivation,
        source_id="nm_ocd_wcproduction",
    )

    assert rows(
        db,
        "select entity_type, entity_key, reporting_level, source_id"
        "  from canonical.production_monthly where api10 = %s",
        NM_WELL,
    ) == [("well", NM_WELL, "well", "nm_ocd_wcproduction")]


def test_a_new_mexico_completion_pool_row_coexists_with_its_well_row(db, lineage_refs):
    """NM's native grain. The pool row and the well total are different objects (S-B)."""
    manifest, derivation = lineage_refs
    for entity_type, entity_key, level, pool, aggregation in (
        ("well_completion_pool", f"{NM_WELL}:{NM_POOL}", "well_completion_pool", NM_POOL, None),
        ("well", NM_WELL, "well_completion_pool", None, "sum_over_pools"),
    ):
        seed_production(
            db,
            api10=NM_WELL,
            production_month=MONTH,
            report_vintage=VINTAGE,
            volume=Decimal("4210.000"),
            manifest_id=manifest,
            derivation_id=derivation,
            source_id="nm_ocd_wcproduction",
            entity_type=entity_type,
            entity_key=entity_key,
            reporting_level=level,
            well_completion_pool=pool,
            aggregation=aggregation,
        )

    assert rows(
        db,
        "select entity_type, aggregation from canonical.production_monthly"
        " where source_id = 'nm_ocd_wcproduction' order by entity_type",
    ) == [("well", "sum_over_pools"), ("well_completion_pool", None)]


def test_a_texas_lease_row_keys_on_its_district_because_the_lease_number_does_not(db, lineage_refs):
    manifest, derivation = lineage_refs
    seed_production(
        db,
        api10=None,
        production_month=MONTH,
        report_vintage=VINTAGE,
        volume=Decimal("18000.000"),
        manifest_id=manifest,
        derivation_id=derivation,
        source_id="tx_pdq_dsv",
        entity_type="lease",
        entity_key=TX_LEASE_KEY,
        reporting_level="lease",
        granularity="lease_reported",
    )

    assert rows(
        db,
        "select entity_type, entity_key, api10, granularity"
        "  from canonical.production_monthly where source_id = 'tx_pdq_dsv'",
    ) == [("lease", TX_LEASE_KEY, None, "lease_reported")]


def test_two_sources_may_report_the_same_entity_month_on_independent_vintages(db, lineage_refs):
    """Why source_id is in the key at all (S-E): their vintages move independently."""
    manifest, derivation = lineage_refs
    for source_id in ("nd_mpr_xlsx", "nm_ocd_wcproduction"):
        seed_production(
            db,
            api10=NM_WELL,
            production_month=MONTH,
            report_vintage=VINTAGE,
            volume=Decimal("4210.000"),
            manifest_id=manifest,
            derivation_id=derivation,
            source_id=source_id,
        )

    assert rows(
        db,
        "select count(*) from canonical.production_monthly where entity_key = %s",
        NM_WELL,
    ) == [(2,)]


def test_condensate_is_promotable_for_the_states_that_report_it(db, lineage_refs):
    manifest, derivation = lineage_refs
    seed_production(
        db,
        api10=NM_WELL,
        production_month=MONTH,
        report_vintage=VINTAGE,
        volume=Decimal("311.000"),
        manifest_id=manifest,
        derivation_id=derivation,
        source_id="nm_ocd_wcproduction",
        stream="condensate",
    )

    assert rows(
        db,
        "select stream, unit from canonical.production_monthly where stream = 'condensate'",
    ) == [("condensate", "bbl")]
