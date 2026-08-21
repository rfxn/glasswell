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
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import zipfile
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import chain
from pathlib import Path
from typing import IO, Any

import polars as pl
import psycopg
from psycopg.rows import dict_row

from glasswell.ingest.base import IngestRun, open_ingest_run, resolve_environment
from glasswell.ingest.xml_stream import stream_records
from glasswell.lineage.audit import emit
from glasswell.lineage.capture import derive
from glasswell.lineage.conformance import ConformanceRule, QuarantineBatch, apply_rules, load_rules
from glasswell.lineage.errors import RuleSpecError
from glasswell.lineage.fetch import fetch_raw
from glasswell.lineage.ftp import FTP, FtpTransferFailed, close_ftp, connect_ftp, ftp_url
from glasswell.lineage.models import InputRef, ManifestRecord, OutputSpec
from glasswell.lineage.quarantine import quarantine
from glasswell.lineage.serialization import hash_payload
from glasswell.staging.duck import PartitionWrite, partition_uri, write_partition

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
) -> None:
    for batch in batches:
        reason = batch.reason_code if batch.reason_code in vocabulary else UNREGISTERED_REASON
        capped = batch.frame.height > QUARANTINE_BATCH_CAP
        recorded = batch.frame.head(QUARANTINE_BATCH_CAP) if capped else batch.frame
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
        description="Fetch the NM OCD tables into the raw zone, and stage them from it."
    )
    parser.add_argument("--dsn", required=True)
    half = parser.add_mutually_exclusive_group(required=True)
    half.add_argument("--fetch-only", action="store_true", help="pull the artifacts; stage nothing")
    half.add_argument(
        "--stage-only",
        action="store_true",
        help="stage the artifacts already in the raw zone; no socket is opened to the source",
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
    arguments = parser.parse_args(argv)

    tables = [table.strip() for table in arguments.tables.split(",") if table.strip()]
    unknown = [table for table in tables if table not in TABLES]
    if unknown:
        parser.error(f"not an in-scope NM table: {unknown}")

    connection = psycopg.connect(arguments.dsn)
    results: list[TableFetch] | list[StageReport]
    try:
        try:
            if arguments.stage_only:
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
