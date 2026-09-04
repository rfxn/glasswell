"""What the migration has to have built before anything can load a lease.

Layer boundaries are the subject: staging holds source-faithful text, canonical holds the
filed lease volume at its native grain and refuses an allocated one, and the estimate lives in
a mart that cannot express a half-populated error band.
"""

from __future__ import annotations

from datetime import date

import psycopg
import pytest

from tests.support.seed import seed_derivation, seed_manifest, seed_well

TX_TABLES = [
    ("staging", "tx_pdq_lease_cycle"),
    ("staging", "tx_pdq_well_completion"),
    ("staging", "tx_pdq_regulatory_lease"),
    ("canonical", "lease_membership"),
    ("marts", "tx_allocated_production"),
    ("marts", "tx_allocation_ledger"),
    ("marts", "tx_crosswalk_residual"),
    ("marts", "allocation_method_error"),
    ("marts", "tx_allocation_census"),
]


def columns(db: psycopg.Connection, schema: str, table: str) -> set[str]:
    with db.cursor() as cursor:
        cursor.execute(
            "select column_name from information_schema.columns"
            " where table_schema = %s and table_name = %s",
            (schema, table),
        )
        return {row[0] for row in cursor.fetchall()}


@pytest.mark.parametrize(("schema", "table"), TX_TABLES)
def test_the_migration_builds_the_table(db, schema: str, table: str) -> None:
    with db.cursor() as cursor:
        cursor.execute("select to_regclass(%s)", (f"{schema}.{table}",))
        assert cursor.fetchone()[0] is not None


def test_canonical_wells_gains_the_plug_date_and_the_view_is_re_issued_carrying_it(db) -> None:
    """M-20. 027 added two columns to the table and left the view behind; 040 came back three
    releases later to fix it, and its header comment is the instruction this follows."""
    assert "plug_date" in columns(db, "canonical", "wells")
    assert "plug_date" in columns(db, "canonical", "wells_latest")


def test_the_view_still_carries_every_column_040_gave_it(db) -> None:
    """A create-or-replace that dropped a column would be caught by the readers; one that
    silently narrowed the projection would not, because every reader selects by name."""
    projected = columns(db, "canonical", "wells_latest")

    assert {
        "api10", "api14", "state_code", "county_code_at_permit", "ndic_file_no",
        "operator_name_reported", "operator_id", "well_name", "status_canonical",
        "status_reported", "well_type_reported", "spud_date", "confidential_flag", "basin",
        "land_unit_label", "effective_from", "source_manifest_id", "derivation_id",
        "created_at", "total_depth_ft", "completion_date", "plug_date",
    } <= projected


def test_a_plug_date_is_effective_dated_like_every_other_well_attribute(db) -> None:
    seed_well(db, api10="4200300001", effective_from=date(2026, 8, 1))
    seed_well(db, api10="4200300001", effective_from=date(2026, 9, 1), plug_date=date(2015, 4, 2))
    with db.cursor() as cursor:
        cursor.execute("select plug_date from canonical.wells_latest where api10 = '4200300001'")
        assert cursor.fetchone()[0] == date(2015, 4, 2)


def test_canonical_still_refuses_an_allocated_production_row(db) -> None:
    """020_production_entity_key.sql:43-46 is what keeps 4F.1 and 4F.2 apart independently of
    any code this track writes: the estimate cannot be written to canonical at all."""
    manifest = seed_manifest(db, sha256="e" * 64, source_id="tx_pdq_dsv", source_key="PDQ_DSV.zip")
    derivation = seed_derivation(db, operation="canonical.promote")
    with pytest.raises(psycopg.errors.CheckViolation), db.cursor() as cursor:
        cursor.execute(
            "insert into canonical.production_monthly (entity_type, entity_key, api10,"
            " production_month, stream, volume, unit, reporting_level, granularity, source_id,"
            " report_vintage, null_semantics, value_hash, source_manifest_id, derivation_id)"
            " values ('well', '4200300001', '4200300001', '2024-01-01', 'oil', 100, 'bbl',"
            " 'well', 'lease_allocated', 'tx_pdq_dsv', '2026-08-27', 'reported', 'h', %s, %s)",
            (manifest, derivation),
        )
    db.rollback()


def test_a_lease_row_promotes_at_its_native_grain(db) -> None:
    manifest = seed_manifest(db, sha256="e" * 64, source_id="tx_pdq_dsv", source_key="PDQ_DSV.zip")
    derivation = seed_derivation(db, operation="canonical.promote")
    with db.cursor() as cursor:
        cursor.execute(
            "insert into canonical.production_monthly (entity_type, entity_key, api10,"
            " production_month, stream, volume, unit, reporting_level, granularity, source_id,"
            " report_vintage, null_semantics, value_hash, source_manifest_id, derivation_id)"
            " values ('lease', 'O-08-000101', null, '2024-01-01', 'oil', 901, 'bbl',"
            " 'lease', 'lease_reported', 'tx_pdq_dsv', '2026-08-27', 'reported', 'h', %s, %s)",
            (manifest, derivation),
        )
        cursor.execute(
            "select count(*) from canonical.production_monthly where entity_type = 'lease'"
        )
        assert cursor.fetchone()[0] == 1


def test_a_membership_row_cannot_be_edited_in_place(db) -> None:
    """Restatements are appended: a later vintage that drops a well removes it from no month
    already resolved at an earlier one."""
    manifest = seed_manifest(db, sha256="e" * 64, source_id="tx_pdq_dsv", source_key="PDQ_DSV.zip")
    derivation = seed_derivation(db, operation="canonical.promote")
    with db.cursor() as cursor:
        cursor.execute(
            "insert into canonical.lease_membership (jurisdiction_code, lease_key, api10,"
            " link_role, source_id, effective_from, source_manifest_id, derivation_id)"
            " values ('TX', 'O-08-000101', '4200300001', 'canonical_crosswalk', 'tx_pdq_dsv',"
            " '2026-08-27', %s, %s)",
            (manifest, derivation),
        )
    with pytest.raises(psycopg.errors.RestrictViolation, match="append_only_violation"), \
            db.cursor() as cursor:
        cursor.execute("delete from canonical.lease_membership")
    db.rollback()


def test_one_wellbore_on_two_leases_is_two_membership_rows(db) -> None:
    """M-16. 21.9 percent of Texas API-10s carry more than one lease record, and they are the
    thing being allocated rather than a duplicate to collapse."""
    manifest = seed_manifest(db, sha256="e" * 64, source_id="tx_pdq_dsv", source_key="PDQ_DSV.zip")
    derivation = seed_derivation(db, operation="canonical.promote")
    with db.cursor() as cursor:
        cursor.executemany(
            "insert into canonical.lease_membership (jurisdiction_code, lease_key, api10,"
            " link_role, source_id, effective_from, source_manifest_id, derivation_id)"
            " values ('TX', %s, '4200300001', 'canonical_crosswalk', 'tx_pdq_dsv',"
            " '2026-08-27', %s, %s)",
            [("O-08-000101", manifest, derivation), ("G-08-000303", manifest, derivation)],
        )
        cursor.execute(
            "select count(*) from canonical.lease_membership where api10 = '4200300001'"
        )
        assert cursor.fetchone()[0] == 2


def _allocated_row(**overrides: object) -> dict[str, object]:
    row = {
        "api10": "4200300001",
        "lease_key": "O-08-000101",
        "production_month": date(2024, 1, 1),
        "stream": "liquid",
        "volume": 301,
        "unit": "bbl",
        "basis": "oil+condensate",
        "allocation_class": "allocated_equal_share",
        "granularity": "lease_allocated",
        "allocation_model_id": "alloc_v0_2026_09",
        "allocation_rule_id": "cr_tx_allocation_v0_1",
        "eligible_wells": 3,
        "membership_vintage": date(2026, 8, 27),
        "error_bounds_outcome": "not_measured",
        "error_rule_id": "cr_alloc_v0_error_bounds_1",
        "error_bed": None,
        "error_lo": None,
        "error_hi": None,
    }
    row.update(overrides)
    return row


def _insert_allocated(db, derivation: str, row: dict[str, object]) -> None:
    with db.cursor() as cursor:
        cursor.execute(
            "insert into marts.tx_allocated_production (api10, lease_key, production_month,"
            " stream, volume, unit, basis, allocation_class, granularity, allocation_model_id,"
            " allocation_rule_id, eligible_wells, membership_vintage, error_bounds_outcome,"
            " error_rule_id, error_bed, error_lo, error_hi, lease_derivation_id,"
            " snapshot_vintage, derivation_id)"
            " values (%(api10)s, %(lease_key)s, %(production_month)s, %(stream)s, %(volume)s,"
            " %(unit)s, %(basis)s, %(allocation_class)s, %(granularity)s,"
            " %(allocation_model_id)s, %(allocation_rule_id)s, %(eligible_wells)s,"
            " %(membership_vintage)s, %(error_bounds_outcome)s, %(error_rule_id)s,"
            " %(error_bed)s, %(error_lo)s, %(error_hi)s, %(derivation)s, '2026-08-27',"
            " %(derivation)s)",
            {**row, "derivation": derivation},
        )


@pytest.fixture
def allocation_rules(db) -> str:
    from glasswell.seed.conformance_tx import seed_conformance_allocation, seed_conformance_tx

    seed_conformance_tx(db)
    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.sources (source_id, name, jurisdiction)"
            " values ('mt_bogc_pru_production', 'MT PRU', 'MT') on conflict do nothing"
        )
    seed_conformance_allocation(db)
    return seed_derivation(db, operation="alloc.apply")


def test_an_allocated_row_carries_its_class_its_model_and_its_bounds_outcome(
    db, allocation_rules: str
) -> None:
    _insert_allocated(db, allocation_rules, _allocated_row())
    with db.cursor() as cursor:
        cursor.execute(
            "select allocation_model_id, error_bounds_outcome"
            "  from marts.tx_allocated_production"
        )
        assert cursor.fetchone() == ("alloc_v0_2026_09", "not_measured")


def test_an_observed_class_cannot_claim_an_allocated_granularity(
    db, allocation_rules: str
) -> None:
    """granularity cannot distinguish the two observed classes, because both are
    well_observed; the CHECK is what stops the pair drifting apart."""
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_allocated(
            db, allocation_rules, _allocated_row(allocation_class="observed_gas_well")
        )
    db.rollback()


def test_a_half_populated_error_band_is_impossible_in_either_direction(
    db, allocation_rules: str
) -> None:
    """M-17. Serving lo without hi, or a measured outcome with no bed, is the shape a
    fabricated band would take."""
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_allocated(db, allocation_rules, _allocated_row(error_lo=-0.2, error_hi=0.2))
    db.rollback()
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_allocated(
            db, allocation_rules, _allocated_row(error_bounds_outcome="measured")
        )
    db.rollback()


def test_a_well_excluded_after_its_plug_date_carries_no_volume(
    db, allocation_rules: str
) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_allocated(
            db,
            allocation_rules,
            _allocated_row(allocation_class="excluded_after_plug", volume=12),
        )
    db.rollback()


def test_the_mart_is_keyed_by_lease_as_well_as_by_well(db, allocation_rules: str) -> None:
    """Folding a well's shares into one row would make lease_key, eligible_wells,
    allocation_class and membership_vintage ambiguous, and the stream fold would hide it."""
    _insert_allocated(db, allocation_rules, _allocated_row())
    _insert_allocated(
        db,
        allocation_rules,
        _allocated_row(lease_key="G-08-000303", allocation_class="observed_gas_well",
                       granularity="well_observed", eligible_wells=1),
    )
    with db.cursor() as cursor:
        cursor.execute(
            "select count(*) from marts.tx_allocated_production where api10 = '4200300001'"
        )
        assert cursor.fetchone()[0] == 2


def test_the_cumulative_coverage_class_admits_a_third_value(db) -> None:
    """R-1. A total that sums allocated months without saying so is the naked number this
    rule exists to prevent."""
    with db.cursor() as cursor:
        cursor.execute(
            "select pg_get_constraintdef(oid) from pg_constraint"
            " where conname = 'well_cumulatives_coverage_outcome_check'"
        )
        definition = cursor.fetchone()[0]

    assert "observed_with_allocated" in definition
    assert {"allocated_months", "allocated_share"} <= columns(db, "marts", "well_cumulatives")


def test_the_census_is_a_series_and_not_a_latest(db) -> None:
    """N-27. R-5 needs to see the in-scope population move, which is what tells the owner
    whether the county scope has to narrow."""
    with db.cursor() as cursor:
        cursor.execute(
            "select a.attname from pg_index i"
            "  join pg_attribute a on a.attrelid = i.indrelid and a.attnum = any(i.indkey)"
            " where i.indrelid = 'marts.tx_allocation_census'::regclass and i.indisprimary"
            " order by a.attname"
        )
        assert [row[0] for row in cursor.fetchall()] == ["measure", "measured_on"]


def test_the_selector_registry_admits_the_allocation_and_both_response_datasets(db) -> None:
    """M-9/M-21. Handles are fail-closed, so an unregistered claim shape raises rather than
    resolving; the summed per-well point is stored nowhere and is addressed at api.respond."""
    with db.cursor() as cursor:
        cursor.execute(
            "select operation, output_dataset, selector_profile"
            "  from lineage.selector_output_registry"
            " where output_dataset like '%tx_%' or output_dataset like '%allocation%'"
            " order by output_dataset"
        )
        rows = cursor.fetchall()

    assert ("alloc.apply", "marts.tx_allocated_production", "tx_allocated_series") in rows
    assert ("api.respond", "api.tx_production", "response_output") in rows
    assert ("api.respond", "api.allocation_validators", "response_output") in rows


def test_the_pdq_source_gained_the_cadence_its_health_check_needs(db) -> None:
    """N-14. A null expected_poll_interval makes a missed window undetectable, and R-03
    requires /v1/health to go degraded on one."""
    with db.cursor() as cursor:
        cursor.execute(
            "select cadence, expected_poll_interval, attempt_timeout"
            "  from lineage.source_poll_policies where source_id = 'tx_pdq_dsv'"
        )
        cadence, interval, timeout = cursor.fetchone()

    assert cadence == "Last Saturday each month"
    assert interval.days == 35
    assert timeout.seconds == 12 * 60 * 60
