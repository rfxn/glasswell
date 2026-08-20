"""Derivation persistence and the write-conflict rules that make the ID a determinism check."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

import psycopg
from psycopg.types.json import Jsonb

from glasswell.lineage.errors import DeterminismViolation
from glasswell.lineage.models import DerivationRecord
from glasswell.lineage.serialization import json_ready

RecordAction = Literal["insert", "update", "noop"]


@dataclass(frozen=True, slots=True)
class RecordOutcome:
    derivation_id: str
    created: bool


class DerivationRecorder(Protocol):
    def record(self, record: DerivationRecord) -> RecordOutcome: ...


def reconcile(
    *,
    existing_status: str | None,
    existing_sha256: str | None,
    incoming: DerivationRecord,
) -> RecordAction:
    """SB-07 §1.3: the content-addressed PK collides on a repeat run, so the store is the
    determinism detector."""
    if existing_status is None:
        return "insert"
    if existing_status == "failed":
        return "update" if incoming.status == "ok" else "noop"
    if incoming.status == "failed":
        return "noop"
    if (
        existing_sha256 is not None
        and incoming.output_sha256 is not None
        and existing_sha256 != incoming.output_sha256
    ):
        raise DeterminismViolation(incoming.derivation_id, existing_sha256, incoming.output_sha256)
    return "update" if existing_sha256 is None and incoming.output_sha256 is not None else "noop"


_INSERT_DERIVATION = """
insert into lineage.derivations (
    derivation_id, operation, output_store, output_dataset, output_partition, output_locator,
    output_sha256, output_rows, output_schema_version, params, params_hash, code_version,
    code_dirty, env_id, model_id, recipe_id, created_vintage, created_at, duration_ms,
    correlation_id, status, determinism_class, ttl_class)
values (%(derivation_id)s, %(operation)s, %(output_store)s, %(output_dataset)s,
        %(output_partition)s, %(output_locator)s, %(output_sha256)s, %(output_rows)s,
        %(output_schema_version)s, %(params)s, %(params_hash)s, %(code_version)s,
        %(code_dirty)s, %(env_id)s, %(model_id)s, %(recipe_id)s, %(created_vintage)s,
        %(created_at)s, %(duration_ms)s, %(correlation_id)s, %(status)s,
        %(determinism_class)s, %(ttl_class)s)
"""

_UPDATE_DERIVATION = """
update lineage.derivations
   set status = %(status)s, output_sha256 = %(output_sha256)s, output_rows = %(output_rows)s,
       output_locator = %(output_locator)s, duration_ms = %(duration_ms)s,
       created_at = %(created_at)s, correlation_id = %(correlation_id)s
 where derivation_id = %(derivation_id)s
"""


class PostgresRecorder:
    """Writes `lineage.derivations` and its edge tables through one connection."""

    def __init__(self, connection: psycopg.Connection) -> None:
        self._connection = connection

    def record(self, record: DerivationRecord) -> RecordOutcome:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "select status, output_sha256 from lineage.derivations where derivation_id = %s"
                " for update",
                (record.derivation_id,),
            )
            row = cursor.fetchone()
            action = reconcile(
                existing_status=row[0] if row else None,
                existing_sha256=row[1] if row else None,
                incoming=record,
            )
            if action == "noop":
                return RecordOutcome(record.derivation_id, False)

            parameters = record.model_dump()
            parameters["output_partition"] = Jsonb(json_ready(dict(record.output_partition)))
            parameters["params"] = Jsonb(json_ready(dict(record.params)))
            if action == "update":
                cursor.execute(_UPDATE_DERIVATION, parameters)
                cursor.execute(
                    "delete from lineage.derivation_inputs where derivation_id = %s",
                    (record.derivation_id,),
                )
                cursor.execute(
                    "delete from lineage.derivation_rules where derivation_id = %s",
                    (record.derivation_id,),
                )
            else:
                cursor.execute(_INSERT_DERIVATION, parameters)

            cursor.executemany(
                "insert into lineage.derivation_inputs"
                " (derivation_id, ord, kind, ref_id, selector, as_of_vintage, role)"
                " values (%s, %s, %s, %s, %s, %s, %s)",
                [
                    (
                        record.derivation_id,
                        ref.ord,
                        ref.kind,
                        ref.ref_id,
                        ref.selector,
                        ref.as_of_vintage,
                        ref.role,
                    )
                    for ref in record.inputs
                ],
            )
            cursor.executemany(
                "insert into lineage.derivation_rules (derivation_id, rule_id, applied_rows)"
                " values (%s, %s, %s)",
                [(record.derivation_id, r.rule_id, r.applied_rows) for r in record.rules],
            )
        return RecordOutcome(record.derivation_id, action == "insert")
