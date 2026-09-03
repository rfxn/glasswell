"""The canonical status class domain as the serving path reads it: rows, refused when absent.

`lineage.status_classes` is the single writer of a class name, its symbology and its legend
order. Every registered status map targets it through a foreign key, so the domain is a
constraint rather than a sixth copy of a list.

An empty domain is a refusal and never a default, for the reason `load_jurisdictions` refuses an
empty registry: the definition is rows, so a missing definition is a service fault. A default
here would be a class every well on the map is drawn by, with no decision behind it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import psycopg
from psycopg.rows import dict_row

from glasswell.lineage.errors import LineageError


class StatusClassDomainError(LineageError):
    """R8: the domain is rows, so a missing domain is a refusal, never an assumed default."""


@dataclass(frozen=True, slots=True)
class StatusClass:
    status_canonical: str
    label: str
    colour: str
    glyph: str
    min_zoom: int
    sort_order: int
    is_absence: bool
    note: str
    rule_id: str
    effective_from: date
    published_at: date
    rationale: str


_DOMAIN = """
select status_canonical, label, colour, glyph, min_zoom, sort_order, is_absence, note,
       rule_id, effective_from, published_at, rationale
  from lineage.status_classes
 order by sort_order
"""

_FIELDS = tuple(StatusClass.__dataclass_fields__)


def load_status_classes(connection: psycopg.Connection) -> tuple[StatusClass, ...]:
    """Every class the domain declares, in legend order. Refuses an empty domain."""
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(_DOMAIN)
        rows = cursor.fetchall()
    if not rows:
        raise StatusClassDomainError(
            "lineage.status_classes holds no row: the canonical status class domain is"
            " unloaded, so no well can be served a class that cites a decision"
        )
    return tuple(StatusClass(**{name: row[name] for name in _FIELDS}) for row in rows)


def absence_class(connection: psycopg.Connection) -> str:
    """The one class no mapping produces. Refuses rather than guessing a name for it."""
    domain = load_status_classes(connection)
    absent = [row.status_canonical for row in domain if row.is_absence]
    if len(absent) != 1:
        raise StatusClassDomainError(
            f"lineage.status_classes declares {len(absent)} absence classes, not one:"
            " the class a well with no resolvable status is served as has no single name"
        )
    return absent[0]


def mapped_status_classes(connection: psycopg.Connection) -> tuple[str, ...]:
    """The classes a registered map may target, in legend order: the domain less the absence."""
    return tuple(
        row.status_canonical for row in load_status_classes(connection) if not row.is_absence
    )
