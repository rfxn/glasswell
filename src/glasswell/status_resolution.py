"""Read-time resolution of a canonical well status from the conformance registry.

`canonical.wells.status_canonical` is null for every New Mexico header and stays that way: the
table is append-only and a re-promotion would have to invent a valid time the OCD never filed
(cr_nm_wellhistory_status_vocab_2). The class is therefore a join, and it lives here rather
than at any one call site so that the tile mart, the well card and the status summary cannot
answer differently on the same screen.

The invariant is one shared resolver, never a second mapping in the API: the tile mart and
every serving path read `canonical.status_resolution`, and no surface translates a status code
on its own. A mart-only resolver would leave the API serving null; an API-only one would leave
the tiles serving null. Neither is what shipped.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from glasswell.lineage.jurisdictions import load_jurisdictions
from glasswell.lineage.status_classes import mapped_status_classes

RESOLVER_VIEW = "canonical.status_resolution"

# The class where neither the promotion nor the registry resolves one. Spelled once, and only
# where a caller has no connection to read the domain with: `lineage.status_classes` is the
# single writer, `ABSENCE_CLASS_SQL` is how every serving path reads it, and the seed carries
# this name into the row marked `is_absence` rather than repeating the word.
UNMAPPED_CLASS = "unmapped"

# How every serving path reads that name: a one-row uncorrelated scalar subselect on the domain.
# `resolved_status()` is a pure string builder called at query-assembly time from eight sites, so
# a connection parameter would change all eight signatures; a module constant would be the
# literal the domain exists to replace; a process cache would be the unbounded one the v0.76
# sentinel filed. The subselect keeps the signature, keeps lineage.status_classes as the single
# writer, and turns an empty domain into a null class that infra/verify.sh V-3 catches.
ABSENCE_CLASS_SQL = "(select status_canonical from lineage.status_classes where is_absence)"

# A jurisdiction resolves at read time when its registered status-vocabulary rule says so in
# its own spec, which is where 071 put the fact. Read off the registry rather than pinned here:
# a fifth state with read-time resolution is a `jurisdiction_rules` row and this answers for it
# without an edit. The mapping *table* is still per-regulator and still arrives in a migration
# — no row can conjure one — but which jurisdiction it answers for is registry data.
READ_TIME = "read_time"

_RESOLVER_RULES = """
select j.identity_prefix, r.rule_id
  from lineage.jurisdictions_as_of(%(knowledge_as_of)s, %(valid_as_of)s) j
  join lineage.jurisdiction_rules r
    on r.jurisdiction_code = j.jurisdiction_code
   and r.effective_from = j.effective_from
   and r.published_at = j.published_at
   and r.decision = 'status_vocabulary'
   and r.serving
  join lineage.conformance_rules c on c.rule_id = r.rule_id
 where j.identity_prefix is not null
   and c.spec->>'resolved_at' = %(read_time)s
 order by j.identity_prefix
"""


# The per-map scan, kept as the parity gate's input rather than as the definition. Every
# registered vocabulary names the table its classes live in and the column they live under, in
# the rule's own spec, so this is what a standing gate compares the domain against: a map
# producing a class the domain does not hold, or a domain row no map produces.
_VOCABULARY_SOURCES = """
select j.jurisdiction_code,
       r.rule_id,
       c.spec->>'resolved_at'     as resolved_at,
       c.spec->>'unmapped_action' as unmapped_action,
       c.spec->>'mapping_table'   as mapping_table,
       c.spec->>'value_col'       as value_col
  from lineage.jurisdictions_as_of(%(knowledge_as_of)s, %(valid_as_of)s) j
  join lineage.jurisdiction_rules r
    on r.jurisdiction_code = j.jurisdiction_code
   and r.effective_from = j.effective_from
   and r.published_at = j.published_at
   and r.decision = 'status_vocabulary'
   and r.serving
  join lineage.conformance_rules c on c.rule_id = r.rule_id
 where c.spec->>'mapping_table' is not null
   and c.spec->>'value_col' is not null
 order by j.jurisdiction_code
"""


@dataclass(frozen=True, slots=True)
class JurisdictionVocabulary:
    """One registration's status vocabulary as the wire serves it."""

    jurisdiction_code: str
    rule_id: str
    resolved_at: str | None
    unmapped_action: str | None
    classes: tuple[str, ...]


def served_status_vocabulary(
    connection: psycopg.Connection, as_of: date | None = None
) -> list[str]:
    """Every canonical class a registered mapping may target, in one sorted list.

    Read from `lineage.status_classes`, which is the domain every map has a foreign key to,
    rather than unioned over the maps: a class is a decision with a rule and an effective date,
    and a list computed from whatever the maps happen to say cannot be one. The absence class is
    not in it, because no mapping produces it. A caller measuring classes wants both and adds it.

    `as_of` is unread and kept: the domain carries one clock by construction (a class that stops
    existing has to be repointed in every map that names it inside one transaction), and eight
    callers pass the registry's own cut.
    """
    return sorted(mapped_status_classes(connection))


def served_vocabularies(
    connection: psycopg.Connection, as_of: date | None = None
) -> tuple[JurisdictionVocabulary, ...]:
    """Each registration's vocabulary: its rule, its two spec keys, and what its map produces.

    The classes are read from the registered mapping table rather than from the domain, because
    what this answers is which of the domain's classes *this* regulator can file. North Dakota
    is the only one that produces `confidential`, and that is a fact about its codebook.
    """
    registry = load_jurisdictions(connection, as_of)
    with connection.cursor() as cursor:
        cursor.execute(
            _VOCABULARY_SOURCES,
            {
                "knowledge_as_of": registry.knowledge_as_of,
                "valid_as_of": registry.valid_as_of,
            },
        )
        sources = cursor.fetchall()
    served: list[JurisdictionVocabulary] = []
    with connection.cursor() as cursor:
        for code, rule_id, resolved_at, unmapped_action, table, column in sources:
            # Identifiers, so a registered table name cannot be a parameter and cannot be
            # concatenated: the rule spec is data, and data does not compose SQL here.
            cursor.execute(
                sql.SQL("select distinct {column} from {table} where {column} is not null")
                .format(column=sql.Identifier(column), table=sql.Identifier("lineage", table))
            )
            served.append(
                JurisdictionVocabulary(
                    jurisdiction_code=code,
                    rule_id=rule_id,
                    resolved_at=resolved_at,
                    unmapped_action=unmapped_action,
                    classes=tuple(sorted(str(value) for (value,) in cursor.fetchall())),
                )
            )
    return tuple(served)


def status_map_classes(
    connection: psycopg.Connection, as_of: date | None = None
) -> list[str]:
    """Every distinct class the registered mapping tables actually produce, sorted.

    The parity gate's input, and the reason `served_status_vocabulary` can stop being a union:
    a class here and not in the domain is a map with no published decision behind it, and a
    mapped domain row absent here is a class registered for a state that never landed.
    """
    return sorted(
        {
            status
            for vocabulary in served_vocabularies(connection, as_of)
            for status in vocabulary.classes
        }
    )


def resolver_rules(
    connection: psycopg.Connection, as_of: date | None = None
) -> dict[str, str]:
    """API state code -> the rule that resolves its status at read time, for those that do."""
    registry = load_jurisdictions(connection, as_of)
    with connection.cursor() as cursor:
        cursor.execute(
            _RESOLVER_RULES,
            {
                "knowledge_as_of": registry.knowledge_as_of,
                "valid_as_of": registry.valid_as_of,
                "read_time": READ_TIME,
            },
        )
        return dict(cursor.fetchall())


# A registration whose status vocabulary resolves at read time, and no resolved row for it.
# `refresh_status_resolution()` skips a registration whose mapping table has not landed rather
# than aborting -- a refresh that raised would take the migration, or the deploy's seed that
# calls it, down with it -- and the transient case self-heals inside one deploy. The
# non-transient one does not: a `mapping_table` misspelt in a rule spec, or a map renamed by a
# later migration, draws that jurisdiction's whole spine in the unmapped class with no signal.
# This is the signal; `/v1/status` serves it and `infra/verify.sh` asserts on it.
_UNRESOLVED_READ_TIME = """
select j.jurisdiction_code, j.identity_prefix, j.name,
       c.spec->>'mapping_table' as mapping_table,
       to_regclass('lineage.' || quote_ident(c.spec->>'mapping_table')) is null as map_absent
  from lineage.jurisdictions_as_of(%(knowledge_as_of)s, %(valid_as_of)s) j
  join lineage.jurisdiction_rules r
    on r.jurisdiction_code = j.jurisdiction_code
   and r.effective_from = j.effective_from
   and r.published_at = j.published_at
   and r.decision = 'status_vocabulary'
   and r.serving
  join lineage.conformance_rules c on c.rule_id = r.rule_id
 where j.identity_prefix is not null
   and c.spec->>'resolved_at' = %(read_time)s
   and not exists (select 1 from lineage.status_resolution_resolved s
                    where s.for_state_code = j.identity_prefix)
 order by j.identity_prefix
"""


def unresolved_read_time_jurisdictions(
    connection: psycopg.Connection, as_of: date | None = None
) -> list[dict[str, object]]:
    """Every jurisdiction the registry says resolves at read time and the resolver has no row for.

    Empty is the healthy answer. A non-empty one is a served class nobody is computing.
    """
    registry = load_jurisdictions(connection, as_of)
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            _UNRESOLVED_READ_TIME,
            {
                "knowledge_as_of": registry.knowledge_as_of,
                "valid_as_of": registry.valid_as_of,
                "read_time": READ_TIME,
            },
        )
        return cursor.fetchall()


def resolver_join(spine: str, *, resolver: str = "sr") -> str:
    """Left join `spine` onto the resolver on its state code and reported status."""
    return (
        f" left join {RESOLVER_VIEW} {resolver}"
        f" on {resolver}.for_state_code = {spine}.state_code"
        f" and {resolver}.for_status_reported = {spine}.status_reported"
    )


def resolved_status(spine: str, *, resolver: str = "sr") -> str:
    """The served class: what the promotion wrote, else what the registry resolves, else absent.

    Never null. Null is indistinguishable from not-yet-loaded to every consumer, which is what
    blueprint §3.0.1a forbids and what every Texas well that filed no status code has been
    served since Texas landed. The third arm is one line in the one helper the tile mart, the
    facet, the filter, the count and the card all call, so they change together or not at all.
    """
    return (
        f"coalesce({spine}.status_canonical, {resolver}.resolved_status, {ABSENCE_CLASS_SQL})"
    )
