from __future__ import annotations

from datetime import date
from decimal import Decimal

from glasswell.seed import seed_all
from tests.support.seed import (
    seed_derivation,
    seed_manifest,
    seed_production,
    seed_well,
    seed_well_spatial,
)


def shift_month(value: date, months: int) -> date:
    absolute = value.year * 12 + value.month - 1 + months
    year, zero_month = divmod(absolute, 12)
    return date(year, zero_month + 1, 1)


def seed_model_population(
    db,
    *,
    extra_recent_peers: int = 0,
    one_peer_gas_gap: bool = False,
    one_test_missing_lateral: bool = False,
) -> None:
    seed_all(db)
    manifest_id = seed_manifest(db, sha256="7" * 64)
    derivation_id = seed_derivation(db)
    for ordinal in range(60 + extra_recent_peers):
        api10 = f"33053{ordinal:05d}"
        if ordinal < 30:
            first_production = date(2018, 1, 1)
        elif ordinal < 45:
            first_production = date(2021, 2, 1)
        elif ordinal < 60:
            first_production = date(2022, 2, 1)
        else:
            first_production = date(2020, 1, 1)
        completion = shift_month(first_production, -1)
        seed_well(
            db,
            api10=api10,
            completion_date=completion,
            confidential_flag=ordinal == 59,
            manifest_id=manifest_id,
            derivation_id=derivation_id,
        )
        longitude = -103.8 + ordinal * 0.01
        seed_well_spatial(
            db,
            api10=api10,
            geom_type="surface",
            wkt=f"POINT({longitude} 47.5)",
            manifest_id=manifest_id,
            derivation_id=derivation_id,
        )
        if not (one_test_missing_lateral and ordinal == 45):
            seed_well_spatial(
                db,
                api10=api10,
                geom_type="lateral",
                wkt=f"LINESTRING({longitude} 47.5, {longitude + 0.025} 47.5)",
                manifest_id=manifest_id,
                derivation_id=derivation_id,
            )
        with db.cursor() as cursor:
            cursor.execute(
                "insert into canonical.well_completions"
                " (completion_key, api10, well_completion_pool, pool_reported, source_id,"
                " production_month, report_vintage, source_manifest_id, derivation_id)"
                " values (%s, %s, 'BAKKEN', 'BAKKEN', 'nd_mpr_xlsx', %s, %s, %s, %s)",
                (
                    f"{api10}:BAKKEN",
                    api10,
                    first_production,
                    date(2026, 8, 1),
                    manifest_id,
                    derivation_id,
                ),
            )
        for month_index in range(24):
            production_month = shift_month(first_production, month_index)
            for stream, volume in (
                ("oil", Decimal("100.000")),
                ("gas", Decimal("200.000")),
                ("water", Decimal("30.000")),
            ):
                missing_gas = (
                    one_peer_gas_gap and ordinal == 60 and month_index == 0 and stream == "gas"
                )
                seed_production(
                    db,
                    api10=api10,
                    production_month=production_month,
                    report_vintage=date(2026, 8, 1),
                    volume=Decimal("0") if missing_gas else volume,
                    stream=stream,
                    manifest_id=manifest_id,
                    derivation_id=derivation_id,
                    null_semantics="no_report" if missing_gas else "reported",
                    days_produced=0 if missing_gas else 30,
                )
