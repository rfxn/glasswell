from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import psycopg

from glasswell.lineage.capture import derive, lineage_session
from glasswell.lineage.manifests import register_manifest
from glasswell.lineage.models import DeriveEnvironment, OutputSpec
from glasswell.lineage.serialization import hash_payload
from glasswell.lineage.store import PostgresRecorder
from tests.conftest import FIXTURE_ENV_ID
from tests.support.fakes import FixedClock

FETCHED_AT = datetime(2026, 8, 1, 5, 2, 11, tzinfo=UTC)

FIXTURE_ENV = DeriveEnvironment(
    code_version="git:0000test",
    code_dirty=False,
    env_id=FIXTURE_ENV_ID,
)


def seed_manifest(
    connection: psycopg.Connection,
    *,
    sha256: str,
    source_id: str = "nd_mpr_xlsx",
    source_key: str = "2024_03.xlsx",
    fetched_at: datetime = FETCHED_AT,
) -> str:
    registration = register_manifest(
        connection,
        sha256=sha256,
        size_bytes=len(sha256),
        source_id=source_id,
        source_key=source_key,
        acquisition_url=f"https://example.invalid/{source_key}",
        acquisition_method="https_get",
        fetched_at=fetched_at,
        storage_uri=f"/data/raw/{source_id}/{source_key}",
    )
    return registration.manifest.manifest_id


def seed_derivation(
    connection: psycopg.Connection,
    *,
    operation: str = "canonical.promote",
    params: dict | None = None,
    partition: dict[str, str] | None = None,
) -> str:
    recorder = PostgresRecorder(connection)
    with lineage_session(
        recorder=recorder, environment=FIXTURE_ENV, clock=FixedClock(), correlation_id="run_seed"
    ), derive(
        operation,  # type: ignore[arg-type]
        output=OutputSpec(
            store="parquet",
            dataset="canonical.production_monthly",
            partition=partition or {"source_id": "nd_mpr_xlsx"},
        ),
        params=params or {},
    ) as context:
        context.set_output_hash("0" * 64)
    return context.derivation_id


def seed_production(
    connection: psycopg.Connection,
    *,
    api10: str,
    production_month: date,
    report_vintage: date,
    volume: Decimal,
    manifest_id: str,
    derivation_id: str,
    stream: str = "oil",
    source_id: str = "nd_mpr_xlsx",
    granularity: str = "well_observed",
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into canonical.production_monthly (api10, production_month, stream, source_id,"
            " report_vintage, volume, unit, days_produced, granularity, value_hash,"
            " source_manifest_id, derivation_id)"
            " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                api10,
                production_month,
                stream,
                source_id,
                report_vintage,
                volume,
                "bbl",
                30,
                granularity,
                hash_payload({"volume": volume, "unit": "bbl"}),
                manifest_id,
                derivation_id,
            ),
        )
