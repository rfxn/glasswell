"""MBOGC monthly production: both published grains, staged faithfully and promoted under rules.

One archive carries the well grain and the lease (PRU) grain, so one fetch registers one
manifest whose member inventory hashes both. The sheet, the identity slice, the month
convention, the stream vocabulary and the units all come from `lineage.conformance_rules`;
this module holds no mapping literal of its own beyond the artifact's own path (SB-07 §6.3).

The well member is 573 MB uncompressed against a host with far less free space, so it is never
extracted: staging streams from the zip member, and promotion then reads staging one production
month at a time rather than materialising 5.8 million rows.
"""

from __future__ import annotations

import argparse
import calendar
import zipfile
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx
import polars as pl
import psycopg

from glasswell.db.dsn import add_dsn_argument, resolve_dsn
from glasswell.identity import api10_identity
from glasswell.ingest.base import IngestRun, open_ingest_run, record_vintage_day
from glasswell.ingest.promote import (
    append_canonical,
    classify_null_semantics,
    current_heads,
    record,
    reject_same_vintage_divergence,
    unchanged_removed,
)
from glasswell.lineage.audit import emit
from glasswell.lineage.capture import derive
from glasswell.lineage.conformance import (
    QuarantineBatch,
    apply_rules,
    load_rules,
    rule_for_family,
)
from glasswell.lineage.fetch import fetch_raw
from glasswell.lineage.fetch_attempts import durable_fetch_attempts
from glasswell.lineage.models import ConformanceRule, InputRef, OutputSpec
from glasswell.lineage.quarantine import quarantine
from glasswell.lineage.serialization import hash_payload

__rule_version__ = "1"

SOURCE_ID = "mt_bogc_well_production"
PRU_SOURCE_ID = "mt_bogc_pru_production"
ARCHIVE_URL = (
    "https://bogfiles.dnrc.mt.gov/Reporting/Production/Historical/MT_Historical_Production.zip"
)
ARCHIVE_KEY = "MT_Historical_Production.zip"
MEDIA_TYPE = "application/zip"

WELL_MEMBER = "MT_HistoricalWellProduction.tab"
PRU_MEMBER = "MT_HistoricalPRUProduction.tab"
WELL_STAGING = "staging.mt_bogc_well"
PRU_STAGING = "staging.mt_bogc_pru"

WELL_FORMAT_RULE = "cr_mt_well_format_1"
PRU_FORMAT_RULE = "cr_mt_pru_format_1"
IDENTITY_FAMILY = "cr_mt_api_identity"
MONTH_FAMILY = "cr_mt_month_convention"
PRU_MONTH_FAMILY = "cr_mt_pru_month_convention"
UNITS_FAMILY = "cr_mt_units"
PRU_UNITS_FAMILY = "cr_mt_pru_units"
SENTINEL_FAMILY = "cr_mt_lease_unit_sentinel"

WELL_GRANULARITY = "well_observed"
PRU_GRANULARITY = "lease_reported"
# Canonical already names this token, and ST_FMTN_CD is Montana's pool label.
AGGREGATION = "sum_over_pools"

UNREGISTERED_REASON = "unknown_vocab"
IDENTITY_REASON = "parse_error"
COLLISION_REASON = "key_collision"

STAGE_BATCH_ROWS = 50_000


@dataclass(frozen=True, slots=True)
class GrainReport:
    member: str
    staged_rows: int = 0
    rows_examined: int = 0
    rows_appended: int = 0
    months_touched: tuple[str, ...] = ()
    quarantined: Mapping[str, int] = field(default_factory=dict)
    restatement_summary: Mapping[str, int] = field(default_factory=dict)
    promote_derivation_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class IngestReport:
    manifest_id: str
    source_key: str
    report_vintage: date
    unchanged: bool
    well: GrainReport | None = None
    pru: GrainReport | None = None


def liquids_basis() -> str:
    """cr_mt_liquids_policy_1: MBOGC publishes oil and condensate combined, and the basis
    travels with every figure derived from it."""
    return "oil+condensate"


def zip_inventory(path: Path) -> list[dict[str, Any]]:
    """Hash both decompressed members without materialising either beside the raw artifact."""
    import hashlib

    inventory: list[dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive:
        for member in sorted(archive.infolist(), key=lambda item: item.filename):
            digest = hashlib.sha256()
            size = 0
            with archive.open(member) as stream:
                for chunk in iter(lambda: stream.read(1 << 20), b""):
                    digest.update(chunk)
                    size += len(chunk)
            inventory.append(
                {
                    "member": member.filename,
                    "bytes": size,
                    "compressed_bytes": member.compress_size,
                    "sha256": digest.hexdigest(),
                }
            )
    return inventory


def month_from_report_date(value: str | None) -> date | None:
    """cr_mt_month_convention_1: Rpt_Date is an end-of-month stamp for the month produced."""
    if not value:
        return None
    parts = value.strip().split("/")
    if len(parts) != 3:
        return None
    try:
        month, _day, year = (int(part) for part in parts)
        return date(year, month, 1)
    except ValueError:
        return None


def is_end_of_month(value: str | None) -> bool:
    """The convention the rule asserts, so a source that stops honouring it is detectable."""
    if not value:
        return False
    parts = value.strip().split("/")
    if len(parts) != 3:
        return False
    try:
        month, day, year = (int(part) for part in parts)
        return day == calendar.monthrange(year, month)[1]
    except ValueError:
        return False


def _decimal(value: str | None) -> Decimal | None:
    if value is None or value.strip() == "":
        return None
    try:
        return Decimal(value.strip())
    except InvalidOperation:
        return None


def stream_member(
    archive_path: Path | str, member: str, *, columns: Sequence[str]
) -> Iterator[dict[str, str | None]]:
    """Yield one dict per data row straight from the zip member.

    Every value stays text: staging is source-faithful and holds no opinions (§3.4.2). A blank
    final line is end-of-file rather than a record (cr_mt_trailing_record_1).
    """
    with zipfile.ZipFile(archive_path) as bundle, bundle.open(member) as stream:
        header = stream.readline().decode("utf-8").rstrip("\r\n").split("\t")
        normalised = [name.strip().lower() for name in header]
        if normalised != list(columns):
            raise ValueError(
                f"{member} header moved: expected {list(columns)}, read {normalised}"
            )
        for line in stream:
            text = line.decode("utf-8", errors="replace").rstrip("\r\n")
            if not text:
                continue
            values = text.split("\t")
            if len(values) != len(normalised):
                # A short or long row cannot be keyed to columns; it is staged as a null row
                # under its ordinal so the ledger still holds it.
                yield dict.fromkeys(normalised, None)
                continue
            yield {
                name: (value if value != "" else None)
                for name, value in zip(normalised, values, strict=True)
            }


def _staging_columns(connection: psycopg.Connection, table: str) -> list[str]:
    schema, _, name = table.partition(".")
    with connection.cursor() as cursor:
        cursor.execute(
            "select column_name from information_schema.columns"
            " where table_schema = %s and table_name = %s"
            "   and column_name not in ('manifest_id', 'source_row_ordinal', 'ingested_at')"
            " order by ordinal_position",
            (schema, name),
        )
        return [row[0] for row in cursor.fetchall()]


def stage_member(
    connection: psycopg.Connection,
    archive_path: Path | str,
    *,
    member: str,
    table: str,
    manifest_id: str,
) -> int:
    """Stream the member into staging in batches; the whole file never sits in memory."""
    columns = _staging_columns(connection, table)
    quoted = ", ".join(f'"{name}"' for name in ("manifest_id", "source_row_ordinal", *columns))
    placeholders = ", ".join(["%s"] * (len(columns) + 2))
    statement = f"insert into {table} ({quoted}) values ({placeholders})"
    batch: list[tuple[Any, ...]] = []
    staged = 0
    with connection.cursor() as cursor:
        for ordinal, row in enumerate(stream_member(archive_path, member, columns=columns), 1):
            batch.append((manifest_id, ordinal, *(row[name] for name in columns)))
            if len(batch) >= STAGE_BATCH_ROWS:
                cursor.executemany(statement, batch)
                staged += len(batch)
                batch.clear()
        if batch:
            cursor.executemany(statement, batch)
            staged += len(batch)
    return staged


def already_staged(connection: psycopg.Connection, table: str, manifest_id: str) -> int:
    """Rows this manifest already staged. Re-fetching identical bytes must not re-stage them."""
    with connection.cursor() as cursor:
        cursor.execute(f"select count(*) from {table} where manifest_id = %s", (manifest_id,))
        return int(cursor.fetchone()[0])


def staged_months(connection: psycopg.Connection, table: str, manifest_id: str) -> list[str]:
    """The distinct production months this manifest staged, in order.

    Promotion is chunked on this rather than on the file, because the file is not sorted by
    month and a whole-file group-by would hold every row.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            f"select distinct substring(rpt_date from 7 for 4)"
            f" || '-' || substring(rpt_date from 1 for 2) as month"
            f"  from {table} where manifest_id = %s and rpt_date is not null"
            f" order by month",
            (manifest_id,),
        )
        return [row[0] for row in cursor.fetchall()]


def read_staged_month(
    connection: psycopg.Connection, table: str, manifest_id: str, month: str
) -> pl.DataFrame:
    """One month's staged rows, in the shape the parse stage handed on."""
    columns = _staging_columns(connection, table)
    selection = ", ".join(f'"{name}"' for name in ("source_row_ordinal", *columns))
    year, _, number = month.partition("-")
    with connection.cursor() as cursor:
        cursor.execute(
            f"select {selection} from {table}"
            f" where manifest_id = %s and substring(rpt_date from 7 for 4) = %s"
            f"   and substring(rpt_date from 1 for 2) = %s"
            f" order by source_row_ordinal",
            (manifest_id, year, number),
        )
        rows = cursor.fetchall()
    schema = {
        name: (pl.Int64 if name == "source_row_ordinal" else pl.String)
        for name in ("source_row_ordinal", *columns)
    }
    return pl.DataFrame(rows, schema=schema, orient="row")


def _rule(rules: Sequence[ConformanceRule], rule_id: str) -> ConformanceRule:
    for rule in rules:
        if rule.rule_id == rule_id:
            return rule
    raise LookupError(f"conformance rule {rule_id} is not seeded")


def _executable(rules: Sequence[ConformanceRule]) -> list[ConformanceRule]:
    """Drop the policy declarations this module implements directly.

    The code_ref executor is unimplemented: those rows state decisions (the liquids basis, the
    null semantics, the formation rollup, the basin scope) that live in this module's own code
    and are cited on the derivations it writes.
    """
    return [rule for rule in rules if rule.rule_kind != "code_ref"]


def _reason_vocabulary(connection: psycopg.Connection) -> frozenset[str]:
    import re

    with connection.cursor() as cursor:
        cursor.execute(
            "select pg_get_constraintdef(c.oid) from pg_constraint c"
            "  join pg_class t on t.oid = c.conrelid"
            "  join pg_namespace n on n.oid = t.relnamespace"
            " where n.nspname = 'lineage' and t.relname = 'quarantine_rows'"
            "   and c.contype = 'c' and pg_get_constraintdef(c.oid) like '%%reason_code%%'"
        )
        row = cursor.fetchone()
    return frozenset(re.findall(r"'([a-z_]+)'::text", row[0])) if row else frozenset()


def _route_quarantine(
    run: IngestRun,
    batches: Sequence[QuarantineBatch],
    *,
    stage: str,
    manifest_id: str,
    source_id: str,
    staging_table: str,
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
            source_id=source_id,
            staging_table=staging_table,
            stage=stage,
            seen_at=run.session.clock.now(),
            rule_id=batch.rule_id,
            correlation_id=run.session.correlation_id,
        )
        counts[reason] = counts.get(reason, 0) + result.opened + result.reoccurred


def _typed_well_frame(
    staged: pl.DataFrame, *, rules: Sequence[ConformanceRule], sentinel: str
) -> pl.DataFrame:
    identity = api10_identity(rule_for_family(rules, IDENTITY_FAMILY))
    return staged.with_columns(
        pl.col("api_wellno")
        .map_elements(identity.normalize, return_dtype=pl.String)
        .alias("api10"),
        pl.col("rpt_date")
        .map_elements(month_from_report_date, return_dtype=pl.Date)
        .alias("production_month"),
        pl.col("days_prod").cast(pl.Int64, strict=False),
        # cr_mt_lease_unit_sentinel_1: -999 means no lease unit and must never become a key.
        pl.when(pl.col("lease_unit") == sentinel)
        .then(None)
        .otherwise(pl.col("lease_unit"))
        .alias("lease_unit"),
        *[
            pl.col(name).cast(pl.Decimal(18, 3), strict=False)
            for name in ("bbls_oil_cond", "mcf_gas", "bbls_wtr")
        ],
    )


def _long_well_frame(frame: pl.DataFrame, labels: Sequence[str]) -> pl.DataFrame:
    return pl.concat(
        [frame.with_columns(pl.lit(label).alias("stream_raw")) for label in labels],
        how="vertical",
    )


def _with_measured_value(
    frame: pl.DataFrame, *, labels: Sequence[str], units: Mapping[str, Any]
) -> pl.DataFrame:
    volume = pl.lit(None, dtype=pl.Decimal(18, 3))
    unit = pl.lit(None, dtype=pl.String)
    for label in labels:
        column = label.lower()
        if column not in units:
            continue
        matches = pl.col("stream_raw") == label
        volume = pl.when(matches).then(pl.col(column)).otherwise(volume)
        unit = pl.when(matches).then(pl.lit(str(units[column]))).otherwise(unit)
    return frame.with_columns(volume.alias("volume"), unit.alias("unit"))


@dataclass(frozen=True, slots=True)
class FormationPromotion:
    records: list[dict[str, Any]]
    aggregates: list[dict[str, Any]]
    collided: pl.DataFrame


def formation_promotion_records(frame: pl.DataFrame) -> FormationPromotion:
    """cr_mt_formation_rollup_1: a well reporting two formations promotes as both plus a sum.

    One filing for a well-month-stream promotes as the well. Two or more promote as one row per
    formation plus a well row carrying their exact sum, disclosed as
    `aggregation = sum_over_formations`, so a consumer can tell a two-formation well from a
    one-formation well. Days take the maximum: a well producing 31 days from two formations
    produced for 31 days, not 62.
    """
    marker = "__mt_promotion_index"
    indexed = frame.with_row_index(marker).sort("source_row_ordinal")
    groups: dict[tuple[str, date, str], list[dict[str, Any]]] = {}
    for row in indexed.iter_rows(named=True):
        groups.setdefault(
            (row["api10"], row["production_month"], row["stream_canonical"]), []
        ).append(row)

    records: list[dict[str, Any]] = []
    aggregates: list[dict[str, Any]] = []
    collided: list[int] = []
    for (api10, month, stream), filings in groups.items():
        by_formation: dict[str, dict[str, Any]] = {}
        for filing in filings:
            key = filing["st_fmtn_cd"]
            if key is not None and key not in by_formation:
                by_formation[key] = filing
        decomposable = len(filings) > 1 and len(by_formation) == len(filings)
        if not decomposable:
            head, *rest = filings
            # Two filings under one formation code, or one with no code: the rule cannot say
            # which is the well, so the rest stay in the ledger rather than being resolved by
            # file ordinal. Measured zero such groups over the whole 2026-08-17 file.
            collided.extend(filing[marker] for filing in rest)
            records.append(
                record(
                    entity_type="well",
                    entity_key=api10,
                    reporting_level="well",
                    well_completion_pool=head["st_fmtn_cd"],
                    aggregation=None,
                    api10=api10,
                    production_month=month,
                    stream=stream,
                    volume=head["volume"],
                    unit=head["unit"],
                    days=head["days_prod"],
                    semantics=classify_null_semantics(head["volume"]),
                    granularity=WELL_GRANULARITY,
                )
            )
            continue
        for key, filing in by_formation.items():
            records.append(
                record(
                    entity_type="well_completion_pool",
                    entity_key=f"{api10}:{key}",
                    reporting_level="well_completion_pool",
                    well_completion_pool=key,
                    aggregation=None,
                    api10=api10,
                    production_month=month,
                    stream=stream,
                    volume=filing["volume"],
                    unit=filing["unit"],
                    days=filing["days_prod"],
                    semantics=classify_null_semantics(filing["volume"]),
                    granularity=WELL_GRANULARITY,
                )
            )
        filings_by_formation = list(by_formation.values())
        volumes = [filing["volume"] for filing in filings_by_formation]
        total = sum((volume for volume in volumes if volume is not None), Decimal(0))
        days = [f["days_prod"] for f in filings_by_formation if f["days_prod"] is not None]
        semantics = (
            "no_report"
            if all(volume is None for volume in volumes)
            else classify_null_semantics(total)
        )
        aggregates.append(
            record(
                entity_type="well",
                entity_key=api10,
                reporting_level="well_completion_pool",
                well_completion_pool=None,
                aggregation=AGGREGATION,
                api10=api10,
                production_month=month,
                stream=stream,
                volume=total,
                unit=next((f["unit"] for f in filings_by_formation if f["unit"]), None),
                days=max(days) if days else None,
                semantics=semantics,
                granularity=WELL_GRANULARITY,
            )
        )

    rejected = indexed.filter(pl.col(marker).is_in(collided)).drop(marker)
    return FormationPromotion(records=records, aggregates=aggregates, collided=rejected)


def _stream_labels(connection: psycopg.Connection, columns: Sequence[str]) -> list[str]:
    """The reported measure columns the registry promotes, scoped to this member's header."""
    with connection.cursor() as cursor:
        cursor.execute(
            "select stream_raw from lineage.mt_stream_promoted_map order by stream_raw"
        )
        promoted = [row[0] for row in cursor.fetchall()]
    lowered = {name.lower() for name in columns}
    return [label for label in promoted if label.lower() in lowered]


def promote_well_month(
    run: IngestRun,
    *,
    manifest: Any,
    month: str,
    parse_rules: Sequence[ConformanceRule],
    validate_rules: Sequence[ConformanceRule],
    conform_rules: Sequence[ConformanceRule],
    labels: Sequence[str],
    units: Mapping[str, Any],
    sentinel: str,
    vocabulary: frozenset[str],
    counts: dict[str, int],
) -> tuple[str, int, int, int]:
    """Promote one production month of the well grain. Returns the derivation and its counts."""
    connection = run.connection
    manifest_input = InputRef(
        kind="manifest",
        ref_id=manifest.manifest_id,
        role="primary",
        as_of_vintage=manifest.fetch_vintage,
    )
    with derive(
        "canonical.promote",
        output=OutputSpec(
            store="postgres",
            dataset="canonical.production_monthly",
            partition={"month": month, "manifest_id": manifest.manifest_id, "grain": "well"},
        ),
        params={"source_key": ARCHIVE_KEY, "member": WELL_MEMBER,
                "liquids_basis": liquids_basis(), "state_code": "25"},
        inputs=[manifest_input],
    ) as promotion:
        staged = read_staged_month(connection, WELL_STAGING, manifest.manifest_id, month)
        typed = _typed_well_frame(staged, rules=parse_rules, sentinel=sentinel)
        identified = typed.filter(
            pl.col("api10").is_not_null() & pl.col("production_month").is_not_null()
        )
        unidentified = typed.filter(
            pl.col("api10").is_null() | pl.col("production_month").is_null()
        )
        if not unidentified.is_empty():
            _route_quarantine(
                run,
                [
                    QuarantineBatch(
                        reason_code=IDENTITY_REASON,
                        rule_id=rule_for_family(parse_rules, IDENTITY_FAMILY).rule_id,
                        frame=unidentified,
                    )
                ],
                stage="parse",
                manifest_id=manifest.manifest_id,
                source_id=SOURCE_ID,
                staging_table=WELL_STAGING,
                vocabulary=vocabulary,
                counts=counts,
            )

        validated = apply_rules(identified, validate_rules)
        _route_quarantine(
            run, validated.quarantined, stage="validate", manifest_id=manifest.manifest_id,
            source_id=SOURCE_ID, staging_table=WELL_STAGING, vocabulary=vocabulary,
            counts=counts,
        )
        conformed = apply_rules(_long_well_frame(validated.frame, labels), conform_rules)
        _route_quarantine(
            run, conformed.quarantined, stage="conform", manifest_id=manifest.manifest_id,
            source_id=SOURCE_ID, staging_table=WELL_STAGING, vocabulary=vocabulary,
            counts=counts,
        )

        promoted = formation_promotion_records(
            _with_measured_value(conformed.frame, labels=labels, units=units)
        )
        if not promoted.collided.is_empty():
            _route_quarantine(
                run,
                [
                    QuarantineBatch(
                        reason_code=COLLISION_REASON,
                        rule_id="cr_mt_entity_key_1",
                        frame=promoted.collided,
                    )
                ],
                stage="conform",
                manifest_id=manifest.manifest_id,
                source_id=SOURCE_ID,
                staging_table=WELL_STAGING,
                vocabulary=vocabulary,
                counts=counts,
            )

        everything = [*promoted.records, *promoted.aggregates]
        heads = current_heads(connection, everything, source_id=SOURCE_ID)
        appended = reject_same_vintage_divergence(
            connection,
            unchanged_removed(promoted.records, heads),
            source_id=SOURCE_ID,
            report_vintage=run.as_of,
        )
        aggregates = reject_same_vintage_divergence(
            connection,
            unchanged_removed(promoted.aggregates, heads),
            source_id=SOURCE_ID,
            report_vintage=run.as_of,
        )
        restated = sum(1 for entry in appended + aggregates if heads.holds(entry))

        for application in (validated, conformed):
            for rule_id in application.applied_rule_ids:
                promotion.add_rule(rule_id, applied_rows=application.applied_rows[rule_id])
        promotion.set_rows(len(promoted.records))
        promotion.set_output_hash(
            hash_payload([entry["value_hash"] for entry in promoted.records])
        )

    append_canonical(
        connection, appended + aggregates, source_id=SOURCE_ID,
        manifest_id=manifest.manifest_id, derivation_id=promotion.derivation_id,
        report_vintage=run.as_of,
    )
    return promotion.derivation_id, len(everything), len(appended) + len(aggregates), restated


def promote_pru_month(
    run: IngestRun,
    *,
    manifest: Any,
    month: str,
    validate_rules: Sequence[ConformanceRule],
    conform_rules: Sequence[ConformanceRule],
    labels: Sequence[str],
    units: Mapping[str, Any],
    sentinel: str,
    vocabulary: frozenset[str],
    counts: dict[str, int],
) -> tuple[str, int, int, int]:
    """Promote one production month of the lease grain.

    Only the three production measures reach canonical; the fifteen disposition columns stay in
    staging under cr_mt_pru_stream_scope_1, because no canonical stream vocabulary admits them.
    """
    connection = run.connection
    manifest_input = InputRef(
        kind="manifest",
        ref_id=manifest.manifest_id,
        role="primary",
        as_of_vintage=manifest.fetch_vintage,
    )
    with derive(
        "canonical.promote",
        output=OutputSpec(
            store="postgres",
            dataset="canonical.production_monthly",
            partition={"month": month, "manifest_id": manifest.manifest_id, "grain": "lease"},
        ),
        params={"source_key": ARCHIVE_KEY, "member": PRU_MEMBER,
                "liquids_basis": liquids_basis(), "reporting_level": "lease",
                "allocation_required": False, "state_code": "25"},
        inputs=[manifest_input],
    ) as promotion:
        staged = read_staged_month(connection, PRU_STAGING, manifest.manifest_id, month)
        typed = staged.with_columns(
            pl.col("rpt_date")
            .map_elements(month_from_report_date, return_dtype=pl.Date)
            .alias("production_month"),
            pl.when(pl.col("lease_unit") == sentinel)
            .then(None)
            .otherwise(pl.col("lease_unit"))
            .alias("lease_unit"),
            *[
                pl.col(name).cast(pl.Decimal(18, 3), strict=False)
                for name in ("oil_prod", "gas_prod", "wtr_prod")
            ],
        )
        identified = typed.filter(
            pl.col("lease_unit").is_not_null() & pl.col("production_month").is_not_null()
        )
        unidentified = typed.filter(
            pl.col("lease_unit").is_null() | pl.col("production_month").is_null()
        )
        if not unidentified.is_empty():
            _route_quarantine(
                run,
                [QuarantineBatch(reason_code=IDENTITY_REASON,
                                 rule_id="cr_mt_pru_entity_key_1", frame=unidentified)],
                stage="parse", manifest_id=manifest.manifest_id, source_id=PRU_SOURCE_ID,
                staging_table=PRU_STAGING, vocabulary=vocabulary, counts=counts,
            )

        validated = apply_rules(identified, validate_rules)
        _route_quarantine(
            run, validated.quarantined, stage="validate", manifest_id=manifest.manifest_id,
            source_id=PRU_SOURCE_ID, staging_table=PRU_STAGING, vocabulary=vocabulary,
            counts=counts,
        )
        conformed = apply_rules(_long_well_frame(validated.frame, labels), conform_rules)
        _route_quarantine(
            run, conformed.quarantined, stage="conform", manifest_id=manifest.manifest_id,
            source_id=PRU_SOURCE_ID, staging_table=PRU_STAGING, vocabulary=vocabulary,
            counts=counts,
        )

        measured = _with_measured_value(conformed.frame, labels=labels, units=units)
        records = [
            record(
                entity_type="lease",
                entity_key=row["lease_unit"],
                reporting_level="lease",
                well_completion_pool=None,
                aggregation=None,
                api10=None,
                production_month=row["production_month"],
                stream=row["stream_canonical"],
                volume=row["volume"],
                unit=row["unit"],
                days=None,
                semantics=classify_null_semantics(row["volume"]),
                granularity=PRU_GRANULARITY,
            )
            for row in measured.iter_rows(named=True)
        ]
        heads = current_heads(connection, records, source_id=PRU_SOURCE_ID)
        appended = reject_same_vintage_divergence(
            connection, unchanged_removed(records, heads),
            source_id=PRU_SOURCE_ID, report_vintage=run.as_of,
        )
        restated = sum(1 for entry in appended if heads.holds(entry))

        for application in (validated, conformed):
            for rule_id in application.applied_rule_ids:
                promotion.add_rule(rule_id, applied_rows=application.applied_rows[rule_id])
        promotion.set_rows(len(records))
        promotion.set_output_hash(hash_payload([entry["value_hash"] for entry in records]))

    append_canonical(
        connection, appended, source_id=PRU_SOURCE_ID, manifest_id=manifest.manifest_id,
        derivation_id=promotion.derivation_id, report_vintage=run.as_of,
    )
    return promotion.derivation_id, len(records), len(appended), restated


def _grain_rules(
    connection: psycopg.Connection, source_id: str, as_of: date
) -> tuple[list[ConformanceRule], list[ConformanceRule], list[ConformanceRule]]:
    return (
        _executable(load_rules(connection, source_id=source_id, stage="parse", as_of=as_of)),
        _executable(load_rules(connection, source_id=source_id, stage="validate", as_of=as_of)),
        _executable(load_rules(connection, source_id=source_id, stage="conform", as_of=as_of)),
    )


def ingest_archive(
    run: IngestRun,
    *,
    url: str | None = None,
    client: httpx.Client | None = None,
    months: Sequence[str] | None = None,
) -> IngestReport:
    """Fetch the archive once, stage both members, then promote each grain month by month.

    `months` narrows the promotion to named production months; a full back-load promotes every
    month the manifest staged, accumulating onto one vintage-day ledger row.
    """
    connection = run.connection
    fetched = fetch_raw(
        connection,
        SOURCE_ID,
        ARCHIVE_KEY,
        url=url or ARCHIVE_URL,
        raw_root=run.raw_root,
        client=client,
        media_type=MEDIA_TYPE,
        decompressed_inventory=zip_inventory,
    )
    manifest = fetched.manifest
    payload = fetched.payload_path

    vocabulary = _reason_vocabulary(connection)
    well_counts: dict[str, int] = {}
    pru_counts: dict[str, int] = {}

    well_parse, well_validate, well_conform = _grain_rules(connection, SOURCE_ID, run.as_of)
    _, pru_validate, pru_conform = _grain_rules(connection, PRU_SOURCE_ID, run.as_of)
    sentinel = str(
        rule_for_family(well_parse, SENTINEL_FAMILY).spec.get("sentinel", "-999")
    )
    well_units = _rule(well_conform, "cr_mt_units_1").spec["units"]
    pru_units = _rule(pru_conform, "cr_mt_pru_units_1").spec["units"]

    # Staging is keyed (manifest_id, source_row_ordinal), so a re-run over identical bytes
    # would collide on every row. The bytes were already parsed under the parse-stage rules
    # and that is a historical record, not something to redo.
    well_staged = already_staged(connection, WELL_STAGING, manifest.manifest_id)
    if not well_staged:
        well_staged = stage_member(
            connection, payload, member=WELL_MEMBER, table=WELL_STAGING,
            manifest_id=manifest.manifest_id,
        )
    pru_staged = already_staged(connection, PRU_STAGING, manifest.manifest_id)
    if not pru_staged:
        pru_staged = stage_member(
            connection, payload, member=PRU_MEMBER, table=PRU_STAGING,
            manifest_id=manifest.manifest_id,
        )
    emit(
        connection,
        "staging.load_completed",
        subject_type="manifest",
        subject_id=manifest.manifest_id,
        payload={WELL_STAGING: well_staged, PRU_STAGING: pru_staged},
        correlation_id=run.session.correlation_id,
        occurred_at=run.session.clock.now(),
    )

    well_labels = _stream_labels(connection, _staging_columns(connection, WELL_STAGING))
    pru_labels = _stream_labels(connection, _staging_columns(connection, PRU_STAGING))

    well = _promote_grain(
        run, manifest=manifest, table=WELL_STAGING, months=months,
        promote=lambda month: promote_well_month(
            run, manifest=manifest, month=month, parse_rules=well_parse,
            validate_rules=well_validate, conform_rules=well_conform, labels=well_labels,
            units=well_units, sentinel=sentinel, vocabulary=vocabulary, counts=well_counts,
        ),
        member=WELL_MEMBER, staged=well_staged, counts=well_counts,
    )
    pru = _promote_grain(
        run, manifest=manifest, table=PRU_STAGING, months=months,
        promote=lambda month: promote_pru_month(
            run, manifest=manifest, month=month, validate_rules=pru_validate,
            conform_rules=pru_conform, labels=pru_labels, units=pru_units, sentinel=sentinel,
            vocabulary=vocabulary, counts=pru_counts,
        ),
        member=PRU_MEMBER, staged=pru_staged, counts=pru_counts,
    )

    for source_id, grain in ((SOURCE_ID, well), (PRU_SOURCE_ID, pru)):
        record_vintage_day(
            connection,
            source_id=source_id,
            vintage_date=run.as_of,
            manifest_ids=[manifest.manifest_id],
            opened_at=run.session.clock.now(),
            promotion_derivation_id=(
                grain.promote_derivation_ids[-1] if grain.promote_derivation_ids else None
            ),
            rows_examined=grain.rows_examined,
            rows_appended=grain.rows_appended,
            months_touched=list(grain.months_touched),
            restatement_summary=dict(grain.restatement_summary),
        )
    return IngestReport(
        manifest_id=manifest.manifest_id,
        source_key=ARCHIVE_KEY,
        report_vintage=run.as_of,
        unchanged=fetched.unchanged,
        well=well,
        pru=pru,
    )


def _promote_grain(
    run: IngestRun,
    *,
    manifest: Any,
    table: str,
    months: Sequence[str] | None,
    promote: Any,
    member: str,
    staged: int,
    counts: dict[str, int],
) -> GrainReport:
    available = staged_months(run.connection, table, manifest.manifest_id)
    selected = [month for month in available if months is None or month in months]
    derivations: list[str] = []
    examined = appended = 0
    restatement: dict[str, int] = {}
    for month in selected:
        derivation_id, month_examined, month_appended, restated = promote(month)
        derivations.append(derivation_id)
        examined += month_examined
        appended += month_appended
        if restated:
            restatement[month] = restated
    return GrainReport(
        member=member,
        staged_rows=staged,
        rows_examined=examined,
        rows_appended=appended,
        months_touched=tuple(selected),
        quarantined=dict(counts),
        restatement_summary=restatement,
        promote_derivation_ids=tuple(derivations),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ingest the MBOGC historical production archive, both grains."
    )
    add_dsn_argument(parser)
    parser.add_argument("--raw-root")
    parser.add_argument(
        "--month",
        action="append",
        help="promote only this production month as YYYY-MM; repeatable",
    )
    arguments = parser.parse_args(argv)
    arguments.dsn = resolve_dsn(arguments.dsn)

    with durable_fetch_attempts(arguments.dsn), psycopg.connect(arguments.dsn) as connection:
        with open_ingest_run(
            connection, source_id=SOURCE_ID, raw_root=arguments.raw_root
        ) as run:
            report = ingest_archive(run, months=arguments.month)
        connection.commit()
    for grain in (report.well, report.pru):
        if grain is None:
            continue
        print(
            f"{grain.member}: staged {grain.staged_rows}, months {len(grain.months_touched)},"
            f" appended {grain.rows_appended}, quarantined {dict(grain.quarantined)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
