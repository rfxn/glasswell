from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from glasswell.lineage.capture import derive, lineage_session
from glasswell.lineage.manifests import register_manifest
from glasswell.lineage.models import DeriveEnvironment, OutputSpec
from glasswell.lineage.serialization import hash_payload
from glasswell.lineage.store import PostgresRecorder
from tests.conftest import FIXTURE_ENV_ID
from tests.support.fakes import FixedClock

FETCHED_AT = datetime(2026, 8, 1, 5, 2, 11, tzinfo=UTC)
EFFECTIVE_FROM = date(2026, 8, 1)
LATERAL_WKT = "LINESTRING(-103.5803 47.9075, -103.5401 47.9081)"
SURFACE_WKT = "POINT(-103.5803 47.9075)"

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


_WELL_DEFAULTS: dict[str, Any] = {
    "api14": None,
    "state_code": "33",
    "county_code_at_permit": "053",
    "ndic_file_no": "22023",
    "operator_name_reported": "DEVON ENERGY WILLISTON, L.L.C",
    "operator_id": None,
    "well_name": "BILL 14-23 1H",
    "status_canonical": "active",
    "status_reported": "A",
    "well_type_reported": "OG",
    "spud_date": date(2019, 5, 27),
    "confidential_flag": False,
    "basin": "williston",
    "land_unit_label": "151N-101W-11",
}

_INSERT_WELL = (
    "insert into canonical.wells (api10, api14, state_code, county_code_at_permit, ndic_file_no,"
    " operator_name_reported, operator_id, well_name, status_canonical, status_reported,"
    " well_type_reported, spud_date, confidential_flag, basin, land_unit_label, effective_from,"
    " source_manifest_id, derivation_id)"
    " values (%(api10)s, %(api14)s, %(state_code)s, %(county_code_at_permit)s,"
    " %(ndic_file_no)s, %(operator_name_reported)s, %(operator_id)s, %(well_name)s,"
    " %(status_canonical)s, %(status_reported)s, %(well_type_reported)s, %(spud_date)s,"
    " %(confidential_flag)s, %(basin)s, %(land_unit_label)s, %(effective_from)s,"
    " %(source_manifest_id)s, %(derivation_id)s)"
)


def seed_well(
    connection: psycopg.Connection,
    *,
    api10: str,
    effective_from: date = EFFECTIVE_FROM,
    manifest_id: str | None = None,
    derivation_id: str | None = None,
    **overrides: Any,
) -> str:
    unknown = set(overrides) - set(_WELL_DEFAULTS)
    if unknown:
        raise TypeError(f"canonical.wells has no column {sorted(unknown)}")
    row = {
        **_WELL_DEFAULTS,
        **overrides,
        "api10": api10,
        "effective_from": effective_from,
        "source_manifest_id": manifest_id or seed_manifest(connection, sha256="e" * 64),
        "derivation_id": derivation_id or seed_derivation(connection),
    }
    row["api14"] = row["api14"] or f"{api10}0000"
    with connection.cursor() as cursor:
        cursor.execute(_INSERT_WELL, row)
    return api10


def seed_well_spatial(
    connection: psycopg.Connection,
    *,
    api10: str,
    geom_type: str = "lateral",
    geom_key: str | None = None,
    wkt: str | None = None,
    source_datum: str = "EPSG:4269",
    transform_rule_id: str = "cr_nd_datum_1",
    manifest_id: str | None = None,
    derivation_id: str | None = None,
) -> str:
    key = geom_key or ("surface" if geom_type == "surface" else f"{api10}0000_LAT1")
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into canonical.well_spatial (api10, geom_type, geom_key, geom, source_datum,"
            " transform_rule_id, source_manifest_id, derivation_id)"
            " values (%s, %s, %s, st_geomfromtext(%s, 4326), %s, %s, %s, %s)",
            (
                api10,
                geom_type,
                key,
                wkt or (SURFACE_WKT if geom_type == "surface" else LATERAL_WKT),
                source_datum,
                transform_rule_id,
                manifest_id or seed_manifest(connection, sha256="e" * 64),
                derivation_id or seed_derivation(connection),
            ),
        )
    return key


def seed_glossary_term(
    connection: psycopg.Connection,
    *,
    term: str,
    short_definition: str = "A seeded term.",
    expanded_definition: str = "A seeded term, defined at the length the drawer renders.",
    aliases: list[str] | None = None,
    domain_tags: list[str] | None = None,
    related_terms: list[str] | None = None,
    source_refs: list[str] | None = None,
    highlightable: bool = True,
) -> str:
    term_id = f"gt_{term.lower().replace(' ', '_')}"
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into canonical.glossary_terms (term_id, term, aliases, short_definition,"
            " expanded_definition, domain_tags, related_terms, source_refs, highlightable)"
            " values (%s, %s, %s, %s, %s, %s, %s, %s, %s) on conflict do nothing",
            (
                term_id,
                term,
                aliases or [],
                short_definition,
                expanded_definition,
                domain_tags or ["lineage"],
                related_terms or [],
                source_refs or ["blueprint-v0.6 §9"],
                highlightable,
            ),
        )
    return term_id


def seed_conformance_rule(
    connection: psycopg.Connection,
    *,
    rule_id: str,
    rule_kind: str = "vocab_map",
    source_id: str = "nd_mpr_xlsx",
    stage: str = "conform",
    applies_to_fields: list[str] | None = None,
    spec: dict[str, Any] | None = None,
    rule: str = "A seeded rule.",
    rationale: str = "Seeded so a contract test can assert against a known row.",
    evidence_url: str = "https://www.dmr.nd.gov/oilgas/mprindex.asp",
    effective_from: date = date(2026, 1, 1),
) -> str:
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into lineage.conformance_rules (rule_id, rule_family, source_id, stage,"
            " applies_to_fields, rule_kind, spec, rule, rationale, evidence_url, effective_from)"
            " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) on conflict do nothing",
            (
                rule_id,
                rule_id.rsplit("_", 1)[0],
                source_id,
                stage,
                applies_to_fields or ["status"],
                rule_kind,
                Jsonb(spec or {"key_col": "status", "value_col": "status_canonical"}),
                rule,
                rationale,
                evidence_url,
                effective_from,
            ),
        )
    return rule_id


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
