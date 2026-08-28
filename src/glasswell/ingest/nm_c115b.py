"""Preserve the NM OCD C-115B natural-gas-waste well-level series (M1-9).

The service publishes a rolling ~13-month `reporting_period` window and nothing behind it, so
a month that rolls out is gone from the endpoint for good. This module is the recurring
capture: one ordered walk, one checksummed artifact, one manifest, one staging load. It stops
at staging by design — canonical promotion reads preserved bytes and can happen at leisure,
while the bytes cannot be re-fetched once the window moves.

The identity, vocabulary, walk order, datum and source selection are conformance rows read
from the registry; this module is their executor and restates none of them.
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
    "https://gis.emnrd.nm.gov/arcgis/rest/services/OCDPUB/C115B_NaturalGasWaste/FeatureServer"
)
LAYER_ID = 0
SOURCE_ID = "nm_c115b_upstream"
SOURCE_KEY = "c115b_upstream_by_well.geojsonl"
STAGING_TABLE = "staging.nm_c115b_upstream"

SOURCE_RULE_ID = "cr_nm_c115b_source_1"
WALK_ORDER_RULE_ID = "cr_nm_c115b_walk_order_1"
IDENTITY_RULE_ID = "cr_nm_c115b_api10_1"
WASTE_VOCAB_RULE_ID = "cr_nm_c115b_waste_vocab_1"
DATUM_RULE_ID = "cr_nm_c115b_datum_1"
FETCH_RULES = (SOURCE_RULE_ID, WALK_ORDER_RULE_ID)

# (id, reporting_period, waste_type) is a total order over the layer, so `resultOffset` pages
# are contiguous and disjoint. OBJECTID is not — see cr_nm_c115b_walk_order_1.
WALK_ORDER = "id ASC, reporting_period ASC, waste_type ASC"
WHERE = "1=1"

COLUMNS: tuple[str, ...] = (
    "id",
    "name",
    "type",
    "status",
    "lease_type",
    "ogrid",
    "ogrid_name",
    "latitude",
    "longitude",
    "pool_id_list",
    "details",
    "files",
    "structure_id",
    "structure_type",
    "reporting_period_year",
    "reporting_period",
    "waste_type",
    "volume",
)

REASON_CODES: tuple[str, ...] = (
    "key_incomplete",
    "unknown_vocab",
    "out_of_range_date",
    "unreliable_numeric",
    "duplicate_row",
    "parse_error",
)

_DASHED_API10 = re.compile(r"\A(\d{2})-(\d{3})-(\d{5})\Z")
_YYYYMM = re.compile(r"\A(\d{4})(0[1-9]|1[0-2])\Z")
_WASTE_TYPES = frozenset({"F", "V"})


class SchemaDrift(ValueError):
    """The service no longer carries a property the staging table declares."""


class DatumMismatch(ValueError):
    """The service's recorded spatial reference disagrees with the conformance registry."""


def api10_from_dashed(value: object) -> str:
    """The service ships API-10 dashed (`30-015-03890`); the spine holds it undashed."""
    match = _DASHED_API10.match(str(value or ""))
    if match is None:
        raise ValueError(f"{value!r} is not a dashed API-10")
    return "".join(match.groups())


def waste_type_code(value: object) -> str | None:
    code = str(value or "").strip().upper()
    return code if code in _WASTE_TYPES else None


def month_from_reporting_period(value: object) -> date | None:
    match = _YYYYMM.match(str(value if value is not None else ""))
    if match is None:
        return None
    return date(int(match.group(1)), int(match.group(2)), 1)


def volume_or_none(value: object) -> int | None:
    """A reported waste volume, kept as filed; anything that is not a whole count is refused."""
    if isinstance(value, bool) or value is None or isinstance(value, float):
        return None
    try:
        volume = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return volume if volume >= 0 else None


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
    months: tuple[str, ...]
    unchanged: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "manifest_id": self.manifest_id,
            "staged_rows": self.staged_rows,
            "quarantined": dict(self.quarantined),
            "months": list(self.months),
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
        "reporting_period": row["reporting_period"],
        "waste_type": row["waste_type"],
        "volume": row["volume"],
        "detail": detail,
    }


def _judge(
    row: Mapping[str, Any], seen: dict[tuple[str, str, str], int]
) -> tuple[str, str] | None:
    """The declared reason this row fails a rule, or None. `seen` accumulates identity keys."""
    try:
        api10 = api10_from_dashed(row["id"])
    except ValueError as error:
        return "key_incomplete", str(error)
    code = waste_type_code(row["waste_type"])
    if code is None:
        return "unknown_vocab", f"waste_type {row['waste_type']!r} is not F or V"
    month = month_from_reporting_period(row["reporting_period"])
    if month is None:
        return (
            "out_of_range_date",
            f"reporting_period {row['reporting_period']!r} is not YYYYMM",
        )
    if volume_or_none(row["volume"]) is None:
        return "unreliable_numeric", f"volume {row['volume']!r} is not a whole count"
    key = (api10, month.isoformat(), code)
    first = seen.get(key)
    if first is not None:
        return "duplicate_row", f"identity key already read at source row {first}"
    seen[key] = int(row["source_row_ordinal"])
    return None


def parse_features(
    features: Iterable[tuple[int, Mapping[str, Any]]], *, manifest_id: str = ""
) -> ParseResult:
    """Stage every source row verbatim and record a reason for each one that fails a rule."""
    rows: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []
    seen: dict[tuple[str, str, str], int] = {}
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
        verdict = _judge(row, seen)
        if verdict is not None:
            rejects.append(_reject(row, *verdict))
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
    """One FeatureCollection per line (SB-01 §1.2.1); the ordinal is the walk order."""
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


def _months(connection: psycopg.Connection, manifest_id: str) -> tuple[str, ...]:
    with connection.cursor() as cursor:
        cursor.execute(
            f"select distinct reporting_period from {STAGING_TABLE}"
            " where manifest_id = %s and reporting_period is not null order by 1",
            (manifest_id,),
        )
        return tuple(period for (period,) in cursor.fetchall())


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
    """Fetch the well-level layer, preserve the bytes, and stage them. Staging is the terminus."""
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
            months=_months(connection, manifest.manifest_id),
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

    output = OutputSpec(
        store="postgis", dataset=STAGING_TABLE, partition={"manifest_id": manifest_id}
    )
    with derive(
        "stage.parse",
        output=output,
        params={"source_key": SOURCE_KEY, "source_epsg": source_epsg, "layer_id": LAYER_ID},
        inputs=[InputRef(kind="manifest", ref_id=manifest_id, as_of_vintage=vintage)],
        rules=[IDENTITY_RULE_ID, WASTE_VOCAB_RULE_ID, DATUM_RULE_ID, WALK_ORDER_RULE_ID],
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

    months = _months(connection, manifest_id)
    record_vintage_day(
        connection,
        source_id=SOURCE_ID,
        vintage_date=vintage,
        manifest_ids=[manifest_id],
        opened_at=current_session().clock.now(),
        promotion_derivation_id=context.derivation_id,
        rows_examined=len(parsed.rows),
        rows_appended=len(parsed.rows),
        months_touched=months,
    )
    return LoadResult(
        source_id=SOURCE_ID,
        manifest_id=manifest_id,
        parse_derivation_id=context.derivation_id,
        staged_rows=len(parsed.rows),
        quarantined=counts,
        months=months,
    )


_RULE_FOR_REASON = {
    "key_incomplete": IDENTITY_RULE_ID,
    "unknown_vocab": WASTE_VOCAB_RULE_ID,
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
        description="Preserve the NM OCD C-115B well-level flaring and venting series."
    )
    parser.add_argument("--dsn", required=True)
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
