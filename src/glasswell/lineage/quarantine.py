"""Quarantine writes (SB-07 §8). Rejected rows are recorded with a reason, never dropped."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import polars as pl
import psycopg
from psycopg.types.json import Jsonb

from glasswell.lineage.audit import emit
from glasswell.lineage.ids import new_ulid
from glasswell.lineage.serialization import canonical_json, hash_payload, json_ready

PAYLOAD_CAP_BYTES = 8192


@dataclass(frozen=True, slots=True)
class QuarantineResult:
    opened: int
    reoccurred: int


_UPSERT = """
insert into lineage.quarantine_rows (
    quarantine_id, row_fingerprint, source_id, staging_table, stage, reason_code, rule_id,
    row_payload, first_seen_at, first_seen_manifest_id, last_seen_at, last_seen_manifest_id)
values (%(quarantine_id)s, %(row_fingerprint)s, %(source_id)s, %(staging_table)s, %(stage)s,
        %(reason_code)s, %(rule_id)s, %(row_payload)s, %(seen_at)s, %(manifest_id)s,
        %(seen_at)s, %(manifest_id)s)
on conflict (row_fingerprint, reason_code, rule_id) do update
   set last_seen_at = excluded.last_seen_at,
       last_seen_manifest_id = excluded.last_seen_manifest_id,
       occurrence_count = lineage.quarantine_rows.occurrence_count + 1
returning (xmax = 0) as inserted
"""


def quarantine(
    connection: psycopg.Connection,
    rows: pl.DataFrame,
    *,
    reason_code: str,
    manifest_id: str,
    source_id: str,
    staging_table: str,
    stage: str,
    seen_at: datetime,
    rule_id: str | None = None,
    correlation_id: str | None = None,
) -> QuarantineResult:
    """Fingerprint-deduped: a row rejected nightly for a year is one entry with a counter."""
    opened = 0
    reoccurred = 0
    with connection.cursor() as cursor:
        for row in rows.iter_rows(named=True):
            payload = json_ready(row)
            if len(canonical_json(payload)) > PAYLOAD_CAP_BYTES:
                payload = {"oversized": True, "manifest_id": manifest_id, "columns": list(row)}
            cursor.execute(
                _UPSERT,
                {
                    "quarantine_id": "qtn_" + new_ulid(seen_at),
                    "row_fingerprint": hash_payload(json_ready(row)),
                    "source_id": source_id,
                    "staging_table": staging_table,
                    "stage": stage,
                    "reason_code": reason_code,
                    "rule_id": rule_id,
                    "row_payload": Jsonb(payload),
                    "seen_at": seen_at,
                    "manifest_id": manifest_id,
                },
            )
            result = cursor.fetchone()
            if result is not None and result[0]:
                opened += 1
            else:
                reoccurred += 1

    payload = {"reason_code": reason_code, "rule_id": rule_id, "manifest_id": manifest_id}
    for event_type, count in (("quarantine.opened", opened), ("quarantine.reoccurred", reoccurred)):
        if count:
            emit(
                connection,
                event_type,
                subject_type="quarantine",
                subject_id=staging_table,
                payload={**payload, "rows": count},
                correlation_id=correlation_id,
                occurred_at=seen_at,
            )
    return QuarantineResult(opened=opened, reoccurred=reoccurred)
