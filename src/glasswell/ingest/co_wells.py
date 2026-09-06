"""ECMC well headers into canonical, under the rules that decide what a Colorado well is.

Four decisions govern this promotion and every one of them is a row: how the API-10 is built
from two columns that carry no state code, which of two byte-identical feature rows is the
well, what a header's valid time is, and that the class a status letter maps to is resolved at
read time rather than written here. No state code appears in this module.

`status_canonical` is deliberately left null. `canonical.wells` is append-only and ECMC
republishes nightly, so writing the class at promotion would invent a valid time the regulator
never filed; `canonical.status_resolution` is where the map and the card both read it from.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import polars as pl
import psycopg

from glasswell.absence import absent_if_blank
from glasswell.db.dsn import add_dsn_argument, resolve_dsn
from glasswell.ingest.base import IngestRun, open_ingest_run, resolve_environment
from glasswell.lineage.capture import current_session, derive
from glasswell.lineage.conformance import load_rules, rule_for_family
from glasswell.lineage.fetch_attempts import durable_fetch_attempts
from glasswell.lineage.models import InputRef, OutputSpec
from glasswell.lineage.quarantine import quarantine
from glasswell.lineage.serialization import hash_payload

__rule_version__ = "1"

SOURCE_ID = "co_ecmc_wells_shp"
STAGING_TABLE = "staging.co_ecmc_wells"
CANONICAL_WELLS = "canonical.wells"
CANONICAL_SPATIAL = "canonical.well_spatial"
GEOM_TYPE = "surface"

IDENTITY_FAMILY = "cr_co_wells_api10"
DEDUP_FAMILY = "cr_co_wells_dedup"
DATUM_FAMILY = "cr_co_wells_datum"
EFFECTIVE_FAMILY = "cr_co_wells_effective"
PROVENANCE_FAMILY = "cr_co_wells_geometry_provenance"
SCOPE_FAMILY = "cr_co_wells_geometry_scope"
STATUS_FAMILY = "cr_co_wells_status_vocab"
WELL_TYPE_FAMILY = "cr_co_wells_well_type"
QUALIFIER_FAMILY = "cr_co_wells_location_qualifier"
BLANK_FAMILY = "cr_co_wells_shp_blank_is_absent"

# The identity tuple deduplication is decided over: everything that identifies the feature.
IDENTITY_COLUMNS = ("facil_id", "loc_id", "facil_stat", "latitude", "longitude")


@dataclass(frozen=True, slots=True)
class HeaderReport:
    manifest_id: str
    rows_read: int
    wells_appended: int
    geometry_appended: int
    quarantined: dict[str, int]
    derivation_id: str

    def to_dict(self) -> dict[str, object]:
        return {
            "manifest_id": self.manifest_id,
            "rows_read": self.rows_read,
            "wells_appended": self.wells_appended,
            "geometry_appended": self.geometry_appended,
            "quarantined": dict(sorted(self.quarantined.items())),
            "derivation_id": self.derivation_id,
        }


_APPEND_HEADERS = f"""
insert into {CANONICAL_WELLS} (
    api10, state_code, county_code_at_permit, operator_id, operator_name_reported, well_name,
    status_reported, status_canonical, well_type_reported, spud_date, effective_from,
    source_manifest_id, derivation_id)
values (%(api10)s, %(state_code)s, %(county_code_at_permit)s, %(operator_id)s,
        %(operator_name_reported)s, %(well_name)s, %(status_reported)s, null,
        %(well_type_reported)s, %(spud_date)s, %(effective_from)s, %(manifest_id)s,
        %(derivation_id)s)
on conflict (api10, effective_from) do nothing
"""

_APPEND_SPATIAL = f"""
insert into {CANONICAL_SPATIAL} (
    api10, geom_type, geom_key, geom, source_datum, transform_rule_id, location_qualifier,
    source_manifest_id, derivation_id)
select %(api10)s, %(geom_type)s, %(geom_key)s, s.geom, %(source_datum)s,
       %(transform_rule_id)s, %(location_qualifier)s, %(manifest_id)s, %(derivation_id)s
  from {STAGING_TABLE} s
 where s.manifest_id = %(manifest_id)s and s.source_row_ordinal = %(ordinal)s
   and s.geom is not null
on conflict (api10, geom_type, geom_key) do nothing
"""


def build_api10(row: dict[str, Any], spec: dict[str, Any]) -> str | None:
    """The API-10 the identity rule composes, or None for a caller to quarantine."""
    pad = dict(spec["pad"])
    parts = [str(spec["state_code"])]
    for column in spec["source_cols"]:
        value = row.get(column)
        if value is None or not str(value).strip().isdigit():
            return None
        parts.append(str(value).strip().rjust(int(pad[column]), str(spec["pad_char"])))
    built = str(spec["separator"]).join(parts)
    return built if len(built) == 10 else None


def label_conforms(row: dict[str, Any], spec: dict[str, Any]) -> bool:
    label = str(row.get(str(spec["label_col"])) or "").strip()
    return re.fullmatch(str(spec["label_pattern"]), label) is not None


def location_qualifier(row: dict[str, Any], spec: dict[str, Any]) -> str:
    """Loc_Qual's first token, case-folded, which is the class the rule registers.

    ECMC files sixteen strings differing only in that token's case, so the fold is the whole
    mapping; a value the rule does not register is refused rather than passed through, because
    an unclassed coordinate quality served as a class is the naked claim this rule removes.
    """
    raw = str(row.get("loc_qual") or "").strip()
    token = raw.split(" ")[0].lower() if raw else ""
    if not token:
        return str(spec["blank_class"])
    if token not in spec["classes"]:
        raise ValueError(
            f"{raw} folds to {token}, which cr_co_wells_location_qualifier_1 does not register"
        )
    return token


def effective_from(row: dict[str, Any], spec: dict[str, Any], fallback: date) -> date:
    """Stat_Date, the regulator's own clock for the field the status rule reads."""
    raw = row.get(str(spec["effective_from_field"]))
    text = "" if raw is None else str(raw).strip()
    if not text:
        return fallback
    for pattern in ("%Y-%m-%d", "%Y%m%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text[:10], pattern).date()
        except ValueError:
            continue
    return fallback


# Read under cr_co_wells_shp_blank_is_absent_1, not only staged under it: the generations
# already in staging were written before the rule existed and staging is never edited in place,
# so a promotion that read them verbatim would put the empty string back into canonical.
_STAGED_ATTRIBUTES = (
    "api_county", "api_seq", "api_label", "operat_num", "operator", "well_name", "well_num",
    "spud_date", "facil_id", "facil_stat", "well_class", "stat_date", "loc_qual", "loc_id",
    "latitude", "longitude",
)
_STAGED = (
    "select source_row_ordinal,"
    f" {', '.join(f'{absent_if_blank(name)} as {name}' for name in _STAGED_ATTRIBUTES)},"
    "       geom is not null as has_geometry"
    f"  from {STAGING_TABLE} where manifest_id = %s order by source_row_ordinal"
)


def _staged(connection: psycopg.Connection, manifest_id: str) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(_STAGED, (manifest_id,))
        columns = [column.name for column in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _latest_manifest(connection: psycopg.Connection) -> tuple[str, date]:
    with connection.cursor() as cursor:
        cursor.execute(
            "select manifest_id, coalesce(fetch_vintage, fetched_at::date)"
            "  from lineage.manifests where source_id = %s"
            " order by fetched_at desc limit 1",
            (SOURCE_ID,),
        )
        row = cursor.fetchone()
    if row is None:
        raise LookupError(f"no manifest for {SOURCE_ID}: run the GIS ingest first")
    return str(row[0]), row[1]


def _date(value: Any) -> date | None:
    text = "" if value is None else str(value).strip()
    if not text:
        return None
    for pattern in ("%Y-%m-%d", "%Y%m%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text[:10], pattern).date()
        except ValueError:
            continue
    return None


def _quarantine(
    connection: psycopg.Connection,
    rows: Sequence[dict[str, Any]],
    *,
    reason_code: str,
    manifest_id: str,
    rule_id: str | None,
) -> int:
    if not rows:
        return 0
    session = current_session()
    quarantine(
        connection,
        pl.DataFrame([{key: str(value) for key, value in row.items()} for row in rows]),
        reason_code=reason_code,
        manifest_id=manifest_id,
        source_id=SOURCE_ID,
        staging_table=STAGING_TABLE,
        stage="conform",
        seen_at=session.clock.now(),
        rule_id=rule_id,
        correlation_id=session.correlation_id,
    )
    return len(rows)


def promote_headers(run: IngestRun) -> HeaderReport:
    """Promote the staged header table into the canonical spine and its surface geometry."""
    connection = run.connection
    conform = load_rules(connection, source_id=SOURCE_ID, stage="conform", as_of=run.as_of)
    validate = load_rules(connection, source_id=SOURCE_ID, stage="validate", as_of=run.as_of)
    parse = load_rules(connection, source_id=SOURCE_ID, stage="parse", as_of=run.as_of)
    identity = rule_for_family(conform, IDENTITY_FAMILY)
    qualifier = rule_for_family(conform, QUALIFIER_FAMILY)
    dedup = rule_for_family(validate, DEDUP_FAMILY)
    datum = rule_for_family(conform, DATUM_FAMILY)
    effective = rule_for_family(conform, EFFECTIVE_FAMILY)
    cited = [
        identity.rule_id,
        dedup.rule_id,
        effective.rule_id,
        rule_for_family(conform, STATUS_FAMILY).rule_id,
        rule_for_family(conform, WELL_TYPE_FAMILY).rule_id,
        rule_for_family(parse, BLANK_FAMILY).rule_id,
        qualifier.rule_id,
    ]
    spatial_cited = [
        datum.rule_id,
        rule_for_family(conform, PROVENANCE_FAMILY).rule_id,
        rule_for_family(conform, SCOPE_FAMILY).rule_id,
    ]
    manifest_id, vintage = _latest_manifest(connection)
    staged = _staged(connection, manifest_id)

    keyless: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    coordinateless: list[dict[str, Any]] = []
    promoted: list[dict[str, Any]] = []
    seen: dict[tuple, int] = {}
    for row in staged:
        api10 = build_api10(row, dict(identity.spec))
        if api10 is None or not label_conforms(row, dict(identity.spec)):
            keyless.append(row)
            continue
        fingerprint = (api10, *(row[column] for column in IDENTITY_COLUMNS))
        first = seen.get(fingerprint)
        if first is not None:
            # min(ordinal) is kept, so the row the regulator wrote first is the well and the
            # discard is held beside it rather than dropped.
            duplicates.append({**row, "kept_source_row_ordinal": first})
            continue
        seen[fingerprint] = row["source_row_ordinal"]
        if not row["has_geometry"]:
            coordinateless.append(row)
        promoted.append(
            {
                "api10": api10,
                "state_code": str(identity.spec["state_code"]),
                "county_code_at_permit": row["api_county"],
                "operator_id": row["operat_num"],
                "operator_name_reported": row["operator"],
                "well_name": row["well_name"],
                "status_reported": row["facil_stat"],
                "well_type_reported": row["well_class"],
                "spud_date": _date(row["spud_date"]),
                "effective_from": effective_from(row, dict(effective.spec), vintage),
                "location_qualifier": location_qualifier(row, dict(qualifier.spec)),
                "ordinal": row["source_row_ordinal"],
            }
        )

    with derive(
        "canonical.promote",
        output=OutputSpec(
            store="postgis",
            dataset=CANONICAL_WELLS,
            partition={"manifest_id": manifest_id},
        ),
        params={"source_id": SOURCE_ID, "geom_type": GEOM_TYPE},
        inputs=[InputRef(kind="manifest", ref_id=manifest_id, as_of_vintage=vintage)],
        rules=[*cited, *spatial_cited],
    ) as promotion:
        promotion.set_rows(len(promoted))
        promotion.set_output_hash(
            hash_payload({"wells": len(promoted), "manifest_id": manifest_id})
        )

    written = {"manifest_id": manifest_id, "derivation_id": promotion.derivation_id}
    with connection.cursor() as cursor:
        cursor.executemany(
            _APPEND_HEADERS,
            [{**row, **written} for row in promoted],
        )
        wells_appended = len(promoted)
        cursor.executemany(
            _APPEND_SPATIAL,
            [
                {
                    **written,
                    "api10": row["api10"],
                    "ordinal": row["ordinal"],
                    "geom_type": GEOM_TYPE,
                    "geom_key": manifest_id,
                    "source_datum": str(datum.spec["source_prj"]),
                    "transform_rule_id": datum.rule_id,
                    "location_qualifier": row["location_qualifier"],
                }
                for row in promoted
            ],
        )
        cursor.execute(
            f"select count(*) from {CANONICAL_SPATIAL} where source_manifest_id = %s",
            (manifest_id,),
        )
        geometry_appended = int(cursor.fetchone()[0])

    quarantined = {
        "key_incomplete": _quarantine(
            connection, keyless, reason_code=str(identity.spec["reason_code"]),
            manifest_id=manifest_id, rule_id=identity.rule_id,
        ),
        "duplicate_row": _quarantine(
            connection, duplicates, reason_code=str(dedup.spec["reason_code"]),
            manifest_id=manifest_id, rule_id=dedup.rule_id,
        ),
        "coordinate_absent": _quarantine(
            connection, coordinateless, reason_code="coordinate_absent",
            manifest_id=manifest_id, rule_id=datum.rule_id,
        ),
    }
    return HeaderReport(
        manifest_id=manifest_id,
        rows_read=len(staged),
        wells_appended=wells_appended,
        geometry_appended=geometry_appended,
        quarantined=quarantined,
        derivation_id=promotion.derivation_id,
    )


def run_headers(
    connection: psycopg.Connection,
    *,
    env_id: str | None = None,
    code_version: str | None = None,
) -> HeaderReport:
    environment = resolve_environment(connection, env_id=env_id, code_version=code_version)
    with open_ingest_run(connection, source_id=SOURCE_ID, environment=environment) as run:
        return promote_headers(run)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Promote ECMC well headers and their surface geometry into canonical."
    )
    add_dsn_argument(parser)
    parser.add_argument("--env-id", default=None)
    parser.add_argument("--code-version", default=None)
    arguments = parser.parse_args(argv)
    arguments.dsn = resolve_dsn(arguments.dsn)

    with durable_fetch_attempts(arguments.dsn), psycopg.connect(arguments.dsn) as connection:
        report = run_headers(
            connection, env_id=arguments.env_id, code_version=arguments.code_version
        )
        connection.commit()
    print(json.dumps(report.to_dict(), sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
