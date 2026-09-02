"""ECMC production into canonical, at completion grain and with the well row beside it.

ECMC files each completion's volumes directly, so there is no allocation step: the rows are
already at the grain glasswell serves. The rollup is glasswell's, not the regulator's, which is
why it is disclosed rather than assumed -- `cr_co_production_grain_1` carries its semantics and
`cr_co_production_entity_key_1` decides both keys.

North Dakota's dual write, exactly: one row per completion plus one well row carrying their
exact sum, disclosed as `sum_over_pools`, so `/v1/wells/{api10}/production` renders and a
reader can tell a two-completion well from a one-completion well. A well-month with a single
completion promotes as the well and carries no aggregation, because relabelling it an aggregate
would signal a restatement that did not happen.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import psycopg

from glasswell.db.dsn import add_dsn_argument, resolve_dsn
from glasswell.ingest.base import IngestRun, open_ingest_run, resolve_environment
from glasswell.ingest.co_wells import build_api10
from glasswell.ingest.promote import classify_null_semantics
from glasswell.lineage.capture import derive
from glasswell.lineage.conformance import load_rules, rule_for_family
from glasswell.lineage.fetch_attempts import durable_fetch_attempts
from glasswell.lineage.models import InputRef, OutputSpec
from glasswell.lineage.serialization import hash_payload

__rule_version__ = "1"

SOURCE_ID = "co_ecmc_monthly_prod"
HEADER_SOURCE_ID = "co_ecmc_wells_shp"
STAGING_TABLE = "staging.co_ecmc_production"
CANONICAL_PRODUCTION = "canonical.production_monthly"
CANONICAL_COMPLETIONS = "canonical.well_completions"

ENTITY_KEY_FAMILY = "cr_co_production_entity_key"
GRAIN_FAMILY = "cr_co_production_grain"
LIQUIDS_FAMILY = "cr_co_production_liquids"
IDENTITY_FAMILY = "cr_co_wells_api10"

GRANULARITY = "well_observed"
AGGREGATION = "sum_over_pools"
# The three streams ECMC files, with the unit each is filed in. Condensate is not a column:
# cr_co_production_liquids_1 is the row that says the oil stream carries it.
STREAMS: tuple[tuple[str, str, str], ...] = (
    ("oil", "oilproduced", "bbl"),
    ("gas", "gasproduced", "mcf"),
    ("water", "waterproduced", "bbl"),
)


@dataclass(frozen=True, slots=True)
class ProductionReport:
    manifest_id: str
    rows_read: int
    pool_rows: int
    well_rows: int
    aggregate_rows: int
    completions: int
    derivation_id: str

    def to_dict(self) -> dict[str, object]:
        return {
            "manifest_id": self.manifest_id,
            "rows_read": self.rows_read,
            "pool_rows": self.pool_rows,
            "well_rows": self.well_rows,
            "aggregate_rows": self.aggregate_rows,
            "completions": self.completions,
            "derivation_id": self.derivation_id,
        }


_INSERT_CANONICAL = f"""
insert into {CANONICAL_PRODUCTION} (
    entity_type, entity_key, reporting_level, well_completion_pool, aggregation,
    api10, production_month, stream, source_id, report_vintage, volume, unit, days_produced,
    granularity, value_hash, source_manifest_id, derivation_id, null_semantics)
values (%(entity_type)s, %(entity_key)s, %(reporting_level)s, %(well_completion_pool)s,
        %(aggregation)s, %(api10)s, %(production_month)s, %(stream)s, %(source_id)s,
        %(report_vintage)s, %(volume)s, %(unit)s, %(days_produced)s, %(granularity)s,
        %(value_hash)s, %(source_manifest_id)s, %(derivation_id)s, %(null_semantics)s)
on conflict do nothing
"""

_INSERT_COMPLETION = f"""
insert into {CANONICAL_COMPLETIONS} (
    completion_key, api10, well_completion_pool, pool_reported, source_id, production_month,
    report_vintage, source_manifest_id, derivation_id)
values (%(completion_key)s, %(api10)s, %(well_completion_pool)s, %(pool_reported)s,
        %(source_id)s, %(production_month)s, %(report_vintage)s, %(source_manifest_id)s,
        %(derivation_id)s)
on conflict do nothing
"""


def _decimal(value: Any) -> Decimal | None:
    text = "" if value is None else str(value).strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _integer(value: Any) -> int | None:
    text = "" if value is None else str(value).strip()
    try:
        return int(text)
    except ValueError:
        return None


def _value_hash(volume: Decimal | None, unit: str | None, days: int | None, semantics: str) -> str:
    return hash_payload(
        {
            "volume": volume,
            "unit": unit,
            "days_produced": days,
            "granularity": GRANULARITY,
            "null_semantics": semantics,
        }
    )


def _record(
    *,
    entity_type: str,
    entity_key: str,
    reporting_level: str,
    well_completion_pool: str | None,
    aggregation: str | None,
    api10: str,
    production_month: date,
    stream: str,
    volume: Decimal | None,
    unit: str,
    days: int | None,
) -> dict[str, Any]:
    semantics = classify_null_semantics(volume)
    return {
        "entity_type": entity_type,
        "entity_key": entity_key,
        "reporting_level": reporting_level,
        "well_completion_pool": well_completion_pool,
        "aggregation": aggregation,
        "api10": api10,
        "production_month": production_month,
        "stream": stream,
        # canonical.volume is NOT NULL, so an absent volume is carried as zero and the
        # null_semantics label is what distinguishes it from a reported zero.
        "volume": volume if volume is not None else Decimal(0),
        "unit": unit,
        "days_produced": days,
        "granularity": GRANULARITY,
        "value_hash": _value_hash(volume, unit, days, semantics),
        "null_semantics": semantics,
    }


def sum_over_pools(
    filings: Sequence[Mapping[str, Any]],
) -> tuple[Decimal | None, int | None]:
    """cr_co_production_grain_1: volume sums exactly, days take the maximum, never the sum.

    A well cannot produce more days than the month holds, and the completions are concurrent
    observations of one wellbore. The total is None only when every filing is absent, which is
    what makes `no_report` on the well row mean the well filed nothing rather than zero.
    """
    volumes = [filing["volume"] for filing in filings]
    reported = [volume for volume in volumes if volume is not None]
    days = [filing["days"] for filing in filings if filing["days"] is not None]
    total = sum(reported, Decimal(0)) if reported else None
    return total, (max(days) if days else None)


def completion_key(
    row: Mapping[str, Any], api10: str, spec: Mapping[str, Any]
) -> tuple[str, str]:
    """The entity key and the completion it identifies, both decided by the key rule.

    Returned as a pair because they are two different things: the key names the row in
    canonical, and the completion identifier names the thing inside the well that filed it.
    """
    separator = str(spec["separator"])
    columns = {
        "api10": api10,
        "api_sidetrack": str(row["apisidetrack"] or "").strip(),
        "formation_code": str(row["formationcode"] or "").strip(),
        "facility_id": str(row["facilityid"] or "").strip(),
    }
    parts = [str(columns[name]) for name in spec["source_cols"]]
    within = [str(columns[name]) for name in spec["source_cols"] if name != "api10"]
    return separator.join(parts), separator.join(within)


def promotion_records(
    staged: Sequence[Mapping[str, Any]],
    *,
    identity_spec: Mapping[str, Any],
    key_spec: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Pool rows, well rows and the completions beneath them, per API-10 month and stream."""
    groups: dict[tuple[str, date, str], list[dict[str, Any]]] = {}
    completions: dict[tuple[str, str, date], dict[str, Any]] = {}
    for row in staged:
        api10 = build_api10(
            {
                "api_county": row["apicountycode"],
                "api_seq": row["apisequencenumber"],
            },
            dict(identity_spec),
        )
        month = _month(row)
        if api10 is None or month is None:
            continue
        key, completion = completion_key(row, api10, key_spec)
        # Written for a one-completion month too, unlike North Dakota: ECMC files a formation
        # code on every row, so every well-month has a named completion and dropping it would
        # lose the only place pool_reported is carried before any vocabulary mapping.
        completions[(key, api10, month)] = {
            "completion_key": key,
            "api10": api10,
            "well_completion_pool": completion,
            "pool_reported": str(row["formationcode"] or "").strip() or None,
            "production_month": month,
        }
        for stream, column, unit in STREAMS:
            groups.setdefault((api10, month, stream), []).append(
                {
                    "entity_key": key,
                    "completion": completion,
                    "pool": str(row["formationcode"] or "").strip() or None,
                    "volume": _decimal(row[column]),
                    "days": _integer(row["daysproduced"]),
                    "unit": unit,
                }
            )

    pool_rows: list[dict[str, Any]] = []
    well_rows: list[dict[str, Any]] = []
    for (api10, month, stream), filings in groups.items():
        unit = filings[0]["unit"]
        if len(filings) == 1:
            # One completion is the well: relabelling it an aggregate would signal a
            # restatement that did not happen (cr_co_production_grain_1, ND's reason).
            filing = filings[0]
            well_rows.append(
                _record(
                    entity_type="well", entity_key=api10, reporting_level="well",
                    well_completion_pool=filing["completion"], aggregation=None, api10=api10,
                    production_month=month, stream=stream, volume=filing["volume"],
                    unit=unit, days=filing["days"],
                )
            )
            continue
        for filing in filings:
            pool_rows.append(
                _record(
                    entity_type="well_completion_pool", entity_key=filing["entity_key"],
                    reporting_level="well_completion_pool",
                    well_completion_pool=filing["completion"], aggregation=None, api10=api10,
                    production_month=month, stream=stream, volume=filing["volume"],
                    unit=unit, days=filing["days"],
                )
            )
        total, days = sum_over_pools(filings)
        well_rows.append(
            _record(
                entity_type=str(key_spec["aggregate_entity_type"]),
                entity_key=api10,
                reporting_level="well_completion_pool",
                well_completion_pool=None,
                aggregation=AGGREGATION,
                api10=api10,
                production_month=month,
                stream=stream,
                volume=total,
                unit=unit,
                days=days,
            )
        )
    return pool_rows, well_rows, list(completions.values())


def _month(row: Mapping[str, Any]) -> date | None:
    year = _integer(row["reportyear"])
    month = _integer(row["reportmonth"])
    if year is None or month is None or not 1 <= month <= 12:
        return None
    return date(year, month, 1)


def _staged(connection: psycopg.Connection, manifest_id: str) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(
            "select source_row_ordinal, apicountycode, apisequencenumber, apisidetrack,"
            "       formationcode, facilityid, reportyear, reportmonth, daysproduced,"
            "       oilproduced, gasproduced, waterproduced, accepteddate, revised"
            f"  from {STAGING_TABLE} where manifest_id = %s order by source_row_ordinal",
            (manifest_id,),
        )
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
        raise LookupError(f"no manifest for {SOURCE_ID}: run the production ingest first")
    return str(row[0]), row[1]


def promote_production(run: IngestRun) -> ProductionReport:
    """Promote the staged rolling file at completion grain, with the well row beside it."""
    connection = run.connection
    conform = load_rules(connection, source_id=SOURCE_ID, stage="conform", as_of=run.as_of)
    identity = rule_for_family(
        load_rules(
            connection, source_id=HEADER_SOURCE_ID, stage="conform", as_of=run.as_of
        ),
        IDENTITY_FAMILY,
    )
    key_rule = rule_for_family(conform, ENTITY_KEY_FAMILY)
    grain = rule_for_family(conform, GRAIN_FAMILY)
    liquids = rule_for_family(conform, LIQUIDS_FAMILY)
    manifest_id, vintage = _latest_manifest(connection)
    staged = _staged(connection, manifest_id)
    pool_rows, well_rows, completions = promotion_records(
        staged, identity_spec=identity.spec, key_spec=key_rule.spec
    )

    with derive(
        "canonical.promote",
        output=OutputSpec(
            store="postgis",
            dataset=CANONICAL_PRODUCTION,
            partition={"manifest_id": manifest_id},
        ),
        params={"source_id": SOURCE_ID, "streams": [stream for stream, _, _ in STREAMS]},
        inputs=[InputRef(kind="manifest", ref_id=manifest_id, as_of_vintage=vintage)],
        rules=[identity.rule_id, key_rule.rule_id, grain.rule_id, liquids.rule_id],
    ) as promotion:
        promotion.set_rows(len(pool_rows) + len(well_rows))
        promotion.set_output_hash(
            hash_payload(
                {
                    "pool_rows": len(pool_rows),
                    "well_rows": len(well_rows),
                    "manifest_id": manifest_id,
                }
            )
        )

    written = {
        "source_id": SOURCE_ID,
        "report_vintage": vintage,
        "source_manifest_id": manifest_id,
        "derivation_id": promotion.derivation_id,
    }
    with connection.cursor() as cursor:
        cursor.executemany(
            _INSERT_CANONICAL, [{**row, **written} for row in (*pool_rows, *well_rows)]
        )
        cursor.executemany(
            _INSERT_COMPLETION, [{**row, **written} for row in completions]
        )
    return ProductionReport(
        manifest_id=manifest_id,
        rows_read=len(staged),
        pool_rows=len(pool_rows),
        well_rows=len(well_rows),
        aggregate_rows=sum(1 for row in well_rows if row["aggregation"] == AGGREGATION),
        completions=len(completions),
        derivation_id=promotion.derivation_id,
    )


def run_production(
    connection: psycopg.Connection,
    *,
    env_id: str | None = None,
    code_version: str | None = None,
) -> ProductionReport:
    environment = resolve_environment(connection, env_id=env_id, code_version=code_version)
    with open_ingest_run(connection, source_id=SOURCE_ID, environment=environment) as run:
        return promote_production(run)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Promote the staged ECMC production file into canonical."
    )
    add_dsn_argument(parser)
    parser.add_argument("--env-id", default=None)
    parser.add_argument("--code-version", default=None)
    arguments = parser.parse_args(argv)
    arguments.dsn = resolve_dsn(arguments.dsn)

    with durable_fetch_attempts(arguments.dsn), psycopg.connect(arguments.dsn) as connection:
        report = run_production(
            connection, env_id=arguments.env_id, code_version=arguments.code_version
        )
        connection.commit()
    print(json.dumps(report.to_dict(), sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
