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

from datetime import date

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from glasswell.lineage.jurisdictions import load_jurisdictions

RESOLVER_VIEW = "canonical.status_resolution"

# The class where neither the promotion nor the registry resolves one: the source filed no
# status. Not documented_unmapped, which is a code the regulator did publish and glasswell has
# no word for. The canvas already coalesces a null status to this name, so the ledger uses it.
UNMAPPED_CLASS = "unmapped"

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


# Every registered vocabulary names the table its classes live in and the column they live
# under, in the rule's own spec (`vocab_map`). The canonical class list is therefore registry
# data rather than a roster: a fifth jurisdiction's classes join the vocabulary through its
# rule row, and a class renamed in one map is renamed here without an edit. This is the same
# list the client's closed eleven come from -- each of `web/src/map/status.ts`'s classes cites
# one of these rules -- so the two cannot drift apart silently.
_VOCABULARY_SOURCES = """
select distinct c.spec->>'mapping_table' as mapping_table,
                c.spec->>'value_col'     as value_col
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
 order by 1, 2
"""


def served_status_vocabulary(
    connection: psycopg.Connection, as_of: date | None = None
) -> list[str]:
    """Every canonical class the registered status vocabularies name, in one sorted list.

    The absence class is not in it: no mapping produces `unmapped`, which is what makes it the
    absence class. A caller measuring classes wants both and adds it.
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
    classes: set[str] = set()
    with connection.cursor() as cursor:
        for table, column in sources:
            # Identifiers, so a registered table name cannot be a parameter and cannot be
            # concatenated: the rule spec is data, and data does not compose SQL here.
            cursor.execute(
                sql.SQL("select distinct {column} from {table} where {column} is not null")
                .format(column=sql.Identifier(column), table=sql.Identifier("lineage", table))
            )
            classes.update(str(value) for (value,) in cursor.fetchall())
    return sorted(classes)


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
    """The served class: what the promotion wrote, else what the registry resolves."""
    return f"coalesce({spine}.status_canonical, {resolver}.resolved_status)"
