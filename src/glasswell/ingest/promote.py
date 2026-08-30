"""Bitemporal append to canonical.production_monthly, parameterised by source.

The rules here are the ones SB-07 §3.2 states once for every source: append only what changed,
never overwrite a row already recorded at the same vintage, and read heads only for the
entity-months in hand. `nd_mpr` still carries its own copies bound to a module-level
SOURCE_ID; consolidating the two is a follow-up that must not ride along with a new state.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import psycopg

from glasswell.lineage.errors import VintageAlreadyPromoted
from glasswell.lineage.serialization import hash_payload

_HEADS_IN_SCOPE = """
select entity_type, entity_key, production_month, stream, value_hash, reporting_level,
       aggregation
  from canonical.production_monthly_latest
 where source_id = %(source_id)s and entity_key = any(%(entity_keys)s::text[])
   and production_month = any(%(months)s::date[])
"""

_ROWS_AT_VINTAGE = """
select entity_type, entity_key, production_month, stream, value_hash, reporting_level,
       aggregation
  from canonical.production_monthly
 where source_id = %(source_id)s and report_vintage = %(report_vintage)s
   and entity_key = any(%(entity_keys)s::text[])
   and production_month = any(%(months)s::date[])
"""

_INSERT_CANONICAL = """
insert into canonical.production_monthly (
    entity_type, entity_key, reporting_level, well_completion_pool, aggregation,
    api10, production_month, stream, source_id, report_vintage, volume, unit, days_produced,
    granularity, value_hash, source_manifest_id, derivation_id, null_semantics)
values (%(entity_type)s, %(entity_key)s, %(reporting_level)s, %(well_completion_pool)s,
        %(aggregation)s, %(api10)s, %(production_month)s, %(stream)s, %(source_id)s,
        %(report_vintage)s, %(volume)s, %(unit)s, %(days_produced)s, %(granularity)s,
        %(value_hash)s, %(source_manifest_id)s, %(derivation_id)s, %(null_semantics)s)
"""


def classify_null_semantics(volume: Decimal | None, *, confidential: bool = False) -> str:
    """Absent, zero and withheld are three facts, never collapsed."""
    if volume is None:
        return "withheld" if confidential else "no_report"
    return "reported_zero" if volume == 0 else "reported"


def value_hash(
    volume: Decimal | None,
    unit: str | None,
    days: int | None,
    semantics: str,
    granularity: str,
) -> str:
    """Covers the measured value only, exactly as migration 008 defined it.

    Widening it to the entity columns re-appends every unchanged row at a new vintage, which
    the ledger would publish as a restatement that never happened.
    """
    return hash_payload(
        {
            "volume": volume,
            "unit": unit,
            "days_produced": days,
            "granularity": granularity,
            "null_semantics": semantics,
        }
    )


def record(
    *,
    entity_type: str,
    entity_key: str,
    reporting_level: str,
    well_completion_pool: str | None,
    aggregation: str | None,
    api10: str | None,
    production_month: date,
    stream: str,
    volume: Decimal | None,
    unit: str | None,
    days: int | None,
    semantics: str,
    granularity: str,
) -> dict[str, Any]:
    return {
        "entity_type": entity_type,
        "entity_key": entity_key,
        "reporting_level": reporting_level,
        "well_completion_pool": well_completion_pool,
        "aggregation": aggregation,
        "api10": api10,
        "production_month": production_month,
        "stream": stream,
        # canonical.volume is NOT NULL, so an absent volume is carried as zero and
        # null_semantics is what distinguishes it from a reported zero.
        "volume": volume if volume is not None else Decimal(0),
        "unit": unit,
        "days_produced": days,
        "granularity": granularity,
        "value_hash": value_hash(volume, unit, days, semantics, granularity),
        "null_semantics": semantics,
    }


def head_key(entry: Mapping[str, Any]) -> tuple[str, str, date, str]:
    return (entry["entity_type"], entry["entity_key"], entry["production_month"], entry["stream"])


def change_key(entry: Mapping[str, Any]) -> tuple[str, str | None, str | None]:
    """What has to differ before a row is worth appending.

    `value_hash` alone is not enough: a rollup that happens to equal the row it supersedes
    hashes identically, and dropping it would leave the old undisclosed row as the head.
    """
    return (entry["value_hash"], entry["reporting_level"], entry["aggregation"])


@dataclass(frozen=True, slots=True)
class ScopedHeads:
    """The heads for one promotion's entity-months. A lookup outside them refuses."""

    by_key: dict[tuple[str, str, date, str], tuple[str, str | None, str | None]]
    entity_months: frozenset[tuple[str, date]]

    def head_of(self, entry: Mapping[str, Any]) -> tuple[str, str | None, str | None] | None:
        pair = (entry["entity_key"], entry["production_month"])
        if pair not in self.entity_months:
            raise LookupError(
                f"{pair} is outside the head scope this read covered; answering it as absent"
                " would append a restatement as a first observation"
            )
        return self.by_key.get(head_key(entry))

    def holds(self, entry: Mapping[str, Any]) -> bool:
        return self.head_of(entry) is not None


def _scoped_heads(
    connection: psycopg.Connection,
    statement: str,
    records: Sequence[Mapping[str, Any]],
    *,
    source_id: str,
    **parameters: Any,
) -> ScopedHeads:
    """Read heads for exactly the entity-months `records` covers, never for all of canonical."""
    entity_months = frozenset(
        (entry["entity_key"], entry["production_month"]) for entry in records
    )
    if not entity_months:
        return ScopedHeads(by_key={}, entity_months=entity_months)
    with connection.cursor() as cursor:
        cursor.execute(
            statement,
            {
                "source_id": source_id,
                "entity_keys": sorted({key for key, _ in entity_months}),
                "months": sorted({month for _, month in entity_months}),
                **parameters,
            },
        )
        # Iterated rather than fetchall(): the list would hold every row a second time.
        by_key = {(r[0], r[1], r[2], r[3]): (r[4], r[5], r[6]) for r in cursor}
    return ScopedHeads(by_key=by_key, entity_months=entity_months)


def current_heads(
    connection: psycopg.Connection, records: Sequence[Mapping[str, Any]], *, source_id: str
) -> ScopedHeads:
    return _scoped_heads(connection, _HEADS_IN_SCOPE, records, source_id=source_id)


def unchanged_removed(
    records: Sequence[Mapping[str, Any]], heads: ScopedHeads
) -> list[dict[str, Any]]:
    """Change-only append: the PK carries the vintage, so the head check is here."""
    return [dict(entry) for entry in records if heads.head_of(entry) != change_key(entry)]


def reject_same_vintage_divergence(
    connection: psycopg.Connection,
    records: Sequence[Mapping[str, Any]],
    *,
    source_id: str,
    report_vintage: date,
) -> list[dict[str, Any]]:
    """Return the rows that can land at this vintage; raise if any would have to overwrite one.

    A repeat run that computes what is already recorded is a no-op, and one that computes
    something else is an error rather than a silent `on conflict do nothing`.
    """
    if not records:
        return []
    occupied = _scoped_heads(
        connection,
        _ROWS_AT_VINTAGE,
        records,
        source_id=source_id,
        report_vintage=report_vintage,
    )
    landable: list[dict[str, Any]] = []
    divergent: list[str] = []
    for entry in records:
        existing = occupied.head_of(entry)
        if existing is None:
            landable.append(dict(entry))
        elif existing != change_key(entry):
            divergent.append(
                f"{entry['entity_type']} {entry['entity_key']} {entry['production_month']}"
                f" {entry['stream']}: recorded {existing}, computed {change_key(entry)}"
            )
    if divergent:
        raise VintageAlreadyPromoted(
            "canonical.production_monthly", report_vintage, len(divergent), divergent[0]
        )
    return landable


def append_canonical(
    connection: psycopg.Connection,
    records: Sequence[Mapping[str, Any]],
    *,
    source_id: str,
    manifest_id: str,
    derivation_id: str,
    report_vintage: date,
) -> None:
    if not records:
        return
    with connection.cursor() as cursor:
        cursor.executemany(
            _INSERT_CANONICAL,
            [
                {
                    **entry,
                    "source_id": source_id,
                    "report_vintage": report_vintage,
                    "source_manifest_id": manifest_id,
                    "derivation_id": derivation_id,
                }
                for entry in records
            ],
        )
