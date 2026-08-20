"""Bitemporal vintage mechanics (SB-07 §3). Restatements are new vintages, never updates."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from glasswell.lineage.models import VintageRecord
from glasswell.lineage.serialization import json_ready

# S-E: the window partitions on the entity key, so a well's two pool filings are two heads and
# not one row shadowing the other. There is no tiebreak after report_vintage because there
# cannot be one: the primary key holds every column this window partitions and orders on, so a
# tie inside a partition is unrepresentable. A same-vintage re-promotion does not produce two
# rows to order - it is refused (VintageAlreadyPromoted).
_SELECT_PRODUCTION = """
select entity_type, entity_key, reporting_level, well_completion_pool, aggregation, api10,
       production_month, stream, source_id, report_vintage, volume, unit, days_produced,
       granularity, value_hash, source_manifest_id, derivation_id, null_semantics
  from (select p.*,
               row_number() over (
                   partition by entity_type, entity_key, production_month, stream, source_id
                   order by report_vintage desc) as vintage_rank
          from canonical.production_monthly p
         where (%(as_of)s::date is null or p.report_vintage <= %(as_of)s::date)
           and (%(api10)s::text is null or p.api10 = %(api10)s)
           and (%(entity_type)s::text is null or p.entity_type = %(entity_type)s)
           and (%(entity_key)s::text is null or p.entity_key = %(entity_key)s)
           and (%(well_completion_pool)s::text is null
                or p.well_completion_pool = %(well_completion_pool)s)
           and (%(stream)s::text is null or p.stream = %(stream)s)
           and (%(source_id)s::text is null or p.source_id = %(source_id)s)
           and (%(production_month)s::date is null
                or p.production_month = %(production_month)s::date)) ranked
 where vintage_rank = 1
 order by entity_type, entity_key, production_month, stream, source_id
"""


def select_production(
    connection: psycopg.Connection,
    *,
    as_of: date | None = None,
    api10: str | None = None,
    production_month: date | None = None,
    stream: str | None = None,
    source_id: str | None = None,
    entity_type: str | None = None,
    entity_key: str | None = None,
    well_completion_pool: str | None = None,
) -> list[dict[str, Any]]:
    """As-of semantics: greatest report_vintage <= as_of, per (entity, month, stream, source).

    `as_of=None` is the serving default — latest known state. `api10` selects a well's rows at
    every level, so a caller that wants the well's own series passes `entity_type='well'`.
    """
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            _SELECT_PRODUCTION,
            {
                "as_of": as_of,
                "api10": api10,
                "production_month": production_month,
                "stream": stream,
                "source_id": source_id,
                "entity_type": entity_type,
                "entity_key": entity_key,
                "well_completion_pool": well_completion_pool,
            },
        )
        return [dict(row) for row in cursor.fetchall()]


def open_vintage(
    connection: psycopg.Connection,
    *,
    source_id: str,
    vintage_date: date,
    manifest_ids: Sequence[str],
    opened_at: datetime,
    promotion_derivation_id: str | None = None,
    rows_examined: int = 0,
    rows_appended: int = 0,
    months_touched: Sequence[str] = (),
    restatement_summary: Mapping[str, int] | None = None,
) -> VintageRecord:
    """Record one (source, vintage) promotion — the row /explain and the ledger cite."""
    record = VintageRecord(
        vintage_id=f"vin_{source_id}_{vintage_date.isoformat()}",
        source_id=source_id,
        vintage_date=vintage_date,
        manifest_ids=list(manifest_ids),
        opened_at=opened_at,
        promotion_derivation_id=promotion_derivation_id,
        rows_examined=rows_examined,
        rows_appended=rows_appended,
        months_touched=list(months_touched),
        restatement_summary=dict(restatement_summary or {}),
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into lineage.vintages (vintage_id, source_id, vintage_date, manifest_ids,"
            " opened_at, promotion_derivation_id, rows_examined, rows_appended, months_touched,"
            " restatement_summary)"
            " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
            " on conflict (source_id, vintage_date) do update"
            " set manifest_ids = excluded.manifest_ids,"
            "     promotion_derivation_id = excluded.promotion_derivation_id,"
            "     rows_examined = excluded.rows_examined,"
            "     rows_appended = excluded.rows_appended,"
            "     months_touched = excluded.months_touched,"
            "     restatement_summary = excluded.restatement_summary",
            (
                record.vintage_id,
                record.source_id,
                record.vintage_date,
                list(record.manifest_ids),
                record.opened_at,
                record.promotion_derivation_id,
                record.rows_examined,
                record.rows_appended,
                list(record.months_touched),
                Jsonb(json_ready(dict(record.restatement_summary))),
            ),
        )
    return record
