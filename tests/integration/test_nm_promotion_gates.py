"""G7-2's container-side half: the index the New Mexico promotion must not cost North Dakota.

The deployed gate reads `Index Scan using production_monthly_api10_idx` out of an
`explain (analyze, buffers)` on a real API-10, and it is a merge blocker because a Seq Scan over
24.8M rows on the served path is the failure mode adding 17.6M New Mexico rows creates. That
assertion cannot run in CI — a fixture-sized table has no reason to prefer an index.

What *can* run here is everything the deployed gate depends on and nothing else asserts:
the index exists, it leads on `api10`, and the served query resolves to it once a sequential
scan stops being free. The predicate-placement property those rest on is already pinned by
`test_nm_dims.py::test_both_the_served_query_and_the_latest_view_filter_below_the_window`; it is
referenced here rather than restated.
"""

from __future__ import annotations

import psycopg
import pytest

from glasswell.ingest import nm_dims
from glasswell.lineage.vintages import _SELECT_PRODUCTION

pytestmark = pytest.mark.integration

INDEX = "production_monthly_api10_idx"
VIEW_PROBE = "select * from canonical.production_monthly_latest where api10 = '3305301633'"


def _plan(db: psycopg.Connection, sql: str) -> dict:
    with db.cursor() as cursor:
        cursor.execute("set local enable_seqscan = off")
        cursor.execute(f"explain (format json) {sql}")
        return cursor.fetchone()[0][0]["Plan"]


def _index_names(plan: dict) -> set[str]:
    names = {plan["Index Name"]} if "Index Name" in plan else set()
    for child in plan.get("Plans", []):
        names |= _index_names(child)
    return names


def test_the_api10_index_the_deployed_gate_names_exists_and_leads_on_api10(
    db: psycopg.Connection,
):
    """DR-79's index is the whole of G7-2's pass condition, and no other test names it.

    A later migration that drops it, renames it, or reorders its columns would leave the served
    ND path to a sequential scan of 24.8M rows and CI would stay green.
    """
    with db.cursor() as cursor:
        cursor.execute(
            "select indexdef from pg_indexes"
            " where schemaname = 'canonical' and tablename = 'production_monthly'"
            " and indexname = %s",
            (INDEX,),
        )
        row = cursor.fetchone()

    assert row is not None, f"{INDEX} is gone; the deployed G7-2 gate cannot pass"
    definition = row[0]
    assert "(api10" in definition.replace("USING btree ", "").replace("using btree ", "")


def test_the_served_production_query_resolves_to_that_index(db: psycopg.Connection):
    """The served path's predicate sits below the window, so the planner *can* prune to the
    index. This asserts that it does — the half a size-independent placement check leaves open.
    """
    assert INDEX in _index_names(_plan(db, nm_dims.SERVED_PRODUCTION_PROBE))


def test_the_latest_view_resolves_to_that_index_too(db: psycopg.Connection):
    """Migration 031 put api10 in the view's PARTITION BY so one well no longer re-ranks the
    table. The land-grid mart reads this view unfiltered, which is a separate cost measured on
    the host as G7-3; this pins the per-well path only.
    """
    assert INDEX in _index_names(_plan(db, VIEW_PROBE))


def test_the_probe_the_gate_walks_is_still_the_query_the_api_serves(db: psycopg.Connection):
    """`SERVED_PRODUCTION_PROBE` is a hand-copy of `select_production`'s window.

    If `_SELECT_PRODUCTION` gains a partition column and the probe does not, the gate keeps
    passing while it measures a query nothing serves.
    """
    window = (
        "partition by entity_type, entity_key, production_month, stream, source_id\n"
        "                   order by report_vintage desc"
    )
    assert window in _SELECT_PRODUCTION
    normalised = " ".join(nm_dims.SERVED_PRODUCTION_PROBE.split())
    assert " ".join(window.split()) in normalised
    assert "canonical.production_monthly p" in normalised
