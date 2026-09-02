"""The two costs a facet over every jurisdiction paid, and the rule that names the third.

`web/PERF.md` §7 is the measurement; this is the shape that measurement depends on. Both
assertions are about the plan the deployed database can reach, so both are written against a
relation and an index rather than against a timing, which no fixture can reproduce.
"""

from __future__ import annotations

import psycopg
import pytest

from glasswell.api.routers.facets import _FACETS, _SCOPED_LATEST, _VALUE_SORTS, DIMENSIONS

pytestmark = pytest.mark.integration

FACET_INDEX = "wells_facet_dimensions_idx"


def _indexdef(connection: psycopg.Connection, name: str) -> str:
    with connection.cursor() as cursor:
        cursor.execute(
            "select pg_get_indexdef(c.oid) from pg_class c"
            " join pg_namespace n on n.oid = c.relnamespace"
            " where c.relname = %s and n.nspname = 'canonical'",
            (name,),
        )
        row = cursor.fetchone()
    assert row is not None, f"{name} is not present"
    return str(row[0])


def _status_facet_plan(connection: psycopg.Connection) -> str:
    """The exact statement `get_well_facets` emits for the one dimension that joins."""
    scoped = _SCOPED_LATEST.format(
        column=DIMENSIONS["status"]["column"], join=DIMENSIONS["status"].get("join", "")
    )
    statement = _FACETS.format(scoped=scoped, order=_VALUE_SORTS[("count", "desc")])
    with connection.cursor() as cursor:
        # A fixture holds tens of rows, where a sequential scan -- or a bitmap over two of
        # them -- is genuinely cheaper and the planner is right to take it. Turning both off is
        # what makes the assertions below claims about the index rather than about the
        # fixture's size. Neither is set on the serving path; at 809,191 rows the planner
        # reaches this plan on its own (web/PERF.md section 7).
        cursor.execute("set local enable_seqscan = off")
        cursor.execute("set local enable_bitmapscan = off")
        cursor.execute(
            f"explain {statement}",
            {"states": ["33", "42"], "as_of": None, "q": None, "top": 15},
        )
        return "\n".join(str(row[0]) for row in cursor.fetchall())


def test_the_covering_index_carries_the_reported_status(db: psycopg.Connection) -> None:
    """The status dimension resolves through a join on `status_reported`, so a covering list
    without it costs the facet its index-only scan — 296,762 buffers of heap at four states on
    the deployed load, against 12,778 for every other dimension."""
    definition = _indexdef(db, FACET_INDEX)

    assert "INCLUDE" in definition
    include = definition.split("INCLUDE", 1)[1]
    for column in (
        "operator_name_reported",
        "county_code_at_permit",
        "status_canonical",
        "status_reported",
        "well_type_reported",
        "completion_date",
        "derivation_id",
    ):
        assert column in include, column


def test_the_status_facet_reads_the_covering_index_rather_than_the_heap(
    db: psycopg.Connection,
) -> None:
    """The plan the INCLUDE buys. A plain `Index Scan` here is the defect: it means a heap visit
    per spine row for a column the index could have carried."""
    plan = _status_facet_plan(db)

    assert f"Index Only Scan using {FACET_INDEX}" in plan, plan


def test_the_resolver_is_reached_by_lookup_rather_than_by_scanning_it(
    db: psycopg.Connection,
) -> None:
    """The plan the keyed relation buys, and the whole of (b): one index probe per spine row
    against a relation the planner knows the size and the order of, instead of a merge on
    `state_code` alone with the reported code left to a join filter."""
    plan = _status_facet_plan(db)

    assert "status_resolution_resolved_pkey" in plan, plan
    assert "Rows Removed by Join Filter" not in plan, plan


def test_the_resolver_can_be_looked_up_by_both_keys(db: psycopg.Connection) -> None:
    """A view over a window function gives the planner no index and no order, so over a set of
    states it merged on `state_code` alone and filtered the reported code — 4,179,636 rows
    removed by that filter on the deployed load. A keyed relation is what makes it a lookup."""
    with db.cursor() as cursor:
        cursor.execute(
            "select i.indisprimary,"
            "       array_agg(a.attname order by k.ord)"
            "  from pg_index i"
            "  join pg_class c on c.oid = i.indrelid"
            "  join pg_namespace n on n.oid = c.relnamespace"
            "  join lateral unnest(i.indkey) with ordinality as k(attnum, ord) on true"
            "  join pg_attribute a on a.attrelid = c.oid and a.attnum = k.attnum"
            " where n.nspname = 'lineage' and c.relname = 'status_resolution_resolved'"
            "   and (i.indisprimary or i.indisunique)"
            " group by i.indexrelid, i.indisprimary"
        )
        keyed = {tuple(row[1]) for row in cursor.fetchall()}

    assert ("for_state_code", "for_status_reported") in keyed, keyed


def test_the_resolver_matches_the_registry_it_was_built_from(db: psycopg.Connection) -> None:
    """Materialised data with no authority of its own has one obligation: to equal its source.

    Read-time resolution was exact by construction before this; now it is exact by refresh, and
    this is the gate that says so.
    """
    with db.cursor() as cursor:
        cursor.execute(
            "select for_state_code, for_status_reported, resolved_status"
            "  from canonical.status_resolution"
            " except"
            " select j.identity_prefix, m.status, m.status_canonical"
            "   from lineage.nm_wellhistory_status_map m"
            "   join lineage.jurisdictions_as_of(current_date, current_date) j"
            "     on j.jurisdiction_code = 'NM'"
            "  where j.identity_prefix is not null"
        )
        extra = cursor.fetchall()
        cursor.execute(
            "select j.identity_prefix, m.status, m.status_canonical"
            "  from lineage.nm_wellhistory_status_map m"
            "  join lineage.jurisdictions_as_of(current_date, current_date) j"
            "    on j.jurisdiction_code = 'NM'"
            " where j.identity_prefix is not null"
            " except"
            " select for_state_code, for_status_reported, resolved_status"
            "   from canonical.status_resolution"
        )
        missing = cursor.fetchall()

    with db.cursor() as cursor:
        cursor.execute("select count(*) from canonical.status_resolution")
        resolved = int(cursor.fetchone()[0])

    # A resolver that resolves nothing satisfies both differences by vacuity, and the registry
    # this fixture carries is the migration's own.
    assert resolved > 0
    assert extra == []
    assert missing == []


def test_appending_to_the_status_map_reaches_the_resolver(db: psycopg.Connection) -> None:
    """Both sources are append-only, so an append is the only way their content can change and
    a statement trigger on it is exact. Without the refresh the resolver is a stale copy."""
    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.nm_wellhistory_status_map"
            " (status, decode, status_canonical, published_vintage)"
            " values ('Y', 'Planted by the suite', 'inactive', current_date)"
        )
        cursor.execute(
            "select resolved_status from canonical.status_resolution"
            " where for_status_reported = 'Y'"
        )
        resolved = cursor.fetchall()
    db.rollback()

    assert [row[0] for row in resolved] == ["inactive"]

