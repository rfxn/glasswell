from __future__ import annotations

from datetime import date
from decimal import Decimal

import psycopg
import pytest
from psycopg.rows import dict_row

from glasswell.api.provenance import register_response_figures
from glasswell.lineage.capture import derive, lineage_session
from glasswell.lineage.envelope import Figure, figure
from glasswell.lineage.errors import DeterminismViolation, InvalidSelector, LineageUnresolved
from glasswell.lineage.models import InputRef, OutputSpec
from glasswell.lineage.selector_registry import identity_selector_term, validate_selector
from glasswell.lineage.store import PostgresRecorder
from tests.support.fakes import FixedClock
from tests.support.seed import FIXTURE_ENV, seed_manifest, seed_well

API10 = "3305301234"
MONTH = date(2026, 1, 1)


def _derivation(
    connection: psycopg.Connection, *, dataset: str, manifest_id: str, output_rows: int = 1
) -> str:
    with (
        lineage_session(
            recorder=PostgresRecorder(connection),
            environment=FIXTURE_ENV,
            clock=FixedClock(),
            correlation_id=f"run_selector_{dataset}",
        ),
        derive(
            "canonical.promote",
            output=OutputSpec(store="postgres", dataset=dataset),
            params={"fixture": "selector_output_registry"},
            inputs=[
                InputRef(
                    kind="manifest",
                    ref_id=manifest_id,
                    as_of_vintage=date(2026, 8, 1),
                )
            ],
        ) as context,
    ):
        context.set_output_hash("ab" * 32)
        context.set_rows(output_rows)
    return context.derivation_id


def _row(connection: psycopg.Connection, derivation_id: str) -> dict:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "select derivation_id, operation, output_dataset, output_partition,"
            " output_sha256, params, determinism_class, ttl_class"
            " from lineage.derivations where derivation_id = %s",
            (derivation_id,),
        )
        return dict(cursor.fetchone())


def test_ordinary_production_selector_checks_entity_stream_month_and_derivation(
    db: psycopg.Connection,
) -> None:
    manifest_id = seed_manifest(db, sha256="1" * 64)
    derivation_id = _derivation(db, dataset="canonical.production_monthly", manifest_id=manifest_id)
    with db.cursor() as cursor:
        cursor.execute(
            "insert into canonical.production_monthly"
            " (api10, production_month, stream, source_id, report_vintage, volume, unit,"
            " days_produced, granularity, value_hash, source_manifest_id, derivation_id)"
            " values (%s, %s, 'oil', 'nd_mpr_xlsx', '2026-08-01', %s, 'bbl', 31,"
            " 'well_observed', %s, %s, %s)",
            (API10, MONTH, Decimal("12.5"), "f" * 64, manifest_id, derivation_id),
        )
    row = _row(db, derivation_id)

    validate_selector(
        db,
        row,
        f"api10={API10}&col=oil_bbl&pm=2026-01",
        handle=f"{derivation_id}#api10={API10}&col=oil_bbl&pm=2026-01",
    )
    with pytest.raises(LineageUnresolved):
        validate_selector(
            db,
            row,
            "api10=3305309999&col=oil_bbl&pm=2026-01",
            handle=f"{derivation_id}#api10=3305309999&col=oil_bbl&pm=2026-01",
        )
    with pytest.raises(LineageUnresolved):
        validate_selector(
            db,
            row,
            f"api10={API10}&col=gas_mcf&pm=2026-01",
            handle=f"{derivation_id}#api10={API10}&col=gas_mcf&pm=2026-01",
        )
    with pytest.raises(InvalidSelector):
        validate_selector(
            db,
            row,
            f"api10={API10}&col=volume&pm=2026-01",
            handle=f"{derivation_id}#api10={API10}&col=volume&pm=2026-01",
        )


def test_total_depth_selector_checks_the_persisted_well_value(
    db: psycopg.Connection,
) -> None:
    manifest_id = seed_manifest(db, sha256="2" * 64)
    derivation_id = _derivation(
        db, dataset="canonical.wells", manifest_id=manifest_id, output_rows=2
    )
    seed_well(
        db,
        api10=API10,
        manifest_id=manifest_id,
        derivation_id=derivation_id,
        total_depth_ft=Decimal("11234.5"),
    )
    seed_well(
        db,
        api10=API10,
        effective_from=date(2026, 7, 1),
        manifest_id=manifest_id,
        derivation_id=derivation_id,
        total_depth_ft=Decimal("11200.0"),
    )
    row = _row(db, derivation_id)

    validate_selector(
        db,
        row,
        f"api10={API10}&effective_from=2026-08-01&col=total_depth_ft",
        handle=(f"{derivation_id}#api10={API10}&effective_from=2026-08-01&col=total_depth_ft"),
    )
    with pytest.raises(InvalidSelector):
        validate_selector(
            db,
            row,
            f"api10={API10}&effective_from=2026-08-01&col=completion_date",
            handle=(f"{derivation_id}#api10={API10}&effective_from=2026-08-01&col=completion_date"),
        )
    with pytest.raises(InvalidSelector, match="effective_from"):
        validate_selector(
            db,
            row,
            f"api10={API10}&col=total_depth_ft",
            handle=f"{derivation_id}#api10={API10}&col=total_depth_ft",
        )


def test_pool_production_selector_checks_the_pool_entity_grain(
    db: psycopg.Connection,
) -> None:
    manifest_id = seed_manifest(db, sha256="4" * 64)
    derivation_id = _derivation(db, dataset="canonical.production_monthly", manifest_id=manifest_id)
    entity_key = f"{API10}:RED RIVER/ALT"
    with db.cursor() as cursor:
        cursor.execute(
            "insert into canonical.production_monthly"
            " (entity_type, entity_key, reporting_level, well_completion_pool, api10,"
            " production_month, stream, source_id, report_vintage, volume, unit,"
            " days_produced, granularity, value_hash, source_manifest_id, derivation_id)"
            " values ('well_completion_pool', %s, 'well_completion_pool', 'RED RIVER/ALT',"
            " %s, %s, 'gas', 'nd_mpr_xlsx', '2026-08-01', 15, 'mcf', 31,"
            " 'well_observed', %s, %s, %s)",
            (entity_key, API10, MONTH, "e" * 64, manifest_id, derivation_id),
        )
    row = _row(db, derivation_id)
    selector = f"{identity_selector_term('entity_key', entity_key)}&col=gas_mcf&pm=2026-01"

    validate_selector(db, row, selector, handle=f"{derivation_id}#{selector}")
    with pytest.raises(LineageUnresolved):
        validate_selector(
            db,
            row,
            f"api10={API10}&col=gas_mcf&pm=2026-01",
            handle=f"{derivation_id}#api10={API10}&col=gas_mcf&pm=2026-01",
        )


def test_response_aggregate_registration_is_exact_and_idempotent(
    db: psycopg.Connection,
) -> None:
    manifest_id = seed_manifest(db, sha256="3" * 64)
    input_id = _derivation(db, dataset="canonical.well_spatial", manifest_id=manifest_id)
    value = figure(
        "5280.00",
        unit="ft",
        derivation=input_id,
        selector=f"api10={API10}&col=lateral_length_ft",
    )
    arguments = {
        "dataset": "api.well_detail",
        "operation_id": "get_well",
        "locator": f"/v1/wells/{API10}",
        "partition": {"api10": API10},
        "input_derivations": [input_id],
        "correlation_id": "run_selector_response",
        "rule_ids": ["cr_nd_compute_crs_1"],
    }

    with db.cursor() as cursor:
        cursor.execute("set role glasswell_api")
    try:
        first = register_response_figures(db, value, **arguments)
        second = register_response_figures(db, value, **arguments)
    finally:
        with db.cursor() as cursor:
            cursor.execute("reset role")

    assert isinstance(first, Figure)
    assert isinstance(second, Figure)
    assert first.derivation == second.derivation
    row = _row(db, first.derivation)
    assert (row["operation"], row["output_dataset"]) == ("api.respond", "api.well_detail")
    assert (row["determinism_class"], row["ttl_class"]) == ("D3", "ephemeral")
    assert row["output_partition"] == {"request_selector": f"api10={API10}"}
    assert row["params"] == {"operation_id": "get_well"}
    validate_selector(db, row, str(first.selector), handle=first.handle)
    with db.cursor() as cursor:
        cursor.execute(
            "select count(*) from lineage.derivations"
            " where operation = 'api.respond' and output_dataset = 'api.well_detail'"
        )
        assert cursor.fetchone()[0] == 1
        cursor.execute(
            "select rule_id from lineage.derivation_rules where derivation_id = %s",
            (first.derivation,),
        )
        assert cursor.fetchall() == [("cr_nd_compute_crs_1",)]
        cursor.execute(
            "select selector, evidence from lineage.response_selector_outputs"
            " where derivation_id = %s",
            (first.derivation,),
        )
        assert cursor.fetchall() == [
            (f"api10={API10}&col=lateral_length_ft", {"value": "5280.00", "unit": "ft"})
        ]

    with pytest.raises(InvalidSelector):
        validate_selector(
            db,
            row,
            f"api10={API10}&col=total_depth_ft",
            handle=f"{first.derivation}#api10={API10}&col=total_depth_ft",
        )


def test_changed_response_output_hits_the_derivation_determinism_gate(
    db: psycopg.Connection,
) -> None:
    manifest_id = seed_manifest(db, sha256="5" * 64)
    input_id = _derivation(db, dataset="canonical.well_spatial", manifest_id=manifest_id)
    arguments = {
        "dataset": "api.well_detail",
        "operation_id": "get_well",
        "locator": f"/v1/wells/{API10}",
        "partition": {"api10": API10},
        "input_derivations": [input_id],
        "correlation_id": "run_selector_collision",
    }
    first = figure(
        "5280.00",
        unit="ft",
        derivation=input_id,
        selector=f"api10={API10}&col=lateral_length_ft",
    )
    changed = first.model_copy(update={"value": "5281.00"})

    registered = register_response_figures(db, first, **arguments)
    with pytest.raises(DeterminismViolation):
        register_response_figures(db, changed, **arguments)

    row = db.execute(
        "select evidence from lineage.response_selector_outputs where derivation_id = %s",
        (registered.derivation,),
    ).fetchone()
    assert row[0] == {"value": "5280.00", "unit": "ft"}
