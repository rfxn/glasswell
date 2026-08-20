"""ND monthly production: the free NDIC MPR path, staged faithfully and promoted under rules.

The sheet, the epoch, the identity slice, the promoted stream vocabulary and the units all come
from `lineage.conformance_rules` — this module holds no mapping literal of its own (SB-07 §6.3).
"""

from __future__ import annotations

import argparse
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import openpyxl
import polars as pl
import psycopg

from glasswell.ingest.base import IngestRun, open_ingest_run
from glasswell.lineage.audit import emit
from glasswell.lineage.capture import derive
from glasswell.lineage.conformance import QuarantineBatch, apply_rules, load_rules
from glasswell.lineage.fetch import fetch_raw
from glasswell.lineage.models import ConformanceRule, InputRef, OutputSpec
from glasswell.lineage.quarantine import quarantine
from glasswell.lineage.serialization import hash_payload
from glasswell.lineage.vintages import open_vintage

__rule_version__ = "1"

SOURCE_ID = "nd_mpr_xlsx"
STAGING_TABLE = "staging.nd_mpr_oil"
STREAM_TABLE = "nd_stream_map"
URL_TEMPLATE = "https://www.dmr.nd.gov/oilgas/mpr/{year:04d}_{month:02d}.xlsx"
MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
EXCEL_EPOCH = date(1899, 12, 30)
GRANULARITY = "well_observed"

FORMAT_RULE = "cr_nd_mpr_format_1"
IDENTITY_RULE = "cr_nd_api_identity_1"
MONTH_RULE = "cr_nd_month_convention_1"
UNITS_RULE = "cr_nd_units_1"

# The reason vocabulary is read from the CHECK (migration 011), never hardcoded. A rule naming
# a code the CHECK does not admit still degrades rather than raising, keeping its rule_id.
UNREGISTERED_REASON = "unknown_vocab"
IDENTITY_REASON = "parse_error"
COLLISION_REASON = "key_collision"

_COLLISION_RANK = "__glasswell_collision_rank"

_ISO_DATE_RE = re.compile(r"\A\d{4}-\d{2}-\d{2}")
_NON_DIGITS_RE = re.compile(r"\D")
_SNAKE_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_REASON_LITERAL_RE = re.compile(r"'([a-z_]+)'::text")


@dataclass(frozen=True, slots=True)
class IngestReport:
    manifest_id: str
    source_key: str
    report_vintage: date
    unchanged: bool
    staged_rows: int = 0
    rows_examined: int = 0
    rows_appended: int = 0
    quarantined: Mapping[str, int] = field(default_factory=dict)
    restatement_summary: Mapping[str, int] = field(default_factory=dict)
    promote_derivation_id: str | None = None


def liquids_basis() -> str:
    """cr_nd_liquids_policy_1: ND liquids are oil plus condensate and the basis travels along."""
    return "oil+condensate"


def classify_null_semantics(volume: Decimal | None, *, confidential: bool = False) -> str:
    """cr_nd_null_semantics_1: absent, zero and withheld are three facts, never collapsed."""
    if volume is None:
        return "withheld" if confidential else "no_report"
    return "reported_zero" if volume == 0 else "reported"


def excel_serial_to_month(serial: float | int | str, *, epoch: date = EXCEL_EPOCH) -> date:
    """ReportDate is valid time — the month produced, never the vintage it was learned in."""
    return (epoch + timedelta(days=int(float(serial)))).replace(day=1)


def month_from_cell(value: object, *, epoch: date = EXCEL_EPOCH) -> date | None:
    if value is None or value == "":
        return None
    text = str(value)
    # openpyxl decodes a date-formatted serial before the reader sees it; both forms are real.
    if _ISO_DATE_RE.match(text):
        return date.fromisoformat(text[:10]).replace(day=1)
    try:
        return excel_serial_to_month(text, epoch=epoch)
    except ValueError:
        return None


def api10_from_api14(
    value: object, *, digits: int = 14, api10_slice: Sequence[int] = (0, 10)
) -> str:
    """API-10 is the first ten digits of API_WELLNO; digits 13-14 are convention, not identity."""
    text = _NON_DIGITS_RE.sub("", str(value))
    if len(text) != digits:
        raise ValueError(f"{value!r} is not a {digits}-digit API number")
    start, stop = api10_slice
    return text[start:stop]


def _api10_or_none(value: object, **options: Any) -> str | None:
    try:
        return api10_from_api14(value, **options)
    except (TypeError, ValueError):
        return None


def _snake(name: object) -> str:
    return _SNAKE_RE.sub("_", str(name)).lower()


def _cell_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def read_header(path: Path | str, *, sheet: str) -> list[str]:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        header = next(workbook[sheet].iter_rows(min_row=1, max_row=1, values_only=True))
    finally:
        workbook.close()
    return [str(name) for name in header]


def parse_workbook(path: Path | str, *, sheet: str) -> pl.DataFrame:
    """Every cell as text: staging is source-faithful and holds no opinions (§3.4.2)."""
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        rows = workbook[sheet].iter_rows(values_only=True)
        header = [_snake(name) for name in next(rows)]
        records = [
            dict(zip(header, (_cell_text(cell) for cell in row), strict=False)) for row in rows
        ]
    finally:
        workbook.close()
    frame = pl.DataFrame(records, schema=dict.fromkeys(header, pl.String))
    return frame.with_row_index("source_row_ordinal", offset=1)


def _rule(rules: Sequence[ConformanceRule], rule_id: str) -> ConformanceRule:
    for rule in rules:
        if rule.rule_id == rule_id:
            return rule
    raise LookupError(f"conformance rule {rule_id} is not seeded for {SOURCE_ID}")


def _stream_labels(connection: psycopg.Connection) -> list[str]:
    """The reported column names come from the registry, so a new disposition needs no code."""
    with connection.cursor() as cursor:
        cursor.execute(f"select stream_raw from lineage.{STREAM_TABLE} order by stream_raw")
        return [row[0] for row in cursor.fetchall()]


def _reason_vocabulary(connection: psycopg.Connection) -> frozenset[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            "select pg_get_constraintdef(c.oid) from pg_constraint c"
            "  join pg_class t on t.oid = c.conrelid"
            "  join pg_namespace n on n.oid = t.relnamespace"
            " where n.nspname = 'lineage' and t.relname = 'quarantine_rows'"
            "   and c.contype = 'c' and pg_get_constraintdef(c.oid) like '%%reason_code%%'"
        )
        row = cursor.fetchone()
    return frozenset(_REASON_LITERAL_RE.findall(row[0])) if row else frozenset()


def _staging_columns(connection: psycopg.Connection) -> set[str]:
    schema, _, table = STAGING_TABLE.partition(".")
    with connection.cursor() as cursor:
        cursor.execute(
            "select column_name from information_schema.columns"
            " where table_schema = %s and table_name = %s",
            (schema, table),
        )
        return {row[0] for row in cursor.fetchall()}


def load_staging(connection: psycopg.Connection, frame: pl.DataFrame, *, manifest_id: str) -> int:
    unknown = sorted(set(frame.columns) - _staging_columns(connection))
    if unknown:
        raise ValueError(f"{STAGING_TABLE} has no column for {unknown}; the upstream header moved")
    columns = ["manifest_id", *frame.columns]
    statement = (
        f"insert into {STAGING_TABLE} ({', '.join(f'\"{name}\"' for name in columns)})"
        f" values ({', '.join(['%s'] * len(columns))})"
    )
    with connection.cursor() as cursor:
        cursor.executemany(statement, [(manifest_id, *row) for row in frame.iter_rows()])
    return frame.height


def _typed_frame(
    staged: pl.DataFrame, *, rules: Sequence[ConformanceRule], measures: Sequence[str]
) -> pl.DataFrame:
    identity = _rule(rules, IDENTITY_RULE).spec
    epoch = date.fromisoformat(str(_rule(rules, MONTH_RULE).spec["epoch"]))
    options = {
        "digits": int(str(identity["digits"])),
        "api10_slice": tuple(identity["api10_slice"]),
    }
    return staged.with_columns(
        pl.col("api_wellno")
        .map_elements(lambda value: _api10_or_none(value, **options), return_dtype=pl.String)
        .alias("api10"),
        pl.col("report_date")
        .map_elements(lambda value: month_from_cell(value, epoch=epoch), return_dtype=pl.Date)
        .alias("production_month"),
        pl.col("days").cast(pl.Int64, strict=False),
        *[pl.col(name).cast(pl.Decimal(18, 3), strict=False) for name in measures],
    )


def _long_frame(frame: pl.DataFrame, labels: Sequence[str]) -> pl.DataFrame:
    """One row per reported column, carrying the source label the vocabulary rule maps."""
    return pl.concat(
        [frame.with_columns(pl.lit(label).alias("stream_raw")) for label in labels], how="vertical"
    )


def _with_measured_value(
    frame: pl.DataFrame, *, labels: Sequence[str], units: Mapping[str, Any]
) -> pl.DataFrame:
    volume = pl.lit(None, dtype=pl.Decimal(18, 3))
    unit = pl.lit(None, dtype=pl.String)
    for label in labels:
        column = _snake(label)
        if column not in units:
            continue
        matches = pl.col("stream_raw") == label
        volume = pl.when(matches).then(pl.col(column)).otherwise(volume)
        unit = pl.when(matches).then(pl.lit(str(units[column]))).otherwise(unit)
    return frame.with_columns(volume.alias("volume"), unit.alias("unit"))


def split_key_collisions(frame: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """The MPR's grain is (api14, pool, month); canonical's is (api10, month, stream).

    A well completed in two pools files two rows, so the natural key collides on real data. The
    first row by source ordinal promotes and the rest are returned for quarantine — an unlegislated
    sum across pools is exactly the kind of silent aggregation SB-07 §6 exists to prevent.
    """
    ranked = frame.with_columns(
        pl.col("source_row_ordinal")
        .rank("ordinal")
        .over(["api10", "production_month", "stream_canonical"])
        .alias(_COLLISION_RANK)
    )
    kept = ranked.filter(pl.col(_COLLISION_RANK) == 1).drop(_COLLISION_RANK)
    collided = ranked.filter(pl.col(_COLLISION_RANK) > 1).drop(_COLLISION_RANK)
    return kept, collided


def _promotion_records(frame: pl.DataFrame) -> list[dict[str, Any]]:
    records = []
    for row in frame.iter_rows(named=True):
        volume = row["volume"]
        semantics = classify_null_semantics(volume)
        payload = {
            "volume": volume,
            "unit": row["unit"],
            "days_produced": row["days"],
            "granularity": GRANULARITY,
            "null_semantics": semantics,
        }
        records.append(
            {
                "api10": row["api10"],
                "production_month": row["production_month"],
                "stream": row["stream_canonical"],
                # canonical.volume is NOT NULL, so an absent volume is carried as zero and the
                # null_semantics label is what distinguishes it from a reported zero.
                "volume": volume if volume is not None else Decimal(0),
                "unit": row["unit"],
                "days_produced": row["days"],
                "granularity": GRANULARITY,
                "value_hash": hash_payload(payload),
                "null_semantics": semantics,
            }
        )
    return records


def _current_heads(connection: psycopg.Connection) -> dict[tuple[str, date, str], str]:
    with connection.cursor() as cursor:
        cursor.execute(
            "select api10, production_month, stream, value_hash"
            " from canonical.production_monthly_latest where source_id = %s",
            (SOURCE_ID,),
        )
        return {(row[0], row[1], row[2]): row[3] for row in cursor.fetchall()}


_INSERT_CANONICAL = """
insert into canonical.production_monthly (
    api10, production_month, stream, source_id, report_vintage, volume, unit, days_produced,
    granularity, value_hash, source_manifest_id, derivation_id, null_semantics)
values (%(api10)s, %(production_month)s, %(stream)s, %(source_id)s, %(report_vintage)s,
        %(volume)s, %(unit)s, %(days_produced)s, %(granularity)s, %(value_hash)s,
        %(source_manifest_id)s, %(derivation_id)s, %(null_semantics)s)
on conflict do nothing
"""


def _route_quarantine(
    run: IngestRun,
    batches: Sequence[QuarantineBatch],
    *,
    stage: str,
    manifest_id: str,
    vocabulary: frozenset[str],
    counts: dict[str, int],
) -> None:
    for batch in batches:
        reason = batch.reason_code if batch.reason_code in vocabulary else UNREGISTERED_REASON
        result = quarantine(
            run.connection,
            batch.frame,
            reason_code=reason,
            manifest_id=manifest_id,
            source_id=SOURCE_ID,
            staging_table=STAGING_TABLE,
            stage=stage,
            seen_at=run.session.clock.now(),
            rule_id=batch.rule_id,
            correlation_id=run.session.correlation_id,
        )
        counts[reason] = counts.get(reason, 0) + result.opened + result.reoccurred


def ingest_month(
    run: IngestRun,
    *,
    year: int,
    month: int,
    url: str | None = None,
    client: httpx.Client | None = None,
) -> IngestReport:
    """Fetch one MPR month, stage it, and promote it under the seeded rules."""
    connection = run.connection
    source_key = f"{year:04d}_{month:02d}.xlsx"
    fetched = fetch_raw(
        connection,
        SOURCE_ID,
        source_key,
        url=url or URL_TEMPLATE.format(year=year, month=month),
        raw_root=run.raw_root,
        client=client,
        media_type=MEDIA_TYPE,
    )
    manifest = fetched.manifest
    if fetched.unchanged and _already_staged(connection, manifest.manifest_id):
        return IngestReport(
            manifest_id=manifest.manifest_id,
            source_key=source_key,
            report_vintage=run.as_of,
            unchanged=True,
        )

    parse_rules = load_rules(connection, source_id=SOURCE_ID, stage="parse", as_of=run.as_of)
    conform_rules = [
        rule
        for rule in load_rules(connection, source_id=SOURCE_ID, stage="conform", as_of=run.as_of)
        # The code_ref executor is unimplemented in this slice: those two rows are policy
        # declarations this module implements directly (liquids_basis, classify_null_semantics).
        if rule.rule_kind != "code_ref"
    ]
    sheet = str(_rule(parse_rules, FORMAT_RULE).spec["sheet"])
    labels = _stream_labels(connection)
    measures = [_snake(label) for label in labels]
    vocabulary = _reason_vocabulary(connection)
    quarantined: dict[str, int] = {}
    manifest_input = InputRef(
        kind="manifest",
        ref_id=manifest.manifest_id,
        role="primary",
        as_of_vintage=manifest.fetch_vintage,
    )
    partition = {"month": f"{year:04d}-{month:02d}", "manifest_id": manifest.manifest_id}

    with derive(
        "canonical.promote",
        output=OutputSpec(
            store="postgres", dataset="canonical.production_monthly", partition=partition
        ),
        params={"source_key": source_key, "liquids_basis": liquids_basis()},
        inputs=[manifest_input],
    ) as promotion:
        with derive(
            "stage.parse",
            output=OutputSpec(store="postgres", dataset=STAGING_TABLE, partition=partition),
            params={"sheet": sheet, "source_key": source_key},
            inputs=[manifest_input],
        ) as parsing:
            staged = parse_workbook(fetched.payload_path, sheet=sheet)
            parsed = apply_rules(staged, parse_rules)
            _route_quarantine(
                run,
                parsed.quarantined,
                stage="parse",
                manifest_id=manifest.manifest_id,
                vocabulary=vocabulary,
                counts=quarantined,
            )
            staged_rows = load_staging(
                connection, parsed.frame, manifest_id=manifest.manifest_id
            )
            for rule_id in parsed.applied_rule_ids:
                parsing.add_rule(rule_id, applied_rows=staged_rows)
            parsing.set_rows(staged_rows)
            parsing.set_output_hash(hash_payload(parsed.frame.rows()))
            emit(
                connection,
                "staging.load_completed",
                subject_type="manifest",
                subject_id=manifest.manifest_id,
                payload={"table": STAGING_TABLE, "rows": staged_rows},
                correlation_id=run.session.correlation_id,
                occurred_at=run.session.clock.now(),
            )

        typed = _typed_frame(parsed.frame, rules=parse_rules, measures=measures)
        identified = typed.filter(pl.col("api10").is_not_null())
        unidentified = typed.filter(pl.col("api10").is_null())
        if not unidentified.is_empty():
            _route_quarantine(
                run,
                [
                    QuarantineBatch(
                        reason_code=IDENTITY_REASON, rule_id=IDENTITY_RULE, frame=unidentified
                    )
                ],
                stage="parse",
                manifest_id=manifest.manifest_id,
                vocabulary=vocabulary,
                counts=quarantined,
            )

        validated = apply_rules(
            identified,
            load_rules(connection, source_id=SOURCE_ID, stage="validate", as_of=run.as_of),
        )
        _route_quarantine(
            run,
            validated.quarantined,
            stage="validate",
            manifest_id=manifest.manifest_id,
            vocabulary=vocabulary,
            counts=quarantined,
        )

        conformed = apply_rules(_long_frame(validated.frame, labels), conform_rules)
        _route_quarantine(
            run,
            conformed.quarantined,
            stage="conform",
            manifest_id=manifest.manifest_id,
            vocabulary=vocabulary,
            counts=quarantined,
        )

        units = _rule(conform_rules, UNITS_RULE).spec["units"]
        promotable, collided = split_key_collisions(
            _with_measured_value(conformed.frame, labels=labels, units=units)
        )
        if not collided.is_empty():
            _route_quarantine(
                run,
                [
                    QuarantineBatch(
                        reason_code=COLLISION_REASON, rule_id=IDENTITY_RULE, frame=collided
                    )
                ],
                stage="conform",
                manifest_id=manifest.manifest_id,
                vocabulary=vocabulary,
                counts=quarantined,
            )
        records = _promotion_records(promotable)
        heads = _current_heads(connection)
        appended = []
        restatement: dict[str, int] = {}
        for record in records:
            key = (record["api10"], record["production_month"], record["stream"])
            previous = heads.get(key)
            if previous == record["value_hash"]:
                continue
            appended.append(record)
            if previous is not None:
                month_key = record["production_month"].isoformat()
                restatement[month_key] = restatement.get(month_key, 0) + 1

        for rule_id in (*validated.applied_rule_ids, *conformed.applied_rule_ids):
            promotion.add_rule(rule_id, applied_rows=len(records))
        promotion.set_rows(len(appended))
        promotion.set_output_hash(hash_payload([record["value_hash"] for record in appended]))

    months = sorted({record["production_month"].isoformat() for record in records})
    _append_canonical(
        connection,
        appended,
        manifest_id=manifest.manifest_id,
        derivation_id=promotion.derivation_id,
        report_vintage=run.as_of,
    )
    open_vintage(
        connection,
        source_id=SOURCE_ID,
        vintage_date=run.as_of,
        manifest_ids=[manifest.manifest_id],
        opened_at=run.session.clock.now(),
        promotion_derivation_id=promotion.derivation_id,
        rows_examined=len(records),
        rows_appended=len(appended),
        months_touched=months,
        restatement_summary=restatement,
    )
    payload = {
        "manifest_id": manifest.manifest_id,
        "rows_examined": len(records),
        "rows_appended": len(appended),
        "months_touched": months,
        "quarantined": quarantined,
        "liquids_basis": liquids_basis(),
    }
    emit(
        connection,
        "canonical.promotion_completed",
        subject_type="vintage",
        subject_id=f"vin_{SOURCE_ID}_{run.as_of.isoformat()}",
        payload=payload,
        correlation_id=run.session.correlation_id,
        occurred_at=run.session.clock.now(),
    )
    if restatement:
        emit(
            connection,
            "canonical.restatement_detected",
            subject_type="vintage",
            subject_id=f"vin_{SOURCE_ID}_{run.as_of.isoformat()}",
            payload={**payload, "restatement_summary": restatement},
            correlation_id=run.session.correlation_id,
            occurred_at=run.session.clock.now(),
        )
    return IngestReport(
        manifest_id=manifest.manifest_id,
        source_key=source_key,
        report_vintage=run.as_of,
        unchanged=fetched.unchanged,
        staged_rows=staged_rows,
        rows_examined=len(records),
        rows_appended=len(appended),
        quarantined=quarantined,
        restatement_summary=restatement,
        promote_derivation_id=promotion.derivation_id,
    )


def _already_staged(connection: psycopg.Connection, manifest_id: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            f"select 1 from {STAGING_TABLE} where manifest_id = %s limit 1", (manifest_id,)
        )
        return cursor.fetchone() is not None


def _append_canonical(
    connection: psycopg.Connection,
    records: Sequence[Mapping[str, Any]],
    *,
    manifest_id: str,
    derivation_id: str,
    report_vintage: date,
) -> None:
    """Change-only append (SB-07 §3.2): the PK carries the vintage, so the head check is here."""
    if not records:
        return
    with connection.cursor() as cursor:
        cursor.executemany(
            _INSERT_CANONICAL,
            [
                {
                    **record,
                    "source_id": SOURCE_ID,
                    "report_vintage": report_vintage,
                    "source_manifest_id": manifest_id,
                    "derivation_id": derivation_id,
                }
                for record in records
            ],
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest one ND monthly production report.")
    parser.add_argument("--month", required=True, help="production month as YYYY-MM")
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--raw-root")
    arguments = parser.parse_args(argv)
    year, _, month = arguments.month.partition("-")

    with psycopg.connect(arguments.dsn) as connection:
        with open_ingest_run(
            connection, source_id=SOURCE_ID, raw_root=arguments.raw_root
        ) as run:
            report = ingest_month(run, year=int(year), month=int(month))
        connection.commit()
    print(
        f"{report.source_key}: manifest {report.manifest_id}, staged {report.staged_rows},"
        f" appended {report.rows_appended}, quarantined {report.quarantined}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
