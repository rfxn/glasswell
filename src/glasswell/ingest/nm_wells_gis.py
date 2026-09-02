"""Capture the OCD public wells layer as a second, independent New Mexico well population.

The FTP header archive is a frozen 2026-08-20 snapshot; this layer is refreshed as permits are
approved. Two independently produced measurements of the same population are what make a
cross-source parity rule a measurement rather than a rhetorical device, and the `ulstr` column
is the seam a future New Mexico land grid attaches to.

Staging is the terminus, deliberately and for the reason `nm_c115b.py` stops there too: the
parity measurement is what decides whether and how this source promotes, and promoting first
would make the parity rule a rationalisation of a choice already made.

The walk order, identity, datum and source selection are conformance rows read from the
registry; this module is their executor and restates none of them.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import polars as pl
import psycopg

from glasswell.db.dsn import add_dsn_argument, resolve_dsn
from glasswell.ingest.arcgis import arcgis_rest_paginate
from glasswell.ingest.base import record_vintage_day, resolve_environment
from glasswell.lineage import (
    ConformanceRule,
    InputRef,
    OutputSpec,
    PostgresRecorder,
    current_session,
    derive,
    lineage_session,
    load_rules,
    quarantine,
)
from glasswell.lineage.fetch_attempts import durable_fetch_attempts
from glasswell.lineage.serialization import hash_payload

SERVICE_URL = (
    "https://gis.emnrd.nm.gov/arcgis/rest/services/OCDView/Wells_Public/FeatureServer"
)
LAYER_ID = 0
SOURCE_ID = "nm_ocd_wells_gis"
SOURCE_KEY = "nm_ocd_wells_public.geojsonl"
STAGING_TABLE = "staging.nm_ocd_wells_gis"

SOURCE_RULE_ID = "cr_nm_wells_gis_source_1"
WALK_ORDER_RULE_ID = "cr_nm_wells_gis_walk_order_1"
IDENTITY_RULE_ID = "cr_nm_wells_gis_api10_1"
DATUM_RULE_ID = "cr_nm_wells_gis_datum_1"
PARITY_RULE_ID = "cr_nm_wells_gis_parity_1"
FETCH_RULES = (SOURCE_RULE_ID, WALK_ORDER_RULE_ID)

WHERE = "1=1"

COLUMNS: tuple[str, ...] = (
    "id",
    "name",
    "type",
    "status",
    "sub_type_code",
    "ogrid",
    "ogrid_name",
    "district_code",
    "district",
    "county_code",
    "county",
    "ulstr",
    "latitude",
    "longitude",
    "projection",
    "directional_status",
    "details",
    "files",
    "year_spudded",
    "spud_date",
    "lease_type",
    "measured_vertical_depth",
    "true_vertical_depth",
    "pool_id_list",
    "last_production_date",
    "plug_date",
)

REASON_CODES: tuple[str, ...] = ("key_incomplete", "duplicate_row", "parse_error")

_DASHED_API10 = re.compile(r"\A(\d{2})-(\d{3})-(\d{5})\Z")


class SchemaDrift(ValueError):
    """The service no longer carries a property the staging table declares."""


class DatumMismatch(ValueError):
    """The service's recorded spatial reference disagrees with the conformance registry."""


def api10_from_dashed(value: object) -> str:
    """The layer ships API-10 dashed (`30-001-00505`); the spine holds it undashed."""
    match = _DASHED_API10.match(str(value or ""))
    if match is None:
        raise ValueError(f"{value!r} is not a dashed API-10")
    return "".join(match.groups())


@dataclass(frozen=True, slots=True)
class ParseResult:
    rows: list[dict[str, Any]]
    rejects: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class LoadResult:
    source_id: str
    manifest_id: str
    parse_derivation_id: str
    staged_rows: int
    quarantined: Mapping[str, int]
    unchanged: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "manifest_id": self.manifest_id,
            "parse_derivation_id": self.parse_derivation_id,
            "staged_rows": self.staged_rows,
            "quarantined": dict(self.quarantined),
            "unchanged": self.unchanged,
        }


def _text(value: object) -> str | None:
    return None if value is None else str(value)


def _reject(row: Mapping[str, Any], reason_code: str, detail: str) -> dict[str, Any]:
    return {
        "manifest_id": row["manifest_id"],
        "source_row_ordinal": row["source_row_ordinal"],
        "reason_code": reason_code,
        "id": row["id"],
        "detail": detail,
    }


def parse_features(
    features: Iterable[tuple[int, Mapping[str, Any]]], *, manifest_id: str = ""
) -> ParseResult:
    """Stage every source row verbatim and record a reason for each one that fails a rule."""
    rows: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for ordinal, feature in features:
        attributes = dict(feature.get("properties") or {})
        missing = [column for column in COLUMNS if column not in attributes]
        if missing:
            raise SchemaDrift(f"{SOURCE_KEY} has no {', '.join(missing)} property")
        row: dict[str, Any] = {column: _text(attributes[column]) for column in COLUMNS}
        row["manifest_id"] = manifest_id
        row["source_row_ordinal"] = ordinal
        note = _unstorable(feature.get("geometry"))
        row["geom_wkt"] = None if note else _point_wkt(feature["geometry"])
        rows.append(row)

        if note:
            rejects.append(_reject(row, "parse_error", note))
        try:
            api10 = api10_from_dashed(row["id"])
        except ValueError as error:
            rejects.append(_reject(row, "key_incomplete", str(error)))
            continue
        first = seen.get(api10)
        if first is not None:
            rejects.append(
                _reject(row, "duplicate_row", f"id already read at source row {first}")
            )
            continue
        seen[api10] = ordinal
    return ParseResult(rows=rows, rejects=rejects)


def _unstorable(geometry: Mapping[str, Any] | None) -> str | None:
    if not geometry:
        return "the source feature carries no geometry"
    if geometry.get("type") != "Point":
        return f"{geometry.get('type')} does not fit the declared Point column"
    coordinates = geometry.get("coordinates") or ()
    if len(coordinates) < 2:
        return "the source point carries fewer than two ordinates"
    return None


def _point_wkt(geometry: Mapping[str, Any]) -> str:
    longitude, latitude = geometry["coordinates"][:2]
    return f"POINT ({longitude} {latitude})"


def _features(payload_path: Path) -> Iterator[tuple[int, dict[str, Any]]]:
    """One FeatureCollection per line; the ordinal is the walk order."""
    ordinal = 0
    with payload_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            for feature in json.loads(line).get("features", ()):
                yield ordinal, feature
                ordinal += 1


def _rule(connection: psycopg.Connection, rule_id: str) -> ConformanceRule:
    for rule in load_rules(connection, source_id=SOURCE_ID):
        if rule.rule_id == rule_id:
            return rule
    raise LookupError(f"no {rule_id} rule is seeded for {SOURCE_ID}")


def _already_staged(connection: psycopg.Connection, manifest_id: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            f"select 1 from {STAGING_TABLE} where manifest_id = %s limit 1", (manifest_id,)
        )
        return cursor.fetchone() is not None


def _existing_parse_derivation(connection: psycopg.Connection, manifest_id: str) -> str:
    with connection.cursor() as cursor:
        cursor.execute(
            "select derivation_id from lineage.derivations"
            " where operation = 'stage.parse' and output_dataset = %s"
            "   and output_partition ->> 'manifest_id' = %s",
            (STAGING_TABLE, manifest_id),
        )
        found = cursor.fetchone()
    return found[0] if found else ""


def load(
    connection: psycopg.Connection,
    *,
    service_url: str = SERVICE_URL,
    raw_root: Path | str | None = None,
    client: httpx.Client | None = None,
    page_size: int | None = None,
    page_delay_seconds: float | None = None,
    restage: bool = False,
) -> LoadResult:
    """Walk the layer, preserve the bytes, stage them. Staging is the terminus."""
    datum = _rule(connection, DATUM_RULE_ID)
    walk_order = _rule(connection, WALK_ORDER_RULE_ID)
    source_epsg = int(datum.spec["source_epsg"])
    storage_epsg = int(datum.spec["target_epsg"])

    fetch_kwargs: dict[str, Any] = {}
    if page_delay_seconds is not None:
        fetch_kwargs["page_delay_seconds"] = page_delay_seconds
    fetched = arcgis_rest_paginate(
        connection,
        SOURCE_ID,
        SOURCE_KEY,
        service_url=service_url,
        layer_id=LAYER_ID,
        where=WHERE,
        raw_root=raw_root,
        client=client,
        page_size=page_size,
        order_by=str(walk_order.spec["order_by"]),
        rules=FETCH_RULES,
        **fetch_kwargs,
    )
    manifest = fetched.manifest
    recorded_sr = manifest.acquisition_params.get("out_sr")
    if recorded_sr is not None and int(recorded_sr) != source_epsg:
        raise DatumMismatch(
            f"{SOURCE_KEY} recorded wkid {recorded_sr}; the registry declares EPSG:{source_epsg}"
        )

    if restage:
        _clear_staging(connection, manifest.manifest_id)
    elif fetched.unchanged and _already_staged(connection, manifest.manifest_id):
        return LoadResult(
            source_id=SOURCE_ID,
            manifest_id=manifest.manifest_id,
            parse_derivation_id=_existing_parse_derivation(connection, manifest.manifest_id),
            staged_rows=0,
            quarantined=dict.fromkeys(REASON_CODES, 0),
            unchanged=True,
        )

    return _stage(
        connection,
        fetched.payload_path,
        manifest_id=manifest.manifest_id,
        vintage=manifest.fetch_vintage,
        source_epsg=source_epsg,
        storage_epsg=storage_epsg,
    )


def _clear_staging(connection: psycopg.Connection, manifest_id: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(f"delete from {STAGING_TABLE} where manifest_id = %s", (manifest_id,))
        return cursor.rowcount


def _stage(
    connection: psycopg.Connection,
    payload_path: Path,
    *,
    manifest_id: str,
    vintage: date,
    source_epsg: int,
    storage_epsg: int,
) -> LoadResult:
    parsed = parse_features(_features(payload_path), manifest_id=manifest_id)
    geometry = f"ST_Transform(ST_GeomFromText(%(geom_wkt)s, {source_epsg}), {storage_epsg})"
    columns = ", ".join(COLUMNS)
    placeholders = ", ".join(f"%({column})s" for column in COLUMNS)
    statement = (
        f"insert into {STAGING_TABLE} (manifest_id, source_row_ordinal, {columns}, geom)"
        f" values (%(manifest_id)s, %(source_row_ordinal)s, {placeholders}, {geometry})"
        " on conflict (manifest_id, source_row_ordinal) do nothing"
    )

    with derive(
        "stage.parse",
        output=OutputSpec(
            store="postgis", dataset=STAGING_TABLE, partition={"manifest_id": manifest_id}
        ),
        params={"source_key": SOURCE_KEY, "source_epsg": source_epsg, "layer_id": LAYER_ID},
        inputs=[InputRef(kind="manifest", ref_id=manifest_id, as_of_vintage=vintage)],
        rules=[IDENTITY_RULE_ID, DATUM_RULE_ID, WALK_ORDER_RULE_ID, PARITY_RULE_ID],
    ) as context:
        with connection.cursor() as cursor:
            cursor.executemany(statement, parsed.rows)
        context.set_rows(len(parsed.rows))
        context.set_output_hash(
            hash_payload({"rows": len(parsed.rows), "manifest_id": manifest_id})
        )

    counts = dict.fromkeys(REASON_CODES, 0)
    for reason_code in REASON_CODES:
        held = [reject for reject in parsed.rejects if reject["reason_code"] == reason_code]
        counts[reason_code] = _quarantine(connection, held, reason_code=reason_code)

    record_vintage_day(
        connection,
        source_id=SOURCE_ID,
        vintage_date=vintage,
        manifest_ids=[manifest_id],
        opened_at=current_session().clock.now(),
        promotion_derivation_id=context.derivation_id,
        rows_examined=len(parsed.rows),
        rows_appended=len(parsed.rows),
    )
    return LoadResult(
        source_id=SOURCE_ID,
        manifest_id=manifest_id,
        parse_derivation_id=context.derivation_id,
        staged_rows=len(parsed.rows),
        quarantined=counts,
    )


_RULE_FOR_REASON = {
    "key_incomplete": IDENTITY_RULE_ID,
    "duplicate_row": WALK_ORDER_RULE_ID,
}


def _quarantine(
    connection: psycopg.Connection, rows: Sequence[Mapping[str, Any]], *, reason_code: str
) -> int:
    if not rows:
        return 0
    session = current_session()
    quarantine(
        connection,
        pl.DataFrame(rows),
        reason_code=reason_code,
        manifest_id=str(rows[0]["manifest_id"]),
        source_id=SOURCE_ID,
        staging_table=STAGING_TABLE,
        stage="parse",
        seen_at=session.clock.now(),
        rule_id=_RULE_FOR_REASON.get(reason_code),
        correlation_id=session.correlation_id,
    )
    return len(rows)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Capture the NM OCD public wells layer into staging."
    )
    add_dsn_argument(parser)
    parser.add_argument("--service-url", default=SERVICE_URL)
    parser.add_argument("--raw-root", default=None)
    parser.add_argument("--env-id", default=None, help="override the fingerprinted env id")
    parser.add_argument("--code-version", default=None)
    parser.add_argument(
        "--restage",
        action="store_true",
        help="re-parse from the stored bytes after a rule or schema change",
    )
    arguments = parser.parse_args(argv)
    arguments.dsn = resolve_dsn(arguments.dsn)

    with durable_fetch_attempts(arguments.dsn), psycopg.connect(arguments.dsn) as connection:
        environment = resolve_environment(
            connection, env_id=arguments.env_id, code_version=arguments.code_version
        )
        with lineage_session(recorder=PostgresRecorder(connection), environment=environment):
            result = load(
                connection,
                service_url=arguments.service_url,
                raw_root=arguments.raw_root,
                restage=arguments.restage,
            )
            connection.commit()
            print(json.dumps(result.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
