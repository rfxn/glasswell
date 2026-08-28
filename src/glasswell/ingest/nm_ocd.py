"""New Mexico OCD: one polite pull of the nine in-scope tables, then staging that is verbatim.

The FTP publishes undated per-table zips and overwrites them nightly, so the retrieval vintage
is glasswell's own stamp and the `source_key` is the constant filename — a vintage-stamped key
would start a fresh supersession chain on every pull. The layout comes from the registry, the
host from the pin: this module holds no mapping literal beyond the address SB-01 §1.2 requires
a human to change.

Staging is streamed out of the zip member, never extracted: the production spine is 48.31 GB
uncompressed and NM contributes nothing to the scratch budget. The eight sibling tables land as
verbatim text rows in Postgres; the spine lands as one Parquet partition (SB-01 §3.2) whose only
Postgres trace is a registry row.

Promotion is set-based for the same reason. The unit of work is one (report_vintage,
production_month) batch — never more than 147,714 rows — and what decides whether a row is worth
appending is a server-side anti-join against the canonical head, not a Python dictionary of
48.1M value hashes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import zipfile
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal
from itertools import chain
from pathlib import Path
from typing import IO, Any

import polars as pl
import psycopg
from psycopg.rows import dict_row

from glasswell.ingest.base import (
    IngestRun,
    open_ingest_run,
    record_vintage_day,
    resolve_environment,
)
from glasswell.ingest.xml_stream import stream_records
from glasswell.lineage.audit import emit
from glasswell.lineage.capture import derive
from glasswell.lineage.conformance import (
    ConformanceRule,
    QuarantineBatch,
    apply_rules,
    load_rules,
    rule_for_family,
)
from glasswell.lineage.errors import RuleSpecError, VintageAlreadyPromoted
from glasswell.lineage.fetch import fetch_raw
from glasswell.lineage.fetch_attempts import durable_fetch_attempts
from glasswell.lineage.ftp import FTP, FtpTransferFailed, close_ftp, connect_ftp, ftp_url
from glasswell.lineage.models import InputRef, ManifestRecord, OutputSpec
from glasswell.lineage.quarantine import quarantine
from glasswell.lineage.serialization import hash_payload
from glasswell.staging.duck import (
    PartitionWrite,
    frame_of,
    identifier,
    partition_reader,
    partition_uri,
    write_partition,
)

__rule_version__ = "1"

FTP_HOST = "164.64.106.6"  # pinned; a failure halts, never guesses (SB-01 §1.2)
MEDIA_TYPE = "application/zip"
SPINE_TABLE = "wcproduction"
# The nine in-scope tables. othervolume, podvolume, podstorage, wcinjection and acreage are
# deliberately out of scope (PLAN-NM §6) and are not fetched.
TABLES: tuple[str, ...] = (
    "pool",
    "ogrid",
    "property",
    "spacingunit",
    "podwc",
    "pod",
    "wchistory",
    "wellhistory",
    SPINE_TABLE,
)
# SB-01 §1.3: sequential, spaced, one connection. The source has no published grant, so the
# pull is paced to be unmistakably a single polite client rather than a crawl.
FETCH_SPACING_SECONDS = 5.0
# The host reset the data channel on the third transfer of the first real pull, so a transfer
# failure is retried on a fresh login. A host that will not answer at all is never retried:
# SB-01 §1.2 makes that a halt, not a wait.
FETCH_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 15.0

LAYOUT_FAMILY = "ftp_layout"
VINTAGE_FAMILY = "undated_vintage"
HOST_PIN_FAMILY = "host_pin"
PARSE_FAMILY = "parse"
PAD_FAMILY = "pad"
# Retrieval rules judge a filename and a URL, not a row, so they are cited on the fetch
# derivation and never handed to apply_rules: their applies_to_fields are not frame columns and
# a parse_directive would read the whole batch as a header failure.
ACQUISITION_FAMILIES = (LAYOUT_FAMILY, VINTAGE_FAMILY, HOST_PIN_FAMILY)

STAGING_ARTIFACT = "records"
PARTITION_TABLE = "staging.stg_nm_ocd_wcproduction__partitions"
ORDINAL = "source_row_ordinal"
# SB-01 §3.1.3. ND's staging is 1-based (nd_mpr.py:167); that is shipped and stays as it is.
ORDINAL_BASE = 0
# The reason vocabulary is read from the live CHECK, never hardcoded; a rule naming a code the
# CHECK does not admit degrades rather than raising, keeping its rule_id (nd_mpr.py:178-188).
UNREGISTERED_REASON = "unknown_vocab"
# quarantine() writes one row per rejected row. A mis-parsed 48.1M-record member would insert
# for hours, so a batch past this cap records a sample and the count instead.
QUARANTINE_BATCH_CAP = 1000
# The promotion's rejects are individually meaningful and bounded by measurement: 2017-08 is the
# worst month at 18,308 rows and the whole in-window population is 50,058, so the ledger is
# complete where staging's cap would have recorded a sample of it.
PROMOTION_QUARANTINE_CAP = 60000

CANONICAL_TABLE = "canonical.production_monthly"
ENTITY_KEY_FAMILY = "entity_key"
UNITS_FAMILY = "units"
LIQUIDS_FAMILY = "liquids"
NULL_SEMANTICS_FAMILY = "null_semantics"
WINDOW_FAMILY = "window"
DAYS_FAMILY = "days"
COLLISION_FAMILY = "collision"
MONTH_FAMILY = "month"
STREAM_VOCAB_FAMILY = "stream_vocab"
API10_FAMILY = "api10"
STREAM_COLUMN = "stream_raw"
MONTH_COLUMN = "production_month"
# The three states this source can tell apart. `withheld` is in the declared vocabulary and has
# no NM producer: prod_amt is never absent across 48,104,334 rows.
NO_REPORT, REPORTED_ZERO, REPORTED = "no_report", "reported_zero", "reported"
# The columns the batch table and the canonical insert share, in one order.
CANONICAL_COLUMNS: tuple[str, ...] = (
    "entity_type",
    "entity_key",
    "reporting_level",
    "well_completion_pool",
    "aggregation",
    "api10",
    "production_month",
    "stream",
    "volume",
    "unit",
    "days_produced",
    "granularity",
    "value_hash",
    "null_semantics",
)
_KEY_COLUMNS: tuple[str, ...] = ("entity_type", "entity_key", "production_month", "stream")
_ROWS_MARK = "__glasswell_rows"
_ANSWERS_MARK = "__glasswell_answers"
_FIRST_MARK = "__glasswell_first"

_REASON_LITERAL_RE = re.compile(r"'([a-z_]+)'::text")


@dataclass(frozen=True, slots=True)
class TableFetch:
    table: str
    source_id: str
    source_key: str
    manifest_id: str
    sha256: str
    bytes: int
    unchanged: bool
    payload_path: str
    upstream_mtime: str | None
    fetch_vintage: str

    def to_dict(self) -> dict[str, object]:
        return {
            "table": self.table,
            "source_id": self.source_id,
            "source_key": self.source_key,
            "manifest_id": self.manifest_id,
            "sha256": self.sha256,
            "bytes": self.bytes,
            "unchanged": self.unchanged,
            "payload_path": self.payload_path,
            "upstream_mtime": self.upstream_mtime,
            "fetch_vintage": self.fetch_vintage,
        }


def source_id_for(table: str) -> str:
    return f"nm_ocd_{table}"


def _rule(rules: Sequence[ConformanceRule], table: str, family: str) -> ConformanceRule:
    wanted = f"cr_nm_{table}_{family}"
    for rule in rules:
        if rule.rule_family == wanted:
            return rule
    raise RuleSpecError(f"{wanted} is not seeded for nm_ocd_{table}; run seed_all first")


def fetch_table(
    run: IngestRun,
    table: str,
    *,
    connection: FTP | None = None,
    raw_root: Path | str | None = None,
) -> TableFetch:
    """Fetch one table's zip under the rules that say where it lives and what it is called."""
    source_id = source_id_for(table)
    rules = load_rules(run.connection, source_id=source_id, stage="parse", as_of=run.as_of)
    layout = _rule(rules, table, LAYOUT_FAMILY)
    vintage_rule = _rule(rules, table, VINTAGE_FAMILY)
    # code_ref has no executor (nd_mpr.py filters the same way); the pin is read and cited.
    host_pin = _rule(rules, table, HOST_PIN_FAMILY)
    if str(host_pin.spec["host"]) != FTP_HOST:
        raise RuleSpecError(
            f"{host_pin.rule_id} pins {host_pin.spec['host']!r} and the module pins {FTP_HOST!r};"
            " re-pin both in one change (SB-01 §1.2)"
        )

    source_key = str(vintage_rule.spec["source_key"])
    result = fetch_raw(
        run.connection,
        source_id,
        source_key,
        url=ftp_url(FTP_HOST, str(layout.spec["path"])),
        acquisition_method="ftp_anon",
        raw_root=raw_root if raw_root is not None else run.raw_root,
        ftp=connection,
        rules=[layout.rule_id, vintage_rule.rule_id, host_pin.rule_id],
        media_type=MEDIA_TYPE,
    )
    manifest = result.manifest
    return TableFetch(
        table=table,
        source_id=source_id,
        source_key=source_key,
        manifest_id=manifest.manifest_id,
        sha256=manifest.sha256,
        bytes=manifest.bytes,
        unchanged=result.unchanged,
        payload_path=str(result.payload_path),
        upstream_mtime=manifest.upstream_mtime.isoformat() if manifest.upstream_mtime else None,
        fetch_vintage=manifest.fetch_vintage.isoformat(),
    )


def fetch_all(
    run: IngestRun,
    *,
    tables: Sequence[str] = TABLES,
    raw_root: Path | str | None = None,
    spacing_seconds: float = FETCH_SPACING_SECONDS,
    backoff_seconds: float = RETRY_BACKOFF_SECONDS,
    sleep: object = time.sleep,
) -> list[TableFetch]:
    """One login, the tables in order, spaced, each transfer retried a bounded number of times."""
    _require_sources(run.connection, tables)
    fetched: list[TableFetch] = []
    connection = _open_session(run)
    try:
        for index, table in enumerate(tables):
            if index:
                sleep(spacing_seconds)  # type: ignore[operator]
            for attempt in range(FETCH_ATTEMPTS):
                try:
                    fetched.append(
                        fetch_table(run, table, connection=connection, raw_root=raw_root)
                    )
                    break
                except FtpTransferFailed:
                    # fetch_raw has already recorded the failure; committing keeps that row
                    # whether or not the retry succeeds.
                    run.connection.commit()
                    if attempt == FETCH_ATTEMPTS - 1:
                        raise
                    # The reset leaves the control channel mid-command, so the retry gets a
                    # fresh login rather than another RETR down a broken one.
                    close_ftp(connection)
                    sleep(backoff_seconds * (attempt + 1))  # type: ignore[operator]
                    connection = _open_session(run)
            run.connection.commit()
    finally:
        close_ftp(connection)
    return fetched


def _open_session(run: IngestRun) -> FTP:
    """The shared login happens outside fetch_raw, so its halt is recorded here instead."""
    try:
        return connect_ftp(FTP_HOST)
    except OSError as error:
        emit(
            run.connection,
            "raw.fetch_failed",
            subject_type="manifest",
            subject_id=f"nm_ocd/{FTP_HOST}",
            payload={
                "url": ftp_url(FTP_HOST, "/"),
                "reason": getattr(error, "glasswell_reason", type(error).__name__),
                "detail": str(error),
            },
            correlation_id=run.session.correlation_id,
        )
        run.connection.commit()
        raise


def _require_sources(connection: psycopg.Connection, tables: Sequence[str]) -> None:
    """Fail before the socket opens, not nine artifacts in (open_ingest_run's contract)."""
    wanted = [source_id_for(table) for table in tables]
    with connection.cursor() as cursor:
        cursor.execute(
            "select source_id from lineage.sources where source_id = any(%s)", (wanted,)
        )
        present = {row[0] for row in cursor.fetchall()}
    missing = [source for source in wanted if source not in present]
    if missing:
        raise LookupError(f"lineage.sources has no row for {missing}; seed it before fetching")


class SchemaDrift(RuntimeError):
    """The artifact carries a column its parse directive never declared."""


class RowCountMismatch(RuntimeError):
    """SB-01 §3.5's invariant: every parsed row is staged or quarantined, never neither."""


@dataclass(frozen=True, slots=True)
class StageReport:
    table: str
    source_id: str
    manifest_id: str
    staging_table: str
    parsed_rows: int
    staged_rows: int
    quarantined: Mapping[str, int] = field(default_factory=dict)
    derivation_id: str = ""
    parquet_uri: str | None = None
    parquet_sha256: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "table": self.table,
            "source_id": self.source_id,
            "manifest_id": self.manifest_id,
            "staging_table": self.staging_table,
            "parsed_rows": self.parsed_rows,
            "staged_rows": self.staged_rows,
            "quarantined": dict(self.quarantined),
            "derivation_id": self.derivation_id,
            "parquet_uri": self.parquet_uri,
            "parquet_sha256": self.parquet_sha256,
        }


def staging_table_for(table: str) -> str:
    """The spine's rows are Parquet, so its Postgres identity is the partition registry."""
    if table == SPINE_TABLE:
        return PARTITION_TABLE
    return f"staging.stg_nm_ocd_{table}__{STAGING_ARTIFACT}"


def head_manifest(connection: psycopg.Connection, source_id: str) -> ManifestRecord:
    """The manifest a staging run reads: the current head, never a superseded artifact."""
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute("select * from lineage.manifest_head where source_id = %s", (source_id,))
        rows = cursor.fetchall()
    if not rows:
        raise LookupError(f"{source_id} has no manifest; fetch before staging")
    if len(rows) > 1:
        raise LookupError(f"{source_id} has {len(rows)} heads; one source_key per NM source")
    return ManifestRecord(**dict(rows[0]))


def stage_table(
    run: IngestRun,
    table: str,
    *,
    manifest: ManifestRecord,
    payload_path: Path | str | None = None,
    batch_rows: int | None = None,
) -> StageReport:
    """Stream one artifact into staging under its parse rules, verbatim and reconciled."""
    connection = run.connection
    source_id = source_id_for(table)
    rules = load_rules(connection, source_id=source_id, stage="parse", as_of=run.as_of)
    directive = _rule(rules, table, PARSE_FAMILY)
    frame_rules = [rule for rule in rules if not _is_acquisition(rule, table)]

    spec = directive.spec
    member = str(spec["member"])
    expected = [str(column) for column in spec["expected_columns"]]
    rows_per_batch = int(batch_rows or spec["batch_rows"])
    staging_table = staging_table_for(table)
    bulk = table == SPINE_TABLE
    counts: dict[str, int] = {}
    applied: dict[str, int] = {}
    tally = {"parsed": 0, "staged": 0}
    payload = Path(payload_path if payload_path is not None else manifest.storage_uri)
    # derive() reads params when the block exits, so the §3.5 reconciliation counts are recorded
    # on the derivation itself rather than only in an audit payload.
    params: dict[str, Any] = {
        "source_key": manifest.source_key,
        "member": member,
        "batch_rows": rows_per_batch,
    }
    output = OutputSpec(
        store="parquet" if bulk else "postgres",
        dataset=staging_table,
        partition={"source_id": source_id, "manifest_id": manifest.manifest_id},
        locator=str(partition_uri(source_id, STAGING_ARTIFACT, manifest.manifest_id))
        if bulk
        else "",
    )
    with derive(
        "stage.parse",
        output=output,
        params=params,
        inputs=[
            InputRef(
                kind="manifest",
                ref_id=manifest.manifest_id,
                role="primary",
                as_of_vintage=manifest.fetch_vintage,
            )
        ],
    ) as parsing:
        if not bulk:
            _clear_staged(connection, staging_table, manifest.manifest_id)
        with zipfile.ZipFile(payload) as bundle:
            _require_member(bundle, member, payload)
            with bundle.open(member) as raw:
                batches = _staged_batches(
                    run,
                    raw,
                    spec=spec,
                    expected=expected,
                    rows_per_batch=rows_per_batch,
                    frame_rules=frame_rules,
                    source_id=source_id,
                    staging_table=staging_table,
                    manifest_id=manifest.manifest_id,
                    vocabulary=_reason_vocabulary(connection),
                    counts=counts,
                    applied=applied,
                    tally=tally,
                )
                # Driving the first batch runs the reader and the quarantine exits for it, so an
                # artifact whose every row is rejected still records counts and writes nothing.
                head = next(batches, None)
                frames = chain([head], batches) if head is not None else iter(())
                written = None
                if not bulk:
                    output_sha256 = _copy_batches(
                        connection, frames, table=staging_table, manifest_id=manifest.manifest_id
                    )
                elif head is None:
                    output_sha256 = hashlib.sha256().hexdigest()
                else:
                    written = write_partition(frames, Path(output.locator))
                    _register_partition(connection, manifest.manifest_id, written)
                    output_sha256 = written.sha256

        rejected = sum(counts.values())
        if tally["parsed"] != tally["staged"] + rejected:
            raise RowCountMismatch(
                f"{staging_table}: parsed {tally['parsed']} rows but staged {tally['staged']}"
                f" and quarantined {rejected}; every parsed row is one or the other (SB-01 §3.5)"
            )
        params.update(
            parsed_rows=tally["parsed"], staged_rows=tally["staged"], quarantined_rows=rejected
        )
        # The directive's spec — member, record tag, namespace, encoding — shaped every staged
        # row; apply_rules only sees it check a header (nd_mpr.py:648-655).
        applied[directive.rule_id] = tally["staged"]
        for rule_id, rows in applied.items():
            parsing.add_rule(rule_id, applied_rows=rows)
        parsing.set_rows(tally["staged"])
        parsing.set_output_hash(output_sha256)
        emit(
            connection,
            "staging.load_completed",
            subject_type="manifest",
            subject_id=manifest.manifest_id,
            payload={
                "table": staging_table,
                "rows": tally["staged"],
                "parsed_rows": tally["parsed"],
                "quarantined_rows": rejected,
                "parquet_uri": written.uri if written else None,
            },
            correlation_id=run.session.correlation_id,
            occurred_at=run.session.clock.now(),
        )
    return StageReport(
        table=table,
        source_id=source_id,
        manifest_id=manifest.manifest_id,
        staging_table=staging_table,
        parsed_rows=tally["parsed"],
        staged_rows=tally["staged"],
        quarantined=counts,
        derivation_id=parsing.derivation_id,
        parquet_uri=written.uri if written else None,
        parquet_sha256=written.sha256 if written else None,
    )


def stage_all(
    run: IngestRun, *, tables: Sequence[str] = TABLES, batch_rows: int | None = None
) -> list[StageReport]:
    """Stage each fetched artifact from the raw zone. No phase after the pull opens a socket."""
    reports = []
    for table in tables:
        manifest = head_manifest(run.connection, source_id_for(table))
        reports.append(stage_table(run, table, manifest=manifest, batch_rows=batch_rows))
        run.connection.commit()
    return reports


def _staged_batches(
    run: IngestRun,
    raw: IO[bytes],
    *,
    spec: Mapping[str, Any],
    expected: Sequence[str],
    rows_per_batch: int,
    frame_rules: Sequence[ConformanceRule],
    source_id: str,
    staging_table: str,
    manifest_id: str,
    vocabulary: frozenset[str],
    counts: dict[str, int],
    applied: dict[str, int],
    tally: dict[str, int],
) -> Iterator[pl.DataFrame]:
    """One batch at a time: read, ordinal, rules, quarantine, hand on. Nothing accumulates."""
    ordinal = ORDINAL_BASE
    for batch in stream_records(
        raw,
        record_tag=str(spec["record_tag"]),
        namespace=str(spec["namespace"]),
        encoding=str(spec["encoding"]),
        batch_rows=rows_per_batch,
    ):
        _require_declared_columns(batch, expected, staging_table)
        indexed = batch.with_row_index(ORDINAL, offset=ordinal).with_columns(
            pl.col(ORDINAL).cast(pl.Int64)
        )
        ordinal += batch.height
        tally["parsed"] += batch.height
        application = apply_rules(indexed, frame_rules)
        _route_quarantine(
            run,
            application.quarantined,
            stage="parse",
            source_id=source_id,
            staging_table=staging_table,
            manifest_id=manifest_id,
            vocabulary=vocabulary,
            counts=counts,
        )
        for rule_id, rows in application.applied_rows.items():
            applied[rule_id] = applied.get(rule_id, 0) + rows
        if application.frame.is_empty():
            continue
        tally["staged"] += application.frame.height
        yield application.frame


def _require_declared_columns(
    batch: pl.DataFrame, expected: Sequence[str], staging_table: str
) -> None:
    """`unexpected_column: halt`. A field the source grew is a change, not a row to reject."""
    unexpected = [column for column in batch.columns if column not in expected]
    if unexpected:
        raise SchemaDrift(
            f"{staging_table}: the artifact carries {unexpected}, which its parse directive does"
            " not declare; supersede the rule and the staging DDL before loading it"
        )


def _route_quarantine(
    run: IngestRun,
    batches: Sequence[QuarantineBatch],
    *,
    stage: str,
    source_id: str,
    staging_table: str,
    manifest_id: str,
    vocabulary: frozenset[str],
    counts: dict[str, int],
    cap: int = QUARANTINE_BATCH_CAP,
) -> None:
    for batch in batches:
        reason = batch.reason_code if batch.reason_code in vocabulary else UNREGISTERED_REASON
        capped = batch.frame.height > cap
        recorded = batch.frame.head(cap) if capped else batch.frame
        result = quarantine(
            run.connection,
            recorded,
            reason_code=reason,
            manifest_id=manifest_id,
            source_id=source_id,
            staging_table=staging_table,
            stage=stage,
            seen_at=run.session.clock.now(),
            rule_id=batch.rule_id,
            correlation_id=run.session.correlation_id,
        )
        counts[reason] = counts.get(reason, 0) + batch.frame.height
        emit(
            run.connection,
            "staging.rows_quarantined",
            subject_type="manifest",
            subject_id=manifest_id,
            payload={
                "staging_table": staging_table,
                "reason_code": reason,
                "rule_id": batch.rule_id,
                "rows": batch.frame.height,
                "recorded": recorded.height,
                "opened": result.opened,
                "reoccurred": result.reoccurred,
                "capped": capped,
            },
            correlation_id=run.session.correlation_id,
            occurred_at=run.session.clock.now(),
        )


def _copy_batches(
    connection: psycopg.Connection,
    batches: Iterator[pl.DataFrame],
    *,
    table: str,
    manifest_id: str,
) -> str:
    """COPY each batch into its verbatim row table, folding the batch hashes as it goes."""
    digest = hashlib.sha256()
    with connection.cursor() as cursor:
        for frame in batches:
            columns = ", ".join(f'"{name}"' for name in ("manifest_id", *frame.columns))
            with cursor.copy(f"copy {table} ({columns}) from stdin") as copy:
                for row in frame.iter_rows():
                    copy.write_row((manifest_id, *row))
            digest.update(hash_payload(frame.rows()).encode("ascii"))
    return digest.hexdigest()


def _clear_staged(connection: psycopg.Connection, table: str, manifest_id: str) -> None:
    """Re-staging a manifest replaces its rows; staging is the parser's own scratch layer."""
    with connection.cursor() as cursor:
        cursor.execute(f"delete from {table} where manifest_id = %s", (manifest_id,))


_REGISTER_PARTITION = f"""
insert into {PARTITION_TABLE} (manifest_id, parquet_uri, rows, sha256, sort_order)
values (%(manifest_id)s, %(parquet_uri)s, %(rows)s, %(sha256)s, %(sort_order)s)
on conflict (manifest_id) do update
   set parquet_uri = excluded.parquet_uri, rows = excluded.rows, sha256 = excluded.sha256,
       sort_order = excluded.sort_order, written_at = now()
"""


def _register_partition(
    connection: psycopg.Connection, manifest_id: str, written: PartitionWrite
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            _REGISTER_PARTITION,
            {
                "manifest_id": manifest_id,
                "parquet_uri": written.uri,
                "rows": written.rows,
                "sha256": written.sha256,
                "sort_order": written.sort_order,
            },
        )


def _require_member(bundle: zipfile.ZipFile, member: str, payload: Path) -> None:
    if member not in bundle.namelist():
        raise SchemaDrift(
            f"{payload}: the archive holds {bundle.namelist()} and the parse directive names"
            f" {member!r}"
        )


def _is_acquisition(rule: ConformanceRule, table: str) -> bool:
    return rule.rule_family in {f"cr_nm_{table}_{family}" for family in ACQUISITION_FAMILIES}


def _reason_vocabulary(connection: psycopg.Connection) -> frozenset[str]:
    """Read the admitted codes out of the live CHECK, so an unadmitted one degrades, not raises."""
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


@dataclass(frozen=True, slots=True)
class PromotionPolicy:
    """Every promotion decision, read out of the registry rather than written down here."""

    entity_type: str
    reporting_level: str
    granularity: str
    volume_field: str
    stream_field: str
    year_field: str
    units: Mapping[str, str]
    liquids_policy: str
    semantics: Sequence[str]  # validated at construction; the classifier emits three of them
    days_field: str
    days_minimum: int
    window_start: date
    key_columns: Sequence[str]
    pool_column: str
    trim: Mapping[str, Any]
    month_expression: str
    rule_ids: Mapping[str, str]
    collision_evidence: Sequence[str]

    @classmethod
    def from_rules(cls, rules: Sequence[ConformanceRule]) -> PromotionPolicy:
        def pinned(family: str) -> ConformanceRule:
            return rule_for_family(rules, f"cr_nm_{SPINE_TABLE}_{family}")

        entity = pinned(ENTITY_KEY_FAMILY)
        units = pinned(UNITS_FAMILY)
        days = pinned(DAYS_FAMILY)
        month = pinned(MONTH_FAMILY)
        key = pinned(API10_FAMILY)
        # The three whose executor stamps no row count, so the promotion stamps it for them.
        cited = (WINDOW_FAMILY, DAYS_FAMILY, COLLISION_FAMILY)
        return cls(
            entity_type=str(entity.spec["entity_type"]),
            reporting_level=str(entity.spec["reporting_level"]),
            granularity=str(entity.spec["granularity"]),
            volume_field=str(units.spec["volume_field"]),
            year_field=identifier(str(month.spec["year_field"])),
            stream_field=str(pinned(STREAM_VOCAB_FAMILY).spec["source_field"]),
            units={str(k): str(v) for k, v in units.spec["units_by_stream"].items()},
            liquids_policy=str(pinned(LIQUIDS_FAMILY).spec["liquids_policy"]),
            semantics=_admitted_semantics(pinned(NULL_SEMANTICS_FAMILY)),
            days_field=str(days.spec["source_field"]),
            days_minimum=int(str(days.spec["minimum"])),
            window_start=date.fromisoformat(
                str(pinned(WINDOW_FAMILY).spec["promotion_window_start"])
            ),
            key_columns=[str(column) for column in key.spec["source_cols"]],
            pool_column=str(entity.spec["source_cols"][1]),
            trim=dict(pinned(PAD_FAMILY).spec["trim"]),
            month_expression=_month_expression(month.spec),
            rule_ids={family: pinned(family).rule_id for family in cited},
            # The cells the collision rule says it ruled on, carried through so a withheld
            # filing is readable out of the ledger rather than only out of staging, which
            # SB-01 §3.2 truncates at 30 days (gate-nm-fp O1).
            collision_evidence=[
                str(column) for column in pinned(COLLISION_FAMILY).spec["declares_fields"]
            ],
        )

    def cite(self, family: str) -> str:
        return self.rule_ids[family]


def _admitted_semantics(rule: ConformanceRule) -> tuple[str, ...]:
    """The classifier emits three tokens; the rule row is what says they are admissible."""
    declared = tuple(str(token) for token in rule.spec["vocabulary"])
    emitted = (NO_REPORT, REPORTED_ZERO, REPORTED)
    missing = [token for token in emitted if token not in declared]
    if missing:
        raise RuleSpecError(
            f"{rule.rule_id} does not admit {missing}; its vocabulary is {declared}"
        )
    return declared


def _month_expression(spec: Mapping[str, Any]) -> str:
    """`production_month` in SQL, composed by the rule rather than by this module (m7)."""
    year = identifier(str(spec["year_field"]))
    month = identifier(str(spec["month_field"]))
    return f"make_date(cast({year} as integer), cast({month} as integer), {int(spec['day'])})"


def _identity_expression(policy: PromotionPolicy) -> str:
    columns = [*policy.key_columns, policy.pool_column, policy.stream_field]
    return " || '|' || ".join(identifier(column) for column in columns)


def promotion_records(frame: pl.DataFrame, *, policy: PromotionPolicy) -> pl.DataFrame:
    """The canonical rows one staged batch computes, hashed on the measurement alone."""
    volume = pl.col(policy.volume_field)
    filed = pl.col(policy.days_field).cast(pl.Int64, strict=False)
    # A day count longer than the month it is filed for is not a day count: 41,593 in-window
    # rows carry one, and the volume beside it is real (cr_nm_wcproduction_days_1).
    admissible = filed.is_between(policy.days_minimum, pl.col(MONTH_COLUMN).dt.month_end().dt.day())
    computed = frame.with_columns(
        pl.lit(policy.entity_type).alias("entity_type"),
        pl.lit(policy.reporting_level).alias("reporting_level"),
        pl.col(policy.pool_column).alias("well_completion_pool"),
        pl.lit(None, dtype=pl.String).alias("aggregation"),
        pl.col("stream_canonical").alias("stream"),
        volume.alias("reported_volume"),
        pl.col("stream_canonical")
        .replace_strict(dict(policy.units), default=None, return_dtype=pl.String)
        .alias("unit"),
        pl.when(admissible).then(filed).otherwise(None).cast(pl.Int16).alias("days_produced"),
        pl.lit(policy.granularity).alias("granularity"),
        pl.when(volume.is_null())
        .then(pl.lit(NO_REPORT))
        .when(volume == 0)
        .then(pl.lit(REPORTED_ZERO))
        .otherwise(pl.lit(REPORTED))
        .alias("null_semantics"),
    )
    hashed = computed.with_columns(
        pl.Series(
            "value_hash",
            [
                hash_payload({**row, "liquids_policy": policy.liquids_policy})
                for row in computed.select(
                    pl.col("reported_volume").alias("volume"),
                    "unit",
                    "days_produced",
                    "null_semantics",
                ).iter_rows(named=True)
            ],
            dtype=pl.String,
        ),
        # canonical.volume is NOT NULL, so an absent volume is carried as zero and
        # null_semantics is what separates it from a reported one (nd_mpr.py's precedent).
        pl.col("reported_volume").fill_null(Decimal(0)).alias("volume"),
    )
    carried = [
        column
        for column in policy.collision_evidence
        if column in hashed.columns and column not in CANONICAL_COLUMNS
    ]
    return hashed.select("source_row_ordinal", *CANONICAL_COLUMNS, *carried)


@dataclass(frozen=True, slots=True)
class CollisionRouting:
    kept: pl.DataFrame
    duplicates: pl.DataFrame
    collisions: pl.DataFrame


def route_collisions(records: pl.DataFrame) -> CollisionRouting:
    """One S-E row per key, or none — never one of two answers chosen by file order.

    NM files two rows for 25,029 in-window well-completion-months, almost always under two
    OGRIDs. Where both say the same thing the second is a duplicate; where they disagree the
    artifact does not say which is the month, so nothing is promoted and both are quarantined.
    """
    marked = records.with_columns(
        pl.len().over(_KEY_COLUMNS).alias(_ROWS_MARK),
        pl.col("value_hash").n_unique().over(_KEY_COLUMNS).alias(_ANSWERS_MARK),
        (pl.col("source_row_ordinal") == pl.col("source_row_ordinal").min().over(_KEY_COLUMNS))
        .alias(_FIRST_MARK),
    )
    marks = [_ROWS_MARK, _ANSWERS_MARK, _FIRST_MARK]
    agreed = pl.col(_ANSWERS_MARK) == 1
    return CollisionRouting(
        kept=marked.filter(agreed & pl.col(_FIRST_MARK)).drop(marks),
        duplicates=marked.filter(agreed & ~pl.col(_FIRST_MARK)).drop(marks),
        collisions=marked.filter(~agreed).drop(marks),
    )


@dataclass(frozen=True, slots=True)
class MonthOutcome:
    production_month: date
    staged_rows: int
    promoted_rows: int
    restated_rows: int
    suppressed_unchanged: int
    quarantined: Mapping[str, int]
    derivation_id: str


@dataclass(frozen=True, slots=True)
class PromotionReport:
    manifest_id: str
    report_vintage: date
    window_start: date
    months: list[str] = field(default_factory=list)
    staged_rows: int = 0
    promoted_rows: int = 0
    restated_rows: int = 0
    suppressed_unchanged: int = 0
    skipped_unchanged_mod_dte: int = 0
    quarantined: Mapping[str, int] = field(default_factory=dict)
    restatement_summary: Mapping[str, int] = field(default_factory=dict)
    vintage_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "manifest_id": self.manifest_id,
            "report_vintage": self.report_vintage.isoformat(),
            "window_start": self.window_start.isoformat(),
            "months": len(self.months),
            "staged_rows": self.staged_rows,
            "promoted_rows": self.promoted_rows,
            "restated_rows": self.restated_rows,
            "suppressed_unchanged": self.suppressed_unchanged,
            "skipped_unchanged_mod_dte": self.skipped_unchanged_mod_dte,
            "quarantined": dict(self.quarantined),
            "vintage_id": self.vintage_id,
        }


_CREATE_BATCH = """
create temp table nm_promotion_batch (
    entity_type text not null, entity_key text not null, reporting_level text not null,
    well_completion_pool text, aggregation text, api10 text, production_month date not null,
    stream text not null, volume numeric(18, 3) not null, unit text not null,
    days_produced smallint, granularity text not null, value_hash text not null,
    null_semantics text not null
) on commit drop
"""

# The head for one month, read off (source_id, production_month) — migration 028's index — so
# the anti-join never touches the other 634 months.
_HEAD = f"""
with head as (
    select distinct on (entity_type, entity_key, stream)
           entity_type, entity_key, stream, value_hash
      from {CANONICAL_TABLE}
     where source_id = %(source_id)s and production_month = %(production_month)s
     order by entity_type, entity_key, stream, report_vintage desc, derivation_id desc
)
"""

_COUNT_RESTATED = (
    _HEAD
    + """
select count(*) from nm_promotion_batch b
  join head h using (entity_type, entity_key, stream)
 where h.value_hash <> b.value_hash
"""
)

# The literal complement of _APPEND's predicate, so promoted + suppressed is measured against
# the head rather than derived as `kept - promoted` — which cancels `promoted` out of the
# reconciliation identity and leaves a mis-split unfalsifiable (gate-nm-fp O6).
_COUNT_SUPPRESSED = (
    _HEAD
    + """
select count(*) from nm_promotion_batch b
  left join head h using (entity_type, entity_key, stream)
 where h.value_hash is not distinct from b.value_hash
"""
)

_APPEND = (
    _HEAD
    + f"""
insert into {CANONICAL_TABLE} (
    entity_type, entity_key, reporting_level, well_completion_pool, aggregation, api10,
    production_month, stream, source_id, report_vintage, volume, unit, days_produced,
    granularity, value_hash, source_manifest_id, derivation_id, null_semantics)
select b.entity_type, b.entity_key, b.reporting_level, b.well_completion_pool, b.aggregation,
       b.api10, b.production_month, b.stream, %(source_id)s, %(report_vintage)s, b.volume,
       b.unit, b.days_produced, b.granularity, b.value_hash, %(manifest_id)s,
       %(derivation_id)s, b.null_semantics
  from nm_promotion_batch b
  left join head h using (entity_type, entity_key, stream)
 where h.value_hash is distinct from b.value_hash
"""
)

_VINTAGE_DIVERGENCE = f"""
select count(*), min(b.entity_key || ' ' || b.production_month::text || ' ' || b.stream
       || ': recorded ' || p.value_hash || ', computed ' || b.value_hash)
  from nm_promotion_batch b
  join {CANONICAL_TABLE} p
    on p.source_id = %(source_id)s and p.report_vintage = %(report_vintage)s
   and p.entity_type = b.entity_type and p.entity_key = b.entity_key
   and p.production_month = b.production_month and p.stream = b.stream
 where p.value_hash <> b.value_hash
"""

# The other half of the same question: a row this vintage recorded that the run no longer
# computes. Withdrawing an answer is as much a rewrite as changing one.
_VINTAGE_WITHDRAWN = f"""
select count(*), min(p.entity_key || ' ' || p.production_month::text || ' ' || p.stream
       || ': recorded ' || p.value_hash || ', computed nothing')
  from {CANONICAL_TABLE} p
 where p.source_id = %(source_id)s and p.report_vintage = %(report_vintage)s
   and p.production_month = %(production_month)s
   and not exists (
       select 1 from nm_promotion_batch b
        where b.entity_type = p.entity_type and b.entity_key = p.entity_key
          and b.production_month = p.production_month and b.stream = p.stream)
"""


def promote_month(
    run: IngestRun,
    *,
    manifest: ManifestRecord,
    month: date,
    policy: PromotionPolicy,
    window_start: date,
    frame: pl.DataFrame,
    validate_rules: Sequence[ConformanceRule],
    conform_rules: Sequence[ConformanceRule],
    vocabulary: frozenset[str],
    skipped_unchanged: int = 0,
) -> MonthOutcome:
    """One (report_vintage, production_month) batch, from staged text to appended rows."""
    connection = run.connection
    counts: dict[str, int] = {}
    staged_rows = frame.height
    params: dict[str, Any] = {
        "production_month": month.isoformat(),
        # The window the run actually applied, not the rule's default: a figure served from a
        # widened run is distinguishable from one served before it only if this is the effective
        # one (cr_nm_wcproduction_window_1's rationale).
        "window_start": window_start.isoformat(),
        "liquids_policy": policy.liquids_policy,
        "staged_rows": staged_rows,
        "skipped_unchanged_mod_dte": skipped_unchanged,
    }
    with derive(
        "canonical.promote",
        output=OutputSpec(
            store="postgres",
            dataset=CANONICAL_TABLE,
            partition={
                "source_id": source_id_for(SPINE_TABLE),
                "manifest_id": manifest.manifest_id,
                "production_month": month.isoformat(),
            },
        ),
        params=params,
        inputs=[
            InputRef(
                kind="manifest",
                ref_id=manifest.manifest_id,
                role="primary",
                as_of_vintage=manifest.fetch_vintage,
            )
        ],
    ) as promotion:
        typed = _typed_frame(frame, policy=policy, month=month)
        validated = apply_rules(typed, validate_rules)
        _route_promotion_quarantine(
            run, validated.quarantined, stage="validate", manifest=manifest, vocabulary=vocabulary,
            counts=counts,
        )
        conformed = apply_rules(validated.frame, conform_rules)
        _route_promotion_quarantine(
            run, conformed.quarantined, stage="conform", manifest=manifest, vocabulary=vocabulary,
            counts=counts,
        )

        records = promotion_records(conformed.frame, policy=policy)
        routing = route_collisions(records)
        _route_promotion_quarantine(
            run,
            [
                QuarantineBatch(
                    reason_code=reason,
                    rule_id=policy.cite(COLLISION_FAMILY),
                    frame=rejected,
                )
                for reason, rejected in (
                    ("key_collision", routing.collisions),
                    ("duplicate_row", routing.duplicates),
                )
                if not rejected.is_empty()
            ],
            stage="join",
            manifest=manifest,
            vocabulary=vocabulary,
            counts=counts,
        )

        _load_batch(connection, routing.kept)
        _refuse_vintage_rewrite(
            connection, month=month, report_vintage=run.as_of, complete=skipped_unchanged == 0
        )
        head_parameters = {"source_id": source_id_for(SPINE_TABLE), "production_month": month}
        restated = _scalar(connection, _COUNT_RESTATED, head_parameters)
        # Both counts read the head, so both are taken before the append moves it.
        suppressed = _scalar(connection, _COUNT_SUPPRESSED, head_parameters)

        stamped: dict[str, int] = {}
        for application in (validated, conformed):
            for rule_id in application.applied_rule_ids:
                stamped[rule_id] = stamped.get(rule_id, 0) + application.applied_rows[rule_id]
        # A declaration's executor validates a header and stamps nothing, but these three
        # decided rows: the window chose which were read, the day domain judged every record
        # and the collision rule ruled on every group above one (fp-audit D4 — rows touched).
        stamped[policy.cite(WINDOW_FAMILY)] = staged_rows
        stamped[policy.cite(DAYS_FAMILY)] = records.height
        stamped[policy.cite(COLLISION_FAMILY)] = (
            routing.collisions.height + routing.duplicates.height
        )
        for rule_id, rows in stamped.items():
            promotion.add_rule(rule_id, applied_rows=rows)
        promotion.set_rows(routing.kept.height)
        # What the batch computed, not what the store kept: hashing the appended subset would
        # make the derivation a function of prior state and trip the determinism detector.
        promotion.set_output_hash(hash_payload(sorted(records["value_hash"].to_list())))

    promoted = _append_promoted(
        connection,
        month=month,
        manifest_id=manifest.manifest_id,
        derivation_id=promotion.derivation_id,
        report_vintage=run.as_of,
    )
    rejected = sum(counts.values())
    if staged_rows != promoted + rejected + suppressed:
        raise RowCountMismatch(
            f"{CANONICAL_TABLE} {month}: read {staged_rows} rows but promoted {promoted},"
            f" quarantined {rejected} and suppressed {suppressed} unchanged; a row that was read"
            " is exactly one of those (SB-01 §5.1)"
        )
    return MonthOutcome(
        production_month=month,
        staged_rows=staged_rows,
        promoted_rows=promoted,
        restated_rows=restated,
        suppressed_unchanged=suppressed,
        quarantined=counts,
        derivation_id=promotion.derivation_id,
    )


def _typed_frame(frame: pl.DataFrame, *, policy: PromotionPolicy, month: date) -> pl.DataFrame:
    """Staging is verbatim text. The three casts the rules need, and no other opinion.

    `prod_amt` is cast before the conform pass because `_unit_conform` multiplies by a Decimal
    and raises `TypeError` from inside polars on a String column, and the trim comes off the pad
    rule rather than a `.strip()`, which would eat the leading spaces that are data elsewhere.
    """
    trim = policy.trim[policy.stream_field]
    return frame.with_columns(
        pl.col(policy.stream_field).str.strip_chars_end(str(trim["char"])).alias(STREAM_COLUMN),
        pl.col(policy.volume_field).cast(pl.Decimal(18, 3), strict=False),
        pl.lit(month, dtype=pl.Date).alias(MONTH_COLUMN),
    )


def _route_promotion_quarantine(
    run: IngestRun,
    batches: Sequence[QuarantineBatch],
    *,
    stage: str,
    manifest: ManifestRecord,
    vocabulary: frozenset[str],
    counts: dict[str, int],
) -> None:
    _route_quarantine(
        run,
        batches,
        stage=stage,
        source_id=source_id_for(SPINE_TABLE),
        staging_table=PARTITION_TABLE,
        manifest_id=manifest.manifest_id,
        vocabulary=vocabulary,
        counts=counts,
        cap=PROMOTION_QUARANTINE_CAP,
    )


def _load_batch(connection: psycopg.Connection, records: pl.DataFrame) -> None:
    columns = ", ".join(f'"{name}"' for name in CANONICAL_COLUMNS)
    with connection.cursor() as cursor:
        cursor.execute(_CREATE_BATCH)
        with cursor.copy(f"copy nm_promotion_batch ({columns}) from stdin") as copy:
            for row in records.select(CANONICAL_COLUMNS).iter_rows():
                copy.write_row(row)


def _scalar(connection: psycopg.Connection, statement: str, parameters: Mapping[str, Any]) -> int:
    with connection.cursor() as cursor:
        cursor.execute(statement, dict(parameters))
        row = cursor.fetchone()
    return int(row[0]) if row else 0


def _refuse_vintage_rewrite(
    connection: psycopg.Connection, *, month: date, report_vintage: date, complete: bool
) -> None:
    """No month rewrites an answer its own vintage already gave: it recomputes it or it refuses.

    The scope is the month, not the run. `promote_all` commits each month as it passes, so a
    refusal here aborts the run without withdrawing the months before it — what those appended
    stays, and `_record_vintage` is what keeps the ledger equal to it (gate-nm-fp D1).

    A1b's landed semantics at the canonical grain (gate-a1b Defect A), which DIR-2's four arms
    do not cover: they are about bytes across days. This is one day, twice.

    `complete` is false when the `mod_dte` shortcut skipped keys, and then only the divergence
    half runs: a key the shortcut skipped was deliberately not computed, so it is indistinguishable
    from one this run withdrew.
    """
    parameters = {
        "source_id": source_id_for(SPINE_TABLE),
        "report_vintage": report_vintage,
        "production_month": month,
    }
    statements = (_VINTAGE_DIVERGENCE, _VINTAGE_WITHDRAWN) if complete else (_VINTAGE_DIVERGENCE,)
    for statement in statements:
        with connection.cursor() as cursor:
            cursor.execute(statement, parameters)
            rows, example = cursor.fetchone()
        if rows:
            raise VintageAlreadyPromoted(CANONICAL_TABLE, report_vintage, int(rows), example)


def _append_promoted(
    connection: psycopg.Connection,
    *,
    month: date,
    manifest_id: str,
    derivation_id: str,
    report_vintage: date,
) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            _APPEND,
            {
                "source_id": source_id_for(SPINE_TABLE),
                "production_month": month,
                "report_vintage": report_vintage,
                "manifest_id": manifest_id,
                "derivation_id": derivation_id,
            },
        )
        return cursor.rowcount


def partition_for(connection: psycopg.Connection, manifest_id: str) -> str | None:
    with connection.cursor() as cursor:
        cursor.execute(
            f"select parquet_uri from {PARTITION_TABLE} where manifest_id = %s", (manifest_id,)
        )
        row = cursor.fetchone()
    return str(row[0]) if row else None


def promote_all(
    run: IngestRun,
    *,
    manifest: ManifestRecord | None = None,
    window_start: date | None = None,
    months: Sequence[date] | None = None,
    mod_dte_shortcut: bool = True,
) -> PromotionReport:
    """Promote the staged spine month by month, at the run's vintage, inside the window."""
    connection = run.connection
    source_id = source_id_for(SPINE_TABLE)
    head = manifest or head_manifest(connection, source_id)
    parse_rules = load_rules(connection, source_id=source_id, stage="parse", as_of=run.as_of)
    conform_rules = load_rules(connection, source_id=source_id, stage="conform", as_of=run.as_of)
    validate_rules = load_rules(connection, source_id=source_id, stage="validate", as_of=run.as_of)
    policy = PromotionPolicy.from_rules([*parse_rules, *conform_rules])
    window = window_start or policy.window_start
    vocabulary = _reason_vocabulary(connection)

    partition = partition_for(connection, head.manifest_id)
    if partition is None:
        raise LookupError(
            f"{head.manifest_id} has no row in {PARTITION_TABLE}; stage before promoting"
        )
    prior = _prior_partition(connection, head) if mod_dte_shortcut else None

    totals: dict[str, int] = {"staged": 0, "promoted": 0, "restated": 0, "suppressed": 0,
                             "skipped": 0}
    counts: dict[str, int] = {}
    restatement: dict[str, int] = {}
    touched: list[str] = []
    views = {"staged": partition} | ({"prior": prior} if prior else {})

    def snapshot() -> PromotionReport:
        return PromotionReport(
            manifest_id=head.manifest_id,
            report_vintage=run.as_of,
            window_start=window,
            months=list(touched),
            staged_rows=totals["staged"],
            promoted_rows=totals["promoted"],
            restated_rows=totals["restated"],
            suppressed_unchanged=totals["suppressed"],
            skipped_unchanged_mod_dte=totals["skipped"],
            quarantined=dict(counts),
            restatement_summary=dict(restatement),
        )

    try:
        with partition_reader(views) as reader:
            wanted = months or staged_months(reader, policy=policy, window_start=window)
            for month in wanted:
                frame, skipped = staged_month(
                    reader, policy=policy, month=month, compare_prior=prior is not None
                )
                if frame.is_empty() and not skipped:
                    continue
                outcome = promote_month(
                    run,
                    manifest=head,
                    month=month,
                    policy=policy,
                    window_start=window,
                    frame=frame,
                    validate_rules=validate_rules,
                    conform_rules=conform_rules,
                    vocabulary=vocabulary,
                    skipped_unchanged=skipped,
                )
                connection.commit()
                totals["staged"] += outcome.staged_rows + skipped
                totals["promoted"] += outcome.promoted_rows
                totals["restated"] += outcome.restated_rows
                totals["suppressed"] += outcome.suppressed_unchanged
                totals["skipped"] += skipped
                touched.append(month.isoformat())
                if outcome.restated_rows:
                    restatement[month.isoformat()] = outcome.restated_rows
                for reason, rows in outcome.quarantined.items():
                    counts[reason] = counts.get(reason, 0) + rows
    except VintageAlreadyPromoted:
        # The diverging month is discarded, but months commit one at a time and the ones before
        # it stay. Leaving the ledger unwritten is what made rows_appended understate canonical
        # at the vintage (gate-nm-fp D1); the run still refuses.
        connection.rollback()
        _record_vintage(run, snapshot())
        connection.commit()
        raise

    return _close_vintage(run, snapshot())


def _record_vintage(run: IngestRun, report: PromotionReport) -> None:
    """The vintage row is the ledger of the vintage-day; `record_vintage_day` accumulates."""
    record_vintage_day(
        run.connection,
        source_id=source_id_for(SPINE_TABLE),
        vintage_date=run.as_of,
        manifest_ids=[report.manifest_id],
        opened_at=run.session.clock.now(),
        rows_examined=report.staged_rows,
        rows_appended=report.promoted_rows,
        months_touched=report.months,
        restatement_summary=report.restatement_summary,
    )


def _close_vintage(run: IngestRun, report: PromotionReport) -> PromotionReport:
    """The counters are the vintage-day's (`_record_vintage`); the events are this run's."""
    connection = run.connection
    source_id = source_id_for(SPINE_TABLE)
    if not report.months:
        return report
    payload = {
        "manifest_id": report.manifest_id,
        "window_start": report.window_start.isoformat(),
        "months_touched": len(report.months),
        "rows_examined": report.staged_rows,
        "rows_appended": report.promoted_rows,
        "rows_suppressed_unchanged": report.suppressed_unchanged,
        "rows_skipped_unchanged_mod_dte": report.skipped_unchanged_mod_dte,
        "quarantined": dict(report.quarantined),
    }
    _record_vintage(run, report)
    emit(
        connection,
        "canonical.promotion_completed",
        subject_type="vintage",
        subject_id=f"vin_{source_id}_{run.as_of.isoformat()}",
        payload=payload,
        correlation_id=run.session.correlation_id,
        occurred_at=run.session.clock.now(),
    )
    if report.restatement_summary:
        emit(
            connection,
            "canonical.restatement_detected",
            subject_type="vintage",
            subject_id=f"vin_{source_id}_{run.as_of.isoformat()}",
            payload={**payload, "restatement_summary": dict(report.restatement_summary)},
            correlation_id=run.session.correlation_id,
            occurred_at=run.session.clock.now(),
        )
    connection.commit()
    return replace(report, vintage_id=f"vin_{source_id}_{run.as_of.isoformat()}")


def _prior_partition(connection: psycopg.Connection, manifest: ManifestRecord) -> str | None:
    """The partition the superseded manifest staged, if it is still on disk (SB-01 §3.2's
    30-day truncation is what makes this an optimisation and not a dependency)."""
    if not manifest.supersedes_manifest_id:
        return None
    uri = partition_for(connection, manifest.supersedes_manifest_id)
    return uri if uri and Path(uri).exists() else None


def staged_months(reader: Any, *, policy: PromotionPolicy, window_start: date) -> list[date]:
    months = reader.execute(
        f"select distinct {policy.month_expression} as m from staged"
        f" where {policy.year_field} >= ? and {policy.month_expression} >= ? order by m",
        [f"{window_start.year:04d}", window_start],
    ).fetchall()
    return [row[0] for row in months]


def staged_month(
    reader: Any, *, policy: PromotionPolicy, month: date, compare_prior: bool
) -> tuple[pl.DataFrame, int]:
    """One month of staged rows, less the keys the prior partition already answered.

    The `mod_dte` shortcut (SB-01 §5.4) compares against the **staged** prior partition rather
    than canonical, whose `mod_dte` is the last value-changing manifest's and is deliberately
    stale under change-only append. It skips whole keys, never single rows: a key whose two
    filings were split between skipped and kept would promote one of two answers that the full
    comparison refuses (M10).
    """
    identity = _identity_expression(policy)
    # The year is bounded on the raw column as well as inside the composed month, because that
    # is what lets the reader prune row groups: 0.75 s a month against 5.5 s (P4.11).
    where = f"{policy.year_field} = ? and {policy.month_expression} = ?"
    bounds = [f"{month.year:04d}", month]
    if not compare_prior:
        whole = reader.sql(f"select * from staged where {where} order by 1", params=bounds)
        return frame_of(whole), 0
    reader.execute(
        f"""
        create or replace temp table unchanged_keys as
        with current as (
            select {identity} as k, count(*) as n,
                   string_agg(mod_dte, '|' order by mod_dte) as signature
              from staged where {where} group by 1),
             earlier as (
            select {identity} as k, count(*) as n,
                   string_agg(mod_dte, '|' order by mod_dte) as signature
              from prior where {where} group by 1)
        select current.k as k, current.n as n from current join earlier using (k)
         where current.n = earlier.n and current.signature = earlier.signature
        """,
        [*bounds, *bounds],
    )
    skipped = reader.execute("select coalesce(sum(n), 0) from unchanged_keys").fetchone()[0]
    frame = frame_of(
        reader.sql(
            f"select * from staged where {where}"
            f" and {identity} not in (select k from unchanged_keys) order by 1",
            params=bounds,
        )
    )
    return frame, int(skipped)


def run_promote(
    connection: psycopg.Connection,
    *,
    window_start: date | None = None,
    months: Sequence[date] | None = None,
    mod_dte_shortcut: bool = True,
    env_id: str | None = None,
    code_version: str | None = None,
) -> PromotionReport:
    resolved = resolve_environment(connection, env_id=env_id, code_version=code_version)
    with open_ingest_run(
        connection, source_id=source_id_for(SPINE_TABLE), environment=resolved
    ) as run:
        return promote_all(
            run, window_start=window_start, months=months, mod_dte_shortcut=mod_dte_shortcut
        )


def run_fetch(
    connection: psycopg.Connection,
    *,
    tables: Sequence[str] = TABLES,
    raw_root: Path | str | None = None,
    spacing_seconds: float = FETCH_SPACING_SECONDS,
    environment: Mapping[str, str] | None = None,
    env_id: str | None = None,
    code_version: str | None = None,
) -> list[TableFetch]:
    resolved = resolve_environment(connection, env_id=env_id, code_version=code_version)
    with open_ingest_run(
        connection,
        source_id=source_id_for(SPINE_TABLE),
        raw_root=raw_root,
        environment=resolved,
    ) as run:
        return fetch_all(
            run, tables=tables, raw_root=raw_root, spacing_seconds=spacing_seconds
        )


def run_stage(
    connection: psycopg.Connection,
    *,
    tables: Sequence[str] = TABLES,
    raw_root: Path | str | None = None,
    batch_rows: int | None = None,
    env_id: str | None = None,
    code_version: str | None = None,
) -> list[StageReport]:
    resolved = resolve_environment(connection, env_id=env_id, code_version=code_version)
    with open_ingest_run(
        connection,
        source_id=source_id_for(SPINE_TABLE),
        raw_root=raw_root,
        environment=resolved,
    ) as run:
        return stage_all(run, tables=tables, batch_rows=batch_rows)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch the NM OCD tables, stage them from the raw zone, and promote the spine."
    )
    parser.add_argument("--dsn", required=True)
    half = parser.add_mutually_exclusive_group(required=True)
    half.add_argument("--fetch-only", action="store_true", help="pull the artifacts; stage nothing")
    half.add_argument(
        "--stage-only",
        action="store_true",
        help="stage the artifacts already in the raw zone; no socket is opened to the source",
    )
    half.add_argument(
        "--promote-only",
        action="store_true",
        help="promote the staged spine into canonical at the run's vintage",
    )
    parser.add_argument(
        "--tables",
        default=",".join(TABLES),
        help="comma-separated subset, so a failed pull resumes without re-fetching the rest",
    )
    parser.add_argument("--raw-root", default=None)
    parser.add_argument("--spacing-seconds", type=float, default=FETCH_SPACING_SECONDS)
    parser.add_argument("--batch-rows", type=int, default=None)
    parser.add_argument("--env-id", default=None)
    parser.add_argument("--code-version", default=None)
    parser.add_argument(
        "--window-start",
        default=None,
        help="ISO date overriding cr_nm_wcproduction_window_1; widening is a re-run (DIR-12)",
    )
    parser.add_argument(
        "--months", default=None, help="comma-separated YYYY-MM-01 months, in place of the window"
    )
    parser.add_argument(
        "--no-mod-dte-shortcut",
        action="store_true",
        help="compare every staged row against the head instead of skipping unchanged mod_dte",
    )
    arguments = parser.parse_args(argv)

    tables = [table.strip() for table in arguments.tables.split(",") if table.strip()]
    unknown = [table for table in tables if table not in TABLES]
    if unknown:
        parser.error(f"not an in-scope NM table: {unknown}")

    window_start = date.fromisoformat(arguments.window_start) if arguments.window_start else None
    months = (
        [date.fromisoformat(month.strip()) for month in arguments.months.split(",")]
        if arguments.months
        else None
    )

    with durable_fetch_attempts(arguments.dsn):
        return _execute_command(arguments, tables=tables, window_start=window_start, months=months)


def _execute_command(
    arguments: argparse.Namespace,
    *,
    tables: Sequence[str],
    window_start: date | None,
    months: Sequence[date] | None,
) -> int:
    connection = psycopg.connect(arguments.dsn)
    results: list[TableFetch] | list[StageReport] | list[PromotionReport]
    try:
        try:
            if arguments.promote_only:
                results = [
                    run_promote(
                        connection,
                        window_start=window_start,
                        months=months,
                        mod_dte_shortcut=not arguments.no_mod_dte_shortcut,
                        env_id=arguments.env_id,
                        code_version=arguments.code_version,
                    )
                ]
            elif arguments.stage_only:
                results = run_stage(
                    connection,
                    tables=tables,
                    raw_root=arguments.raw_root,
                    batch_rows=arguments.batch_rows,
                    env_id=arguments.env_id,
                    code_version=arguments.code_version,
                )
            else:
                results = run_fetch(
                    connection,
                    tables=tables,
                    raw_root=arguments.raw_root,
                    spacing_seconds=arguments.spacing_seconds,
                    env_id=arguments.env_id,
                    code_version=arguments.code_version,
                )
        except VintageAlreadyPromoted as refused:
            # promote_all discarded the diverging month and recorded the vintage for what the
            # months before it committed, so this is a safety net and not the withdrawal.
            connection.rollback()
            print(f"refused: {refused}", flush=True)
            return 2
        except OSError:
            # The raw.fetch_failed row is the halt's evidence; rolling back would leave the
            # ledger claiming the pull never happened (SB-01 §1.2).
            connection.commit()
            raise
        connection.commit()
    finally:
        connection.close()
    for result in results:
        print(json.dumps(result.to_dict(), sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
